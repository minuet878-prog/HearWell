import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Bundles go into Django's static files; templates load each entry by its fixed name
// (collectstatic adds the content hash). Shared code such as React is split into its own file.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../screening/static/screening/frontend",
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        "trend-chart": "src/main.jsx",
        "answer": "src/answer-main.jsx",
        "logout": "src/logout.js",
        "pwa-nav": "src/pwa-nav-main.js",
        "audiogram-input": "src/audiogram-main.jsx",
        "audiogram-view": "src/audiogram-view-main.jsx",
      },
      output: { entryFileNames: "[name].js" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
