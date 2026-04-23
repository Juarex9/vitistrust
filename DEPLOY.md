# VitisTrust Deployment Guide

## Overview

```
Frontend (Vercel)          Backend (Render)
┌─────────────┐            ┌─────────────────┐
│  React App  │───────────▶│   FastAPI       │
│  vercel.app│   API      │   :8000         │
└─────────────┘            └─────────────────┘
```

---

## Prerequisites

1. **Accounts required:**
   - [Vercel](https://vercel.com) (Frontend hosting)
   - [Render](https://render.com) (Backend hosting)
   - [GitHub](https://github.com) (Repository)

2. **APIs required:**
   - Sentinel Hub (satellite imagery)
   - Groq (AI analysis)
   - Hedera (notarization)
   - Stellar Soroban RPC (smart contracts)

---

## Step 1: Backend Deploy (Render)

### Option A: Manual Deploy

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:

   | Setting | Value |
   |---------|-------|
   | Name | `vitistrust-api` |
   | Region | Oregon (or closest) |
   | Branch | `main` |
   | Root Directory | (leave empty) |
   | Runtime | `Python 3` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |

5. Click **"Create Web Service"**

### Option B: Blueprint Deploy (render.yaml)

1. Push `render.yaml` to your repository
2. Render will auto-detect and offer to deploy

### Environment Variables (Required)

Add these in Render dashboard → Environment:

```bash
# ===== STELLAR SOROBAN (Asset Layer) =====
STELLAR_NETWORK=testnet
STELLAR_RPC_URL=https://soroban-testnet.stellar.org:443
STELLAR_ORACLE_SECRET=your_oracle_secret
SOROBAN_CONTRACT_ID=CA...        # Deployed contract address
STELLAR_TIMEOUT_S=60

# ===== HEDERA (Trust Layer) =====
HEDERA_ACCOUNT_ID=0.0.xxxxxx
HEDERA_DER_PRIVATE_KEY=3020...
HEDERA_TOPIC_ID=0.0.xxxxxx

# ===== SATELLITE (Sentinel Hub) =====
SENTINEL_CLIENT_ID=...
SENTINEL_CLIENT_SECRET=...

# ===== AI (Groq) =====
AI_API_KEY=...
AI_MODEL=llama-3.3-70b-versatile
```

### Health Check

After deploy, verify:
```bash
curl https://vitistrust-api.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "rsk": "connected",
  "hedera": "connected"
}
```

---

## Step 2: Frontend Deploy (Vercel)

### Option A: Import from GitHub

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your repository
3. Configure:

   | Setting | Value |
   |---------|-------|
   | Framework | `Vite` |
   | Root Directory | `./` |
   | Build Command | `npm run build` |
   | Output Directory | `frontend-react/dist` |

4. Add environment variable:
   ```
   VITE_API_URL=https://vitistrust-api.onrender.com
   ```

5. Click **"Deploy"**

### Option B: Vercel CLI

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd vitistrust
vercel

# Set production environment variable
vercel env add VITE_API_URL
# Select "Production" and enter: https://vitistrust-api.onrender.com

# Deploy to production
vercel --prod
```

---

## Step 3: Update Frontend API URL

The frontend is configured to use `VITE_API_URL` environment variable.

In Vercel dashboard:
1. Go to your project → Settings → Environment Variables
2. Add:
   - Name: `VITE_API_URL`
   - Value: `https://vitistrust-api.onrender.com` (or your Render URL)
   - Environments: Production, Preview, Development

---

## Step 4: Verify Deployment

### Test Backend
```bash
curl https://vitistrust-api.onrender.com/health
```

### Test Frontend
Visit: `https://your-vercel-project.vercel.app`

### End-to-End Test
1. Enter coordinates (e.g., `-33.4942, -69.2429`)
2. Enter asset address and token ID
3. Click "Run Verification"
4. Verify you get:
   - NDVI image
   - VitisScore
   - Hedera topic ID
   - Stellar transaction hash

---

## Custom Domains (Optional)

### Vercel
1. Project Settings → Domains
2. Add your domain (e.g., `app.vitistrust.com`)
3. Update DNS records as instructed

### Render
1. Service → Settings → Custom Domains
2. Add your domain
3. Update DNS to point to Render

---

## Troubleshooting

### CORS Errors
If frontend can't reach backend:
1. Check Render CORS middleware allows Vercel domain
2. Verify `VITE_API_URL` is set correctly
3. Check browser console for specific errors

### Health Check Fails
```bash
# Test locally first
cd vitistrust
pip install -r requirements.txt
python -c "from backend.main import app; print('Import OK')"
uvicorn backend.main:app --reload
```

### Build Fails on Vercel
1. Check build logs
2. Verify `vercel.json` configuration
3. Ensure `frontend-react` folder exists with `package.json`

---

## URLs

| Service | URL |
|---------|-----|
| Frontend (Vercel) | `https://vitistrust.vercel.app` |
| Backend (Render) | `https://vitistrust-api.onrender.com` |
| API Docs | `https://vitistrust-api.onrender.com/docs` |

---

## Security Notes

1. **Never commit `.env` files** - Use Render/Vercel environment variables
2. **Rotate keys regularly** - Especially STELLAR_ORACLE_SECRET
3. **Use testnet first** - Don't use mainnet private keys until production-ready
4. **Rate limiting** - Consider adding rate limiting for production

---

## Quick Commands

```bash
# Local development
python -m uvicorn backend.main:app --reload
npm run dev  # in frontend-react folder

# Deploy to Vercel
vercel --prod

# Check Render logs
render logs -s vitistrust-api

# Test API
curl https://vitistrust-api.onrender.com/health
```
