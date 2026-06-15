import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // The vendor chunk is dominated by Elastic UI, which is large by nature;
    // isolating it (below) is the right move, so don't warn on its size.
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      output: {
        // Split rarely-changing dependencies into one long-cached vendor
        // chunk so app edits ship a small delta and first load parallelizes.
        manualChunks: (id) =>
          id.includes("node_modules") ? "vendor" : undefined,
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
