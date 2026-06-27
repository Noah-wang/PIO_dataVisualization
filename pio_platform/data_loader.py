from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Any

import pandas as pd

from pio_platform.config import ROLE_PATTERNS


@dataclass
class DatasetBundle:
    dataframe: pd.DataFrame
    profile: dict[str, Any]
    roles: dict[str, str]
    date_candidates: dict[str, pd.Series]
    numeric_fields: list[str]
    categorical_fields: list[str]
    date_fields: list[str]


def list_workbook_sheets(file_bytes: bytes) -> list[str]:
    return pd.ExcelFile(BytesIO(file_bytes)).sheet_names


def load_dataset(
    file_bytes: bytes,
    sheet_name: str,
    header_mode: str = "Auto detect",
    header_row: int = 1,
    header_depth: int = 1,
) -> DatasetBundle:
    raw_df = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)
    raw_df = raw_df.dropna(axis=1, how="all")
    raw_df = raw_df.dropna(axis=0, how="all")

    if raw_df.empty:
        empty_df = pd.DataFrame()
        return DatasetBundle(
            dataframe=empty_df,
            profile={"header_row": 1, "header_depth": 1, "row_count": 0, "column_count": 0},
            roles={},
            date_candidates={},
            numeric_fields=[],
            categorical_fields=[],
            date_fields=[],
        )

    if header_mode == "Auto detect":
        header_row_index, resolved_depth = detect_header_config(raw_df)
    else:
        header_row_index = max(header_row - 1, 0)
        resolved_depth = max(header_depth, 1)

    dataset = materialize_dataset(raw_df, header_row_index, resolved_depth)
    roles, date_candidates = infer_roles(dataset)
    numeric_fields = dataset.select_dtypes(include="number").columns.tolist()
    categorical_fields = [
        column
        for column in dataset.columns
        if dataset[column].dtype == "object" or str(dataset[column].dtype).startswith("string")
    ]
    date_fields = list(date_candidates.keys())

    return DatasetBundle(
        dataframe=dataset,
        profile={
            "header_row": header_row_index + 1,
            "header_depth": resolved_depth,
            "row_count": int(len(dataset)),
            "column_count": int(dataset.shape[1]),
        },
        roles=roles,
        date_candidates=date_candidates,
        numeric_fields=numeric_fields,
        categorical_fields=categorical_fields,
        date_fields=date_fields,
    )


def detect_header_config(raw_df: pd.DataFrame, max_scan_rows: int = 8) -> tuple[int, int]:
    best_score = float("-inf")
    best_config = (0, 1)
    limit = min(len(raw_df), max_scan_rows)

    for row_index in range(limit):
        for depth in (1, 2, 3):
            if row_index + depth >= len(raw_df):
                continue
            candidate = materialize_dataset(raw_df, row_index, depth)
            if candidate.empty:
                continue
            score = _score_candidate(candidate, row_index, depth)
            if score > best_score:
                best_score = score
                best_config = (row_index, depth)

    return best_config


def materialize_dataset(raw_df: pd.DataFrame, header_row_index: int, header_depth: int) -> pd.DataFrame:
    header_block = raw_df.iloc[header_row_index : header_row_index + header_depth].copy()
    data_block = raw_df.iloc[header_row_index + header_depth :].copy()

    if header_depth > 1:
        header_block = header_block.ffill(axis=1)

    data_block = data_block.dropna(axis=1, how="all")
    header_block = header_block[data_block.columns]
    columns = build_columns(header_block)

    dataset = data_block.copy()
    dataset.columns = columns
    dataset = dataset.dropna(axis=0, how="all")
    dataset = dataset.loc[:, ~dataset.columns.str.fullmatch(r"unnamed(?: \d+)?", na=False)]
    dataset.columns = deduplicate_columns(dataset.columns.tolist())
    dataset = dataset.reset_index(drop=True)

    object_columns = dataset.select_dtypes(include="object").columns
    if len(object_columns) > 0:
        dataset[object_columns] = dataset[object_columns].apply(lambda s: s.map(_clean_cell_value))
        for column in object_columns:
            parsed_dates = parse_date_series(dataset[column])
            if parsed_dates.notna().mean() >= 0.75 and _has_date_hint(column):
                dataset[column] = parsed_dates
                continue
            numeric_candidate = pd.to_numeric(dataset[column], errors="coerce")
            if numeric_candidate.notna().mean() >= 0.95 or (
                numeric_candidate.notna().mean() >= 0.5 and _has_numeric_hint(column)
            ):
                dataset[column] = numeric_candidate

    return dataset


