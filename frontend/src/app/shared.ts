import dayjs from "dayjs";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type WorkbookMeta = {
  id: string;
  filename: string;
  sheetNames: string[];
  defaultSheet?: string;
};

export type Kpis = {
  "Total Records": number | null;
  "Total Installation Quantity": number | null;
  "Total Sales Revenue": number | null;
  "Distinct Part Count": number | null;
};

export type WorkspacePayload = {
  workbook: WorkbookMeta;
  sheetName: string;
  roles: Record<string, string>;
  profile: {
    header_row: number;
    header_depth: number;
    row_count: number;
    column_count: number;
  };
  overview: {
    datasetTitle: string;
    sheetName: string;
    kpis: Kpis;
    summary: string[];
    health: {
      dateFieldCount: number;
      numericFieldCount: number;
      categoryFieldCount: number;
      mappedRoleCount: number;
      highMissingFields: string[];
    };
    autoInsights: string[];
  };
  table: {
    columns: Array<{ key: string; title: string; role: string; type: string }>;
    rows: Array<Record<string, string | number | null>>;
    totalRows: number;
    page: number;
    pageSize: number;
    defaultVisibleColumns: string[];
  };
  classification: Record<
    string,
    Array<{
      column: string;
      group: string;
      detectedRole: string;
      confidence: string;
      type: string;
      missingPct: number;
      uniqueCount: number;
      sampleValues: string;
    }>
  >;
  insights: Record<string, { title: string; labels: string[]; values: number[] }>;
  filters: {
    search: string;
    brand: string[];
    model: string[];
    modelYear: string[];
    part: string[];
    modelQuery: string;
    partQuery: string;
    startDate: string;
    endDate: string;
  };
  filterOptions: {
    dateRange: { min: string | null; max: string | null };
    brand: Array<{ label: string; value: string; count: number }>;
    model: Array<{ label: string; value: string; count: number }>;
    modelYear: Array<{ label: string; value: string; count: number }>;
    part: Array<{ label: string; value: string; count: number }>;
  };
};

export type TableState = {
  search: string;
  brand: string[];
  model: string[];
  modelYear: string[];
  part: string[];
  startDate: string;
  endDate: string;
  page: number;
  pageSize: number;
  sortField: string;
  sortOrder: string;
};

export const defaultTableState: TableState = {
  search: "",
  brand: [],
  model: [],
  modelYear: [],
  part: [],
  startDate: "",
  endDate: "",
  page: 1,
  pageSize: 50,
  sortField: "",
  sortOrder: "",
};

export function formatMetric(value: number | null, currency = false) {
  if (value === null || Number.isNaN(value)) return "N/A";
  return currency
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

export function chartOption(title: string, labels: string[], values: number[], kind: "line" | "bar" | "area") {
  const baseSeries = {
    data: values,
    smooth: true,
    symbolSize: 8,
    itemStyle: { color: "#2054f4" },
    lineStyle: { color: "#2054f4", width: 3 },
    areaStyle: kind === "area" ? { color: "rgba(32, 84, 244, 0.18)" } : undefined,
  };

  return {
    backgroundColor: "transparent",
    animationDuration: 600,
    grid: { left: 40, right: 20, top: 50, bottom: 35 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#101725",
      borderWidth: 0,
      textStyle: { color: "#f8fbff" },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#d7e2ef" } },
      axisLabel: { color: "#607087" },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e5ecf5" } },
      axisLabel: { color: "#607087" },
    },
    series: [
      kind === "bar"
        ? {
            type: "bar",
            data: values,
            itemStyle: { color: "#2054f4", borderRadius: [10, 10, 0, 0] },
            barMaxWidth: 36,
          }
        : {
            ...baseSeries,
            type: "line",
          },
    ],
    title: {
      text: title,
      left: 0,
      top: 8,
      textStyle: {
        color: "#122033",
        fontWeight: 700,
        fontSize: 15,
        fontFamily: "Manrope, sans-serif",
      },
    },
  };
}

export function buildWorkspaceParams(nextState: TableState) {
  const params = new URLSearchParams({
    page: String(nextState.page),
    page_size: String(nextState.pageSize),
    search: nextState.search,
    sort_field: nextState.sortField,
    sort_order: nextState.sortOrder,
    start_date: nextState.startDate,
    end_date: nextState.endDate,
  });
  nextState.brand.forEach((value) => params.append("brand", value));
  nextState.model.forEach((value) => params.append("model", value));
  nextState.modelYear.forEach((value) => params.append("model_year", value));
  nextState.part.forEach((value) => params.append("part", value));
  return params;
}
