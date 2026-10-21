import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Bundles go into Django's static files; templates load each entry by its fixed name
// (collectstatic adds the content hash). Shared code such as React is split into its own file.
// The site's stylesheet is built here too, by Tailwind (ADR 0008).
export default defineConfig({
  plugins: [tailwindcss(), react()],
  build: {
    outDir: "../screening/static/screening/frontend",
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        "site": "src/site.css",
        "trend-chart": "src/main.jsx",
        "answer": "src/answer-main.jsx",
        "logout": "src/logout.js",
        "pwa-nav": "src/pwa-nav-main.js",
        "audiogram-input": "src/audiogram-main.jsx",
        "audiogram-view": "src/audiogram-view-main.jsx",
      },
      output: { entryFileNames: "[name].js", assetFileNames: "[name][extname]" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
