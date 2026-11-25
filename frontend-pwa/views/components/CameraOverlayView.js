function compressImageToBlob(sourceElement, maxWidth = 1080) {
  return new Promise((resolve) => {
    const srcW = sourceElement.videoWidth || sourceElement.naturalWidth;
    const srcH = sourceElement.videoHeight || sourceElement.naturalHeight;
    const scale = srcW > maxWidth ? maxWidth / srcW : 1;

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(srcW * scale);
    canvas.height = Math.round(srcH * scale);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(sourceElement, 0, 0, canvas.width, canvas.height);

    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.88);
  });
}

function getGuideSvg(viewType) {
  if (viewType === "side") {
    return `
      <span class="guide-tip">Tampak Samping • Berdiri lurus menghadap samping</span>
      <svg viewBox="0 0 200 320" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="6 5">
        <circle cx="102" cy="48" r="20" />
        <path d="M90 76 C78 96, 76 155, 84 190 L82 305 M112 76 C126 104, 128 152, 118 190 L114 305" />
        <line x1="76" y1="126" x2="128" y2="126" stroke="#fde047" stroke-width="2" />
        <line x1="78" y1="162" x2="122" y2="162" stroke="#4ade80" stroke-width="2" />
      </svg>
    `;
  }
  return `
    <span class="guide-tip">Tampak Depan • Tegak atau serong ringan boleh</span>
    <svg viewBox="0 0 200 320" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="6 5">
      <circle cx="100" cy="48" r="22" />
      <path d="M56 96 C68 82, 132 82, 144 96 L160 185 M56 96 L40 185" />
      <path d="M64 102 L68 188 L132 188 L136 102" />
      <line x1="56" y1="126" x2="144" y2="126" stroke="#fde047" stroke-width="2" />
      <line x1="62" y1="162" x2="138" y2="162" stroke="#4ade80" stroke-width="2" />
      <path d="M68 188 L64 305 M132 188 L136 305 M100 205 L96 305 M100 205 L104 305" />
    </svg>
  `;
}