def build_columns(header_block: pd.DataFrame) -> list[str]:
    values_by_row = []
    for row_number, (_, row) in enumerate(header_block.iterrows()):
        values = [_normalize_label(value) for value in row.tolist()]
        if row_number < len(header_block.index) - 1:
            values = _ffill_labels(values)
        values_by_row.append(values)

    columns: list[str] = []
    for column_index in range(header_block.shape[1]):
        parts: list[str] = []
        for row_values in values_by_row:
            value = row_values[column_index]
            if not value:
                continue
            if value.startswith("Unnamed"):
                continue
            if parts and parts[-1] == value:
                continue
            parts.append(value)
        if parts and len(parts) > 1 and all(part == parts[0] for part in parts[:-1]):
            parts = parts[-1:]
        columns.append(" | ".join(parts).strip() or f"Unnamed {column_index + 1}")

    prefix = _shared_prefix(columns)
    if prefix:
        columns = [column[len(prefix) :].strip(" |") if column.startswith(prefix) else column for column in columns]
    majority_prefix = _majority_prefix(columns)
    if majority_prefix:
        columns = [
            column[len(majority_prefix) :].strip(" |") if column.startswith(majority_prefix) else column
            for column in columns
        ]

    return columns


def deduplicate_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    resolved: list[str] = []
    for column in columns:
        base = column or "Unnamed"
        counter = seen.get(base, 0)
        if counter == 0:
            resolved.append(base)
        else:
            resolved.append(f"{base} ({counter + 1})")
        seen[base] = counter + 1
    return resolved


def infer_roles(df: pd.DataFrame) -> tuple[dict[str, str], dict[str, pd.Series]]:
    roles: dict[str, str] = {}
    date_candidates: dict[str, pd.Series] = {}

    for column in df.columns:
        parsed = parse_date_series(df[column])
        if parsed.notna().mean() >= 0.75 and parsed.nunique(dropna=True) > 1 and _is_date_candidate(column, parsed):
            date_candidates[column] = parsed

    for role, patterns in ROLE_PATTERNS.items():
        best_match = None
        best_score = 0
        for column in df.columns:
            normalized = _to_token_string(column)
            score = _match_role_score(normalized, patterns)
            if role == "date" and column in date_candidates:
                score += 2
                if pd.api.types.is_datetime64_any_dtype(df[column]):
                    score += 2
            if role in {"installation_quantity", "revenue"} and score > 0 and pd.api.types.is_numeric_dtype(df[column]):
                score += 1
            if score > best_score:
                best_score = score
                best_match = column

        if best_match and best_score > 0:
            roles[role] = best_match

    if "date" not in roles and date_candidates:
        roles["date"] = next(iter(date_candidates.keys()))

    return roles, date_candidates


def parse_date_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    numeric_like = pd.to_numeric(non_null, errors="coerce")
    numeric_ratio = numeric_like.notna().mean()

    if numeric_ratio >= 0.9:
        sample = numeric_like.dropna().astype("int64").astype(str).head(10)
        lengths = {len(value) for value in sample}
        if lengths == {6}:
            numeric_series = pd.to_numeric(series, errors="coerce")
            return pd.to_datetime(
                numeric_series.map(lambda value: f"{int(value):06d}" if pd.notna(value) else None),
                format="%Y%m",
                errors="coerce",
            )
        if lengths == {8}:
            numeric_series = pd.to_numeric(series, errors="coerce")
            return pd.to_datetime(
                numeric_series.map(lambda value: f"{int(value):08d}" if pd.notna(value) else None),
                format="%Y%m%d",
                errors="coerce",
            )
        if lengths == {4}:
            numeric_series = pd.to_numeric(series, errors="coerce")
            plausible_years = numeric_series.dropna().between(1900, 2100).mean() >= 0.9
            if plausible_years:
                return pd.to_datetime(
                    numeric_series.map(lambda value: f"{int(value):04d}-01-01" if pd.notna(value) else None),
                    format="%Y-%m-%d",
                    errors="coerce",
                )
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    if non_null.astype(str).str.contains(r"[-/]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", case=False, regex=True).mean() < 0.6:
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    return pd.to_datetime(series, errors="coerce")


