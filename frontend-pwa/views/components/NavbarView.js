import { getAuthSession, setAuthSession } from "../../services/apiService.js";

export function renderNavbar(activeRoute, onNavigate) {
  const nav = document.getElementById("bottom-nav");
  const authSlot = document.getElementById("auth-status-slot");
  const session = getAuthSession();

  if (session) {
    authSlot.innerHTML = `<button type="button" class="top-pill" id="btn-logout">Keluar (${session.user.username})</button>`;
    authSlot.querySelector("#btn-logout").addEventListener("click", () => {
      setAuthSession(null);
      onNavigate("ukur");
    });
  } else {
    authSlot.innerHTML = `<button type="button" class="top-pill" id="btn-login-nav">Login Staf</button>`;
    authSlot.querySelector("#btn-login-nav").addEventListener("click", () => onNavigate("login"));
  }

  const items = [
    { id: "ukur", icon: "📷", label: "Ukur 1 Foto" },
    { id: "dashboard", icon: "📋", label: "Riwayat" },
    { id: "katalog", icon: "👗", label: "Katalog Sewa" },
    { id: "remote", icon: "🔗", label: "Ukur Mandiri" },
  ];

  nav.innerHTML = items
    .map(
      (item) => `
      <button type="button" class="nav-btn ${activeRoute === item.id ? "active" : ""}" data-route="${item.id}">
        <span class="nav-icon">${item.icon}</span>
        <span>${item.label}</span>
      </button>`
    )
    .join("");

  nav.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => onNavigate(btn.dataset.route));
  });
}