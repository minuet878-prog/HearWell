import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The bundle goes into Django's static files; the my_hearing template loads it by this fixed name
// (collectstatic adds the content hash).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../screening/static/screening/trend",
    emptyOutDir: true,
    rolldownOptions: {
      input: "src/main.jsx",
      output: { entryFileNames: "trend-chart.js" },
    },
  },
  test: {
    environment: "jsdom",
  },
});
