import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from config.settings import BASE_DIR

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)
MODEL_PATH = BASE_DIR / "saved_models" / "pose_landmarker_full.task"


class PoseSegmenter:
    """Ekstraksi 33 landmark 2D, 33 landmark 3D (world), siluet biner, dan deteksi ArUco opsional."""

    def __init__(self, model_path: Path = MODEL_PATH):
        self.model_path = Path(model_path)
        self._ensure_model_exists()

        base_options = python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            output_segmentation_masks=True,
            min_pose_detection_confidence=0.55,
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def _ensure_model_exists(self):
        if not self.model_path.exists():
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, self.model_path)

    @staticmethod
    def detect_aruco_scale(image_bgr: np.ndarray, marker_size_cm: float = 15.0) -> Optional[float]:
        if not hasattr(cv2, "aruco"):
            return None
        try:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            params = cv2.aruco.DetectorParameters()
            detector = cv2.aruco.ArucoDetector(aruco_dict, params)
            corners, ids, _ = detector.detectMarkers(gray)
            if ids is None or len(corners) == 0:
                return None

            pts = corners[0][0]
            side_lengths = [
                np.linalg.norm(pts[0] - pts[1]),
                np.linalg.norm(pts[1] - pts[2]),
                np.linalg.norm(pts[2] - pts[3]),
                np.linalg.norm(pts[3] - pts[0]),
            ]
            avg_side_px = float(np.mean(side_lengths))
            if avg_side_px < 20:
                return None
            return marker_size_cm / avg_side_px
        except Exception:
            return None

    def extract_full(
        self, image_bgr: np.ndarray
    ) -> Tuple[
        Dict[int, Tuple[float, float, float]],
        Dict[int, Tuple[float, float, float]],
        np.ndarray,
        Optional[float],
    ]:
        h, w, _ = image_bgr.shape
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

        results = self.detector.detect(mp_image)

        if not results.pose_landmarks or not results.segmentation_masks:
            raise ValueError(
                "Tubuh tidak terdeteksi sempurna. Pastikan minimal dari kepala hingga pinggul terlihat jelas."
            )

        landmarks_2d = {
            idx: (lm.x * w, lm.y * h, float(getattr(lm, "visibility", 1.0)))
            for idx, lm in enumerate(results.pose_landmarks[0])
        }

        world_3d = {}
        if results.pose_world_landmarks:
            world_3d = {
                idx: (float(lm.x), float(lm.y), float(lm.z))
                for idx, lm in enumerate(results.pose_world_landmarks[0])
            }

        seg_mask = np.squeeze(results.segmentation_masks[0].numpy_view())
        if seg_mask.shape[:2] != (h, w):
            seg_mask = cv2.resize(seg_mask, (w, h), interpolation=cv2.INTER_LINEAR)
        mask = (seg_mask > 0.5).astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num_labels > 1:
            largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            mask = (labels == largest_label).astype(np.uint8) * 255

        aruco_scale = self.detect_aruco_scale(image_bgr)
        return landmarks_2d, world_3d, mask, aruco_scale

    def extract(self, image_bgr: np.ndarray) -> Tuple[Dict[int, Tuple[float, float]], np.ndarray]:
        lm2d_vis, _, mask, _ = self.extract_full(image_bgr)
        lm2d = {idx: (pt[0], pt[1]) for idx, pt in lm2d_vis.items()}
        return lm2d, mask