from __future__ import annotations

import json
import pickle
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from pio_platform.data_loader import DatasetBundle, list_workbook_sheets, load_dataset
from pio_platform.forecasting import (
    build_anomaly_center,
    build_forecast_narrative,
    build_monthly_part_series,
    build_watchlist,
    detect_series_anomalies,
    explain_latest_change,
    forecast_band,
    forecast_history,
    preprocess_history,
    select_best_model,
)
from pio_platform.pivot import build_pivot
from pio_platform.profiling import build_column_profile, build_insights, compute_kpis


# ── Role / group maps ─────────────────────────────────────────────────────────
ROLE_LABELS = {
    "date": "Time",
    "brand": "Brand",
    "model": "Vehicle model",
    "model_year": "Model year",
    "part_number": "Part number",
    "part_description": "Part description",
    "installation_quantity": "Installation quantity",
    "revenue": "Revenue",
}

SUPPORTING_FIELD_LABELS = {
    "PIS_MST_IVC_DT": "Invoice Date",
    "PIS_SERI": "Series",
    "YYYYMM": "Year-Month",
}

FIELD_GROUPS = {
    "date": "Time",
    "brand": "Vehicle",
    "model": "Vehicle",
    "model_year": "Vehicle",
    "part_number": "Part",
    "part_description": "Part",
    "installation_quantity": "Quantity",
    "revenue": "Revenue",
}

GROUP_ORDER = ["Time", "Vehicle", "Part", "Quantity", "Revenue", "Other"]

# ── Persistence constants ─────────────────────────────────────────────────────
MAX_WORKBOOKS = 20
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)
INDEX_FILE = OUTPUTS_DIR / "index.json"


# ── Session store ─────────────────────────────────────────────────────────────
@dataclass
class WorkbookSession:
    workbook_id: str
    filename: str
    file_bytes: bytes
    sheet_names: list[str]
    bundles: dict[str, DatasetBundle] = field(default_factory=dict)


WORKBOOKS: dict[str, WorkbookSession] = {}
# Values: "processing" | "ready" | "error"
WORKBOOK_STATUS: dict[str, str] = {}


# ── Index helpers ─────────────────────────────────────────────────────────────
def _load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(entries: list[dict]) -> None:
    INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _bundle_cache_path(workbook_id: str, sheet_name: str) -> Path:
    # Ensure sheet_name doesn't contain path traversal characters
    safe_name = "".join(c for c in sheet_name if c.isalnum() or c in ("-", "_")).rstrip()
    return OUTPUTS_DIR / f"{workbook_id}_{safe_name}_bundle.pkl"


def _add_to_index(workbook_id: str, filename: str, sheet_names: list[str]) -> None:
    entries = _load_index()
    # Remove duplicate
    entries = [e for e in entries if e["id"] != workbook_id]
    entries.insert(0, {
        "id": workbook_id,
        "filename": filename,
        "sheetNames": sheet_names,
        "defaultSheet": sheet_names[0] if sheet_names else None,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
    })
    # Evict oldest beyond MAX_WORKBOOKS
    old = entries[MAX_WORKBOOKS:]
    entries = entries[:MAX_WORKBOOKS]
    for entry in old:
        p = OUTPUTS_DIR / f"{entry['id']}.xlsx"
        if p.exists():
            p.unlink(missing_ok=True)
        # Clean up corresponding .pkl files
        for cache_file in OUTPUTS_DIR.glob(f"{entry['id']}_*_bundle.pkl"):
            cache_file.unlink(missing_ok=True)
    _save_index(entries)


# ── Background processing ─────────────────────────────────────────────────────
def _process_workbook_background(workbook_id: str) -> None:
    """Process the default sheet in a background thread."""
    try:
        session = WORKBOOKS.get(workbook_id)
        if not session:
            WORKBOOK_STATUS[workbook_id] = "error"
            return
        _get_bundle(session, session.sheet_names[0])
        WORKBOOK_STATUS[workbook_id] = "ready"
    except Exception:
        WORKBOOK_STATUS[workbook_id] = "error"


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="PIO Demand Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workbooks")
def list_workbooks() -> list[dict[str, Any]]:
    """Return the list of previously uploaded workbooks (from disk index)."""
    return _load_index()


