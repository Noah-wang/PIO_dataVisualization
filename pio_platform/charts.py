from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from pio_platform.config import THEME_PRESETS, ThemePreset
from pio_platform.i18n import t


@dataclass
class ChartResult:
    title: str
    figure: go.Figure
    data: pd.DataFrame
    message: str | None = None


def build_default_charts(
    df: pd.DataFrame,
    roles: dict[str, str],
    date_candidates: dict[str, pd.Series],
    theme_name: str,
    accent_color: str,
    top_parts_metric: str,
) -> list[ChartResult]:
    theme = THEME_PRESETS[theme_name]
    charts: list[ChartResult] = []

    date_col = roles.get("date")
    qty_col = roles.get("installation_quantity")
    revenue_col = roles.get("revenue")
    model_col = roles.get("model")
    part_col = roles.get("part_description") or roles.get("part_number")

    if date_col and date_col in date_candidates and qty_col:
        chart_df = _monthly_aggregate(df, date_candidates[date_col].loc[df.index], qty_col, "sum")
        charts.append(
            ChartResult(
                title="Monthly Installation Quantity Trend",
                figure=_line_or_area_chart(chart_df, "Month", qty_col, "line", theme, accent_color),
                data=chart_df,
            )
        )

    if date_col and date_col in date_candidates and revenue_col:
        chart_df = _monthly_aggregate(df, date_candidates[date_col].loc[df.index], revenue_col, "sum")
        charts.append(
            ChartResult(
                title="Monthly Revenue Trend",
                figure=_line_or_area_chart(chart_df, "Month", revenue_col, "area", theme, accent_color),
                data=chart_df,
            )
        )

    if model_col and revenue_col:
        chart_df = _top_n(df, model_col, revenue_col, 10, "sum")
        charts.append(
            ChartResult(
                title="Top Vehicle Models by Sales",
                figure=_bar_chart(chart_df, model_col, revenue_col, theme, accent_color, horizontal=True),
                data=chart_df,
            )
        )

    if part_col and top_parts_metric in df.columns:
        chart_df = _top_n(df, part_col, top_parts_metric, 12, "sum")
        metric_label = "Revenue" if top_parts_metric == revenue_col else "Installation Quantity"
        charts.append(
            ChartResult(
                title=f"Top Parts by {metric_label}",
                figure=_bar_chart(chart_df, part_col, top_parts_metric, theme, accent_color, horizontal=True),
                data=chart_df,
            )
        )

    return charts


def build_custom_chart(
    df: pd.DataFrame,
    x_field: str,
    metric: str,
    aggregation: str,
    chart_type: str,
    color_field: str | None,
    top_n: int,
    title: str,
    theme_name: str,
    accent_color: str,
    date_candidates: dict[str, pd.Series],
    time_grain: str,
    lang: str,
) -> ChartResult:
    theme = THEME_PRESETS[theme_name]
    chart_data = aggregate_chart_data(
        df=df,
        x_field=x_field,
        metric=metric,
        aggregation=aggregation,
        color_field=color_field,
        top_n=top_n,
        date_candidates=date_candidates,
        time_grain=time_grain,
    )

    if chart_data.empty:
        figure = go.Figure()
        apply_figure_style(figure, theme, accent_color)
        return ChartResult(title=title, figure=figure, data=chart_data, message=t(lang, "chart_no_data"))

    x_column = "Bucket"
    y_column = "Value"

    if chart_type == "line":
        figure = px.line(chart_data, x=x_column, y=y_column, color=color_field or None, markers=True)
    elif chart_type == "bar":
        figure = px.bar(chart_data, x=x_column, y=y_column, color=color_field or None)
    elif chart_type == "area":
        figure = px.area(chart_data, x=x_column, y=y_column, color=color_field or None)
    elif chart_type == "scatter":
        figure = px.scatter(chart_data, x=x_column, y=y_column, color=color_field or None, size_max=14)
    elif chart_type == "pie":
        figure = px.pie(chart_data, names=x_column, values=y_column, color=color_field or None)
    else:
        figure = px.bar(chart_data, x=x_column, y=y_column, color=color_field or None)

    apply_figure_style(figure, theme, accent_color)
    figure.update_layout(title=title)
    if chart_type == "pie":
        figure.update_traces(textposition="inside", textinfo="percent+label")

    return ChartResult(title=title, figure=figure, data=chart_data)


