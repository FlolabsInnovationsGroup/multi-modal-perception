import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { pelApiPlugin } from "./server/vite-pel-plugin";

export default defineConfig({
  plugins: [react(), tailwindcss(), pelApiPlugin()],
});