@app.post("/api/workbooks/upload")
async def upload_workbook(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A workbook filename is required.")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported.")

    file_bytes = await file.read()
    sheet_names = list_workbook_sheets(file_bytes)
    if not sheet_names:
        raise HTTPException(status_code=400, detail="The uploaded workbook does not contain any sheets.")

    workbook_id = uuid4().hex

    # ── Phase 1: persist to disk and return immediately ───────────────────────
    (OUTPUTS_DIR / f"{workbook_id}.xlsx").write_bytes(file_bytes)
    _add_to_index(workbook_id, file.filename, sheet_names)

    session = WorkbookSession(
        workbook_id=workbook_id,
        filename=file.filename,
        file_bytes=file_bytes,
        sheet_names=sheet_names,
    )
    WORKBOOKS[workbook_id] = session
    WORKBOOK_STATUS[workbook_id] = "processing"

    # ── Phase 2: heavy processing in background thread ────────────────────────
    thread = threading.Thread(
        target=_process_workbook_background,
        args=(workbook_id,),
        daemon=True,
    )
    thread.start()

    return {
        "workbookId": workbook_id,
        "filename": file.filename,
        "sheetNames": sheet_names,
        "defaultSheet": sheet_names[0],
    }


@app.get("/api/workbooks/{workbook_id}/status")
def get_workbook_status(workbook_id: str) -> dict[str, Any]:
    """Poll processing status. Also restores sessions after backend restarts."""
    status = WORKBOOK_STATUS.get(workbook_id)
    session = WORKBOOKS.get(workbook_id)

    if status == "ready" and session:
        return {
            "status": "ready",
            "filename": session.filename,
            "sheetNames": session.sheet_names,
            "defaultSheet": session.sheet_names[0] if session.sheet_names else None,
        }

    # Not in memory — try to restore from disk
    entries = _load_index()
    entry = next((e for e in entries if e["id"] == workbook_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Workbook not found.")

    out_file = OUTPUTS_DIR / f"{workbook_id}.xlsx"
    if not out_file.exists():
        raise HTTPException(status_code=404, detail="Workbook file not found on disk.")

    default_sheet = entry.get("defaultSheet") or entry["sheetNames"][0]
    cache_p = _bundle_cache_path(workbook_id, default_sheet)

    # ── Option A: Load from pkl cache instantly if it exists ──────────────────
    if cache_p.exists():
        if not session:
            file_bytes = out_file.read_bytes()
            session = WorkbookSession(
                workbook_id=workbook_id,
                filename=entry["filename"],
                file_bytes=file_bytes,
                sheet_names=entry["sheetNames"],
            )
            WORKBOOKS[workbook_id] = session
        
        if default_sheet not in session.bundles:
            try:
                with open(cache_p, "rb") as f:
                    session.bundles[default_sheet] = pickle.load(f)
            except Exception:
                pass

        WORKBOOK_STATUS[workbook_id] = "ready"
        return {
            "status": "ready",
            "filename": entry["filename"],
            "sheetNames": entry["sheetNames"],
            "defaultSheet": default_sheet,
        }

    # ── Option B: Cache does not exist — compute in background ────────────────
    if not session:
        file_bytes = out_file.read_bytes()
        session = WorkbookSession(
            workbook_id=workbook_id,
            filename=entry["filename"],
            file_bytes=file_bytes,
            sheet_names=entry["sheetNames"],
        )
        WORKBOOKS[workbook_id] = session

    if status != "processing":
        WORKBOOK_STATUS[workbook_id] = "processing"
        thread = threading.Thread(
            target=_process_workbook_background,
            args=(workbook_id,),
            daemon=True,
        )
        thread.start()

    return {
        "status": "processing",
        "filename": entry["filename"],
        "sheetNames": entry["sheetNames"],
        "defaultSheet": default_sheet,
    }


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}")
def get_workspace(
    workbook_id: str,
    sheet_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    sort_field: str = Query(default=""),
    sort_order: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    return _build_workspace_payload(
        session,
        sheet_name,
        page=page,
        page_size=page_size,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        sort_field=sort_field,
        sort_order=sort_order,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/forecast")
def get_part_forecast(
    workbook_id: str,
    sheet_name: str,
    part_number: str = Query(default=""),
    horizon: int = Query(default=3, ge=1, le=12),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    return _build_forecast_payload(
        bundle=bundle,
        part_number=part_number,
        horizon=horizon,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/anomaly-center")
def get_anomaly_center(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    wholesale_bundle = _find_wholesale_bundle(session, exclude_sheet=sheet_name)
    return _build_anomaly_center_payload(
        bundle=bundle,
        wholesale_bundle=wholesale_bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/pivot")
def get_pivot(
    workbook_id: str,
    sheet_name: str,
    rows: list[str] = Query(default=[]),
    cols: list[str] = Query(default=[]),
    measure: str = Query(default="quantity"),
    agg: str = Query(default="sum"),
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
) -> dict[str, Any]:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )
    return build_pivot(
        filtered_df=filtered,
        roles=bundle.roles,
        date_candidates=bundle.date_candidates,
        row_fields=rows,
        col_fields=cols,
        measure=measure,
        agg=agg,
    )


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/export.csv")
def export_filtered_csv(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    visible_cols: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )

    if visible_cols:
        cols_to_export = [c for c in visible_cols.split(",") if c in filtered.columns]
        if cols_to_export:
            filtered = filtered[cols_to_export]

    output = StringIO()
    filtered.to_csv(output, index=False)
    output.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}.csv"'
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@app.get("/api/workbooks/{workbook_id}/sheets/{sheet_name}/export.xlsx")
def export_filtered_xlsx(
    workbook_id: str,
    sheet_name: str,
    search: str = Query(default=""),
    brand: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    model_year: list[str] = Query(default=[]),
    part: list[str] = Query(default=[]),
    model_query: str = Query(default=""),
    part_query: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    visible_cols: str = Query(default=""),
) -> StreamingResponse:
    session = _get_session(workbook_id)
    bundle = _get_bundle(session, sheet_name)
    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )

    if visible_cols:
        cols_to_export = [c for c in visible_cols.split(",") if c in filtered.columns]
        if cols_to_export:
            filtered = filtered[cols_to_export]

    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        filtered.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    output.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="{session.filename.rsplit(".", 1)[0]}-{sheet_name}.xlsx"'
    }
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )



@app.exception_handler(Exception)
def unhandled_exception(_: Any, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Session helpers ───────────────────────────────────────────────────────────
def _get_session(workbook_id: str) -> WorkbookSession:
    session = WORKBOOKS.get(workbook_id)
    if session:
        return session

    # Try restoring from disk (backend restart case)
    entries = _load_index()
    entry = next((e for e in entries if e["id"] == workbook_id), None)
    out_file = OUTPUTS_DIR / f"{workbook_id}.xlsx"
    if not entry or not out_file.exists():
        raise HTTPException(status_code=404, detail="Workbook session not found.")

    file_bytes = out_file.read_bytes()
    session = WorkbookSession(
        workbook_id=workbook_id,
        filename=entry["filename"],
        file_bytes=file_bytes,
        sheet_names=entry["sheetNames"],
    )
    WORKBOOKS[workbook_id] = session
    return session


def _get_bundle(session: WorkbookSession, sheet_name: str) -> DatasetBundle:
    if sheet_name not in session.sheet_names:
        raise HTTPException(status_code=404, detail="Sheet not found in workbook.")
    
    if sheet_name in session.bundles:
        return session.bundles[sheet_name]

    cache_p = _bundle_cache_path(session.workbook_id, sheet_name)
    if cache_p.exists():
        try:
            with open(cache_p, "rb") as f:
                bundle = pickle.load(f)
            session.bundles[sheet_name] = bundle
            return bundle
        except Exception:
            pass

    # No cache file — parse and infer
    bundle = load_dataset(session.file_bytes, sheet_name, header_mode="Auto detect")
    session.bundles[sheet_name] = bundle

    # Save to disk cache
    try:
        with open(cache_p, "wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass

    return bundle


def _build_workspace_payload(
    session: WorkbookSession,
    sheet_name: str,
    page: int,
    page_size: int,
    search: str = "",
    brand: list[str] | None = None,
    model: list[str] | None = None,
    model_year: list[str] | None = None,
    part: list[str] | None = None,
    model_query: str = "",
    part_query: str = "",
    sort_field: str = "",
    sort_order: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    bundle = _get_bundle(session, sheet_name)
    if bundle.dataframe.empty:
        raise HTTPException(status_code=400, detail="The selected worksheet does not contain a usable dataset.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand or [],
        model=model or [],
        model_year=model_year or [],
        part=part or [],
        model_query=model_query,
        part_query=part_query,
        start_date=start_date,
        end_date=end_date,
    )
    page_data = _build_table_page(
        bundle=bundle,
        filtered_df=filtered,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    return {
        "workbook": {
            "id": session.workbook_id,
            "filename": session.filename,
            "sheetNames": session.sheet_names,
        },
        "sheetName": sheet_name,
        "profile": bundle.profile,
        "roles": bundle.roles,
        "overview": _build_overview(session.filename, sheet_name, bundle, filtered),
        "table": page_data,
        "classification": _build_field_classification(bundle),
        "insights": _build_chart_payloads(bundle, filtered),
        "filters": {
            "search": search,
            "brand": brand or [],
            "model": model or [],
            "modelYear": model_year or [],
            "part": part or [],
            "modelQuery": model_query,
            "partQuery": part_query,
            "startDate": start_date,
            "endDate": end_date,
        },
        "filterOptions": _build_filter_options(
            bundle,
            search=search,
            brand=brand,
            model=model,
            model_year=model_year,
            part=part,
            model_query=model_query,
            part_query=part_query,
            start_date=start_date,
            end_date=end_date,
        ),
    }


def _get_column_profile(bundle: DatasetBundle) -> pd.DataFrame:
    if not hasattr(bundle, "_cached_column_profile"):
        bundle._cached_column_profile = build_column_profile(bundle.dataframe, bundle.date_candidates)
    return bundle._cached_column_profile


def _build_overview(
    filename: str,
    sheet_name: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
) -> dict[str, Any]:
    kpis = compute_kpis(filtered_df, bundle.roles)
    profile_df = _get_column_profile(bundle)
    health = {
        "dateFieldCount": len(bundle.date_fields),
        "numericFieldCount": len(bundle.numeric_fields),
        "categoryFieldCount": len(bundle.categorical_fields),
        "mappedRoleCount": len(bundle.roles),
        "highMissingFields": profile_df[profile_df["Missing %"] >= 20]["Column"].head(3).tolist(),
    }

    date_summary = _date_summary(bundle, filtered_df)
    summary = [
        f"{filename} / {sheet_name} has {bundle.profile['row_count']:,} rows across {bundle.profile['column_count']} columns.",
        date_summary,
        f"Detected {health['mappedRoleCount']} business-ready fields for planning workflows.",
    ]
    if health["highMissingFields"]:
        summary.append("Highest missing columns: " + ", ".join(health["highMissingFields"]))

    insights = build_insights(filtered_df, bundle.roles, bundle.date_candidates, "en")

    # Calculate Leaderboard Metrics
    leaders = {}
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")
    revenue_col = bundle.roles.get("revenue")
    qty_col = bundle.roles.get("installation_quantity")

    if brand_col and brand_col in filtered_df.columns:
        metric = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
        if metric:
            top_brand = filtered_df.groupby(brand_col)[metric].sum().sort_values(ascending=False)
            if not top_brand.empty:
                leaders["topBrand"] = {
                    "name": str(top_brand.index[0]),
                    "value": float(top_brand.iloc[0]),
                    "metric": "Revenue" if metric == revenue_col else "Quantity",
                }

    if model_col and model_col in filtered_df.columns:
        metric = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
        if metric:
            top_model = filtered_df.groupby(model_col)[metric].sum().sort_values(ascending=False)
            if not top_model.empty:
                leaders["topModel"] = {
                    "name": str(top_model.index[0]),
                    "value": float(top_model.iloc[0]),
                    "metric": "Revenue" if metric == revenue_col else "Quantity",
                }

    if part_col and part_col in filtered_df.columns:
        metric = qty_col if qty_col and qty_col in filtered_df.columns else revenue_col
        if metric:
            top_part = filtered_df.groupby(part_col)[metric].sum().sort_values(ascending=False)
            if not top_part.empty:
                leaders["topPart"] = {
                    "name": str(top_part.index[0]),
                    "value": float(top_part.iloc[0]),
                    "metric": "Quantity" if metric == qty_col else "Revenue",
                }

    # Calculate additional average/density metrics
    stats = {}
    total_rev = float(filtered_df[revenue_col].sum()) if revenue_col and revenue_col in filtered_df.columns else None
    total_qty = float(filtered_df[qty_col].sum()) if qty_col and qty_col in filtered_df.columns else None
    total_records = len(filtered_df)

    if total_rev is not None and total_qty is not None and total_qty > 0:
        stats["avgUnitPrice"] = total_rev / total_qty
    if total_qty is not None and total_records > 0:
        stats["avgQtyPerRow"] = total_qty / total_records
    if total_rev is not None and total_records > 0:
        stats["avgRevPerRow"] = total_rev / total_records

    # Overall file completeness (mean non-missing %)
    stats["completenessRate"] = float(100.0 - profile_df["Missing %"].mean())

    return {
        "datasetTitle": filename,
        "sheetName": sheet_name,
        "kpis": kpis,
        "summary": summary,
        "health": health,
        "autoInsights": insights,
        "leaders": leaders,
        "stats": stats,
    }


def _build_field_classification(bundle: DatasetBundle) -> dict[str, list[dict[str, Any]]]:
    inverse_roles = {column: role for role, column in bundle.roles.items()}
    profile_df = _get_column_profile(bundle)
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in GROUP_ORDER}


    for row in profile_df.to_dict("records"):
        column = row["Column"]
        role = inverse_roles.get(column)
        group = _resolve_group(column, role, bundle)
        confidence = "High" if role else "Medium" if group != "Other" else "Low"
        groups[group].append(
            {
                "column": column,
                "group": group,
                "detectedRole": ROLE_LABELS.get(role) if role else SUPPORTING_FIELD_LABELS.get(column, "Supporting field"),
                "confidence": confidence,
                "type": row["Type"],
                "missingPct": row["Missing %"],
                "uniqueCount": row["Unique"],
                "sampleValues": row["Sample Values"],
            }
        )

    return {group: groups[group] for group in GROUP_ORDER if groups[group]}


def _resolve_group(column: str, role: str | None, bundle: DatasetBundle) -> str:
    if role and role in FIELD_GROUPS:
        return FIELD_GROUPS[role]
    if column in bundle.date_fields:
        return "Time"
    if column in bundle.numeric_fields:
        return "Other"
    lowered = column.lower()
    if "model" in lowered or "brand" in lowered:
        return "Vehicle"
    if "part" in lowered or "desc" in lowered:
        return "Part"
    return "Other"


def _build_chart_payloads(bundle: DatasetBundle, filtered_df: pd.DataFrame) -> dict[str, Any]:
    charts: dict[str, Any] = {}
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    revenue_col = bundle.roles.get("revenue")
    model_col = bundle.roles.get("model")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")

    if date_col and date_col in bundle.date_candidates and qty_col and qty_col in filtered_df.columns:
        charts["monthlyInstallation"] = _monthly_chart(
            bundle.date_candidates[date_col].loc[filtered_df.index],
            filtered_df[qty_col],
            qty_col,
        )

    if date_col and date_col in bundle.date_candidates and revenue_col and revenue_col in filtered_df.columns:
        charts["monthlyRevenue"] = _monthly_chart(
            bundle.date_candidates[date_col].loc[filtered_df.index],
            filtered_df[revenue_col],
            revenue_col,
        )

    if model_col and revenue_col and model_col in filtered_df.columns and revenue_col in filtered_df.columns:
        top_models = (
            filtered_df.groupby(model_col, dropna=True)[revenue_col]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
        charts["topModels"] = {
            "title": "Top vehicle models by revenue",
            "labels": [str(index) for index in top_models.index.tolist()],
            "values": [float(value) for value in top_models.tolist()],
        }

    metric_col = revenue_col if revenue_col and revenue_col in filtered_df.columns else qty_col
    if part_col and metric_col and part_col in filtered_df.columns:
        top_parts = (
            filtered_df.groupby(part_col, dropna=True)[metric_col]
            .sum()
            .sort_values(ascending=False)
            .head(12)
        )
        charts["topParts"] = {
            "title": f"Top parts by {'revenue' if metric_col == revenue_col else 'installation quantity'}",
            "labels": [str(index) for index in top_parts.index.tolist()],
            "values": [float(value) for value in top_parts.tolist()],
        }

    return charts


def _monthly_chart(date_series: pd.Series, value_series: pd.Series, metric_name: str) -> dict[str, Any]:
    chart_df = pd.DataFrame(
        {"month": date_series.dt.to_period("M").dt.to_timestamp(), metric_name: value_series}
    )
    chart_df = chart_df.groupby("month", dropna=True)[metric_name].sum().reset_index()
    return {
        "title": metric_name,
        "labels": [value.strftime("%Y-%m") for value in chart_df["month"].tolist()],
        "values": [float(value) for value in chart_df[metric_name].tolist()],
    }


def _build_table_page(
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
    page: int,
    page_size: int,
    sort_field: str,
    sort_order: str,
) -> dict[str, Any]:
    working = filtered_df.copy()
    model_year_col = bundle.roles.get("model_year")
    if sort_field and sort_field in working.columns:
        ascending = sort_order not in {"descend", "desc"}
        if sort_field in bundle.date_fields:
            sorter = bundle.date_candidates[sort_field].loc[working.index]
            working = working.assign(__sorter=sorter).sort_values(
                by="__sorter", ascending=ascending, na_position="last", kind="mergesort"
            )
            working = working.drop(columns="__sorter")
        else:
            working = working.sort_values(by=sort_field, ascending=ascending, na_position="last", kind="mergesort")

    total_rows = len(working)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = working.iloc[start:end].copy()

    columns = []
    default_visible = []
    inverse_roles = {column: role for role, column in bundle.roles.items()}

    for column in working.columns:
        role = inverse_roles.get(column)
        columns.append(
            {
                "key": column,
                "title": column,
                "role": ROLE_LABELS.get(role) if role else SUPPORTING_FIELD_LABELS.get(column, ""),
                "type": "year" if column == model_year_col else "date" if column in bundle.date_fields else _dtype_name(working[column]),
            }
        )
        if role or len(default_visible) < 8:
            default_visible.append(column)

    rows = []
    for row_index, (_, row) in enumerate(page_df.iterrows()):
        serialized = {"id": start + row_index}
        for column in page_df.columns:
            parsed_date = None
            if column in bundle.date_candidates:
                parsed_date = bundle.date_candidates[column].loc[row.name]
            serialized[column] = _serialize_cell(
                row[column],
                date_fields=bundle.date_fields,
                column=column,
                parsed_date=parsed_date,
                model_year_col=model_year_col,
            )
        rows.append(serialized)

    return {
        "columns": columns,
        "rows": rows,
        "totalRows": total_rows,
        "page": page,
        "pageSize": page_size,
        "defaultVisibleColumns": default_visible,
    }


def _apply_filters(
    bundle: DatasetBundle,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    part: list[str],
    model_query: str,
    part_query: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    df = bundle.dataframe
    mask = pd.Series(True, index=df.index)

    date_col = bundle.roles.get("date")
    if date_col and date_col in bundle.date_candidates:
        parsed = bundle.date_candidates[date_col]
        if start_date:
            mask &= parsed >= pd.to_datetime(start_date, errors="coerce")
        if end_date:
            mask &= parsed <= pd.to_datetime(end_date, errors="coerce")

    brand_col = bundle.roles.get("brand")
    if brand and brand_col and brand_col in df.columns:
        mask &= df[brand_col].fillna("").astype(str).isin(brand)

    model_col = bundle.roles.get("model")
    if model and model_col and model_col in df.columns:
        mask &= df[model_col].fillna("").astype(str).isin(model)
    if model_query and model_col and model_col in df.columns:
        mask &= df[model_col].fillna("").astype(str).str.contains(model_query, case=False, regex=False)

    model_year_col = bundle.roles.get("model_year")
    if model_year and model_year_col and model_year_col in df.columns:
        year_series = _display_series_for_column(bundle, model_year_col)
        mask &= year_series.isin(model_year)

    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")
    if part and part_col and part_col in df.columns:
        mask &= df[part_col].fillna("").astype(str).isin(part)
    if part_query and part_col and part_col in df.columns:
        mask &= df[part_col].fillna("").astype(str).str.contains(part_query, case=False, regex=False)

    if search:
        search_columns = list(dict.fromkeys(
            [
                column
                for column in [
                    bundle.roles.get("brand"),
                    bundle.roles.get("model"),
                    bundle.roles.get("part_number"),
                    bundle.roles.get("part_description"),
                ]
                if column and column in df.columns
            ] + bundle.categorical_fields[:6]
        ))
        tokens = [token.strip().lower() for token in search.split() if token.strip()]
        if tokens and search_columns:
            combined = df[search_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            token_mask = pd.Series(True, index=df.index)
            for token in tokens:
                token_mask &= combined.str.contains(token, regex=False)
            mask &= token_mask

    return df.loc[mask].copy()


def _build_filter_options(
    bundle: DatasetBundle,
    search: str = "",
    brand: list[str] | None = None,
    model: list[str] | None = None,
    model_year: list[str] | None = None,
    part: list[str] | None = None,
    model_query: str = "",
    part_query: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    brand = brand or []
    model = model or []
    model_year = model_year or []
    part = part or []

    date_range = _filter_date_range(bundle)

    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    model_year_col = bundle.roles.get("model_year")
    part_col = bundle.roles.get("part_description") or bundle.roles.get("part_number")

    # 1. Brand options: apply all filters EXCEPT brand
    if brand_col and brand_col in bundle.dataframe.columns:
        df_for_brand = _apply_filters(
            bundle, search, brand=[], model=model, model_year=model_year, part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        brand_options = _build_value_options(df_for_brand[brand_col], limit=25)
    else:
        brand_options = []

    # 2. Model options: apply all filters EXCEPT model
    if model_col and model_col in bundle.dataframe.columns:
        df_for_model = _apply_filters(
            bundle, search, brand=brand, model=[], model_year=model_year, part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        model_options = _build_value_options(df_for_model[model_col], limit=80)
    else:
        model_options = []

    # 3. Model Year options: apply all filters EXCEPT model_year
    if model_year_col and model_year_col in bundle.dataframe.columns:
        df_for_my = _apply_filters(
            bundle, search, brand=brand, model=model, model_year=[], part=part,
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        model_year_options = _build_value_options(
            _display_series_for_column(bundle, model_year_col).loc[df_for_my.index],
            limit=20,
            sort_by_count=False,
        )
    else:
        model_year_options = []

    # 4. Part options: apply all filters EXCEPT part
    if part_col and part_col in bundle.dataframe.columns:
        df_for_part = _apply_filters(
            bundle, search, brand=brand, model=model, model_year=model_year, part=[],
            model_query=model_query, part_query=part_query, start_date=start_date, end_date=end_date
        )
        part_options = _build_value_options(df_for_part[part_col], limit=120)
    else:
        part_options = []

    return {
        "dateRange": date_range,
        "brand": brand_options,
        "model": model_options,
        "modelYear": model_year_options,
        "part": part_options,
    }


def _build_forecast_payload(
    bundle: DatasetBundle,
    part_number: str,
    horizon: int,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_number_col = bundle.roles.get("part_number")
    part_description_col = bundle.roles.get("part_description")

    if not date_col or date_col not in bundle.date_candidates:
        raise HTTPException(status_code=400, detail="Forecasting requires a reliable date field.")
    if not qty_col or qty_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Forecasting requires an installation quantity field.")
    if not part_number_col or part_number_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Forecasting requires a part number field.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=[],
        model_query="",
        part_query="",
        start_date=start_date,
        end_date=end_date,
    )
    if filtered.empty:
        raise HTTPException(status_code=400, detail="No rows remain after applying the selected forecast filters.")

    part_options = _build_part_number_options(
        filtered,
        part_number_col=part_number_col,
        qty_col=qty_col,
        description_col=part_description_col,
        limit=120,
    )
    if not part_options:
        raise HTTPException(status_code=400, detail="No part numbers are available for forecasting in the selected slice.")

    selected_part = part_number or part_options[0]["value"]
    part_series = build_monthly_part_series(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        part_value=selected_part,
    )
    if part_series.empty:
        raise HTTPException(status_code=404, detail="The selected part does not have a usable monthly history.")

    history = part_series["actual"].astype(float).tolist()
    model_name, candidate_scores, diagnostics = select_best_model(history)
    forecast_input, adjusted_points = preprocess_history(history, diagnostics.preprocessing)
    forecast_values = forecast_history(forecast_input, horizon=horizon, model_name=model_name)
    bands = forecast_band(history, forecast_values, diagnostics)
    narrative = build_forecast_narrative(history, forecast_values, diagnostics)
    anomalies = detect_series_anomalies(part_series)
    change_analysis = explain_latest_change(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        part_value=selected_part,
        brand_col=brand_col,
        model_col=model_col,
    )

    future_months = pd.date_range(part_series["month"].max() + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    forecast_rows = [
        {
            "month": month.strftime("%Y-%m"),
            "actual": None,
            "forecast": band["forecast"],
            "lower": band["lower"],
            "upper": band["upper"],
        }
        for month, band in zip(future_months, bands)
    ]
    history_rows = [
        {
            "month": month.strftime("%Y-%m"),
            "actual": float(actual),
            "forecast": None,
            "lower": None,
            "upper": None,
        }
        for month, actual in zip(part_series["month"], part_series["actual"])
    ]

    description = None
    if part_description_col and part_description_col in filtered.columns:
        desc_series = (
            filtered.loc[filtered[part_number_col].fillna("").astype(str) == selected_part, part_description_col]
            .dropna()
            .astype(str)
        )
        if not desc_series.empty:
            description = desc_series.mode().iloc[0]

    recent_avg = float(pd.Series(history[-3:]).mean()) if history else 0.0
    latest_actual = float(history[-1]) if history else 0.0
    next_forecast = float(forecast_values[0]) if forecast_values else 0.0
    delta_pct = ((next_forecast - latest_actual) / latest_actual * 100) if latest_actual else None

    return {
        "selectedPart": selected_part,
        "partDescription": description,
        "partOptions": part_options,
        "summary": {
            "historyMonths": diagnostics.history_months,
            "horizon": horizon,
            "modelName": diagnostics.model_name,
            "confidence": diagnostics.confidence,
            "preprocessing": diagnostics.preprocessing,
            "selectionBasis": diagnostics.selection_basis,
            "adjustedMonths": adjusted_points,
            "candidateScores": candidate_scores,
            "latestActual": latest_actual,
            "recent3MonthAverage": recent_avg,
            "nextForecast": next_forecast,
            "deltaPct": float(delta_pct) if delta_pct is not None else None,
            "mae": diagnostics.mae,
            "wape": diagnostics.wape,
            "bias": diagnostics.bias,
        },
        "series": history_rows + forecast_rows,
        "insights": narrative,
        "anomalies": anomalies,
        "changeAnalysis": change_analysis,
        "watchlist": build_watchlist(
            filtered,
            part_col=part_number_col,
            qty_col=qty_col,
            date_series=bundle.date_candidates[date_col],
            limit=8,
        ),
    }


def _build_anomaly_center_payload(
    bundle: DatasetBundle,
    wholesale_bundle: DatasetBundle | None,
    search: str,
    brand: list[str],
    model: list[str],
    model_year: list[str],
    part: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    date_col = bundle.roles.get("date")
    qty_col = bundle.roles.get("installation_quantity")
    brand_col = bundle.roles.get("brand")
    model_col = bundle.roles.get("model")
    part_number_col = bundle.roles.get("part_number")
    part_description_col = bundle.roles.get("part_description")

    if not date_col or date_col not in bundle.date_candidates:
        raise HTTPException(status_code=400, detail="Anomaly Center requires a reliable date field.")
    if not qty_col or qty_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Anomaly Center requires an installation quantity field.")
    if not part_number_col or part_number_col not in bundle.dataframe.columns:
        raise HTTPException(status_code=400, detail="Anomaly Center requires a part number field.")

    filtered = _apply_filters(
        bundle,
        search=search,
        brand=brand,
        model=model,
        model_year=model_year,
        part=part,
        model_query="",
        part_query="",
        start_date=start_date,
        end_date=end_date,
    )
    if filtered.empty:
        raise HTTPException(status_code=400, detail="No rows remain after applying the selected anomaly filters.")

    anomaly_center = build_anomaly_center(
        filtered,
        part_col=part_number_col,
        qty_col=qty_col,
        date_series=bundle.date_candidates[date_col],
        brand_col=brand_col,
        model_col=model_col,
        part_description_col=part_description_col,
        wholesale_df=wholesale_bundle.dataframe if wholesale_bundle else None,
        limit=12,
    )
    anomaly_center["filters"] = {
        "search": search,
        "brand": brand,
        "model": model,
        "modelYear": model_year,
        "part": part,
        "startDate": start_date,
        "endDate": end_date,
    }
    return anomaly_center


def _find_wholesale_bundle(session: WorkbookSession, exclude_sheet: str | None = None) -> DatasetBundle | None:
    for candidate in session.sheet_names:
        if exclude_sheet and candidate == exclude_sheet:
            continue
        if "wholesale" in candidate.lower():
            try:
                return _get_bundle(session, candidate)
            except Exception:
                return None
    return None


def _build_part_number_options(
    df: pd.DataFrame,
    part_number_col: str,
    qty_col: str,
    description_col: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    working = df.copy()
    working["__part"] = working[part_number_col].fillna("").astype(str)
    working["__qty"] = pd.to_numeric(working[qty_col], errors="coerce").fillna(0.0)
    working = working[working["__part"] != ""]
    if working.empty:
        return []

    grouped = (
        working.groupby("__part", dropna=True)
        .agg(count=("__part", "size"), quantity=("__qty", "sum"))
        .sort_values(by=["quantity", "count"], ascending=False)
        .head(limit)
        .reset_index()
    )

    descriptions: dict[str, str] = {}
    if description_col and description_col in working.columns:
        desc_df = working[[part_number_col, description_col]].dropna().copy()
        if not desc_df.empty:
            desc_df[part_number_col] = desc_df[part_number_col].astype(str)
            descriptions = (
                desc_df.groupby(part_number_col)[description_col]
                .agg(lambda values: values.astype(str).mode().iloc[0])
                .to_dict()
            )

    options = []
    for row in grouped.to_dict("records"):
        part_value = row["__part"]
        description = descriptions.get(part_value)
        label = f"{part_value} · {description}" if description else part_value
        options.append(
            {
                "label": label,
                "value": part_value,
                "description": description,
                "count": int(row["count"]),
                "quantity": float(row["quantity"]),
            }
        )
    return options



def _filter_date_range(bundle: DatasetBundle) -> dict[str, str | None]:
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return {"min": None, "max": None}
    parsed = bundle.date_candidates[date_col].dropna()
    if parsed.empty:
        return {"min": None, "max": None}
    return {
        "min": parsed.min().strftime("%Y-%m-%d"),
        "max": parsed.max().strftime("%Y-%m-%d"),
    }


def _build_value_options(
    series: pd.Series,
    limit: int,
    sort_by_count: bool = True,
) -> list[dict[str, Any]]:
    clean = series.dropna().astype(str)
    clean = clean[clean.str.strip() != ""]
    if clean.empty:
        return []
    counts = clean.value_counts()
    if sort_by_count:
        counts = counts.head(limit)
    else:
        counts = counts.sort_index().head(limit)
    return [
        {"label": value, "value": value, "count": int(count)}
        for value, count in counts.items()
    ]


def _display_series_for_column(bundle: DatasetBundle, column: str) -> pd.Series:
    if column == bundle.roles.get("model_year") and column in bundle.date_candidates:
        return bundle.date_candidates[column].dt.year.astype("Int64").astype(str)
    return bundle.dataframe[column].fillna("").astype(str)


def _date_summary(bundle: DatasetBundle, filtered_df: pd.DataFrame) -> str:
    date_col = bundle.roles.get("date")
    if not date_col or date_col not in bundle.date_candidates:
        return "No reliable date coverage was detected for this worksheet."
    parsed = bundle.date_candidates[date_col].loc[filtered_df.index].dropna()
    if parsed.empty:
        return "No rows remain inside the current date filters."
    return (
        f"Coverage runs from {parsed.min().strftime('%Y-%m-%d')} to {parsed.max().strftime('%Y-%m-%d')} "
        f"across {parsed.dt.to_period('M').nunique()} active months."
    )


def _dtype_name(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    return "text"


def _serialize_cell(
    value: Any,
    date_fields: list[str],
    column: str,
    parsed_date: Any = None,
    model_year_col: str | None = None,
) -> Any:
    if pd.isna(value):
        return None
    if model_year_col and column == model_year_col:
        if parsed_date is not None and pd.notna(parsed_date):
            return int(pd.to_datetime(parsed_date).year)
        if isinstance(value, (int, float)):
            return int(value)
        return str(value)
    if column in date_fields:
        parsed = pd.to_datetime(parsed_date if parsed_date is not None else value, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)