export function mountCameraOverlay(container, { viewType = "front", onPhotoReady }) {
  let stream = null;
  let facingMode = "environment";

  container.innerHTML = `
    <div class="camera-box">
      <div class="placeholder-cam" id="cam-placeholder">
        <div style="font-size:2.3rem;margin-bottom:6px;">🧍</div>
        <div>Tekan <b>Foto dari HP</b> atau <b>Kamera Live</b><br/>untuk mengambil foto ${viewType === "side" ? "tampak samping" : "tampak depan"}</div>
      </div>
      <video id="cam-video" autoplay playsinline style="display:none;"></video>
      <img id="cam-preview" alt="Pratinjau foto" style="display:none;" />
      <div id="cam-countdown" class="countdown-badge" style="display:none;"></div>
      <div class="overlay-guide" id="cam-overlay">${getGuideSvg(viewType)}</div>
    </div>

    <input type="file" id="native-camera-input" accept="image/*" capture="environment" hidden />
    <input type="file" id="gallery-input" accept="image/*" hidden />

    <div id="controls-idle">
      <div class="btn-grid">
        <button type="button" class="btn btn-primary" id="btn-native-cam">📷 Foto dari HP</button>
        <button type="button" class="btn btn-outline" id="btn-live-cam">🎥 Kamera Live</button>
      </div>
      <button type="button" class="btn btn-outline" id="btn-gallery">🖼️ Pilih dari Galeri</button>
    </div>

    <div id="controls-live" style="display:none;">
      <div class="btn-grid">
        <button type="button" class="btn btn-success" id="btn-snap-now">📸 Jepret Sekarang</button>
        <button type="button" class="btn btn-primary" id="btn-snap-timer">⏱️ Timer 3 Detik</button>
      </div>
      <div class="btn-grid">
        <button type="button" class="btn btn-outline" id="btn-flip-cam">🔄 Balik Kamera</button>
        <button type="button" class="btn btn-outline" id="btn-stop-cam">✖ Tutup Kamera</button>
      </div>
    </div>

    <div id="cam-warning" class="alert alert-error" style="display:none;"></div>
  `;

  const videoEl = container.querySelector("#cam-video");
  const previewEl = container.querySelector("#cam-preview");
  const placeholderEl = container.querySelector("#cam-placeholder");
  const overlayEl = container.querySelector("#cam-overlay");
  const countdownEl = container.querySelector("#cam-countdown");
  const warningEl = container.querySelector("#cam-warning");

  const controlsIdle = container.querySelector("#controls-idle");
  const controlsLive = container.querySelector("#controls-live");
  const nativeCamInput = container.querySelector("#native-camera-input");
  const galleryInput = container.querySelector("#gallery-input");

  function stopStream() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
    videoEl.style.display = "none";
    controlsLive.style.display = "none";
    controlsIdle.style.display = "block";
  }

  async function startLiveCamera() {
    warningEl.style.display = "none";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      warningEl.textContent =
        "Kamera Live membutuhkan HTTPS. Gunakan tombol 'Foto dari HP' untuk membuka kamera ponsel langsung.";
      warningEl.style.display = "block";
      return;
    }
    try {
      stopStream();
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode, width: { ideal: 1080 }, height: { ideal: 1440 } },
        audio: false,
      });
      videoEl.srcObject = stream;
      placeholderEl.style.display = "none";
      previewEl.style.display = "none";
      videoEl.style.display = "block";
      overlayEl.style.display = "flex";
      controlsIdle.style.display = "none";
      controlsLive.style.display = "block";
    } catch {
      warningEl.textContent = "Izin kamera ditolak. Gunakan tombol 'Foto dari HP' atau 'Pilih dari Galeri'.";
      warningEl.style.display = "block";
    }
  }

  async function captureFromLive() {
    const blob = await compressImageToBlob(videoEl);
    const previewUrl = URL.createObjectURL(blob);
    stopStream();
    placeholderEl.style.display = "none";
    overlayEl.style.display = "none";
    previewEl.src = previewUrl;
    previewEl.style.display = "block";
    onPhotoReady(blob);
  }

  function handleFileSelected(file) {
    if (!file) return;
    warningEl.style.display = "none";
    stopStream();
    const img = new Image();
    const objUrl = URL.createObjectURL(file);
    img.onload = async () => {
      const blob = await compressImageToBlob(img);
      placeholderEl.style.display = "none";
      overlayEl.style.display = "none";
      previewEl.src = objUrl;
      previewEl.style.display = "block";
      onPhotoReady(blob);
    };
    img.src = objUrl;
  }

  container.querySelector("#btn-native-cam").addEventListener("click", () => nativeCamInput.click());
  container.querySelector("#btn-gallery").addEventListener("click", () => galleryInput.click());
  container.querySelector("#btn-live-cam").addEventListener("click", startLiveCamera);
  container.querySelector("#btn-stop-cam").addEventListener("click", () => {
    stopStream();
    if (!previewEl.src) placeholderEl.style.display = "block";
  });
  container.querySelector("#btn-flip-cam").addEventListener("click", () => {
    facingMode = facingMode === "environment" ? "user" : "environment";
    startLiveCamera();
  });
  container.querySelector("#btn-snap-now").addEventListener("click", captureFromLive);
  container.querySelector("#btn-snap-timer").addEventListener("click", () => {
    let sec = 3;
    countdownEl.textContent = sec;
    countdownEl.style.display = "block";
    const timer = setInterval(() => {
      sec -= 1;
      if (sec <= 0) {
        clearInterval(timer);
        countdownEl.style.display = "none";
        captureFromLive();
      } else {
        countdownEl.textContent = sec;
      }
    }, 1000);
  });

  nativeCamInput.addEventListener("change", (e) => handleFileSelected(e.target.files[0]));
  galleryInput.addEventListener("change", (e) => handleFileSelected(e.target.files[0]));

  return { destroy: stopStream };
}