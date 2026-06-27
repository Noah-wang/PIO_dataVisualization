from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from pio_platform.config import PRIMARY_FILTER_ROLES
from pio_platform.i18n import role_label, t


@dataclass
class FilterState:
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None
    categorical_selections: dict[str, list[str | int | float]]


def render_filters(
    df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    lang: str,
) -> FilterState:
    categorical_selections: dict[str, list[str | int | float]] = {}
    date_range = None

    date_col = roles.get("date")
    if date_col and date_col in date_candidates:
        parsed = date_candidates[date_col].dropna()
        if not parsed.empty:
            min_date = parsed.min().to_pydatetime()
            max_date = parsed.max().to_pydatetime()
            date_values = st.date_input(
                t(lang, "date_range"),
                value=(min_date.date(), max_date.date()),
                min_value=min_date.date(),
                max_value=max_date.date(),
            )
            if isinstance(date_values, tuple) and len(date_values) == 2:
                date_range = tuple(pd.Timestamp(value) for value in date_values)  # type: ignore[assignment]

    rendered = set()
    for role in PRIMARY_FILTER_ROLES[1:]:
        column = roles.get(role)
        if column and column in df.columns:
            rendered.add(column)
            _render_categorical_filter(df, column, categorical_selections, label=role_label(role, lang), lang=lang)

    with st.expander(t(lang, "additional_dimensions"), expanded=False):
        extra_columns = [
            column
            for column in df.columns
            if column not in rendered
            and column != date_col
            and _is_reasonable_filter_column(df[column])
        ]
        for column in extra_columns[:8]:
            _render_categorical_filter(df, column, categorical_selections, label=column, lang=lang)

    return FilterState(date_range=date_range, categorical_selections=categorical_selections)


def apply_filters(
    df: pd.DataFrame,
    filter_state: FilterState,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
) -> pd.DataFrame:
    filtered = df.copy()
    date_col = roles.get("date")

    if filter_state.date_range and date_col and date_col in date_candidates:
        parsed = date_candidates[date_col]
        start, end = filter_state.date_range
        mask = parsed.between(start, end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1), inclusive="both")
        filtered = filtered.loc[mask.fillna(False)]

    for column, values in filter_state.categorical_selections.items():
        if values:
            filtered = filtered.loc[filtered[column].astype(str).isin(values)]

    return filtered


def _render_categorical_filter(
    df: pd.DataFrame,
    column: str,
    target: dict[str, list[str | int | float]],
    label: str,
    lang: str,
) -> None:
    series = df[column]
    options = sorted(series.dropna().astype(str).unique().tolist())
    selected = st.multiselect(label, options=options, placeholder=t(lang, "all_placeholder", label=label.lower()))
    if selected:
        target[column] = selected


def _is_reasonable_filter_column(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return False
    unique_count = series.dropna().nunique()
    return 1 < unique_count <= 40
