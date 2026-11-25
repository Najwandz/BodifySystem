import { addKatalogItem, deleteKatalogItem, getAuthSession, getKatalogList } from "../services/apiService.js";

export async function renderKatalogSewaView(root) {
  const isLoggedIn = Boolean(getAuthSession());

  root.innerHTML = `
    <div class="card">
      <div class="card-title">👗 Katalog Stok Sewa Busana</div>
      <div id="katalog-list" class="muted">Memuat katalog...</div>
    </div>

    ${
      isLoggedIn
        ? `<div class="card">
            <div class="card-title">➕ Tambah Stok Busana</div>
            <form id="form-katalog">
              <div class="field"><label>Nama Busana</label><input name="nama_busana" required placeholder="Kebaya Brokat Wisuda" /></div>
              <div class="btn-grid">
                <div class="field"><label>Kategori</label><input name="kategori" required placeholder="Kebaya" /></div>
                <div class="field"><label>Ukuran</label><input name="ukuran_label" required placeholder="M" /></div>
              </div>
              <div class="btn-grid">
                <div class="field"><label>Dada Min-Max (cm)</label><input name="dada" required placeholder="89-95" /></div>
                <div class="field"><label>Pinggang Min-Max (cm)</label><input name="pinggang" required placeholder="71-77" /></div>
              </div>
              <div class="btn-grid">
                <div class="field"><label>Bahu Min-Max (cm)</label><input name="bahu" required placeholder="40-43" /></div>
                <div class="field"><label>Stok</label><input name="stok" type="number" value="2" min="1" required /></div>
              </div>
              <button type="submit" class="btn btn-primary">Simpan Busana</button>
            </form>
          </div>`
        : `<div class="alert alert-info">Login sebagai staf (pojok kanan atas) untuk menambah atau menghapus stok busana.</div>`
    }
  `;

  async function loadCatalog() {
    const listEl = root.querySelector("#katalog-list");
    try {
      const items = await getKatalogList();
      if (!items.length) {
        listEl.innerHTML = "<p>Belum ada stok busana tersedia.</p>";
        return;
      }
      listEl.innerHTML = items
        .map(
          (it) => `
          <div class="list-item">
            <div class="list-item-head">
              <b>${it.nama_busana} — Size ${it.ukuran_label}</b>
              ${
                isLoggedIn
                  ? `<button type="button" data-del="${it.id}" class="btn btn-danger btn-sm">Hapus</button>`
                  : `<span class="muted">Stok: ${it.stok}</span>`
              }
            </div>
            <div class="muted">${it.kategori} • Stok: ${it.stok}</div>
            <div class="muted">Dada ${it.dada_min}-${it.dada_max} cm • Pinggang ${it.pinggang_min}-${it.pinggang_max} cm • Bahu ${it.bahu_min}-${it.bahu_max} cm</div>
          </div>`
        )
        .join("");

      listEl.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await deleteKatalogItem(btn.dataset.del);
          loadCatalog();
        });
      });
    } catch (err) {
      listEl.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
  }

  const form = root.querySelector("#form-katalog");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const parseRange = (str) => str.split("-").map((v) => parseFloat(v.trim()));
      const [dMin, dMax] = parseRange(fd.get("dada"));
      const [pMin, pMax] = parseRange(fd.get("pinggang"));
      const [bMin, bMax] = parseRange(fd.get("bahu"));

      await addKatalogItem({
        nama_busana: fd.get("nama_busana"),
        kategori: fd.get("kategori"),
        ukuran_label: fd.get("ukuran_label"),
        dada_min: dMin, dada_max: dMax,
        pinggang_min: pMin, pinggang_max: pMax,
        pinggul_min: pMin + 20, pinggul_max: pMax + 24,
        bahu_min: bMin, bahu_max: bMax,
        stok: parseInt(fd.get("stok"), 10),
      });
      e.target.reset();
      loadCatalog();
    });
  }

  loadCatalog();
}