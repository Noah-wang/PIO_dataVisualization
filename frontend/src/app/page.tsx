"use client";

import {
  AreaChartOutlined,
  DatabaseOutlined,
  FileExcelOutlined,
  HistoryOutlined,
  PartitionOutlined,
  SearchOutlined,
  TableOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { TableColumnsType, TablePaginationConfig } from "antd";
import type { FilterValue, SorterResult } from "antd/es/table/interface";
import type { UploadProps } from "antd";
import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";
import dayjs from "dayjs";

const { Dragger } = Upload;
const { RangePicker } = DatePicker;
const { Title, Paragraph, Text } = Typography;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type WorkbookMeta = {
  id: string;
  filename: string;
  sheetNames: string[];
  defaultSheet?: string;
};

type Kpis = {
  "Total Records": number | null;
  "Total Installation Quantity": number | null;
  "Total Sales Revenue": number | null;
  "Distinct Part Count": number | null;
};

type WorkspacePayload = {
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

type TableState = {
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

const defaultTableState: TableState = {
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

const capabilityCards = [
  {
    icon: <UploadOutlined />,
    title: "Excel-native intake",
    copy: "Bring in workbook exports without reshaping the source file first.",
  },
  {
    icon: <TableOutlined />,
    title: "Server-side data table",
    copy: "Browse large sheets with search, pagination, and business-aware column order.",
  },
  {
    icon: <PartitionOutlined />,
    title: "Field classification",
    copy: "Separate time, vehicle, part, quantity, revenue, and support columns automatically.",
  },
  {
    icon: <AreaChartOutlined />,
    title: "Decision-ready views",
    copy: "Turn worksheet structure into a reliable overview before anomaly and forecast modules land.",
  },
];

function formatMetric(value: number | null, currency = false) {
  if (value === null || Number.isNaN(value)) return "N/A";
  return currency
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function chartOption(title: string, labels: string[], values: number[], kind: "line" | "bar" | "area") {
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

function buildWorkspaceParams(nextState: TableState) {
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

export default function Page() {
  const [messageApi, contextHolder] = message.useMessage();
  const [workbook, setWorkbook] = useState<WorkbookMeta | null>(null);
  const [workspace, setWorkspace] = useState<WorkspacePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("Processing workbook\u2026");
  const [tableLoading, setTableLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [tableState, setTableState] = useState<TableState>(defaultTableState);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
  const [history, setHistory] = useState<Array<{ id: string; filename: string; sheetNames: string[]; defaultSheet: string | null; uploadedAt: string }>>([]);

  // Load history on mount
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/workbooks`)
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (workspace && visibleColumns.length === 0) {
      setVisibleColumns(workspace.table.defaultVisibleColumns);
    }
  }, [workspace, visibleColumns.length]);

  /** Poll /status until ready, then load workspace */
  async function pollUntilReady(workbookId: string, defaultSheet: string) {
    return new Promise<void>((resolve, reject) => {
      const msgs = [
        "Parsing worksheet structure\u2026",
        "Classifying fields\u2026",
        "Computing KPI metrics\u2026",
        "Building insights\u2026",
      ];
      let msgIdx = 0;
      const msgTimer = setInterval(() => {
        msgIdx = (msgIdx + 1) % msgs.length;
        setLoadingMsg(msgs[msgIdx]);
      }, 1800);

      const poll = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE_URL}/api/workbooks/${workbookId}/status`);
          if (!res.ok) { clearInterval(poll); clearInterval(msgTimer); reject(new Error("Status check failed.")); return; }
          const data = await res.json();
          if (data.status === "ready") {
            clearInterval(poll);
            clearInterval(msgTimer);
            resolve();
          } else if (data.status === "error") {
            clearInterval(poll);
            clearInterval(msgTimer);
            reject(new Error("Processing failed on the server."));
          }
        } catch (e) {
          clearInterval(poll);
          clearInterval(msgTimer);
          reject(e);
        }
      }, 1500);
    });
  }

  async function uploadWorkbook(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    setLoading(true);
    setLoadingMsg("Uploading file\u2026");
    try {
      const response = await fetch(`${API_BASE_URL}/api/workbooks/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Upload failed.");
      }
      const meta = await response.json() as { workbookId: string; filename: string; sheetNames: string[]; defaultSheet: string };
      setLoadingMsg("Parsing worksheet structure\u2026");
      await pollUntilReady(meta.workbookId, meta.defaultSheet);
      setWorkbook({ id: meta.workbookId, filename: meta.filename, sheetNames: meta.sheetNames, defaultSheet: meta.defaultSheet });
      await loadWorkspaceById(meta.workbookId, meta.defaultSheet, defaultTableState);
      setTableState(defaultTableState);
      setActiveTab("overview");
      // Refresh history list
      fetch(`${API_BASE_URL}/api/workbooks`).then((r) => r.json()).then(setHistory).catch(() => {});
      messageApi.success("Workbook loaded into the workspace.");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setLoading(false);
    }
    return false;
  }

  async function openFromHistory(entry: { id: string; filename: string; sheetNames: string[]; defaultSheet: string | null }) {
    setLoading(true);
    setLoadingMsg("Restoring workspace\u2026");
    try {
      await pollUntilReady(entry.id, entry.defaultSheet ?? entry.sheetNames[0]);
      setWorkbook({ id: entry.id, filename: entry.filename, sheetNames: entry.sheetNames, defaultSheet: entry.defaultSheet ?? undefined });
      await loadWorkspaceById(entry.id, entry.defaultSheet ?? entry.sheetNames[0], defaultTableState);
      setTableState(defaultTableState);
      setActiveTab("overview");
      messageApi.success("Workspace restored.");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Failed to restore workspace.");
    } finally {
      setLoading(false);
    }
  }

  async function loadWorkspace(nextSheetName: string, nextState: TableState, silent = false) {
    if (!workbook) return;
    const params = buildWorkspaceParams(nextState);

    if (!silent) {
      setTableLoading(true);
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(nextSheetName)}?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load workspace.");
      }
      const payload = (await response.json()) as WorkspacePayload;
      setWorkspace(payload);
      setTableState(nextState);
      if (!silent && visibleColumns.length === 0) {
        setVisibleColumns(payload.table.defaultVisibleColumns);
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Failed to load workspace.");
    } finally {
      if (!silent) {
        setTableLoading(false);
      }
    }
  }

  async function loadWorkspaceById(wbId: string, sheetName: string, nextState: TableState) {
    const params = buildWorkspaceParams(nextState);
    const response = await fetch(
      `${API_BASE_URL}/api/workbooks/${wbId}/sheets/${encodeURIComponent(sheetName)}?${params.toString()}`
    );
    if (!response.ok) {
      throw new Error((await response.json()).detail ?? "Failed to load workspace.");
    }
    const payload = (await response.json()) as WorkspacePayload;
    setWorkspace(payload);
    setVisibleColumns(payload.table.defaultVisibleColumns);
  }

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls",
    multiple: false,
    showUploadList: false,
    beforeUpload: uploadWorkbook,
  };

  const columns: TableColumnsType<Record<string, string | number | null>> =
    workspace?.table.columns
      .filter((column) => visibleColumns.includes(column.key))
      .map((column) => ({
        title: (
          <div className="column-heading">
            <span>{column.title}</span>
            {column.role ? <Tag>{column.role}</Tag> : null}
          </div>
        ),
        dataIndex: column.key,
        key: column.key,
        sorter: true,
        width: column.type === "text" ? 220 : 160,
        render: (value) => {
          if (value === null || value === undefined || value === "") {
            return <span className="cell-empty">-</span>;
          }
          if (typeof value === "number") {
            return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
          }
          return value;
        },
      })) ?? [];

  function handleTableChange(
    pagination: TablePaginationConfig,
    _: Record<string, FilterValue | null>,
    sorter:
      | SorterResult<Record<string, string | number | null>>
      | Array<SorterResult<Record<string, string | number | null>>>
  ) {
    const resolvedSorter = Array.isArray(sorter) ? sorter[0] : sorter;
    const nextState = {
      ...tableState,
      page: pagination.current ?? 1,
      pageSize: pagination.pageSize ?? 50,
      sortField:
        typeof resolvedSorter?.field === "string"
          ? resolvedSorter.field
          : Array.isArray(resolvedSorter?.field) && typeof resolvedSorter.field[0] === "string"
            ? resolvedSorter.field[0]
            : "",
      sortOrder: resolvedSorter?.order ?? "",
    };
    if (workspace) {
      loadWorkspace(workspace.sheetName, nextState);
    }
  }

  function exportCsv() {
    if (!workbook || !workspace) return;
    const params = buildWorkspaceParams({ ...tableState, page: 1 });
    window.open(
      `${API_BASE_URL}/api/workbooks/${workbook.id}/sheets/${encodeURIComponent(workspace.sheetName)}/export.csv?${params.toString()}`,
      "_blank"
    );
  }

  const hasWorkspace = Boolean(workspace && workbook);

  return (
    <main className="page-shell">
      {contextHolder}
      <section className="hero-shell">
        <div className="hero-copy">
          <div className="eyebrow">PIO Demand Intelligence Platform</div>
          <Title className="hero-title">
            From raw workbook exports to a clean planning workspace.
          </Title>
          <Paragraph className="hero-paragraph">
            V1 is built around the first business need: inspect the sales table, classify fields into business-ready
            groups, and surface a reliable overview before we move into anomaly reasoning and sales forecasting.
          </Paragraph>
          <div className="hero-badges">
            <span>Excel intake</span>
            <span>Server-side table browsing</span>
            <span>Field classification</span>
            <span>Forecast-ready foundation</span>
          </div>
        </div>

        {/* 右侧：四个功能卡片垂直堆叠，与左侧等高 */}
        <div className="hero-right">
          {capabilityCards.map((card) => (
            <div key={card.title} className="hero-mini-card">
              <div className="hero-mini-icon">{card.icon}</div>
              <div>
                <div className="hero-mini-title">{card.title}</div>
                <div className="hero-mini-copy">{card.copy}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 上传框 */}
      <div className="hero-upload-row">
        <Dragger {...uploadProps} className="upload-panel upload-hero">
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="upload-title">Drop an Excel workbook here</p>
          <p className="upload-copy">Supports .xlsx and .xls. The source file remains unchanged.</p>
        </Dragger>

        {/* 历史文件列表 */}
        {history.length > 0 && (
          <div className="history-list">
            <div className="history-header">
              <HistoryOutlined />
              <span>Recent files</span>
            </div>
            {history.map((entry) => (
              <button
                key={entry.id}
                className="history-item"
                onClick={() => openFromHistory(entry)}
                disabled={loading}
              >
                <FileExcelOutlined className="history-file-icon" />
                <div className="history-item-info">
                  <span className="history-item-name">{entry.filename}</span>
                  <span className="history-item-meta">
                    {entry.sheetNames.length} sheet{entry.sheetNames.length > 1 ? "s" : ""}
                    {" · "}
                    {new Date(entry.uploadedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                </div>
                <span className="history-item-arrow">→</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="loading-shell">
          <div className="loading-card">
            <Spin size="large" />
            <p className="loading-msg">{loadingMsg}</p>
          </div>
        </div>
      ) : null}

      {hasWorkspace && workspace ? (
        <section className="workspace-shell">
          <div className="workspace-header">
            <div>
              <div className="eyebrow">Active Workspace</div>
              <Title level={2} className="workspace-title">
                {workspace.workbook.filename}
              </Title>
              <Paragraph className="workspace-copy">
                Header row {workspace.profile.header_row}, depth {workspace.profile.header_depth}, {workspace.profile.row_count.toLocaleString()} rows.
              </Paragraph>
            </div>
            <Space size="middle" className="workspace-controls">
              <Select
                className="sheet-select"
                value={workspace.sheetName}
                options={workspace.workbook.sheetNames.map((sheetName) => ({ label: sheetName, value: sheetName }))}
                onChange={(value) => {
                  setVisibleColumns([]);
                  loadWorkspace(value, { ...defaultTableState, pageSize: tableState.pageSize });
                }}
              />
              <Button onClick={exportCsv}>Export filtered CSV</Button>
            </Space>
          </div>

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            className="workspace-tabs"
            items={[
              {
                key: "overview",
                label: "Overview",
                children: (
                  <div className="tab-stack">
                    <Row gutter={[18, 18]}>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic title="Total records" value={formatMetric(workspace.overview.kpis["Total Records"])} />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                            title="Installation quantity"
                            value={formatMetric(workspace.overview.kpis["Total Installation Quantity"])}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                            title="Sales revenue"
                            value={formatMetric(workspace.overview.kpis["Total Sales Revenue"], true)}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} md={12} xl={6}>
                        <Card className="metric-card">
                          <Statistic
                            title="Distinct parts"
                            value={formatMetric(workspace.overview.kpis["Distinct Part Count"])}
                          />
                        </Card>
                      </Col>
                    </Row>

                    <Row gutter={[18, 18]}>
                      <Col xs={24} xl={15}>
                        <Card className="content-card" title="Dataset narrative">
                          <div className="summary-stack">
                            {workspace.overview.summary.map((line) => (
                              <div key={line} className="summary-row">
                                <span className="summary-dot" />
                                <span>{line}</span>
                              </div>
                            ))}
                          </div>
                        </Card>
                      </Col>
                      <Col xs={24} xl={9}>
                        <Card className="content-card" title="Data health">
                          <div className="health-grid">
                            <div>
                              <span className="health-label">Date fields</span>
                              <strong>{workspace.overview.health.dateFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Numeric fields</span>
                              <strong>{workspace.overview.health.numericFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Category fields</span>
                              <strong>{workspace.overview.health.categoryFieldCount}</strong>
                            </div>
                            <div>
                              <span className="health-label">Mapped business roles</span>
                              <strong>{workspace.overview.health.mappedRoleCount}</strong>
                            </div>
                          </div>
                          {workspace.overview.health.highMissingFields.length ? (
                            <Alert
                              className="health-alert"
                              type="warning"
                              showIcon
                              message={`High-missing columns: ${workspace.overview.health.highMissingFields.join(", ")}`}
                            />
                          ) : null}
                        </Card>
                      </Col>
                    </Row>

                    <Card className="content-card" title="Auto insights">
                      {workspace.overview.autoInsights.length ? (
                        <div className="summary-stack">
                          {workspace.overview.autoInsights.map((line) => (
                            <div key={line} className="summary-row">
                              <span className="summary-dot" />
                              <span>{line}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No auto insights available for this slice yet." />
                      )}
                    </Card>
                  </div>
                ),
              },
              {
                key: "table",
                label: "Data Table",
                children: (
                  <div className="tab-stack">
                    <Card className="content-card">
                      <div className="toolbar-grid">
                        <Input
                          allowClear
                          prefix={<SearchOutlined />}
                          placeholder="Search key fields"
                          value={tableState.search}
                          onChange={(event) => setTableState({ ...tableState, search: event.target.value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount={1}
                          placeholder="Brand"
                          optionFilterProp="label"
                          value={tableState.brand}
                          options={workspace.filterOptions.brand.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => setTableState({ ...tableState, brand: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount={1}
                          placeholder="Model"
                          optionFilterProp="label"
                          showSearch
                          value={tableState.model}
                          options={workspace.filterOptions.model.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => setTableState({ ...tableState, model: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount={1}
                          placeholder="Model year"
                          optionFilterProp="label"
                          value={tableState.modelYear}
                          options={workspace.filterOptions.modelYear.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => setTableState({ ...tableState, modelYear: value })}
                        />
                        <Select
                          mode="multiple"
                          allowClear
                          maxTagCount={1}
                          placeholder="Part"
                          optionFilterProp="label"
                          showSearch
                          value={tableState.part}
                          options={workspace.filterOptions.part.map((option) => ({
                            label: `${option.label} (${option.count.toLocaleString()})`,
                            value: option.value,
                          }))}
                          onChange={(value) => setTableState({ ...tableState, part: value })}
                        />
                        <RangePicker
                          value={
                            tableState.startDate && tableState.endDate
                              ? [dayjs(tableState.startDate), dayjs(tableState.endDate)]
                              : null
                          }
                          minDate={workspace.filterOptions.dateRange.min ? dayjs(workspace.filterOptions.dateRange.min) : undefined}
                          maxDate={workspace.filterOptions.dateRange.max ? dayjs(workspace.filterOptions.dateRange.max) : undefined}
                          onChange={(values) =>
                            setTableState({
                              ...tableState,
                              startDate: values?.[0]?.format("YYYY-MM-DD") ?? "",
                              endDate: values?.[1]?.format("YYYY-MM-DD") ?? "",
                            })
                          }
                        />
                        <Select
                          mode="multiple"
                          value={visibleColumns}
                          maxTagCount={2}
                          placeholder="Visible columns"
                          options={workspace.table.columns.map((column) => ({
                            label: column.title,
                            value: column.key,
                          }))}
                          onChange={setVisibleColumns}
                        />
                        <Button type="primary" onClick={() => loadWorkspace(workspace.sheetName, { ...tableState, page: 1 })}>
                          Apply filters
                        </Button>
                        <Button
                          onClick={() => {
                            setTableState({ ...defaultTableState, pageSize: tableState.pageSize });
                            loadWorkspace(workspace.sheetName, { ...defaultTableState, pageSize: tableState.pageSize });
                          }}
                        >
                          Clear
                        </Button>
                      </div>
                    </Card>

                    <Card className="content-card" title="Worksheet records">
                      <Table
                        rowKey="id"
                        loading={tableLoading}
                        columns={columns}
                        dataSource={workspace.table.rows}
                        pagination={{
                          current: workspace.table.page,
                          pageSize: workspace.table.pageSize,
                          total: workspace.table.totalRows,
                          showSizeChanger: true,
                        }}
                        scroll={{ x: 1600 }}
                        onChange={handleTableChange}
                      />
                    </Card>
                  </div>
                ),
              },
              {
                key: "classification",
                label: "Field Classification",
                children: (
                  <div className="classification-stack">
                    {Object.entries(workspace.classification).map(([group, fields]) => (
                      <Card key={group} className="content-card" title={group}>
                        <div className="field-grid">
                          {fields.map((field) => (
                            <div key={field.column} className="field-card">
                              <div className="field-topline">
                                <Text strong>{field.column}</Text>
                                <Tag color={field.confidence === "High" ? "blue" : field.confidence === "Medium" ? "gold" : "default"}>
                                  {field.confidence}
                                </Tag>
                              </div>
                              <div className="field-meta">
                                <span>{field.detectedRole}</span>
                                <span>{field.type}</span>
                              </div>
                              <div className="field-stats">
                                <div>
                                  <label>Missing</label>
                                  <strong>{field.missingPct}%</strong>
                                </div>
                                <div>
                                  <label>Unique</label>
                                  <strong>{field.uniqueCount.toLocaleString()}</strong>
                                </div>
                              </div>
                              <Paragraph className="field-sample" ellipsis={{ rows: 2 }}>
                                {field.sampleValues || "No sample values available."}
                              </Paragraph>
                            </div>
                          ))}
                        </div>
                      </Card>
                    ))}
                  </div>
                ),
              },
              {
                key: "insights",
                label: "Basic Insights",
                children: (
                  <div className="chart-grid">
                    {workspace.insights.monthlyInstallation ? (
                      <Card className="chart-card">
                        <ReactECharts
                          option={chartOption(
                            "Monthly installation quantity",
                            workspace.insights.monthlyInstallation.labels,
                            workspace.insights.monthlyInstallation.values,
                            "line"
                          )}
                          style={{ height: 320 }}
                        />
                      </Card>
                    ) : null}
                    {workspace.insights.monthlyRevenue ? (
                      <Card className="chart-card">
                        <ReactECharts
                          option={chartOption(
                            "Monthly revenue",
                            workspace.insights.monthlyRevenue.labels,
                            workspace.insights.monthlyRevenue.values,
                            "area"
                          )}
                          style={{ height: 320 }}
                        />
                      </Card>
                    ) : null}
                    {workspace.insights.topModels ? (
                      <Card className="chart-card">
                        <ReactECharts
                          option={chartOption(
                            "Top vehicle models by revenue",
                            workspace.insights.topModels.labels,
                            workspace.insights.topModels.values,
                            "bar"
                          )}
                          style={{ height: 320 }}
                        />
                      </Card>
                    ) : null}
                    {workspace.insights.topParts ? (
                      <Card className="chart-card">
                        <ReactECharts
                          option={chartOption(
                            workspace.insights.topParts.title,
                            workspace.insights.topParts.labels,
                            workspace.insights.topParts.values,
                            "bar"
                          )}
                          style={{ height: 320 }}
                        />
                      </Card>
                    ) : null}
                    {!Object.keys(workspace.insights).length ? (
                      <Card className="content-card">
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description="The selected worksheet does not expose enough business-ready fields for the default insight set."
                        />
                      </Card>
                    ) : null}
                  </div>
                ),
              },
            ]}
          />
        </section>
      ) : null}
    </main>
  );
}
