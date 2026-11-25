import { createPelanggan, getExportCsvUrl, getPelangganList } from "../services/apiService.js";

export async function renderDashboardView(root) {
  root.innerHTML = `
    <div class="card">
      <div class="card-title">
        <span>📋 Riwayat Ukuran Pelanggan</span>
        <a href="${getExportCsvUrl()}" class="btn btn-outline btn-sm" style="text-decoration:none;">⬇ Ekspor CSV</a>
      </div>
      <div id="pelanggan-list" class="muted">Memuat riwayat pelanggan...</div>
    </div>

    <div class="card">
      <div class="card-title">🔗 Buat Tautan Ukur Jarak Jauh (Remote Sizing)</div>
      <form id="form-new-customer">
        <div class="field">
          <label>Nama Pelanggan</label>
          <input type="text" name="nama" required placeholder="Nama pelanggan luar kota" />
        </div>
        <div class="field">
          <label>No. WhatsApp</label>
          <input type="tel" name="no_hp" placeholder="08xxxxxxxxxx" />
        </div>
        <button type="submit" class="btn btn-primary">Buat Tautan Pelanggan</button>
      </form>
      <div id="remote-link-box" class="alert alert-info" style="display:none;"></div>
    </div>
  `;

  async function loadCustomers() {
    const listEl = root.querySelector("#pelanggan-list");
    try {
      const customers = await getPelangganList();
      if (!customers.length) {
        listEl.innerHTML = `<p style="padding:10px 0;">Belum ada data pelanggan tersimpan.</p>`;
        return;
      }
      listEl.innerHTML = customers
        .map((c) => {
          const u = c.ukuran_terakhir;
          const shareUrl = `${window.location.origin}/#remote/${c.remote_token}`;
          return `
            <div class="list-item">
              <div class="list-item-head">
                <b>${c.nama}</b>
                <span class="size-badge" style="font-size:0.78rem;padding:2px 10px;">
                  ${u ? `Size ${u.rekomendasi_ukuran || "-"}` : "Menunggu Foto"}
                </span>
              </div>
              <div class="muted">${c.no_hp || "Tanpa No. HP"}</div>
              ${
                u
                  ? `<div style="margin-top:6px;font-size:0.85rem;">
                      Bahu: <b>${u.lebar_bahu} cm</b> • Dada: <b>${u.lingkar_dada} cm</b> • Pinggang: <b>${u.lingkar_pinggang} cm</b>
                    </div>`
                  : ""
              }
              <div style="margin-top:8px;">
                <button type="button" class="btn btn-outline btn-sm btn-copy-link" data-url="${shareUrl}">
                  📋 Salin Link Ukur Mandiri (${c.remote_token})
                </button>
              </div>
            </div>`;
        })
        .join("");

      listEl.querySelectorAll(".btn-copy-link").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await navigator.clipboard.writeText(btn.dataset.url);
          btn.textContent = "✅ Tautan Tersalin!";
          setTimeout(() => (btn.textContent = "📋 Salin Link Ukur Mandiri"), 2000);
        });
      });
    } catch (err) {
      listEl.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
  }

  root.querySelector("#form-new-customer").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const created = await createPelanggan({
      nama: fd.get("nama"),
      no_hp: fd.get("no_hp"),
    });
    const link = `${window.location.origin}/#remote/${created.remote_token}`;
    const box = root.querySelector("#remote-link-box");
    box.innerHTML = `Tautan untuk <b>${created.nama}</b> siap dikirim:<br/><code>${link}</code>`;
    box.style.display = "block";
    e.target.reset();
    loadCustomers();
  });

  loadCustomers();
}