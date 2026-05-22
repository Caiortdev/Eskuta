import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initThemeFromStorage } from "@/lib/theme";
import "./index.css";

// Aplica tema salvo ANTES do React montar pra evitar flash do wrong theme
initThemeFromStorage();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
