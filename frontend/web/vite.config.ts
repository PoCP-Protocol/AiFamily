import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4173,
    proxy: {
      "/families": {
        target: "http://127.0.0.1:8091",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://127.0.0.1:8091",
        changeOrigin: true,
      },
      "^/product-intelligence": {
        target: "http://127.0.0.1:8010",
        changeOrigin: true,
        rewrite: (path) => path,
      },
    },
  },
});
