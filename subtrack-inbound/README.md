# pocketday-inbound

A tiny Cloudflare Email Worker. It forwards every email it receives, unchanged and unstored, to the backend's signed `POST /inbound/email`. Messages over 8 MB are rejected at the edge. Logs contain status codes only.

## Deploy

1. `npm install`
2. `npx wrangler login`
3. `npx wrangler secret put INBOUND_EMAIL_SECRET` (same value as the backend's `INBOUND_EMAIL_SECRET`)
4. Set `BACKEND_URL` in `wrangler.toml` to the deployed backend origin.
5. `npm run deploy`
6. Cloudflare dashboard, pocketday.app, Email Routing, Routing rules, Catch-all, Send to Worker, `pocketday-inbound`.

## Checks

`npm test` and `npm run typecheck`.
