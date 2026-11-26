from typing import Dict, Optional, Tuple
import cv2
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
    def _measure_head_and_body_bounds(
        lm_2d: Dict[int, Tuple[float, float, float]],
        mask: np.ndarray,
        yaw_rad: float = 0.0,
    ) -> Tuple[float, float, float, bool]:
        nose = lm_2d[0]
        y_eye = 0.5 * (lm_2d[2][1] + lm_2d[5][1])
        y_mouth = 0.5 * (lm_2d[9][1] + lm_2d[10][1])
        y_sh = 0.5 * (lm_2d[11][1] + lm_2d[12][1])
        y_an = 0.5 * (lm_2d[27][1] + lm_2d[28][1])

        cos_yaw = max(float(np.cos(yaw_rad)), 0.65)
        h_img, w_img = mask.shape[:2]

        eye_to_mouth_px = max(y_mouth - y_eye, 1.0)
        sh_span_px = max(abs(lm_2d[11][0] - lm_2d[12][0]), eye_to_mouth_px * 3.0)

        head_x_min = max(0, int(round(nose[0] - 0.45 * sh_span_px)))
        head_x_max = min(w_img, int(round(nose[0] + 0.45 * sh_span_px)))
        head_roi_ys = np.where(mask[:, head_x_min:head_x_max] > 0)[0]
        if len(head_roi_ys) > 0:
            mask_head_top = float(head_roi_ys.min())
        else:
            ys_all = np.where(mask > 0)[0]
            mask_head_top = float(ys_all.min()) if len(ys_all) > 0 else max(0.0, y_eye - 1.60 * eye_to_mouth_px)

        landmark_cues = [eye_to_mouth_px / 0.315]
        if yaw_rad < np.radians(18.0):
            if lm_2d[7][2] > 0.5 and lm_2d[8][2] > 0.5:
                ear_span_px = abs(lm_2d[7][0] - lm_2d[8][0]) / cos_yaw
                if ear_span_px > 10.0:
                    landmark_cues.append(ear_span_px / 0.655)
            if lm_2d[2][2] > 0.5 and lm_2d[5][2] > 0.5:
                ipd_px = abs(lm_2d[2][0] - lm_2d[5][0]) / cos_yaw
                if ipd_px > 5.0:
                    landmark_cues.append(ipd_px / 0.285)

        head_lm_ref = float(np.median(landmark_cues))

        neck_y1 = int(np.clip(round(y_mouth + 0.10 * head_lm_ref), 0, h_img - 1))
        neck_y2 = int(np.clip(round(y_sh), neck_y1 + 1, h_img))
        y_chin_sil = None
        if neck_y2 > neck_y1 + 2:
            row_widths = np.sum(mask[neck_y1:neck_y2, head_x_min:head_x_max] > 0, axis=1)
            valid_rows = np.where(row_widths > 4)[0]
            if len(valid_rows) > 0:
                min_w = int(np.min(row_widths[valid_rows]))
                chin_idx = valid_rows[np.where(row_widths[valid_rows] <= min_w + 2)[0][0]]
                y_chin_cand = float(neck_y1 + chin_idx)
                if 0.42 * head_lm_ref <= (y_chin_cand - y_eye) <= 0.64 * head_lm_ref:
                    y_chin_sil = y_chin_cand
                    landmark_cues.append((y_chin_sil - y_eye) / 0.535)

        head_ref_clean = float(np.median(landmark_cues))

        y_crown_skull = max(
            0.0,
            min(
                max(mask_head_top, y_eye - 0.53 * head_ref_clean),
                y_eye - 0.48 * head_ref_clean,
            ),
        )

        all_head_cues = list(landmark_cues)
        crown_to_mouth = y_mouth - y_crown_skull
        if crown_to_mouth > 12.0:
            all_head_cues.append(crown_to_mouth / 0.795)
        if y_chin_sil is not None:
            crown_to_chin = y_chin_sil - y_crown_skull
            if crown_to_chin > 16.0:
                all_head_cues.append(crown_to_chin / 1.03)

        head_real_px = max(float(np.median(all_head_cues)), 14.0)
        y_head_tight = max(
            0.0,
            min(
                max(mask_head_top, y_eye - 0.52 * head_real_px),
                y_eye - 0.48 * head_real_px,
            ),
        )

        ankles_visible = lm_2d[27][2] > 0.45 and lm_2d[28][2] > 0.45
        if ankles_visible and (y_an - y_head_tight) > 100:
            span_tight = max(y_an - y_head_tight, 1.0)
            an_x_min = max(0, int(round(min(lm_2d[27][0], lm_2d[28][0]) - 0.40 * sh_span_px)))
            an_x_max = min(w_img, int(round(max(lm_2d[27][0], lm_2d[28][0]) + 0.40 * sh_span_px)))
            feet_roi_ys = np.where(mask[:, an_x_min:an_x_max] > 0)[0]
            mask_feet_bot = float(feet_roi_ys.max()) if len(feet_roi_ys) > 0 else (y_an + 0.08 * span_tight)

            heels_visible = 29 in lm_2d and 30 in lm_2d and lm_2d[29][2] > 0.45 and lm_2d[30][2] > 0.45
            toes_visible = 31 in lm_2d and 32 in lm_2d and lm_2d[31][2] > 0.45 and lm_2d[32][2] > 0.45

            if heels_visible and toes_visible:
                y_heel = 0.5 * (lm_2d[29][1] + lm_2d[30][1])
                y_toe = 0.5 * (lm_2d[31][1] + lm_2d[32][1])
                y_sole_lm = 0.45 * y_heel + 0.55 * y_toe
                y_feet_cand = max(y_sole_lm, 0.5 * (y_sole_lm + mask_feet_bot))
            elif toes_visible:
                y_toe = 0.5 * (lm_2d[31][1] + lm_2d[32][1])
                y_feet_cand = 0.5 * (y_toe + mask_feet_bot)
            elif heels_visible:
                y_heel = 0.5 * (lm_2d[29][1] + lm_2d[30][1])
                y_feet_cand = max(y_heel, mask_feet_bot)
            else:
                y_feet_cand = mask_feet_bot

            y_feet_tight = float(
                np.clip(y_feet_cand, y_an + 0.055 * span_tight, y_an + 0.105 * span_tight)
            )
            return head_real_px, y_head_tight, y_feet_tight, True

        ys_all = np.where(mask > 0)[0]
        y_bot_fallback = float(ys_all.max()) if len(ys_all) > 0 else float(h_img - 12)
        return head_real_px, y_head_tight, y_bot_fallback, False

    @staticmethod
    def _estimate_invariant_scale(
        lm_2d: Dict[int, Tuple[float, float, float]],
        mask: np.ndarray,
        world_3d: Optional[Dict[int, Tuple[float, float, float]]] = None,
        yaw_rad: float = 0.0,
        pitch_rad: float = 0.0,
    ) -> Tuple[float, float, float, bool]:
        nose = lm_2d[0]
        y_eye = 0.5 * (lm_2d[2][1] + lm_2d[5][1])
        y_mouth = 0.5 * (lm_2d[9][1] + lm_2d[10][1])
        y_sh = 0.5 * (lm_2d[11][1] + lm_2d[12][1])
        y_hp = 0.5 * (lm_2d[23][1] + lm_2d[24][1])
        y_an = 0.5 * (lm_2d[27][1] + lm_2d[28][1])

        # 1. Skala lebar pakaian (dipertahankan persis agar lebar bahu, lingkar dada, dan pinggang tidak berubah)
        eye_to_mouth_px = max(y_mouth - y_eye, 1.0)
        head_h_px = eye_to_mouth_px / 0.32
        scale_head = 23.2 / max(head_h_px, 20.0)

        nose_to_sh_px = max(y_sh - nose[1], 1.0)
        scale_neck = 19.5 / max(nose_to_sh_px, 20.0)

        ys = np.where(mask > 0)[0]
        mask_top = float(ys.min()) if len(ys) > 0 else max(0.0, y_eye - 0.52 * head_h_px)
        mask_bottom = float(ys.max()) if len(ys) > 0 else y_hp

        ankles_visible = lm_2d[27][2] > 0.45 and lm_2d[28][2] > 0.45
        y_head_top = min(mask_top, max(0.0, y_eye - 0.50 * head_h_px))

        head_real_px, y_head_tight, y_feet_tight, full_visible = BodyEstimator._measure_head_and_body_bounds(
            lm_2d, mask, yaw_rad=yaw_rad
        )

        if ankles_visible and (y_an - y_head_top) > 100 and full_visible:
            y_feet = max(mask_bottom, y_an + 0.04 * (y_an - y_head_top))
            full_body_px = max(y_feet - y_head_top, 1.0)

            scale_full = 170.0 / full_body_px
            clamped_head = float(np.clip(scale_head, scale_full * 0.88, scale_full * 1.12))
            scale = 0.75 * scale_full + 0.25 * clamped_head

            exact_body_px = max(y_feet_tight - y_head_tight, 1.0)
            inferred_h = round(full_body_px * scale, 1)
            return scale, inferred_h, exact_body_px, True

        torso_px = max(y_hp - y_sh, 1.0)
        scale_torso = 49.5 / max(torso_px, 40.0)
        scale = float(np.median([scale_head, scale_neck, scale_torso]))
        inferred_h = round(float(np.clip((torso_px * scale) / 0.29, 150.0, 190.0)), 1)
        return scale, inferred_h, 0.0, False

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

    @staticmethod
    def _draw_label_box(
        canvas: np.ndarray,
        text: str,
        x: int,
        y: int,
        font_scale: float,
        thickness: int,
        bg_color: Tuple[int, int, int] = (15, 23, 42),
        text_color: Tuple[int, int, int] = (255, 255, 255),
        border_color: Optional[Tuple[int, int, int]] = None,
    ) -> None:
        h, w = canvas.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        pad_x = max(8, int(round(8 * font_scale / 0.55)))
        pad_y = max(5, int(round(5 * font_scale / 0.55)))

        box_w = tw + 2 * pad_x
        box_h = th + baseline + 2 * pad_y

        x1 = int(np.clip(x, 6, max(6, w - box_w - 6)))
        y1 = int(np.clip(y - box_h + pad_y, 6, max(6, h - box_h - 6)))
        x2 = min(w - 6, x1 + box_w)
        y2 = min(h - 6, y1 + box_h)

        overlay = canvas.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
        cv2.addWeighted(overlay, 0.78, canvas, 0.22, 0, canvas)

        if border_color is not None:
            cv2.rectangle(canvas, (x1, y1), (x2, y2), border_color, max(1, thickness - 1))

        cv2.putText(
            canvas,
            text,
            (x1 + pad_x, y2 - pad_y - baseline // 2),
            font,
            font_scale,
            text_color,
            thickness,
            cv2.LINE_AA,
        )

    def draw_measurement_overlay(
        self,
        front_bgr: np.ndarray,
        measurements: Dict[str, float],
        inferred_height_cm: float = 0.0,
        rekomendasi_ukuran: str = "-",
        pose_info: Optional[Dict] = None,
    ) -> np.ndarray:
        """Menggambar garis ukur baju (Bahu, Dada, Pinggang), rekomendasi, dan panduan cara memfoto pada foto."""
        canvas = front_bgr.copy()
        h, w = canvas.shape[:2]
        scale_ui = max(h / 920.0, 0.55)
        line_thick = max(2, int(round(2.4 * scale_ui)))
        font_scale = 0.56 * scale_ui
        small_scale = 0.46 * scale_ui

        lm_raw, _, mask_raw, _ = self.segmenter.extract_full(front_bgr)
        ankles_visible = lm_raw[27][2] > 0.45 and lm_raw[28][2] > 0.45

        def _slice_bounds(y_val: float, fallback_x1: float, fallback_x2: float) -> Tuple[int, int]:
            ry = int(np.clip(round(y_val), 0, h - 1))
            row_xs = np.where(mask_raw[ry] > 0)[0]
            if len(row_xs) > 4:
                return int(row_xs.min()), int(row_xs.max())
            return int(min(fallback_x1, fallback_x2)), int(max(fallback_x1, fallback_x2))

        y_sh = 0.5 * (lm_raw[11][1] + lm_raw[12][1])
        y_hp = 0.5 * (lm_raw[23][1] + lm_raw[24][1])
        torso_h = max(y_hp - y_sh, 1.0)
        y_chest = y_sh + 0.28 * torso_h
        y_waist = y_sh + 0.68 * torso_h

        sh_x1, sh_x2 = _slice_bounds(y_sh + 0.04 * torso_h, lm_raw[11][0], lm_raw[12][0])
        ch_x1, ch_x2 = _slice_bounds(y_chest, lm_raw[11][0], lm_raw[12][0])
        wa_x1, wa_x2 = _slice_bounds(y_waist, lm_raw[23][0], lm_raw[24][0])

        # 1. Garis ukur baju (Bahu, Dada, Pinggang)
        garment_lines = [
            (int(round(y_sh)), sh_x1, sh_x2, f"Bahu: {measurements['lebar_bahu']} cm", (80, 220, 100)),
            (int(round(y_chest)), ch_x1, ch_x2, f"Dada: {measurements['lingkar_dada']} cm", (60, 185, 255)),
            (int(round(y_waist)), wa_x1, wa_x2, f"Pinggang: {measurements['lingkar_pinggang']} cm", (245, 165, 66)),
        ]
        for gy, gx1, gx2, glabel, gcolor in garment_lines:
            gy = int(np.clip(gy, 12, h - 12))
            cv2.line(canvas, (gx1, gy), (gx2, gy), gcolor, line_thick, cv2.LINE_AA)
            cv2.circle(canvas, (gx1, gy), max(4, line_thick + 1), gcolor, -1, cv2.LINE_AA)
            cv2.circle(canvas, (gx2, gy), max(4, line_thick + 1), gcolor, -1, cv2.LINE_AA)
            self._draw_label_box(
                canvas,
                glabel,
                int(0.5 * (gx1 + gx2)) - int(70 * scale_ui),
                gy - 6,
                small_scale,
                max(1, line_thick - 1),
                border_color=gcolor,
            )

        # 2. Label Rekomendasi Ukuran di bagian atas foto
        self._draw_label_box(
            canvas,
            f"Rekomendasi: Size {rekomendasi_ukuran}",
            12,
            int(34 * scale_ui),
            font_scale,
            line_thick,
            bg_color=(29, 78, 216),
            border_color=(147, 197, 253),
        )

        # 3. Teks contoh cara memfoto di bagian bawah foto agar sesuai rekomendasi
        full_ok = bool((pose_info or {}).get("seluruh_tubuh_terlihat", ankles_visible))
        if full_ok:
            guide_text = "Cara Foto: Kepala-kaki masuk frame, berdiri tegak, lengan lurus"
        else:
            guide_text = "Cara Foto: Mundur agar kepala-kaki masuk frame & lengan lurus"

        self._draw_label_box(
            canvas,
            guide_text,
            12,
            h - 10,
            small_scale,
            max(1, line_thick - 1),
            bg_color=(15, 23, 42),
            border_color=(148, 163, 184),
        )

        return canvas

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

        scale_auto, inferred_height_cm, full_body_px, full_body_visible = self._estimate_invariant_scale(
            lm, mask, world_3d=world_3d, yaw_rad=yaw_rad, pitch_rad=pitch_rad
        )
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
            "seluruh_tubuh_terlihat": full_body_visible,
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