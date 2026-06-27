from __future__ import annotations

from typing import Any

import pandas as pd

from pio_platform.i18n import t


def build_column_profile(df: pd.DataFrame, date_candidates: dict[str, pd.Series]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total_rows = max(len(df), 1)

    for column in df.columns:
        series = df[column]
        missing = int(series.isna().sum())
        non_null = series.dropna()
        dtype = "date" if column in date_candidates else _describe_dtype(series)
        unique_count = int(non_null.nunique()) if not non_null.empty else 0
        sample_values = ", ".join(non_null.astype(str).head(3).tolist())

        rows.append(
            {
                "Column": column,
                "Type": dtype,
                "Missing": missing,
                "Missing %": round((missing / total_rows) * 100, 1),
                "Unique": unique_count,
                "Sample Values": sample_values,
            }
        )

    profile_df = pd.DataFrame(rows)
    if not profile_df.empty:
        profile_df = profile_df.sort_values(by=["Type", "Missing %", "Column"], ascending=[True, False, True])
    return profile_df


def compute_kpis(df: pd.DataFrame, roles: dict[str, str]) -> dict[str, Any]:
    install_col = roles.get("installation_quantity")
    revenue_col = roles.get("revenue")
    part_col = roles.get("part_number") or roles.get("part_description")

    return {
        "Total Records": len(df),
        "Total Installation Quantity": _safe_sum(df, install_col),
        "Total Sales Revenue": _safe_sum(df, revenue_col),
        "Distinct Part Count": int(df[part_col].nunique()) if part_col and part_col in df.columns else None,
    }


def build_insights(
    df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    lang: str,
) -> list[str]:
    insights: list[str] = []
    if df.empty:
        return [t(lang, "insight_no_rows")]

    date_col = roles.get("date")
    revenue_col = roles.get("revenue")
    qty_col = roles.get("installation_quantity")
    model_col = roles.get("model")
    part_col = roles.get("part_description") or roles.get("part_number")

    if date_col and date_col in date_candidates:
        parsed = date_candidates[date_col].loc[df.index].dropna()
        if not parsed.empty:
            insights.append(
                t(
                    lang,
                    "insight_date_coverage",
                    start=parsed.min().date(),
                    end=parsed.max().date(),
                    months=parsed.dt.to_period("M").nunique(),
                )
            )

    if model_col and revenue_col and model_col in df.columns and revenue_col in df.columns:
        top_model = df.groupby(model_col, dropna=True)[revenue_col].sum().sort_values(ascending=False).head(1)
        if not top_model.empty:
            insights.append(
                t(
                    lang,
                    "insight_top_model",
                    model=top_model.index[0],
                    value=_format_number(top_model.iloc[0], currency=True),
                )
            )

    if part_col and qty_col and part_col in df.columns and qty_col in df.columns:
        top_part = df.groupby(part_col, dropna=True)[qty_col].sum().sort_values(ascending=False).head(1)
        if not top_part.empty:
            insights.append(
                t(
                    lang,
                    "insight_top_part",
                    part=top_part.index[0],
                    value=_format_number(top_part.iloc[0]),
                )
            )

    if qty_col and qty_col in df.columns:
        positive_share = (df[qty_col].fillna(0) > 0).mean()
        insights.append(t(lang, "insight_positive_share", share=f"{positive_share:.0%}"))

    return insights[:4]


def _describe_dtype(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    return "category"


def _safe_sum(df: pd.DataFrame, column: str | None) -> float | None:
    if not column or column not in df.columns:
        return None
    return float(df[column].fillna(0).sum())


def _format_number(value: float | int | None, currency: bool = False) -> str:
    if value is None:
        return "N/A"
    if currency:
        return f"${value:,.0f}"
    return f"{value:,.0f}"
