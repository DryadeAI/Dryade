import { defineConfig, type UserConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import fs from "fs";
import os from "os";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";

function loadDryadeCerts(): { key: string; cert: string } | undefined {
  // Priority: env override > repo-shipped certs > user home certs
  const candidates = [
    process.env.DRYADE_CERT_DIR,
    path.resolve(__dirname, "../certs"),
    path.join(os.homedir(), ".dryade", "certs"),
  ].filter(Boolean) as string[];

  for (const dir of candidates) {
    const keyPath = path.join(dir, "server.key");
    const certPath = path.join(dir, "server.pem");
    if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
      return {
        key: fs.readFileSync(keyPath, "utf-8"),
        cert: fs.readFileSync(certPath, "utf-8"),
      };
    }
  }
  return undefined;
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }): UserConfig => {
  const certs = loadDryadeCerts();

  return {
    server: {
      host: "::",
      port: 9005,
      https: certs || false,
      hmr: {
        overlay: false,
      },
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8080",
          changeOrigin: true,
          ws: true,
        },
        "/ws": {
          target: "ws://127.0.0.1:8080",
          ws: true,
          changeOrigin: true,
        },
      },
    },
    plugins: [
      react(),
      mode === "development" && componentTagger(),
      VitePWA({
        registerType: 'prompt',
        includeAssets: ['favicon.svg', 'favicon.ico', 'icons/*.png'],
        manifest: false,
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
              handler: 'CacheFirst',
              options: {
                cacheName: 'google-fonts-cache',
                expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
              handler: 'CacheFirst',
              options: {
                cacheName: 'gstatic-fonts-cache',
                expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
                cacheableResponse: { statuses: [0, 200] }
              }
            },
            {
              urlPattern: /\/api\/.*/i,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'api-cache',
                expiration: { maxEntries: 50, maxAgeSeconds: 60 * 5 },
                cacheableResponse: { statuses: [0, 200] },
                networkTimeoutSeconds: 10
              }
            }
          ]
        }
      }),
    ].filter(Boolean) as UserConfig["plugins"],
    optimizeDeps: {
      exclude: ["@noble/post-quantum"],
      entries: ["index.html"],
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});
