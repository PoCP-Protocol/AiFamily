import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Deterministic browser-test server: frontend and API share one isolated port pair. */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4191,
    strictPort: true,
    proxy: {
      "/families": { target: "http://127.0.0.1:8093", changeOrigin: true },
      "/auth": { target: "http://127.0.0.1:8093", changeOrigin: true },
      "^/product-intelligence": {
        target: "http://127.0.0.1:8010",
        changeOrigin: true,
        rewrite: (path) => path,
      },
    },
  },
});
