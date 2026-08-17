import { createHmac } from "node:crypto";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Mint the same HS256 JWS that Netlify attaches to signed proxy redirects.
 *
 * In production Netlify does this at the edge. Locally there is no Netlify, so
 * the dev server signs requests itself — which keeps `npm run dev` on exactly
 * the same code path as production, with no bypass in the backend.
 *
 * This runs in the Vite dev server (Node), never in the browser, and the secret
 * has no VITE_ prefix so Vite will not inline it into any bundle.
 */
const b64url = (input) =>
  Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const signNetlifyJWS = (secret, siteUrl) => {
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({
      iss: "netlify",
      site_url: siteUrl,
      deploy_context: "dev",
      netlify_id: "local-dev",
      exp: Math.floor(Date.now() / 1000) + 300,
    })
  );
  const body = `${header}.${payload}`;
  const signature = createHmac("sha256", secret).update(body).digest("base64")
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${body}.${signature}`;
};

export default defineConfig(({ mode }) => {
  // Third arg "" loads every var, not just VITE_-prefixed ones.
  const env = loadEnv(mode, process.cwd(), "");
  const target =
    env.MODAL_URL || "https://yangalex1081--receipt-parser-fastapi-app.modal.run";
  const secret = env.NETLIFY_SIGN_SECRET;

  if (!secret) {
    console.warn(
      "\n  [dev] NETLIFY_SIGN_SECRET is not set — /api/* calls will get 401.\n" +
        "  Add it to receipt-parser-frontend/.env (same value as Netlify and Modal).\n"
    );
  }

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          configure: (proxy) => {
            proxy.on("proxyReq", (proxyReq) => {
              if (secret) {
                proxyReq.setHeader(
                  "x-nf-sign",
                  signNetlifyJWS(secret, "http://localhost:3000")
                );
              }
            });
          },
        },
      },
    },
  };
});
