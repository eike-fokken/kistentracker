import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the Vite dev server runs on port 5173 and proxies all
// `/api` requests to the Django backend on port 8080. This means the frontend
// can use same-origin relative URLs and we avoid CORS entirely.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
