import { renderNavbar } from "../views/components/NavbarView.js";
import { renderDashboardView } from "../views/DashboardView.js";
import { renderKatalogSewaView } from "../views/KatalogSewaView.js";
import { renderLoginView } from "../views/LoginView.js";
import { renderRemoteSizingView } from "../views/RemoteSizingView.js";
import { renderUkurTubuhView } from "../views/UkurTubuhView.js";

let cleanupCurrentView = null;

export function navigate(route = "ukur", param = "") {
  if (typeof cleanupCurrentView === "function") {
    cleanupCurrentView();
    cleanupCurrentView = null;
  }

  const root = document.getElementById("app");
  renderNavbar(route, (target) => navigate(target));

  if (route === "login") {
    renderLoginView(root, (nextRoute) => navigate(nextRoute));
  } else if (route === "dashboard") {
    renderDashboardView(root);
  } else if (route === "katalog") {
    renderKatalogSewaView(root);
  } else if (route === "remote") {
    cleanupCurrentView = renderRemoteSizingView(root, param);
  } else {
    cleanupCurrentView = renderUkurTubuhView(root);
  }
}

export function initRouter() {
  const hash = window.location.hash || "";
  if (hash.startsWith("#remote/")) {
    const token = hash.replace("#remote/", "").trim();
    navigate("remote", token);
    return;
  }
  navigate("ukur");
}