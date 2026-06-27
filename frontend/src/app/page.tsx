"use client";

import {
  AreaChartOutlined,
  FileExcelOutlined,
  HistoryOutlined,
  PartitionOutlined,
  TableOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Card,
  Spin,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadProps } from "antd";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  API_BASE_URL,
} from "./shared";

const { Dragger } = Upload;
const { Title, Paragraph } = Typography;

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

export default function Page() {
  const router = useRouter();
  const [messageApi, contextHolder] = message.useMessage();
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("Processing workbook\u2026");
  const [history, setHistory] = useState<Array<{ id: string; filename: string; sheetNames: string[]; defaultSheet: string | null; uploadedAt: string }>>([]);

  // Load history on mount
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/workbooks`)
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => {});
  }, []);

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
      messageApi.success("Upload successful. Redirecting to workspace...");
      
      // Go to workspace page immediately — the workspace page itself will poll and load the workbook!
      router.push(`/workspace/${meta.workbookId}`);
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "Upload failed.");
      setLoading(false);
    }
    return false;
  }

  const uploadProps: UploadProps = {
    accept: ".xlsx,.xls",
    multiple: false,
    showUploadList: false,
    beforeUpload: uploadWorkbook,
  };

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
        <Dragger {...uploadProps} className="upload-panel upload-hero" disabled={loading}>
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
                onClick={() => router.push(`/workspace/${entry.id}`)}
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
    </main>
  );
}
