import { loginStaff } from "../services/apiService.js";

export function renderLoginView(root, onSuccess) {
  root.innerHTML = `
    <div class="card">
      <div class="card-title">🔐 Login Pengelola / Staf Mitra</div>
      <p class="muted" style="margin-bottom:12px;">
        Masuk untuk mengelola katalog stok sewa busana, membuat tautan ukur jarak jauh, dan mengekspor riwayat pelanggan.
      </p>
      <form id="form-login">
        <div class="field">
          <label>Username</label>
          <input type="text" id="login-user" value="admin" required />
        </div>
        <div class="field">
          <label>Password</label>
          <input type="password" id="login-pass" value="admin123" required />
        </div>
        <button type="submit" class="btn btn-primary" id="btn-login">Masuk ke Dasbor</button>
      </form>
      <div id="login-error" class="alert alert-error" style="display:none;"></div>
    </div>
  `;

  const errBox = root.querySelector("#login-error");
  root.querySelector("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.style.display = "none";
    try {
      await loginStaff(
        root.querySelector("#login-user").value.trim(),
        root.querySelector("#login-pass").value
      );
      onSuccess("dashboard");
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
    }
  });
}