def aggregate_chart_data(
    df: pd.DataFrame,
    x_field: str,
    metric: str,
    aggregation: str,
    color_field: str | None,
    top_n: int,
    date_candidates: dict[str, pd.Series],
    time_grain: str,
) -> pd.DataFrame:
    working = df.copy()

    if x_field in date_candidates:
        working["Bucket"] = _bucket_dates(date_candidates[x_field].loc[working.index], time_grain)
    else:
        working["Bucket"] = working[x_field].fillna("Unknown").astype(str)

    group_fields = ["Bucket"]
    if color_field and color_field in working.columns and color_field != x_field:
        working[color_field] = working[color_field].fillna("Unknown").astype(str)
        group_fields.append(color_field)

    agg_func = {"sum": "sum", "average": "mean", "count": "count", "median": "median"}[aggregation]
    chart_df = (
        working.groupby(group_fields, dropna=False)[metric]
        .agg(agg_func)
        .reset_index()
        .rename(columns={metric: "Value"})
    )

    if x_field not in date_candidates:
        ordering = chart_df.groupby("Bucket")["Value"].sum().sort_values(ascending=False).head(top_n).index
        chart_df = chart_df[chart_df["Bucket"].isin(ordering)]
        chart_df["Bucket"] = pd.Categorical(chart_df["Bucket"], categories=list(ordering), ordered=True)
        chart_df = chart_df.sort_values("Bucket")
    else:
        chart_df = chart_df.sort_values("Bucket")

    return chart_df


def apply_figure_style(fig: go.Figure, theme: ThemePreset, accent_color: str) -> None:
    palette = [accent_color, "#6f91ff", "#66b4c7", "#8c6ff7", "#16a34a", "#ef7d57"]
    fig.update_layout(
        plot_bgcolor=theme.chart_bg,
        paper_bgcolor=theme.card_bg if theme.name != "Night Shift" else theme.chart_bg,
        font={"family": "IBM Plex Sans, sans-serif", "color": theme.text, "size": 13},
        hoverlabel={"bgcolor": theme.card_alt_bg, "font": {"color": theme.text}},
        margin={"l": 10, "r": 10, "t": 60, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        colorway=palette,
    )
    if len(fig.data) <= 1:
        for trace in fig.data:
            if hasattr(trace, "marker"):
                trace.marker.color = accent_color
            if hasattr(trace, "line"):
                trace.line.color = accent_color
    fig.update_xaxes(showgrid=False, zeroline=False, color=theme.muted_text)
    fig.update_yaxes(showgrid=True, gridcolor=theme.grid, zeroline=False, color=theme.muted_text)


def _monthly_aggregate(df: pd.DataFrame, date_series: pd.Series, metric: str, aggregation: str) -> pd.DataFrame:
    monthly = pd.DataFrame({"Month": date_series.dt.to_period("M").dt.to_timestamp(), metric: df[metric]})
    return monthly.groupby("Month", dropna=True)[metric].agg(aggregation).reset_index()


def _top_n(df: pd.DataFrame, group_field: str, metric: str, limit: int, aggregation: str) -> pd.DataFrame:
    return (
        df.groupby(group_field, dropna=True)[metric]
        .agg(aggregation)
        .sort_values(ascending=False)
        .head(limit)
        .reset_index()
    )


def _line_or_area_chart(
    chart_df: pd.DataFrame,
    x: str,
    y: str,
    chart_type: str,
    theme: ThemePreset,
    accent_color: str,
) -> go.Figure:
    figure = px.area(chart_df, x=x, y=y) if chart_type == "area" else px.line(chart_df, x=x, y=y, markers=True)
    apply_figure_style(figure, theme, accent_color)
    return figure


def _bar_chart(
    chart_df: pd.DataFrame,
    x: str,
    y: str,
    theme: ThemePreset,
    accent_color: str,
    horizontal: bool = False,
) -> go.Figure:
    if horizontal:
        figure = px.bar(chart_df, x=y, y=x, orientation="h")
    else:
        figure = px.bar(chart_df, x=x, y=y)
    apply_figure_style(figure, theme, accent_color)
    return figure


def _bucket_dates(series: pd.Series, grain: str) -> pd.Series:
    if grain == "Month":
        return series.dt.to_period("M").dt.to_timestamp()
    if grain == "Quarter":
        return series.dt.to_period("Q").dt.to_timestamp()
    if grain == "Year":
        return series.dt.to_period("Y").dt.to_timestamp()
    return series.dt.floor("D")
