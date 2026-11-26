import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { observarRotulosCampos } from "./utils/rotulosCampos";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// Acessibilidade: liga os rótulos aos campos em todas as telas (inclusive login e modais)
observarRotulosCampos(document.body);
