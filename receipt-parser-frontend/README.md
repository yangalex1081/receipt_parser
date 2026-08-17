# Receipt Parser — frontend

React 19 + Vite SPA. Upload a receipt photo, get itemised lines back, assign a
buyer to each and see per-person totals.

## Setup

```bash
npm install
cp .env.example .env      # then paste NETLIFY_SIGN_SECRET
npm run dev               # http://localhost:3000
```

`NETLIFY_SIGN_SECRET` must match the value in the Netlify dashboard and in the
Modal secret. Without it, `/api/*` returns 401 and the dev server warns at
startup.

## How the backend is reached

The browser only ever calls `/api/*` on its own origin and holds no
credentials. In production Netlify proxies those to Modal and signs each
request (see `netlify.toml`). In development `vite.config.js` mints the same
signature, so local and deployed runs share one code path.

Neither `NETLIFY_SIGN_SECRET` nor `MODAL_URL` carries a `VITE_` prefix, which
is what keeps them out of the browser bundle. **Do not add one to the secret** —
any `VITE_`-prefixed value is inlined into the public JS.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on :3000 with the signing proxy |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the build locally (no `/api` proxy) |
| `npm run lint` | ESLint |

## Layout

```
src/
  App.jsx                    layout; owns parsed data + a pristine copy
  components/
    UploadForm.jsx           select, downscale, upload, poll for the result
    ReceiptTable.jsx         editable rows, per-buyer totals
    HealthCheck.jsx          calls /api/health
  index.css                  theme tokens and base styles
```

Full system design, including the auth model and deploy steps, is in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).
