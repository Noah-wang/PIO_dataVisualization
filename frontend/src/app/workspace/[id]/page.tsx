"use client";

import {
  AreaChartOutlined,
  DatabaseOutlined,
  PartitionOutlined,
  SearchOutlined,
  TableOutlined,
  UploadOutlined,
  LeftOutlined,
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
  message,
} from "antd";
import type { TableColumnsType, TablePaginationConfig } from "antd";
import type { FilterValue, SorterResult } from "antd/es/table/interface";
import ReactECharts from "echarts-for-react";
import { useEffect, useState, use } from "react";
import dayjs from "dayjs";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  API_BASE_URL,
  WorkbookMeta,
  WorkspacePayload,
  TableState,
  defaultTableState,
  formatMetric,
  chartOption,
  buildWorkspaceParams,
} from "../../shared";

const { RangePicker } = DatePicker;
const { Title, Paragraph, Text } = Typography;

interface WorkspacePageProps {
  params: Promise<{ id: string }>;
}

export default function WorkspacePage({ params }: WorkspacePageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [messageApi, contextHolder] = message.useMessage();

  const [workbook, setWorkbook] = useState<WorkbookMeta | null>(null);
  const [workspace, setWorkspace] = useState<WorkspacePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMsg, setLoadingMsg] = useState("Restoring workspace\u2026");
  const [tableLoading, setTableLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [tableState, setTableState] = useState<TableState>(defaultTableState);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Set visible columns when workspace loads
  useEffect(() => {
    if (workspace && visibleColumns.length === 0) {
      setVisibleColumns(workspace.table.defaultVisibleColumns);
    }
  }, [workspace, visibleColumns.length]);

  // Initial status check & polling
  useEffect(() => {
    let active = true;
    let pollInterval: NodeJS.Timeout | null = null;
    let msgTimer: NodeJS.Timeout | null = null;

    const msgs = [
      "Parsing worksheet structure\u2026",
      "Classifying fields\u2026",
      "Computing KPI metrics\u2026",
      "Building insights\u2026",
    ];
    let msgIdx = 0;

    async function checkStatus() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/workbooks/${id}/status`);
        if (!res.ok) {
          throw new Error("Unable to check workspace status.");
        }
        const data = await res.json();
        
        if (!active) return;

        if (data.status === "ready") {
          if (pollInterval) clearInterval(pollInterval);
          if (msgTimer) clearInterval(msgTimer);
          
          setWorkbook({
            id,
            filename: data.filename,
            sheetNames: data.sheetNames,
            defaultSheet: data.defaultSheet,
          });

          await loadWorkspaceData(data.defaultSheet ?? data.sheetNames[0], defaultTableState);
          setLoading(false);
        } else if (data.status === "error") {
          if (pollInterval) clearInterval(pollInterval);
          if (msgTimer) clearInterval(msgTimer);
          setError("Workbook processing failed on the server.");
          setLoading(false);
        } else {
          // processing - start polling if not already running
          if (!pollInterval) {
            msgTimer = setInterval(() => {
              msgIdx = (msgIdx + 1) % msgs.length;
              setLoadingMsg(msgs[msgIdx]);
            }, 1800);

            pollInterval = setInterval(checkStatus, 1500);
          }
        }
      } catch (err) {
        if (pollInterval) clearInterval(pollInterval);
        if (msgTimer) clearInterval(msgTimer);
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load workspace.");
          setLoading(false);
        }
      }
    }

    checkStatus();

    return () => {
      active = false;
      if (pollInterval) clearInterval(pollInterval);
      if (msgTimer) clearInterval(msgTimer);
    };
  }, [id]);

  async function loadWorkspaceData(sheetName: string, state: TableState, silent = false) {
    const params = buildWorkspaceParams(state);
    if (!silent) {
      setTableLoading(true);
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workbooks/${id}/sheets/${encodeURIComponent(sheetName)}?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error((await response.json()).detail ?? "Failed to load workspace sheet.");
      }
      const payload = (await response.json()) as WorkspacePayload;
      setWorkspace(payload);
      setTableState(state);
      if (!silent && visibleColumns.length === 0) {
        setVisibleColumns(payload.table.defaultVisibleColumns);
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "Failed to load worksheet data.");
    } finally {
      if (!silent) {
        setTableLoading(false);
      }
    }
  }

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
      loadWorkspaceData(workspace.sheetName, nextState);
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

  return (
    <main className="page-shell">
      {contextHolder}

      <div style={{ marginBottom: 20 }}>
        <Link href="/" style={{ color: "var(--accent)", fontWeight: 500, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <LeftOutlined style={{ fontSize: 12 }} /> Back to Home
        </Link>
      </div>

      {loading ? (
        <div className="loading-shell" style={{ minHeight: "60vh" }}>
          <div className="loading-card">
            <Spin size="large" />
            <p className="loading-msg">{loadingMsg}</p>
          </div>
        </div>
      ) : error ? (
        <Card className="content-card" style={{ maxWidth: 600, margin: "40px auto", textAlign: "center" }}>
          <Alert type="error" showIcon message="Failed to load Workspace" description={error} />
          <Button type="primary" onClick={() => router.push("/")} style={{ marginTop: 24 }}>
            Go Back Home
          </Button>
        </Card>
      ) : workspace ? (
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
                  loadWorkspaceData(value, { ...defaultTableState, pageSize: tableState.pageSize });
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
                        <Button type="primary" onClick={() => loadWorkspaceData(workspace.sheetName, { ...tableState, page: 1 })}>
                          Apply filters
                        </Button>
                        <Button
                          onClick={() => {
                            setTableState({ ...defaultTableState, pageSize: tableState.pageSize });
                            loadWorkspaceData(workspace.sheetName, { ...defaultTableState, pageSize: tableState.pageSize });
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
