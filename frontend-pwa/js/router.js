import { renderNavbar } from "../views/components/NavbarView.js";
import { renderDashboardView } from "../views/DashboardView.js";
import { renderLoginView } from "../views/LoginView.js";
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
  } else {
    cleanupCurrentView = renderUkurTubuhView(root);
  }
}

export function initRouter() {
  navigate("ukur");
}