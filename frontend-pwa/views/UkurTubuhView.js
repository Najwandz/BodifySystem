import { estimateSinglePhoto } from "../services/apiService.js";
import { mountCameraOverlay } from "./components/CameraOverlayView.js";
import { renderSizeResultCard } from "./components/SizeResultCardView.js";

export function renderUkurTubuhView(root) {
  let capturedBlob = null;
  let selectedClothing = "kasual";

  root.innerHTML = `
    <div class="card">
      <div class="card-title">1. Ambil 1 Foto dari HP (Tanpa Tinggi Badan)</div>
      <div id="camera-slot"></div>
    </div>

    <div class="card">
      <div class="card-title">2. Jenis Pakaian Saat Difoto</div>
      <div class="chip-group" id="cloth-chips">
        <button type="button" class="chip" data-val="ketat">Pas Badan</button>
        <button type="button" class="chip active" data-val="kasual">Kasual</button>
        <button type="button" class="chip" data-val="longgar">Longgar</button>
      </div>

      <details style="margin-top:12px;">
        <summary class="muted" style="cursor:pointer;font-weight:600;">+ Simpan ke Riwayat Pelanggan (Opsional)</summary>
        <div style="margin-top:10px;">
          <div class="field">
            <label>Nama Pelanggan</label>
            <input type="text" id="input-nama" placeholder="Contoh: Rina Kartika" />
          </div>
          <div class="field">
            <label>No. WhatsApp / HP</label>
            <input type="tel" id="input-hp" placeholder="08xxxxxxxxxx" />
          </div>
        </div>
      </details>

      <button type="button" id="btn-submit-ukur" class="btn btn-primary" style="margin-top:14px;" disabled>
        📏 Hitung Bahu, Dada & Pinggang
      </button>
      <div id="ukur-error" class="alert alert-error" style="display:none;"></div>
    </div>

    <div id="ukur-result"></div>
  `;

  const submitBtn = root.querySelector("#btn-submit-ukur");
  const errorBox = root.querySelector("#ukur-error");
  const resultSlot = root.querySelector("#ukur-result");

  const cam = mountCameraOverlay(root.querySelector("#camera-slot"), {
    viewType: "front",
    onPhotoReady(blob) {
      capturedBlob = blob;
      submitBtn.disabled = false;
      errorBox.style.display = "none";
    },
  });

  root.querySelectorAll("#cloth-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      root.querySelectorAll("#cloth-chips .chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      selectedClothing = chip.dataset.val;
    });
  });

  submitBtn.addEventListener("click", async () => {
    if (!capturedBlob) return;
    errorBox.style.display = "none";
    submitBtn.disabled = true;
    submitBtn.textContent = "⏳ Menganalisis bentuk tubuh...";

    try {
      const data = await estimateSinglePhoto({
        imageBlob: capturedBlob,
        clothingType: selectedClothing,
        namaPelanggan: root.querySelector("#input-nama").value.trim(),
        noHp: root.querySelector("#input-hp").value.trim(),
      });
      resultSlot.innerHTML = renderSizeResultCard(data);
      resultSlot.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "📏 Hitung Bahu, Dada & Pinggang";
    }
  });

  return () => cam.destroy();
}