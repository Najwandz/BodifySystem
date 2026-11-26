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
    def _estimate_invariant_scale(
        lm_2d: Dict[int, Tuple[float, float, float]],
        mask: np.ndarray,
        world_3d: Optional[Dict[int, Tuple[float, float, float]]] = None,
        yaw_rad: float = 0.0,
        pitch_rad: float = 0.0,
    ) -> Tuple[float, float, float, bool]:
        """
        Mempertahankan skala lebar bahu/dada/pinggang yang sudah akurat, serta menghitung
        tinggi badan real dari rasio proporsi anatomis tidak berdimensi dan rektifikasi perspektif 3D
        sehingga tidak bergantung pada sudut kamera maupun ukuran/resolusi gambar.
        """
        nose = lm_2d[0]
        y_eye = 0.5 * (lm_2d[2][1] + lm_2d[5][1])
        y_mouth = 0.5 * (lm_2d[9][1] + lm_2d[10][1])
        y_sh = 0.5 * (lm_2d[11][1] + lm_2d[12][1])
        y_hp = 0.5 * (lm_2d[23][1] + lm_2d[24][1])
        y_kn = 0.5 * (lm_2d[25][1] + lm_2d[26][1])
        y_an = 0.5 * (lm_2d[27][1] + lm_2d[28][1])

        cos_yaw = max(float(np.cos(yaw_rad)), 0.65)
        img_h = float(mask.shape[0]) if mask is not None and mask.ndim >= 2 else 1080.0

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

        # 2. Estimasi tinggi kepala dalam piksel menggunakan multi-landmark wajah (invarian ukuran gambar & sudut)
        head_from_em = eye_to_mouth_px / 0.292
        eye_to_nose_px = max(nose[1] - y_eye, 1.0)
        head_from_en = eye_to_nose_px / 0.165
        head_vert_px = 0.72 * head_from_em + 0.28 * float(np.clip(head_from_en, head_from_em * 0.88, head_from_em * 1.12))

        if yaw_rad < np.radians(15.0):
            horiz_list = []
            if lm_2d[7][2] > 0.5 and lm_2d[8][2] > 0.5:
                ear_span_px = abs(lm_2d[7][0] - lm_2d[8][0]) / cos_yaw
                if ear_span_px > 10.0:
                    horiz_list.append(ear_span_px / 0.66)
            if lm_2d[2][2] > 0.5 and lm_2d[5][2] > 0.5:
                ipd_px = abs(lm_2d[2][0] - lm_2d[5][0]) / cos_yaw
                if ipd_px > 5.0:
                    horiz_list.append(ipd_px / 0.278)
            if horiz_list:
                head_horiz_px = float(np.median(horiz_list))
                clamped_horiz = float(np.clip(head_horiz_px, head_vert_px * 0.90, head_vert_px * 1.10))
                head_real_px = 0.70 * head_vert_px + 0.30 * clamped_horiz
            else:
                head_real_px = head_vert_px
        else:
            head_real_px = head_vert_px

        head_real_px = max(head_real_px, 12.0)

        if ankles_visible and (y_an - y_head_top) > 100:
            y_feet = max(mask_bottom, y_an + 0.04 * (y_an - y_head_top))
            full_body_px = max(y_feet - y_head_top, 1.0)

            scale_full = 170.0 / full_body_px
            clamped_head = float(np.clip(scale_head, scale_full * 0.88, scale_full * 1.12))
            scale = 0.75 * scale_full + 0.25 * clamped_head

            # Hitung tinggi badan real ( bebas dari sudut kamera dan ukuran gambar )
            y_head_tight = max(0.0, min(max(mask_top, y_eye - 0.53 * head_real_px), y_eye - 0.495 * head_real_px))
            span_tight = max(y_an - y_head_tight, 1.0)
            heels_visible = lm_2d[29][2] > 0.45 and lm_2d[30][2] > 0.45
            if heels_visible:
                y_heel = 0.5 * (lm_2d[29][1] + lm_2d[30][1])
                y_feet_tight = max(y_heel, y_an + 0.032 * span_tight)
            else:
                y_feet_tight = max(min(mask_bottom, y_an + 0.044 * span_tight), y_an + 0.036 * span_tight)

            raw_span_px = max(y_feet_tight - y_head_tight, 1.0)

            if world_3d:
                mid_sh_3d = 0.5 * (np.array(world_3d[11]) + np.array(world_3d[12]))
                mid_hp_3d = 0.5 * (np.array(world_3d[23]) + np.array(world_3d[24]))
                mid_kn_3d = 0.5 * (np.array(world_3d[25]) + np.array(world_3d[26]))
                mid_an_3d = 0.5 * (np.array(world_3d[27]) + np.array(world_3d[28]))

                torso_3d = float(np.linalg.norm(mid_hp_3d - mid_sh_3d))
                femur_3d = float(np.linalg.norm(mid_kn_3d - mid_hp_3d))
                tibia_3d = float(np.linalg.norm(mid_an_3d - mid_kn_3d))
                leg_3d = femur_3d + tibia_3d
                leg_torso_ratio = leg_3d / max(torso_3d, 1e-4)

                torso_2d = max(y_hp - y_sh, 1.0)
                femur_2d = max(y_kn - y_hp, 1.0)
                tibia_2d = max(y_an - y_kn, 1.0)

                s_torso = torso_2d / max(torso_3d, 1e-4)
                s_femur = femur_2d / max(femur_3d, 1e-4)
                s_tibia = tibia_2d / max(tibia_3d, 1e-4)

                # Samakan skala tiap segmen ke bidang kepala/torso atas untuk menghapus kompresi perspektif sudut kamera
                s_ref = float(np.clip(s_torso + 0.40 * (s_torso - s_femur), s_torso * 0.90, s_torso * 1.15))
                head_neck_px = max(y_sh - y_head_tight, 1.0)
                foot_px = max(y_feet_tight - y_an, 1.0)

                rectified_px = (
                    head_neck_px
                    + torso_2d * (s_ref / max(s_torso, 1e-4))
                    + femur_2d * (s_ref / max(s_femur, 1e-4))
                    + tibia_2d * (s_ref / max(s_tibia, 1e-4))
                    + foot_px * (s_ref / max(s_tibia, 1e-4))
                )
                exact_body_px = float(np.clip(rectified_px, raw_span_px * 0.94, raw_span_px * 1.22))

                focal_est = max(img_h * 0.85, 400.0)
                face_protrusion_factor = 1.0 + 0.075 * (s_ref / focal_est)
                head_coronal_px = head_real_px / face_protrusion_factor
            else:
                exact_body_px = raw_span_px
                head_coronal_px = head_real_px / 1.022
                torso_2d = max(y_hp - y_sh, 1.0)
                leg_2d = max(y_an - y_hp, 1.0)
                leg_torso_ratio = leg_2d / torso_2d

            # Rasio proporsi tubuh tidak berdimensi (n_heads & leg_torso_ratio)
            n_heads = exact_body_px / head_coronal_px

            maturity_head = float(np.clip((n_heads - 6.75) / (7.60 - 6.75), 0.0, 1.0))
            maturity_leg = float(np.clip((leg_torso_ratio - 1.56) / (1.78 - 1.56), 0.0, 1.0))
            maturity = 0.65 * maturity_head + 0.35 * maturity_leg

            head_cm = 21.35 + 2.45 * maturity
            inferred_h = round(float(np.clip(n_heads * head_cm, 120.0, 210.0)), 1)
            return scale, inferred_h, exact_body_px, True

        # Jika foto setengah badan (pinggul ke atas)
        torso_px = max(y_hp - y_sh, 1.0)
        scale_torso = 49.5 / max(torso_px, 40.0)
        scale = float(np.median([scale_head, scale_neck, scale_torso]))
        inferred_h = round(float(np.clip((torso_px / head_real_px) * 22.4 / 0.29, 135.0, 195.0)), 1)
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
        inferred_height_cm: float,
        rekomendasi_ukuran: str = "-",
        pose_info: Optional[Dict] = None,
    ) -> np.ndarray:
        """Menggambar garis ukur tinggi badan, ukuran baju, rekomendasi, dan panduan cara memfoto pada foto."""
        canvas = front_bgr.copy()
        h, w = canvas.shape[:2]
        scale_ui = max(h / 920.0, 0.55)
        line_thick = max(2, int(round(2.4 * scale_ui)))
        font_scale = 0.56 * scale_ui
        small_scale = 0.46 * scale_ui

        lm_raw, _, mask_raw, _ = self.segmenter.extract_full(front_bgr)

        y_eye = 0.5 * (lm_raw[2][1] + lm_raw[5][1])
        y_mouth = 0.5 * (lm_raw[9][1] + lm_raw[10][1])
        head_h_px = max((y_mouth - y_eye) / 0.292, 16.0)

        ys = np.where(mask_raw > 0)[0]
        xs_all = np.where(mask_raw > 0)[1]
        mask_top = float(ys.min()) if len(ys) > 0 else max(0.0, y_eye - 0.50 * head_h_px)
        mask_bottom = float(ys.max()) if len(ys) > 0 else float(h - 20)
        body_x_min = int(xs_all.min()) if len(xs_all) > 0 else int(min(lm_raw[11][0], lm_raw[12][0]))
        body_x_max = int(xs_all.max()) if len(xs_all) > 0 else int(max(lm_raw[11][0], lm_raw[12][0]))

        y_head_top = int(np.clip(round(max(0.0, min(max(mask_top, y_eye - 0.53 * head_h_px), y_eye - 0.495 * head_h_px))), 10, h - 20))
        ankles_visible = lm_raw[27][2] > 0.45 and lm_raw[28][2] > 0.45
        y_ankle = 0.5 * (lm_raw[27][1] + lm_raw[28][1])
        if ankles_visible and (y_ankle - y_head_top) > 100:
            body_span = y_ankle - y_head_top
            heels_visible = lm_raw[29][2] > 0.45 and lm_raw[30][2] > 0.45
            if heels_visible:
                y_heel = 0.5 * (lm_raw[29][1] + lm_raw[30][1])
                y_feet_val = max(y_heel, y_ankle + 0.032 * body_span)
            else:
                y_feet_val = max(min(mask_bottom, y_ankle + 0.044 * body_span), y_ankle + 0.036 * body_span)
            y_feet = int(np.clip(round(y_feet_val), y_head_top + 40, h - 12))
        else:
            y_feet = int(np.clip(round(mask_bottom), y_head_top + 40, h - 12))

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

        # 1. Garis ukur vertikal Tinggi Badan (kepala sampai kaki)
        margin_side = max(18, int(round(22 * scale_ui)))
        if body_x_min > margin_side + 30:
            x_height = max(16, body_x_min - margin_side)
        else:
            x_height = min(w - 16, body_x_max + margin_side)

        color_height = (255, 229, 0)  # Cyan terang (BGR)
        cap_half = max(10, int(round(12 * scale_ui)))
        cv2.line(canvas, (x_height, y_head_top), (x_height, y_feet), color_height, line_thick, cv2.LINE_AA)
        cv2.line(canvas, (x_height - cap_half, y_head_top), (x_height + cap_half, y_head_top), color_height, line_thick, cv2.LINE_AA)
        cv2.line(canvas, (x_height - cap_half, y_feet), (x_height + cap_half, y_feet), color_height, line_thick, cv2.LINE_AA)

        tinggi_val = measurements.get("tinggi_badan", inferred_height_cm)
        y_mid_height = int(0.5 * (y_head_top + y_feet))
        self._draw_label_box(
            canvas,
            f"Tinggi: {tinggi_val} cm",
            x_height + 8 if x_height < w // 2 else x_height - int(190 * scale_ui),
            y_mid_height,
            font_scale,
            line_thick,
            border_color=color_height,
        )

        # 2. Garis ukur baju (Bahu, Dada, Pinggang)
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

        # 3. Label Rekomendasi Ukuran di bagian atas foto
        self._draw_label_box(
            canvas,
            f"Rekomendasi: Size {rekomendasi_ukuran} | Tinggi {tinggi_val} cm",
            12,
            int(34 * scale_ui),
            font_scale,
            line_thick,
            bg_color=(29, 78, 216),
            border_color=(147, 197, 253),
        )

        # 4. Teks contoh cara memfoto di bagian bawah foto agar sesuai rekomendasi
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
            if full_body_visible and full_body_px > 0:
                inferred_height_cm = round(full_body_px * aruco_scale, 1)
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
            "tinggi_badan": round(inferred_height_cm, 1),
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
        if not full_body_visible:
            notes.append("tampilkan seluruh badan dari kepala hingga kaki untuk akurasi tinggi badan")

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