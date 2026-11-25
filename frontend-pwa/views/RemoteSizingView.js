import { getRemoteInfo, submitRemoteEstimate } from "../services/apiService.js";
import { mountCameraOverlay } from "./components/CameraOverlayView.js";
import { renderSizeResultCard } from "./components/SizeResultCardView.js";

export async function renderRemoteSizingView(root, initialToken = "") {
  let frontBlob = null;
  let sideBlob = null;
  let camFront = null;
  let camSide = null;

  root.innerHTML = `
    <div class="card">
      <div class="card-title">🔗 Ukur Mandiri Pelanggan (Remote Sizing)</div>
      <div class="field">
        <label>Kode Token Pelanggan</label>
        <div class="btn-grid" style="grid-template-columns: 2fr 1fr; margin-bottom:0;">
          <input type="text" id="remote-token-input" value="${initialToken}" placeholder="Contoh: a1b2c3d4e5f6" />
          <button type="button" class="btn btn-primary" id="btn-load-token">Cek Kode</button>
        </div>
      </div>
      <div id="remote-customer-info"></div>
    </div>

    <div id="remote-form-area" style="display:none;">
      <div class="card">
        <div class="card-title">1. Tinggi Badan & Jenis Pakaian</div>
        <div class="field">
          <label>Tinggi Badan Aktual (cm)</label>
          <input type="number" id="remote-height" min="100" max="230" step="0.5" placeholder="Contoh: 165" required />
        </div>
        <div class="field">
          <label>Pakaian Saat Difoto</label>
          <select id="remote-cloth">
            <option value="ketat">Pas Badan</option>
            <option value="kasual" selected>Kasual</option>
            <option value="longgar">Longgar</option>
          </select>
        </div>
      </div>

      <div class="card">
        <div class="card-title">2. Foto Tampak Depan</div>
        <div id="remote-cam-front"></div>
      </div>

      <div class="card">
        <div class="card-title">3. Foto Tampak Samping</div>
        <div id="remote-cam-side"></div>
      </div>

      <button type="button" id="btn-submit-remote" class="btn btn-success" disabled>
        📤 Kirim Hasil Pengukuran ke Penjahit
      </button>
      <div id="remote-error" class="alert alert-error" style="display:none;"></div>
      <div id="remote-result" style="margin-top:14px;"></div>
    </div>
  `;

  const tokenInput = root.querySelector("#remote-token-input");
  const infoBox = root.querySelector("#remote-customer-info");
  const formArea = root.querySelector("#remote-form-area");
  const submitBtn = root.querySelector("#btn-submit-remote");
  const errBox = root.querySelector("#remote-error");

  function checkReady() {
    const h = parseFloat(root.querySelector("#remote-height").value);
    submitBtn.disabled = !(frontBlob && sideBlob && h >= 100 && h <= 230);
  }

  async function verifyToken(token) {
    if (!token) return;
    infoBox.innerHTML = `<p class="muted">Memeriksa tautan...</p>`;
    try {
      const customer = await getRemoteInfo(token);
      infoBox.innerHTML = `<div class="alert alert-info">Halo <b>${customer.nama}</b>, silakan ambil 2 foto (depan & samping) untuk dikirim langsung ke penjahit.</div>`;
      if (customer.tinggi_badan_cm) {
        root.querySelector("#remote-height").value = customer.tinggi_badan_cm;
      }
      formArea.style.display = "block";
      if (!camFront) {
        camFront = mountCameraOverlay(root.querySelector("#remote-cam-front"), {
          viewType: "front",
          onPhotoReady(b) { frontBlob = b; checkReady(); },
        });
      }
      if (!camSide) {
        camSide = mountCameraOverlay(root.querySelector("#remote-cam-side"), {
          viewType: "side",
          onPhotoReady(b) { sideBlob = b; checkReady(); },
        });
      }
      checkReady();
    } catch (err) {
      formArea.style.display = "none";
      infoBox.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
  }

  root.querySelector("#btn-load-token").addEventListener("click", () => {
    verifyToken(tokenInput.value.trim());
  });
  root.querySelector("#remote-height").addEventListener("input", checkReady);

  submitBtn.addEventListener("click", async () => {
    const token = tokenInput.value.trim();
    const heightCm = parseFloat(root.querySelector("#remote-height").value);
    const clothingType = root.querySelector("#remote-cloth").value;

    errBox.style.display = "none";
    submitBtn.disabled = true;
    submitBtn.textContent = "⏳ Memproses & mengirim data...";

    try {
      const data = await submitRemoteEstimate(token, {
        frontBlob,
        sideBlob,
        heightCm,
        clothingType,
      });
      root.querySelector("#remote-result").innerHTML = renderSizeResultCard(data);
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "📤 Kirim Hasil Pengukuran ke Penjahit";
    }
  });

  if (initialToken) verifyToken(initialToken);

  return () => {
    if (camFront) camFront.destroy();
    if (camSide) camSide.destroy();
  };
}