import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Playwright injects the isolated backend port through process.env; merge it
  // explicitly because loadEnv only reads .env files.
  const apiPort = process.env.VITE_API_PORT || env.VITE_API_PORT || "8091";
  const apiBaseUrl = process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL || "";
  return {
    plugins: [react()],
    define: {
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify(apiBaseUrl),
    },
    server: {
      port: 4173,
      proxy: {
        "/families": {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
        "/auth": {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
        "^/product-intelligence": {
          target: "http://127.0.0.1:8010",
          changeOrigin: true,
          rewrite: (path) => path,
        },
      },
    },
  };
});
