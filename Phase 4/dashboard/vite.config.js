import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built dashboard works when opened from any static path.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
