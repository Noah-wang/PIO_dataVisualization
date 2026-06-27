# PIO Demand Intelligence Platform

> **汽车零部件需求规划团队的智能工作台** — 从原始 Excel 工作簿导出到结构化规划工作区，一步完成。

---

## 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [本地运行](#本地运行)
- [API 说明](#api-说明)
- [路线图](#路线图)

---

## 项目简介

PIO Demand Intelligence Platform（V1）是一个面向汽车零部件规划团队的 Web 工作台，取代了早期的 Streamlit MVP 原型。

V1 专注于第一个核心业务需求：**从 Excel 工作簿中提取、清洗、分类数据，并在进入异常检测和销量预测模块之前，提供一个可靠的数据全貌视图。**

平台已在包含约 **199,000 行**销售记录的真实数据集上完成测试，所有表格浏览均采用服务端分页，不会将完整数据集加载进浏览器。

---

## 功能特性

### 📤 Excel 原生导入
- 支持 `.xlsx` 和 `.xls` 格式，无需预先整理源文件
- 自动检测表头行位置，兼容多层合并表头结构
- 多工作表切换，工作簿不落盘

### 📊 Overview（数据概览）
- **KPI 卡片**：总记录数、安装数量、销售金额、零件种类数
- **数据叙述**：自动生成数据集摘要（时间跨度、字段覆盖情况）
- **数据健康报告**：日期字段、数值字段、类别字段及高缺失列统计
- **自动洞察**：时间覆盖、Top 车型/零件收入等关键发现

### 📋 Data Table（数据表格）
- 服务端分页 + 排序，轻松处理 20 万行以上数据
- 多维度过滤：品牌、车型、年款、零件、日期区间、全文检索
- 列可见性控制，自定义工作视图
- 一键导出当前过滤切片为 CSV

### 🗂️ Field Classification（字段分类）
- 自动将字段归入六类业务组：时间、车辆、零件、数量、收入、其他
- 每个字段展示：检测角色、置信度（高/中/低）、类型、缺失率、唯一值数量、示例值

### 📈 Basic Insights（基础洞察）
- 月度安装量趋势折线图
- 月度收入面积图
- Top 10 车型收入排行柱状图
- Top 12 零件排行柱状图

---

## 技术栈

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 15.x | React 全栈框架 |
| React | 19.x | UI 框架 |
| Ant Design | 5.x | 企业级 UI 组件库 |
| ECharts + echarts-for-react | 5.x / 3.x | 数据可视化图表 |
| TypeScript | 5.x | 类型安全 |
| dayjs | — | 日期处理 |

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.116+ | 异步 REST API 框架 |
| Uvicorn | 0.35+ | ASGI 服务器 |
| Pandas | 3.x | 数据处理与分析 |
| openpyxl / xlrd | — | Excel 文件解析 |
| python-multipart | — | 文件上传支持 |

---

## 项目结构

```
.
├── backend/
│   └── app/
│       └── main.py          # FastAPI 路由：上传、工作区、分页、导出
│
├── frontend/
│   └── src/
│       └── app/
│           ├── page.tsx     # 主页面：上传区 + 工作区（所有 Tab）
│           ├── globals.css  # 全局样式与设计系统
│           └── layout.tsx   # 根布局
│
├── pio_platform/            # 可复用的核心数据处理库
│   ├── data_loader.py       # Excel 解析、表头检测、字段类型推断、角色识别
│   ├── profiling.py         # 列分析、KPI 计算、自动洞察生成
│   ├── config.py            # 字段角色匹配规则配置
│   ├── filters.py           # 数据过滤逻辑
│   ├── charts.py            # 图表数据构建
│   └── i18n.py              # 多语言支持
│
├── requirements.txt         # Python 依赖
├── .gitignore
└── README.md
```

---

## 本地运行

> 需要：Python 3.11+，Node.js 18+

### 1. 启动后端 API

```bash
# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动后端（开发模式，自动热重载）
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端运行后可访问：`http://127.0.0.1:8000/docs`（Swagger 交互文档）

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开浏览器访问：[http://localhost:3000](http://localhost:3000)

### 环境变量（可选）

前端默认连接 `http://127.0.0.1:8000`，可通过环境变量修改：

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

---

## API 说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/workbooks/upload` | 上传 Excel 文件，返回工作区完整数据 |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}` | 获取指定工作表的分页数据（支持过滤、排序） |
| `GET` | `/api/workbooks/{id}/sheets/{sheet}/export.csv` | 导出当前过滤切片为 CSV |

上传接口返回结构：
```json
{
  "workbook": { "id": "...", "filename": "...", "sheetNames": ["..."] },
  "workspace": {
    "overview": { "kpis": {}, "summary": [], "health": {}, "autoInsights": [] },
    "table": { "columns": [], "rows": [], "totalRows": 0 },
    "classification": {},
    "insights": {},
    "filterOptions": {}
  }
}
```

---

## 路线图

V1 作为数据准备和字段分类的基础层，后续模块规划如下：

- [ ] **异常检测**：识别销量异常月份，定位问题零件/车型
- [ ] **驱动力分析**：解释按零件/车型/月份维度的涨跌原因
- [ ] **需求预测**：生成下月/下年销量预测
- [ ] **渗透率分析**：结合整车批发数据计算零件装配渗透率
- [ ] **库存建议**：基于预测输出库存补货推荐

---

## License

MIT
