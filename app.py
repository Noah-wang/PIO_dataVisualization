from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from pio_platform.charts import build_custom_chart, build_default_charts
from pio_platform.config import THEME_PRESETS
from pio_platform.data_loader import DatasetBundle, list_workbook_sheets, load_dataset
from pio_platform.filters import apply_filters, render_filters
from pio_platform.i18n import (
    LANGUAGE_OPTIONS,
    aggregation_label,
    chart_type_label,
    localize_chart_title,
    localize_profile_df,
    t,
    time_grain_label,
)
from pio_platform.profiling import build_column_profile, build_insights, compute_kpis
from pio_platform.ui import (
    inject_global_styles,
    panel_end,
    panel_start,
    render_dataset_metadata,
    render_hero,
    render_kpi_card,
)


st.set_page_config(
    page_title="PIO Demand Intelligence Platform",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data(show_spinner=False)
def get_sheet_names(file_bytes: bytes) -> list[str]:
    return list_workbook_sheets(file_bytes)


@st.cache_data(show_spinner=False)
def get_dataset(
    file_bytes: bytes,
    sheet_name: str,
    header_mode: str,
    header_row: int,
    header_depth: int,
) -> DatasetBundle:
    return load_dataset(file_bytes, sheet_name, header_mode, header_row, header_depth)


def main() -> None:
    if "uploaded_workbooks" not in st.session_state:
        st.session_state["uploaded_workbooks"] = {}
    if "language_display" not in st.session_state:
        st.session_state["language_display"] = list(LANGUAGE_OPTIONS.keys())[0]
    if "theme_name" not in st.session_state:
        st.session_state["theme_name"] = list(THEME_PRESETS.keys())[0]

    language_display = st.session_state["language_display"]
    lang = LANGUAGE_OPTIONS[language_display]
    theme_name = st.session_state["theme_name"]

    accent_color = THEME_PRESETS[theme_name].accent
    inject_global_styles(theme_name, accent_color)
    render_hero(lang)

    workbook_map: dict[str, bytes] = st.session_state["uploaded_workbooks"]

    source_col, parsing_col, view_col = st.columns([1.25, 1, 0.95], gap="large")
    with source_col:
        panel_start(t(lang, "data_source"), t(lang, "data_source_subtitle"))
        uploaded_files = st.file_uploader(
            t(lang, "upload_excel_workbooks"),
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            help=t(lang, "upload_excel_help"),
            label_visibility="visible",
        )
        if uploaded_files:
            st.session_state["uploaded_workbooks"] = {
                uploaded_file.name: uploaded_file.getvalue() for uploaded_file in uploaded_files
            }
            workbook_map = st.session_state["uploaded_workbooks"]

        workbook_name = None
        file_bytes = None
        sheet_name = None
        if workbook_map:
            workbook_name = st.selectbox(t(lang, "workbook"), options=list(workbook_map.keys()))
            file_bytes = workbook_map[workbook_name]
            sheet_names = get_sheet_names(file_bytes)
            sheet_name = st.selectbox(t(lang, "worksheet"), options=sheet_names)
        else:
            st.caption(t(lang, "no_upload_info"))
        panel_end()

    with parsing_col:
        panel_start(t(lang, "parsing_controls"), t(lang, "parsing_controls_subtitle"))
        header_mode_options = {t(lang, "auto_detect"): "Auto detect", t(lang, "manual"): "Manual"}
        header_mode_label = st.radio(t(lang, "header_mode"), options=list(header_mode_options.keys()), horizontal=True)
        header_mode = header_mode_options[header_mode_label]
        manual_row = 1
        manual_depth = 1
        if header_mode == "Manual":
            manual_row = st.number_input(t(lang, "header_row"), min_value=1, max_value=25, value=1, step=1)
            manual_depth = st.number_input(t(lang, "header_depth"), min_value=1, max_value=3, value=1, step=1)
        panel_end()

    with view_col:
        panel_start(t(lang, "view_settings"), t(lang, "view_settings_subtitle"))
        st.selectbox(
            "Language / 语言",
            options=list(LANGUAGE_OPTIONS.keys()),
            key="language_display",
        )
        st.selectbox(
            t(lang, "workspace_theme"),
            options=list(THEME_PRESETS.keys()),
            key="theme_name",
        )
        panel_end()

    if not workbook_map or workbook_name is None or file_bytes is None or sheet_name is None:
        return

    bundle = get_dataset(file_bytes, sheet_name, header_mode, int(manual_row), int(manual_depth))

    if bundle.dataframe.empty:
        st.warning(t(lang, "unusable_sheet_warning"))
        return

    grouping_candidates = bundle.date_fields + [
        column
        for column in bundle.categorical_fields
        if bundle.dataframe[column].dropna().nunique() > 1
    ]
    grouping_candidates = list(dict.fromkeys(grouping_candidates))
    numeric_fields = [field for field in bundle.numeric_fields if bundle.dataframe[field].notna().any()]

    if not grouping_candidates:
        grouping_candidates = bundle.dataframe.columns.tolist()
    if not numeric_fields:
        numeric_fields = bundle.dataframe.columns.tolist()

    default_x_field = bundle.roles.get("date") or bundle.roles.get("model") or grouping_candidates[0]
    default_metric = bundle.roles.get("installation_quantity") or bundle.roles.get("revenue") or numeric_fields[0]

    controls_left, controls_right = st.columns([1.1, 1], gap="large")
    with controls_left:
        panel_start(t(lang, "filters"), t(lang, "filters_subtitle"))
        filter_state = render_filters(bundle.dataframe, bundle.roles, bundle.date_candidates, lang)
        panel_end()

    with controls_right:
        panel_start(t(lang, "custom_chart_builder"), t(lang, "chart_builder_subtitle_short"))
        builder_col1, builder_col2 = st.columns(2, gap="medium")
        with builder_col1:
            x_field = st.selectbox(
                t(lang, "x_axis_grouping_field"),
                options=grouping_candidates,
                index=grouping_candidates.index(default_x_field) if default_x_field in grouping_candidates else 0,
            )
            aggregation = st.selectbox(
                t(lang, "aggregation"),
                options=["sum", "average", "count", "median"],
                index=0,
                format_func=lambda value: aggregation_label(value, lang),
            )
            color_candidates = ["None"] + [
                column
                for column in bundle.categorical_fields
                if column != x_field and bundle.dataframe[column].dropna().nunique() <= 20
            ]
            color_choice = st.selectbox(
                t(lang, "color_grouping"),
                options=color_candidates,
                format_func=lambda value: t(lang, "none") if value == "None" else value,
            )
        with builder_col2:
            metric = st.selectbox(
                t(lang, "numeric_metric"),
                options=numeric_fields,
                index=numeric_fields.index(default_metric) if default_metric in numeric_fields else 0,
            )
            chart_type = st.selectbox(
                t(lang, "chart_type"),
                options=["line", "bar", "area", "scatter", "pie"],
                index=1,
                format_func=lambda value: chart_type_label(value, lang),
            )
            top_n = st.slider(t(lang, "top_n_limit"), min_value=5, max_value=25, value=12, step=1)
        time_grain = "Month"
        if x_field in bundle.date_fields:
            time_grain = st.selectbox(
                t(lang, "time_grain"),
                options=["Day", "Month", "Quarter", "Year"],
                index=1,
                format_func=lambda value: time_grain_label(value, lang),
            )
        chart_title = st.text_input(
            t(lang, "chart_title"),
            value=t(lang, "default_chart_title", aggregation=aggregation_label(aggregation, lang), metric=metric, field=x_field),
        )
        panel_end()

    filtered_df = apply_filters(bundle.dataframe, filter_state, bundle.roles, bundle.date_candidates)
    profile_df = localize_profile_df(build_column_profile(bundle.dataframe, bundle.date_candidates), lang)
    kpis = compute_kpis(filtered_df, bundle.roles)
    insights = build_insights(filtered_df, bundle.roles, bundle.date_candidates, lang)

    render_dataset_metadata(workbook_name, sheet_name, bundle.profile, lang)

    data_csv = filtered_df.to_csv(index=False).encode("utf-8")
    export_col_left, export_col_right = st.columns([1, 3], gap="large")
    with export_col_left:
        st.download_button(t(lang, "export_filtered_csv"), data=data_csv, file_name="pio_filtered_data.csv", mime="text/csv", use_container_width=True)

    kpi_columns = st.columns(4)
    kpi_keys = [
        "Total Records",
        "Total Installation Quantity",
        "Total Sales Revenue",
        "Distinct Part Count",
    ]
    label_map = {
        "Total Records": t(lang, "total_records"),
        "Total Installation Quantity": t(lang, "total_installation_quantity"),
        "Total Sales Revenue": t(lang, "total_sales_revenue"),
        "Distinct Part Count": t(lang, "distinct_part_count"),
    }
    kpi_footnotes = {
        "Total Records": t(lang, "kpi_foot_total_records"),
        "Total Installation Quantity": t(lang, "kpi_foot_total_installation_quantity"),
        "Total Sales Revenue": t(lang, "kpi_foot_total_sales_revenue"),
        "Distinct Part Count": t(lang, "kpi_foot_distinct_part_count"),
    }
    for column_container, label in zip(kpi_columns, kpi_keys, strict=False):
        with column_container:
            render_kpi_card(label_map[label], _format_metric(label, kpis.get(label)), kpi_footnotes[label])

    overview_left, overview_right = st.columns([1.2, 1], gap="large")
    with overview_left:
        panel_start(t(lang, "dataset_overview"), t(lang, "dataset_overview_subtitle"))
        st.dataframe(profile_df, use_container_width=True, hide_index=True)
        panel_end()
    with overview_right:
        panel_start(t(lang, "operational_insights"), t(lang, "operational_insights_subtitle"))
        if insights:
            st.markdown("<ul class='pio-insight-list'>" + "".join(f"<li>{insight}</li>" for insight in insights) + "</ul>", unsafe_allow_html=True)
        else:
            st.caption(t(lang, "no_auto_insights"))
        panel_end()

    default_metric = bundle.roles.get("revenue") or bundle.roles.get("installation_quantity")
    default_charts = build_default_charts(
        filtered_df,
        bundle.roles,
        bundle.date_candidates,
        theme_name,
        accent_color,
        default_metric if default_metric else metric,
    )

    panel_start(t(lang, "default_dashboards"), t(lang, "default_dashboards_subtitle"))
    if not default_charts:
        st.warning(t(lang, "default_dashboard_warning"))
    else:
        for index in range(0, len(default_charts), 2):
            chart_row = st.columns(2, gap="large")
            for chart_container, chart in zip(chart_row, default_charts[index : index + 2], strict=False):
                with chart_container:
                    localized_chart_title = localize_chart_title(chart.title, lang)
                    st.markdown(f"#### {localized_chart_title}")
                    st.plotly_chart(chart.figure, use_container_width=True, config={"displaylogo": False})
                    st.download_button(
                        label=t(lang, "export_chart_csv", title=localized_chart_title),
                        data=chart.data.to_csv(index=False).encode("utf-8"),
                        file_name=f"{_slugify(localized_chart_title)}.csv",
                        mime="text/csv",
                        key=f"default_chart_export_{chart.title}",
                        use_container_width=True,
                    )
    panel_end()

    custom_chart = build_custom_chart(
        df=filtered_df,
        x_field=x_field,
        metric=metric,
        aggregation=aggregation,
        chart_type=chart_type,
        color_field=None if color_choice == "None" else color_choice,
        top_n=top_n,
        title=chart_title,
        theme_name=theme_name,
        accent_color=accent_color,
        date_candidates=bundle.date_candidates,
        time_grain=time_grain,
        lang=lang,
    )

    panel_start(t(lang, "custom_chart_panel_title"), t(lang, "custom_chart_panel_subtitle"))
    if custom_chart.message:
        st.info(custom_chart.message)
    st.plotly_chart(custom_chart.figure, use_container_width=True, config={"displaylogo": False})
    st.download_button(
        t(lang, "export_custom_chart_csv"),
        data=custom_chart.data.to_csv(index=False).encode("utf-8"),
        file_name="pio_custom_chart.csv",
        mime="text/csv",
        use_container_width=True,
    )
    panel_end()

    panel_start(t(lang, "filtered_data"), t(lang, "filtered_data_subtitle"))
    st.dataframe(filtered_df.head(1000), use_container_width=True, hide_index=True)
    panel_end()


def _format_metric(label: str, value: object) -> str:
    if value is None:
        return "N/A"
    if label == "Total Sales Revenue":
        return f"${float(value):,.0f}"
    return f"{float(value):,.0f}" if isinstance(value, (int, float)) else str(value)


def _slugify(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )


if __name__ == "__main__":
    main()
