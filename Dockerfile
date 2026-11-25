FROM python:3.11-slim

WORKDIR /app

# Dependensi sistem untuk OpenCV & MediaPipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend-pwa /app/frontend-pwa

WORKDIR /app/backend

# Siapkan model kalibrasi, model pose MediaPipe, dan ikon PNG untuk Android (APK)
RUN mkdir -p saved_models && \
    python training/train_calibration.py && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task', 'saved_models/pose_landmarker_full.task')" && \
    python -c "import cv2, numpy as np; img=np.full((512,512,3),(216,78,29),np.uint8); cv2.circle(img,(256,155),48,(255,255,255),-1); cv2.rectangle(img,(165,225),(347,395),(255,255,255),-1); cv2.imwrite('/app/frontend-pwa/assets/img/icon-512.png',img); cv2.imwrite('/app/frontend-pwa/assets/img/icon-192.png',cv2.resize(img,(192,192)))"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]