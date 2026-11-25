const API_BASE = "https://yarn-codes-mines-martial.trycloudflare.com";

async function parseApiResponse(res, fallbackMessage) {
  const rawText = await res.text();
  let data = null;
  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail = data?.detail || rawText || fallbackMessage;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export function getAuthSession() {
  try {
    return JSON.parse(localStorage.getItem("bodify_auth") || "null");
  } catch {
    return null;
  }
}

export function setAuthSession(session) {
  if (session) {
    localStorage.setItem("bodify_auth", JSON.stringify(session));
  } else {
    localStorage.removeItem("bodify_auth");
  }
}

export async function loginStaff(username, password) {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await parseApiResponse(res, "Login gagal.");
  setAuthSession(data);
  return data;
}

export async function estimateSinglePhoto({ imageBlob, clothingType, namaPelanggan, noHp, kategoriSewa }) {
  const formData = new FormData();
  formData.append("front_image", imageBlob, "front.jpg");
  formData.append("clothing_type", clothingType || "kasual");
  if (namaPelanggan) formData.append("nama_pelanggan", namaPelanggan);
  if (noHp) formData.append("no_hp", noHp);
  if (kategoriSewa) formData.append("kategori_sewa", kategoriSewa);

  const res = await fetch(`${API_BASE}/api/v1/estimate-single`, {
    method: "POST",
    body: formData,
  });
  return parseApiResponse(res, "Gagal memproses foto.");
}

export async function getPelangganList() {
  const res = await fetch(`${API_BASE}/api/v1/pelanggan`);
  return parseApiResponse(res, "Gagal memuat daftar pelanggan.");
}

export async function createPelanggan(payload) {
  const res = await fetch(`${API_BASE}/api/v1/pelanggan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseApiResponse(res, "Gagal membuat pelanggan.");
}

export function getExportCsvUrl() {
  return `${API_BASE}/api/v1/pelanggan/export/csv`;
}

export async function getRemoteInfo(token) {
  const res = await fetch(`${API_BASE}/api/v1/remote/${encodeURIComponent(token)}`);
  return parseApiResponse(res, "Tautan remote sizing tidak valid.");
}

export async function submitRemoteEstimate(token, { frontBlob, sideBlob, heightCm, clothingType }) {
  const formData = new FormData();
  formData.append("front_image", frontBlob, "front.jpg");
  formData.append("side_image", sideBlob, "side.jpg");
  formData.append("height_cm", String(heightCm));
  formData.append("clothing_type", clothingType || "kasual");

  const res = await fetch(`${API_BASE}/api/v1/remote/${encodeURIComponent(token)}/estimate`, {
    method: "POST",
    body: formData,
  });
  return parseApiResponse(res, "Gagal mengirim pengukuran mandiri.");
}

export async function getKatalogList() {
  const res = await fetch(`${API_BASE}/api/v1/katalog`);
  return parseApiResponse(res, "Gagal memuat katalog sewa.");
}

export async function addKatalogItem(payload) {
  const res = await fetch(`${API_BASE}/api/v1/katalog`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseApiResponse(res, "Gagal menambah busana ke katalog.");
}

export async function deleteKatalogItem(id) {
  const res = await fetch(`${API_BASE}/api/v1/katalog/${id}`, { method: "DELETE" });
  return parseApiResponse(res, "Gagal menghapus item katalog.");
}