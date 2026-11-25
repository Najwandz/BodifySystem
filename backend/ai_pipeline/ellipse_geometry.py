from typing import Dict, Optional, Tuple
import cv2
import numpy as np


def compute_scale_cm_per_px(mask: np.ndarray, height_cm: float) -> float:
    ys = np.where(mask > 0)[0]
    if len(ys) == 0:
        raise ValueError("Siluet tubuh tidak ditemukan pada foto.")
    height_px = float(ys.max() - ys.min())
    if height_px < 100:
        raise ValueError("Objek tubuh terlalu kecil di dalam bingkai kamera.")
    return height_cm / height_px


def ramanujan_ellipse(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    return float(np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b))))


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))


def derotate_mask_and_landmarks(
    mask: np.ndarray,
    landmarks_2d: Dict[int, Tuple[float, float, float]],
) -> Tuple[np.ndarray, Dict[int, Tuple[float, float, float]], float]:
    l_sh, r_sh = landmarks_2d[11], landmarks_2d[12]
    l_hp, r_hp = landmarks_2d[23], landmarks_2d[24]

    mid_sh = np.array([(l_sh[0] + r_sh[0]) * 0.5, (l_sh[1] + r_sh[1]) * 0.5])
    mid_hp = np.array([(l_hp[0] + r_hp[0]) * 0.5, (l_hp[1] + r_hp[1]) * 0.5])

    dx = float(mid_hp[0] - mid_sh[0])
    dy = float(mid_hp[1] - mid_sh[1])
    roll_rad = float(np.arctan2(dx, max(dy, 1.0)))
    roll_deg = float(np.degrees(roll_rad))

    if abs(roll_deg) < 1.5:
        return mask, landmarks_2d, round(roll_deg, 1)

    h, w = mask.shape
    center = ((mid_sh[0] + mid_hp[0]) * 0.5, (mid_sh[1] + mid_hp[1]) * 0.5)
    M = cv2.getRotationMatrix2D(center, -roll_deg, 1.0)
    rotated_mask = cv2.warpAffine(mask, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)

    rotated_lm = {}
    for idx, (x, y, vis) in landmarks_2d.items():
        nx = M[0, 0] * x + M[0, 1] * y + M[0, 2]
        ny = M[1, 0] * x + M[1, 1] * y + M[1, 2]
        rotated_lm[idx] = (float(nx), float(ny), vis)

    return rotated_mask, rotated_lm, round(roll_deg, 1)


def deproject_oblique_width(apparent_width_cm: float, yaw_rad: float, depth_ratio: float) -> float:
    factor = float(np.sqrt(np.cos(yaw_rad) ** 2 + (depth_ratio * np.sin(yaw_rad)) ** 2))
    factor = max(factor, 0.55)
    return apparent_width_cm / factor


def measure_slice_px(
    mask: np.ndarray,
    y_coord: float,
    center_x: Optional[float] = None,
    window: int = 5,
) -> float:
    h, w = mask.shape
    y_int = int(np.clip(round(y_coord), 0, h - 1))
    y_start = max(0, y_int - window)
    y_end = min(h, y_int + window + 1)

    widths = []
    for y in range(y_start, y_end):
        row = mask[y, :]
        if center_x is not None:
            cx = int(np.clip(round(center_x), 0, w - 1))
            if row[cx] == 0:
                continue
            left, right = cx, cx
            while left > 0 and row[left - 1] > 0:
                left -= 1
            while right < w - 1 and row[right + 1] > 0:
                right += 1
            widths.append(right - left)
        else:
            xs = np.where(row > 0)[0]
            if len(xs) > 0:
                widths.append(xs.max() - xs.min())

    return float(np.median(widths)) if widths else 0.0