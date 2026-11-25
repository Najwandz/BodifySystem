export function renderSizeResultCard(data) {
  const m = data.estimasi_ukuran_cm || {};
  const sewa = data.pencocokan_sewa || {};
  const pose = data.info_pose || {};
  const catatan = (sewa.catatan_penyesuaian || []).map((c) => `<li>${c}</li>`).join("");

  const hasExtraMetrics = typeof m.lingkar_pinggul === "number" && m.lingkar_pinggul > 0;

  return `
    <div class="card">
      <div class="card-title">✅ Hasil Estimasi Ukuran Tubuh</div>
      <div class="metric-grid">
        <div class="metric-box">
          <div class="metric-label">Lebar Bahu</div>
          <div class="metric-val">${m.lebar_bahu}</div>
          <div class="metric-unit">cm</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Lingkar Dada</div>
          <div class="metric-val">${m.lingkar_dada}</div>
          <div class="metric-unit">cm</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Lingkar Pinggang</div>
          <div class="metric-val">${m.lingkar_pinggang}</div>
          <div class="metric-unit">cm</div>
        </div>
      </div>

      ${
        hasExtraMetrics
          ? `<div class="metric-grid" style="margin-top:0;">
              <div class="metric-box">
                <div class="metric-label">Lingkar Pinggul</div>
                <div class="metric-val">${m.lingkar_pinggul}</div>
                <div class="metric-unit">cm</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">Panjang Lengan</div>
                <div class="metric-val">${m.panjang_lengan}</div>
                <div class="metric-unit">cm</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">Panjang Badan</div>
                <div class="metric-val">${m.panjang_badan}</div>
                <div class="metric-unit">cm</div>
              </div>
            </div>`
          : ""
      }

      <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-top:1px solid #e2e8f0;">
        <div>
          <div class="muted">Rekomendasi Ukuran Busana</div>
          <div style="font-size:0.84rem;margin-top:2px;">Skor kecocokan: <b>${sewa.skor_kecocokan ?? 0}%</b></div>
        </div>
        <span class="size-badge">Size ${sewa.rekomendasi_ukuran || "-"}</span>
      </div>

      ${catatan ? `<ul class="muted" style="margin:6px 0 0 18px;line-height:1.5;">${catatan}</ul>` : ""}

      <div class="alert alert-info" style="margin-top:12px;">
        ${pose.status_pose ? `<b>Pose:</b> ${pose.status_pose}<br/>` : ""}
        <b>Metode Skala:</b> ${pose.metode_skala || "Kalibrasi Tinggi Badan Aktual"}
        ${data.pelanggan_id ? "<br/><b>Riwayat pelanggan berhasil disimpan.</b>" : ""}
      </div>
    </div>
  `;
}