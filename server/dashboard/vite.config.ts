import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Identificador do build: vai no código (__BUILD_ID__) e em /version.json. O painel aberto compara os dois e
// recarrega sozinho depois de um deploy (components/NovaVersao.tsx).
const BUILD_ID = String(Date.now());

function versaoDoBuild(): Plugin {
  return {
    name: "trilan-version-json",
    apply: "build",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "version.json", source: JSON.stringify({ build: BUILD_ID }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), versaoDoBuild()],
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
