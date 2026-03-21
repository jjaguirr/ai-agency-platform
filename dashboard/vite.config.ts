import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Dev server proxies /v1/* to FastAPI so the dashboard and the API share
// an origin — no CORS config needed. In production, FastAPI serves the
// built assets at / so the origin is inherently shared.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [svelte()],
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
    server: {
      proxy: {
        "/v1": {
          target: env.API_URL || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
