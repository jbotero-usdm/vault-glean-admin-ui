# Vault-Glean Admin Console

A Vercel-hosted admin console for managing the USDM Quality Vault → Glean integration.

## Architecture

- **Vercel (this app)**: Next.js UI + lightweight API routes (read-only audit, monitor, status)
- **Vercel Cron**: Triggers the nightly sync automatically
- **External Worker** (Render/Railway/Fly.io): Runs the long-running sync jobs (>5 min)
- **Slack Webhook**: Notifications for sync results

## Why two services?

Vercel serverless functions have execution time limits:
- Hobby plan: 60s
- Pro plan: 5 min (default), 15 min (background)

Vault Direct Data syncs can take 5–15 min on a full reconcile. So we host:
- UI + quick reads → Vercel
- Heavy sync → external worker (Render free tier or Railway $5/mo)

## Quickstart

### 1. Deploy the worker
See `worker/` directory in the companion repo (separate). Deploy to Render.com.
Set env vars on the worker:
- VAULT_DNS, VAULT_USERNAME, VAULT_PASSWORD
- GLEAN_API_URL, GLEAN_INDEXING_API_TOKEN
- WORKER_API_KEY (must match what's in Vercel)

### 2. Deploy this Next.js app to Vercel
```bash
vercel
```

Set env vars from `.env.example` in Vercel project settings.

### 3. Enable Password Protection
Vercel Project Settings → Deployment Protection → "Password Protection" or "Vercel Authentication"

### 4. Test
- Visit your Vercel URL
- Login with ADMIN_PASSWORD
- Click "Run Sync Now" — it'll trigger the worker
- Status updates appear in the UI

## Operations

- **Nightly sync**: 06:00 UTC (configurable in vercel.json)
- **Nightly monitor report**: 06:30 UTC
- **Slack notification**: Posted on every sync run (success or failure)
