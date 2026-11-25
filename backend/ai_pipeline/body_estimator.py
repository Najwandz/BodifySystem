from typing import Dict, Tuple
import numpy as np

from ai_pipeline.ellipse_geometry import (
    compute_scale_cm_per_px,
    deproject_oblique_width,
    derotate_mask_and_landmarks,
    euclidean_distance,
    measure_slice_px,
    ramanujan_ellipse,
)
from ai_pipeline.pose_segmentation import PoseSegmenter
from ai_pipeline.regression_corrector import RegressionCorrector


CLOTHING_CIRCUMFERENCE_OFFSET_CM = {
    "ketat": 0.0,
    "kasual": 2.0,
    "longgar": 4.5,
}

CLOTHING_SHOULDER_OFFSET_CM = {
    "ketat": 0.0,
    "kasual": 0.6,
    "longgar": 1.5,
}


class BodyEstimator:
    """Orkestrator estimasi ukuran tubuh: mempertahankan proporsi lebar asli (S hingga XXL)."""

    def __init__(self):
        self.segmenter = PoseSegmenter()
        self.corrector = RegressionCorrector()

    @staticmethod
    def _estimate_pose_angles_3d(world_3d: Dict[int, Tuple[float, float, float]]) -> Tuple[float, float]:
        if not world_3d:
            return 0.0, 0.0

        sh_vec = np.array(world_3d[12]) - np.array(world_3d[11])
        hp_vec = np.array(world_3d[24]) - np.array(world_3d[23])

        yaw_sh = float(np.arctan2(abs(sh_vec[2]), max(abs(sh_vec[0]), 1e-4)))
        yaw_hp = float(np.arctan2(abs(hp_vec[2]), max(abs(hp_vec[0]), 1e-4)))
        yaw_rad = float(np.clip(0.65 * yaw_sh + 0.35 * yaw_hp, 0.0, np.radians(52.0)))

        mid_sh = 0.5 * (np.array(world_3d[11]) + np.array(world_3d[12]))
        mid_hp = 0.5 * (np.array(world_3d[23]) + np.array(world_3d[24]))
        spine = mid_hp - mid_sh
        pitch_rad = float(np.clip(np.arctan2(abs(spine[2]), max(abs(spine[1]), 1e-4)), 0.0, np.radians(35.0)))

        return yaw_rad, pitch_rad

    @staticmethod
    def _estimate_invariant_scale(
        lm_2d: Dict[int, Tuple[float, float, float]],
        mask: np.ndarray,
    ) -> Tuple[float, float]:
        """
        Menghitung skala cm/px HANYA dari referensi vertikal & ukuran kepala yang konsisten
        pada semua ukuran tubuh (S, M, L, XL, XXL), tanpa membatasi lebar bahu/dada.
        """
        nose = lm_2d[0]
        y_eye = 0.5 * (lm_2d[2][1] + lm_2d[5][1])
        y_mouth = 0.5 * (lm_2d[9][1] + lm_2d[10][1])
        y_sh = 0.5 * (lm_2d[11][1] + lm_2d[12][1])
        y_hp = 0.5 * (lm_2d[23][1] + lm_2d[24][1])

        # 1. Estimasi tinggi kepala (puncak kepala ke dagu ~ 23.2 cm pada orang dewasa)
        eye_to_mouth_px = max(y_mouth - y_eye, 1.0)
        head_h_px = eye_to_mouth_px / 0.32
        scale_head = 23.2 / max(head_h_px, 20.0)

        # 2. Estimasi dari jarak hidung ke garis bahu (~ 19.5 cm)
        nose_to_sh_px = max(y_sh - nose[1], 1.0)
        scale_neck = 19.5 / max(nose_to_sh_px, 20.0)

        # 3. Cek apakah seluruh tubuh (kepala sampai pergelangan kaki) terlihat di foto
        ys = np.where(mask > 0)[0]
        mask_top = float(ys.min()) if len(ys) > 0 else max(0.0, y_eye - 0.52 * head_h_px)
        mask_bottom = float(ys.max()) if len(ys) > 0 else y_hp

        ankles_visible = lm_2d[27][2] > 0.5 and lm_2d[28][2] > 0.5
        y_ankle = 0.5 * (lm_2d[27][1] + lm_2d[28][1])
        y_head_top = min(mask_top, max(0.0, y_eye - 0.50 * head_h_px))

        if ankles_visible and (y_ankle - y_head_top) > 180:
            y_feet = max(mask_bottom, y_ankle + 0.04 * (y_ankle - y_head_top))
            full_body_px = max(y_feet - y_head_top, 1.0)
            # Tinggi rata-rata dewasa ~170 cm sebagai acuan skala vertikal penuh
            scale_full = 170.0 / full_body_px
            # Gabungkan skala tinggi penuh (75%) + ukuran kepala (25%) yang dibatasi agar stabil
            clamped_head = float(np.clip(scale_head, scale_full * 0.88, scale_full * 1.12))
            scale = 0.75 * scale_full + 0.25 * clamped_head
            inferred_h = round(full_body_px * scale, 1)
            return scale, inferred_h

        # Jika foto setengah badan (pinggul ke atas)
        torso_px = max(y_hp - y_sh, 1.0)
        scale_torso = 49.5 / max(torso_px, 40.0)
        scale = float(np.median([scale_head, scale_neck, scale_torso]))
        inferred_h = round(float(np.clip((torso_px * scale) / 0.29, 150.0, 190.0)), 1)
        return scale, inferred_h

    @staticmethod
    def _detect_crossed_arms(lm_2d: Dict[int, Tuple[float, float, float]]) -> bool:
        """Mendeteksi jika pergelangan tangan / lengan terlipat di depan dada atau perut."""
        l_sh, r_sh = lm_2d[11], lm_2d[12]
        l_wr, r_wr = lm_2d[15], lm_2d[16]
        l_hp, r_hp = lm_2d[23], lm_2d[24]

        x_min = min(l_sh[0], r_sh[0])
        x_max = max(l_sh[0], r_sh[0])
        y_top = min(l_sh[1], r_sh[1])
        y_bot = max(l_hp[1], r_hp[1])

        for wr in (l_wr, r_wr):
            if wr[2] > 0.45 and (x_min < wr[0] < x_max) and (y_top < wr[1] < y_bot):
                return True
        return False

    def estimate_single_photo(
        self,
        front_bgr: np.ndarray,
        clothing_type: str = "kasual",
    ) -> Tuple[Dict[str, float], float, Dict]:
        lm_raw, world_3d, mask_raw, aruco_scale = self.segmenter.extract_full(front_bgr)

        yaw_rad, pitch_rad = self._estimate_pose_angles_3d(world_3d)
        yaw_deg = round(float(np.degrees(yaw_rad)), 1)
        pitch_deg = round(float(np.degrees(pitch_rad)), 1)

        mask, lm, roll_deg = derotate_mask_and_landmarks(mask_raw, lm_raw)
        arms_crossed = self._detect_crossed_arms(lm)

        scale_auto, inferred_height_cm = self._estimate_invariant_scale(lm, mask)
        if aruco_scale is not None:
            scale = aruco_scale
            scale_method = "ArUco Presisi Tinggi (±1–1.5 cm)"
        else:
            scale = scale_auto
            scale_method = "Otomatis Proporsi Vertikal & Kepala"

        l_sh, r_sh = lm[11], lm[12]
        l_hp, r_hp = lm[23], lm[24]

        center_x = 0.25 * (l_sh[0] + r_sh[0] + l_hp[0] + r_hp[0])
        y_sh = 0.5 * (l_sh[1] + r_sh[1])
        y_hp = 0.5 * (l_hp[1] + r_hp[1])
        torso_h = max(y_hp - y_sh, 1.0)

        y_chest = y_sh + 0.28 * torso_h
        y_waist = y_sh + 0.68 * torso_h

        # 1. Lebar bahu luar (bi-deltoid) dengan proyeksi balik sudut serong
        cos_yaw = max(float(np.cos(yaw_rad)), 0.58)
        joint_sh_cm = (euclidean_distance((l_sh[0], l_sh[1]), (r_sh[0], r_sh[1])) * scale) / cos_yaw

        # Ukur siluet sedikit di bawah garis sendi bahu (y_sh + 4% torso) untuk menangkap tepi bahu luar
        sil_sh_app_cm = measure_slice_px(mask, y_sh + 0.04 * torso_h) * scale
        sil_sh_true_cm = deproject_oblique_width(sil_sh_app_cm, yaw_rad, depth_ratio=0.42)

        if sil_sh_true_cm > 0:
            raw_bahu = float(np.clip(sil_sh_true_cm, joint_sh_cm * 1.12, joint_sh_cm * 1.28))
        else:
            raw_bahu = joint_sh_cm * 1.18

        # 2. Lebar dada & pinggang
        w_chest_app_cm = measure_slice_px(mask, y_chest, center_x=center_x) * scale
        w_waist_app_cm = measure_slice_px(mask, y_waist, center_x=center_x) * scale

        w_chest_cm = deproject_oblique_width(w_chest_app_cm, yaw_rad, 0.72)
        w_waist_cm = deproject_oblique_width(w_waist_app_cm, yaw_rad, 0.76)

        if arms_crossed:
            # Jika tangan bersedekap di depan dada, gunakan proporsi anatomis dari lebar bahu luar
            # agar lipatan siku tidak menggelembungkan lingkar pinggang melebihi dada
            w_chest_cm = raw_bahu * 0.79
            w_waist_cm = w_chest_cm * 0.89
        else:
            if w_chest_cm <= 0 or w_chest_cm > raw_bahu * 0.92 or w_chest_cm < raw_bahu * 0.68:
                w_chest_cm = raw_bahu * 0.78
            if w_waist_cm <= 0 or w_waist_cm > w_chest_cm * 1.05 or w_waist_cm < w_chest_cm * 0.72:
                w_waist_cm = w_chest_cm * 0.87

        build_ratio = w_waist_cm / max(w_chest_cm, 1.0)
        chest_depth_ratio = float(np.clip(0.70 + 0.14 * (build_ratio - 0.82), 0.66, 0.82))
        waist_depth_ratio = float(np.clip(0.74 + 0.18 * (build_ratio - 0.82), 0.68, 0.86))

        d_chest_cm = w_chest_cm * chest_depth_ratio
        d_waist_cm = w_waist_cm * waist_depth_ratio

        raw_dada = ramanujan_ellipse(w_chest_cm / 2.0, d_chest_cm / 2.0)
        raw_pinggang = ramanujan_ellipse(w_waist_cm / 2.0, d_waist_cm / 2.0)

        cloth = clothing_type.lower()
        sh_offset = CLOTHING_SHOULDER_OFFSET_CM.get(cloth, 0.6)
        circ_offset = CLOTHING_CIRCUMFERENCE_OFFSET_CM.get(cloth, 2.0)

        result = {
            "lebar_bahu": round(max(32.0, raw_bahu - sh_offset), 1),
            "lingkar_dada": round(max(72.0, raw_dada - circ_offset), 1),
            "lingkar_pinggang": round(max(58.0, raw_pinggang - circ_offset), 1),
        }

        notes = []
        if yaw_deg >= 12.0:
            notes.append(f"serong {yaw_deg}° dikoreksi")
        if abs(roll_deg) >= 4.0:
            notes.append(f"miring {abs(roll_deg)}° diluruskan")
        if arms_crossed:
            notes.append("tangan bersedekap dikoreksi (luruskan lengan di samping untuk akurasi maksimal)")

        status_pose = "Tegak lurus" if not notes else " • ".join(notes).capitalize()

        pose_info = {
            "status_pose": status_pose,
            "sudut_serong_derajat": yaw_deg,
            "sudut_miring_derajat": abs(roll_deg),
            "sudut_condong_derajat": pitch_deg,
            "metode_skala": scale_method,
            "aruco_terdeteksi": aruco_scale is not None,
        }

        return result, inferred_height_cm, pose_info

    def extract_raw(self, front_bgr: np.ndarray, side_bgr: np.ndarray, height_cm: float) -> Dict[str, float]:
        lm_f, mask_f = self.segmenter.extract(front_bgr)
        lm_s, mask_s = self.segmenter.extract(side_bgr)

        scale_f = compute_scale_cm_per_px(mask_f, height_cm)
        scale_s = compute_scale_cm_per_px(mask_s, height_cm)

        l_sh, r_sh = lm_f[11], lm_f[12]
        l_el, r_el = lm_f[13], lm_f[14]
        l_wr, r_wr = lm_f[15], lm_f[16]
        l_hp, r_hp = lm_f[23], lm_f[24]

        center_x_f = 0.25 * (l_sh[0] + r_sh[0] + l_hp[0] + r_hp[0])
        y_sh_f = 0.5 * (l_sh[1] + r_sh[1])
        y_hp_f = 0.5 * (l_hp[1] + r_hp[1])
        torso_f = max(y_hp_f - y_sh_f, 1.0)

        y_sh_s = 0.5 * (lm_s[11][1] + lm_s[12][1])
        y_hp_s = 0.5 * (lm_s[23][1] + lm_s[24][1])
        torso_s = max(y_hp_s - y_sh_s, 1.0)

        y_chest_f, y_chest_s = y_sh_f + 0.28 * torso_f, y_sh_s + 0.28 * torso_s
        y_waist_f, y_waist_s = y_sh_f + 0.68 * torso_f, y_sh_s + 0.68 * torso_s
        y_hip_f, y_hip_s = y_hp_f + 0.08 * torso_f, y_hp_s + 0.08 * torso_s

        joint_sh_cm = euclidean_distance(l_sh, r_sh) * scale_f
        sil_sh_cm = measure_slice_px(mask_f, y_sh_f) * scale_f
        lebar_bahu = min(sil_sh_cm, joint_sh_cm * 1.28) if sil_sh_cm > 0 else joint_sh_cm * 1.18

        w_chest = measure_slice_px(mask_f, y_chest_f, center_x=center_x_f) * scale_f
        d_chest = measure_slice_px(mask_s, y_chest_s) * scale_s
        lingkar_dada = ramanujan_ellipse(w_chest / 2.0, d_chest / 2.0)

        w_waist = measure_slice_px(mask_f, y_waist_f, center_x=center_x_f) * scale_f
        d_waist = measure_slice_px(mask_s, y_waist_s) * scale_s
        lingkar_pinggang = ramanujan_ellipse(w_waist / 2.0, d_waist / 2.0)

        w_hip = measure_slice_px(mask_f, y_hip_f, center_x=center_x_f) * scale_f
        d_hip = measure_slice_px(mask_s, y_hip_s) * scale_s
        lingkar_pinggul = ramanujan_ellipse(w_hip / 2.0, d_hip / 2.0)

        left_arm = euclidean_distance(l_sh, l_el) + euclidean_distance(l_el, l_wr)
        right_arm = euclidean_distance(r_sh, r_el) + euclidean_distance(r_el, r_wr)
        panjang_lengan = 0.5 * (left_arm + right_arm) * scale_f
        panjang_badan = (y_hp_f - y_sh_f) * scale_f * 1.05

        return {
            "lebar_bahu": lebar_bahu,
            "lingkar_dada": lingkar_dada,
            "lingkar_pinggang": lingkar_pinggang,
            "lingkar_pinggul": lingkar_pinggul,
            "panjang_lengan": panjang_lengan,
            "panjang_badan": panjang_badan,
        }

    def estimate(self, front_bgr: np.ndarray, side_bgr: np.ndarray, height_cm: float, clothing_type: str = "kasual"):
        raw = self.extract_raw(front_bgr, side_bgr, height_cm)
        return self.corrector.apply(raw, height_cm, clothing_type)