import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Bundles go into Django's static files; templates load each entry by its fixed name
// (collectstatic adds the content hash). Shared code such as React is split into its own file.
// The site's stylesheet is built here too, by Tailwind (ADR 0008).
export default defineConfig({
  // Keep token alpha values exact through both Tailwind and Vite.
  plugins: [tailwindcss({ optimize: false }), react()],
  // Asset URLs in site.css (the font files, #181) point next to it, under Django's static URL.
  base: "./",
  build: {
    // Font slices stay separate files, so a page downloads only the characters it shows.
    assetsInlineLimit: 0,
    outDir: "../screening/static/screening/frontend",
    emptyOutDir: true,
    // Preserve exact alpha values in design tokens (hex alpha rounds 0.5 to 128/255).
    cssMinify: false,
    rolldownOptions: {
      input: {
        "site": "src/site.css",
        "trend-chart": "src/main.jsx",
        "answer": "src/answer-main.jsx",
        "logout": "src/logout.js",
        "pwa-nav": "src/pwa-nav-main.js",
        "audiogram-input": "src/audiogram-main.jsx",
        "audiogram-view": "src/audiogram-view-main.jsx",
        "my-aid": "src/my-aid.js",
      },
      output: { entryFileNames: "[name].js", assetFileNames: "[name][extname]" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
