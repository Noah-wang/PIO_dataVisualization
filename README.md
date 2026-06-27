# PIO Demand Intelligence Platform

V1 web product for automotive parts planning teams.

This version replaces the Streamlit-first MVP with a dedicated web workspace:

- `frontend/`: Next.js + React + Ant Design
- `backend/`: FastAPI + Pandas Excel parsing
- `pio_platform/`: reusable workbook profiling and field-detection logic

## What V1 does

- Upload `.xlsx` and `.xls` workbooks
- Select a worksheet from the uploaded workbook
- Auto-detect table headers from business-style Excel exports
- Present a polished landing page that flows into a tabbed workspace
- Show an `Overview` tab with KPI cards, data health, and auto insights
- Show a `Data Table` tab with server-side pagination for large sheets
- Show a `Field Classification` tab that groups fields into:
  - Time
  - Vehicle
  - Part
  - Quantity
  - Revenue
  - Other
- Show a `Basic Insights` tab with default trend and ranking charts
- Export the filtered slice as CSV

The sample `PIO_Sales_Data` sheet used during testing contains about `199,000` rows, so table browsing is implemented with backend pagination instead of loading the full dataset into the browser.

## Run locally

### 1. Python API

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 --port 3000
```

Then open:

```text
http://127.0.0.1:3000
```

## Main files

- [backend/app/main.py](/Users/noahwang/Documents/Codex/2026-06-26/build-a-polished-web-based-product/backend/app/main.py)
- [frontend/src/app/page.tsx](/Users/noahwang/Documents/Codex/2026-06-26/build-a-polished-web-based-product/frontend/src/app/page.tsx)
- [frontend/src/app/globals.css](/Users/noahwang/Documents/Codex/2026-06-26/build-a-polished-web-based-product/frontend/src/app/globals.css)
- [pio_platform/data_loader.py](/Users/noahwang/Documents/Codex/2026-06-26/build-a-polished-web-based-product/pio_platform/data_loader.py)
- [pio_platform/profiling.py](/Users/noahwang/Documents/Codex/2026-06-26/build-a-polished-web-based-product/pio_platform/profiling.py)

## Next planned modules

- Sales anomaly detection
- Driver analysis for rises and declines by part / model / month
- Forecast Center for next month and next year demand
- Penetration analysis against vehicle wholesale data
- Inventory recommendation workflows
