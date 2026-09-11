import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 用 127.0.0.1 而非 localhost：Node 会把 localhost 解析成 IPv6 ::1，
      // 而后端 uvicorn 只监听 IPv4 127.0.0.1，会导致 ECONNREFUSED ::1:8000
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
