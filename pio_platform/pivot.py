"""Server-side pivot-table aggregation.

Turns the flat PIO sales table into a cross-tab the way a planner would build
one in Excel: drag dimensions onto rows and columns, pick a measure, and read
the aggregated grid. All work happens server-side so the browser never needs
the full dataset (consistent with the rest of the platform).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

ROW_KEY = "__pio_rowkey"
COL_KEY = "__pio_colkey"
VAL_KEY = "__pio_value"

MAX_ROW_KEYS = 2000
MAX_COL_KEYS = 200

AGG_FUNCS = {"sum", "avg", "count"}


@dataclass
class Dimension:
    key: str
    label: str


@dataclass
class Measure:
    key: str
    label: str


def _month_series(parsed: pd.Series) -> pd.Series:
    return parsed.dt.to_period("M").astype(str).where(parsed.notna(), "")


def _year_series(parsed: pd.Series) -> pd.Series:
    return parsed.dt.year.astype("Int64").astype(str).where(parsed.notna(), "")


def available_dimensions(roles: dict[str, str], date_candidates: dict[str, pd.Series]) -> list[Dimension]:
    """List of dimensions a user can drag onto rows/columns for this sheet."""
    dims: list[Dimension] = []
    if roles.get("brand"):
        dims.append(Dimension("brand", "Brand"))
    if roles.get("model"):
        dims.append(Dimension("model", "Model"))
    if roles.get("model_year"):
        dims.append(Dimension("model_year", "Model year"))
    if roles.get("part_description") or roles.get("part_number"):
        dims.append(Dimension("part", "Part"))
    date_col = roles.get("date")
    if date_col and date_col in date_candidates:
        dims.append(Dimension("month", "Month"))
        dims.append(Dimension("year", "Year"))
    return dims


def available_measures(roles: dict[str, str]) -> list[Measure]:
    measures: list[Measure] = []
    if roles.get("installation_quantity"):
        measures.append(Measure("quantity", "Installation quantity"))
    if roles.get("revenue"):
        measures.append(Measure("revenue", "Sales revenue"))
    measures.append(Measure("records", "Record count"))
    return measures


def _dimension_series(
    df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    key: str,
) -> pd.Series | None:
    if key == "brand" and roles.get("brand") in df.columns:
        return df[roles["brand"]].fillna("").astype(str)
    if key == "model" and roles.get("model") in df.columns:
        return df[roles["model"]].fillna("").astype(str)
    if key == "model_year":
        col = roles.get("model_year")
        if col and col in date_candidates:
            return _year_series(date_candidates[col].loc[df.index])
        if col and col in df.columns:
            return df[col].fillna("").astype(str)
        return None
    if key == "part":
        col = roles.get("part_description") or roles.get("part_number")
        if col and col in df.columns:
            return df[col].fillna("").astype(str)
        return None
    if key in ("month", "year"):
        date_col = roles.get("date")
        if not date_col or date_col not in date_candidates:
            return None
        parsed = date_candidates[date_col].loc[df.index]
        return _month_series(parsed) if key == "month" else _year_series(parsed)
    return None


def _measure_series(df: pd.DataFrame, roles: dict[str, str], measure: str) -> pd.Series:
    if measure == "revenue" and roles.get("revenue") in df.columns:
        return pd.to_numeric(df[roles["revenue"]], errors="coerce").fillna(0.0)
    if measure == "quantity" and roles.get("installation_quantity") in df.columns:
        return pd.to_numeric(df[roles["installation_quantity"]], errors="coerce").fillna(0.0)
    # "records" or fallback: count every row as 1
    return pd.Series(1.0, index=df.index)


def _composite_key(df: pd.DataFrame, roles, date_candidates, fields: list[str]) -> pd.Series | None:
    parts: list[pd.Series] = []
    for field in fields:
        series = _dimension_series(df, roles, date_candidates, field)
        if series is None:
            return None
        parts.append(series.astype(str).replace("", "—"))
    if not parts:
        return pd.Series("Total", index=df.index)
    combined = parts[0]
    for extra in parts[1:]:
        combined = combined.str.cat(extra, sep=" / ")
    return combined


def build_pivot(
    filtered_df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    row_fields: list[str],
    col_fields: list[str],
    measure: str,
    agg: str,
) -> dict[str, Any]:
    """Build a cross-tab payload from an already-filtered dataframe."""
    dims = available_dimensions(roles, date_candidates)
    valid_dim_keys = {dim.key for dim in dims}
    measures = available_measures(roles)
    valid_measure_keys = {m.key for m in measures}

    row_fields = [f for f in row_fields if f in valid_dim_keys]
    col_fields = [f for f in col_fields if f in valid_dim_keys]
    if measure not in valid_measure_keys:
        measure = measures[0].key if measures else "records"
    if agg not in AGG_FUNCS:
        agg = "sum"
    if measure == "records":
        agg = "count"

    base = {
        "rowFields": row_fields,
        "colFields": col_fields,
        "measure": measure,
        "agg": agg,
        "availableDimensions": [{"key": d.key, "label": d.label} for d in dims],
        "availableMeasures": [{"key": m.key, "label": m.label} for m in measures],
        "rowKeys": [],
        "colKeys": [],
        "cells": {},
        "rowTotals": {},
        "colTotals": {},
        "grandTotal": 0.0,
        "rowCount": 0,
        "colCount": 0,
        "truncated": False,
        "measureUnit": "currency" if measure == "revenue" else "number",
    }

    if filtered_df.empty or (not row_fields and not col_fields):
        return base

    row_key = _composite_key(filtered_df, roles, date_candidates, row_fields)
    col_key = _composite_key(filtered_df, roles, date_candidates, col_fields)
    if row_key is None or col_key is None:
        return base

    work = pd.DataFrame(
        {
            ROW_KEY: row_key.values,
            COL_KEY: col_key.values,
            VAL_KEY: _measure_series(filtered_df, roles, measure).values,
        }
    )

    pandas_agg = {"sum": "sum", "avg": "mean", "count": "count"}[agg]

    grid = work.groupby([ROW_KEY, COL_KEY])[VAL_KEY].agg(pandas_agg)
    row_totals = work.groupby(ROW_KEY)[VAL_KEY].agg(pandas_agg)
    col_totals = work.groupby(COL_KEY)[VAL_KEY].agg(pandas_agg)
    grand_total = float(work[VAL_KEY].agg(pandas_agg))

    # Order keys by their total contribution (most important first), descending.
    row_keys = row_totals.sort_values(ascending=False).index.tolist()
    col_keys = col_totals.sort_values(ascending=False).index.tolist()

    truncated = False
    if len(row_keys) > MAX_ROW_KEYS:
        row_keys = row_keys[:MAX_ROW_KEYS]
        truncated = True
    if len(col_keys) > MAX_COL_KEYS:
        col_keys = col_keys[:MAX_COL_KEYS]
        truncated = True

    row_set = set(row_keys)
    col_set = set(col_keys)
    cells: dict[str, dict[str, float]] = {}
    for (rk, ck), value in grid.items():
        if rk not in row_set or ck not in col_set:
            continue
        cells.setdefault(str(rk), {})[str(ck)] = round(float(value), 2)

    base.update(
        {
            "rowKeys": [str(k) for k in row_keys],
            "colKeys": [str(k) for k in col_keys],
            "cells": cells,
            "rowTotals": {str(k): round(float(row_totals[k]), 2) for k in row_keys},
            "colTotals": {str(k): round(float(col_totals[k]), 2) for k in col_keys},
            "grandTotal": round(grand_total, 2),
            "rowCount": len(row_keys),
            "colCount": len(col_keys),
            "truncated": truncated,
        }
    )
    return base
