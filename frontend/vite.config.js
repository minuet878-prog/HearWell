import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Bundles go into Django's static files; templates load each entry by its fixed name
// (collectstatic adds the content hash). Shared code such as React is split into its own file.
// The site's stylesheet is built here too, by Tailwind (ADR 0008).
export default defineConfig({
  plugins: [tailwindcss(), react()],
  // Asset URLs in site.css (the font files, #181) point next to it, under Django's static URL.
  base: "./",
  build: {
    // Font slices stay separate files, so a page downloads only the characters it shows.
    assetsInlineLimit: 0,
    outDir: "../screening/static/screening/frontend",
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        "site": "src/site.css",
        "trend-chart": "src/main.jsx",
        "answer": "src/answer-main.jsx",
        "logout": "src/logout.js",
        "site-shell": "src/site-shell-main.js",
        "audiogram-input": "src/audiogram-main.jsx",
        "audiogram-view": "src/audiogram-view-main.jsx",
        "speech-banana": "src/speech-banana-main.jsx",
        "simulator": "src/simulator-main.jsx",
        "fitting-level": "src/fitting-level.js",
        "continue-notice": "src/continue-notice-main.js",
        "care-journey": "src/care-journey-main.js",
        "guide": "src/guide-main.js",
        "guest-result": "src/guest-result-main.js",
        "guest-save": "src/guest-save-main.js",
        "guest-home": "src/guest-home-main.js",
        "guest-ask": "src/guest-ask-main.js",
        "wear-motion": "src/wear-motion-main.js",
        "arrival-count": "src/arrival-count-main.js",
        "door-count": "src/door-count-main.js",
        "card-stack": "src/card-stack-main.js",
      },
      output: { entryFileNames: "[name].js", assetFileNames: "[name][extname]" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