def _score_candidate(df: pd.DataFrame, row_index: int, depth: int) -> float:
    if df.empty:
        return float("-inf")

    column_count = len(df.columns)
    informative_columns = sum(1 for column in df.columns if not column.lower().startswith("unnamed"))
    unique_ratio = len(set(df.columns)) / max(column_count, 1)
    informative_ratio = informative_columns / max(column_count, 1)
    numeric_header_ratio = sum(1 for column in df.columns if _looks_like_value_header(column)) / max(column_count, 1)
    first_row_non_null = df.head(10).notna().mean().mean()
    numeric_density = pd.to_numeric(df.head(5).stack(), errors="coerce").notna().mean()
    headerish_tokens = {
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "model",
        "brand",
        "total",
    }
    first_row_tokens = df.head(1).astype(str).apply(lambda s: s.str.lower().str.strip()).iloc[0]
    headerish_ratio = first_row_tokens.isin(headerish_tokens).mean()

    score = (
        informative_ratio * 4
        + unique_ratio * 3
        + first_row_non_null * 2
        + numeric_density * 2
        - headerish_ratio * 3
        - numeric_header_ratio * 5
        - row_index * 0.05
        - abs(depth - 1) * 0.05
    )
    return score


def _normalize_label(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _ffill_labels(values: list[str]) -> list[str]:
    filled: list[str] = []
    active = ""
    for value in values:
        if value:
            active = value
            filled.append(value)
        else:
            filled.append(active)
    return filled


def _clean_cell_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _to_token_string(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.replace("|", " ")
    normalized = re.sub(r"[_\-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _match_role_score(normalized_column: str, patterns: list[str]) -> int:
    score = 0
    for pattern in patterns:
        if normalized_column == pattern:
            score += 4
        elif normalized_column.endswith(pattern):
            score += 2
        elif pattern in normalized_column:
            score += 1
    return score


def _is_date_candidate(column: str, parsed: pd.Series) -> bool:
    normalized = _to_token_string(column)
    hinted = _has_date_hint(column)
    monthly_variation = parsed.dt.to_period("M").nunique() > 2
    daily_variation = parsed.dt.day.nunique() > 1
    return hinted or monthly_variation or daily_variation


def _shared_prefix(columns: list[str]) -> str:
    split_columns = [column.split(" | ") for column in columns if column]
    if not split_columns:
        return ""
    prefix_parts: list[str] = []
    for items in zip(*split_columns, strict=False):
        if len(set(items)) == 1:
            prefix_parts.append(items[0])
        else:
            break
    if len(prefix_parts) == 1:
        return f"{prefix_parts[0]} | "
    return ""


def _majority_prefix(columns: list[str]) -> str:
    prefixes: dict[str, int] = {}
    for column in columns:
        if " | " not in column:
            continue
        prefix = column.split(" | ", 1)[0] + " | "
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
    if not prefixes:
        return ""
    prefix, count = max(prefixes.items(), key=lambda item: item[1])
    return prefix if count / len(columns) >= 0.7 else ""


def _has_date_hint(column: str) -> bool:
    normalized = _to_token_string(column)
    return any(token in normalized for token in ("date", "dt", "yyyymm", "month", "period"))


def _has_numeric_hint(column: str) -> bool:
    normalized = _to_token_string(column)
    return any(
        token in normalized
        for token in (
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
            "total",
            "qty",
            "quantity",
            "revenue",
            "sales",
            "amount",
            "volume",
        )
    )


def _looks_like_value_header(column: str) -> bool:
    normalized = str(column).strip().lower()
    compact = normalized.replace(" ", "")
    if re.fullmatch(r"[\d:/\-.]+", compact):
        return True
    return compact.startswith("20") and len(compact) <= 10 and any(char.isdigit() for char in compact)
