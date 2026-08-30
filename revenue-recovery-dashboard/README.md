# Revenue Recovery Agent — Dashboard

Next.js frontend for the Revenue Recovery Agent pipeline (Razorpay AI Buildathon, Track 03).

## Setup (Windows)

1. Make sure your FastAPI backend (`main.py`) is running first, at http://localhost:8000
   (uvicorn main:app --reload)

2. Install dependencies:
   npm install

3. Run the dev server:
   npm run dev

4. Open http://localhost:3000

## What's here

- `/` — Overview dashboard: headline metrics, recovery rate by tone chart
- `/payments` — Full payments table, filterable by category/status
- `/payments/[id]` — Live agent-trace view: click any payment to watch it
  move through detect → diagnose → choose intervention → compliance gate →
  message → simulated response → promise tracking, stage by stage
- `/audit` — Every action blocked by the compliance gate, and why

## Config

The backend URL is set in `.env.local` (defaults to http://localhost:8000).
Change it there if your FastAPI server runs elsewhere.
