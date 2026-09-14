# MCP-RAG 智能知识库平台

基于 **MCP（Model Context Protocol）** 协议的企业级智能知识库系统：**RAG 检索增强** + **异步 API 服务** + **双通道鉴权** + **质量门禁** + **全链路可观测**，支持多 MCP 客户端接入。

## ✨ 特性

- 🔌 **MCP 协议封装**：将 RAG 能力标准化为 6 个 MCP 工具，可被 Claude Desktop、Cherry Studio 等任意 MCP 客户端调用
- 🔍 **混合检索引擎**：向量检索 + BM25 关键词检索 + RRF 融合 + CrossEncoder 重排 + LRU/FAISS 语义缓存
- ⚡ **异步 API 服务**：FastAPI 提供 REST API（检索 / SSE 流式对话 / 文档管理），阻塞推理线程池化、LLM 异步调用
- � **双通道鉴权**：JWT（Web 前端）+ API Key（服务集成），PBKDF2 密码哈希、Key 仅存摘要、支持吊销
- 📁 **数据管线**：后台任务队列 + 文档状态机（pending → parsing → available / duplicate / failed）、文件级/片段级 SHA256 双重去重、同名文档增量替换
- 📊 **质量门禁**：RAGAS 自动化评估（忠实度/相关性/精确率/召回率 + 负样本拒答率），接入 GitHub Actions CI，指标低于阈值自动拦截合并
- 👁️ **可观测性**：structlog 结构化日志（console/JSON）+ 请求 ID 全链路贯穿 + Langfuse 检索/生成 Tracing（未配置自动降级）
- 💬 **Vue3 前端**：流式对话（打字机效果）、检索四阶段可视化、文档生命周期管理、API Key 管理

## 🏗️ 架构

```
┌───────────────────────────────────────────────────────┐
│         Vue3 前端 (localhost:5173)                    │
│  流式对话 · 检索可视化 · 文档管理 · API Key 管理       │
└──────────────────────┬────────────────────────────────┘
                       │ REST / SSE（JWT 鉴权）
┌──────────────────────▼────────────────────────────────┐
│                FastAPI 服务层 (:8000)                  │
│  /api/v1/search · /chat · /documents · /auth          │
│  ─────────────────────────────────────────────        │
│  鉴权(JWT+API Key) · 数据管线(队列/状态机/去重)       │
│  可观测(structlog+Langfuse) · 后台摄入 Worker         │
└──────────────────────┬────────────────────────────────┘
                       │ 进程内直连
┌──────────────────────▼────────────────────────────────┐
│                RAG 引擎层                              │
│  loader → splitter → embedder → vectorstore           │
│  (向量+BM25 混合检索 → RRF 融合 → 重排 → 缓存)         │
└───────────────────────────────────────────────────────┘
                       ▲
                       │ MCP 协议 (stdio)
┌──────────────────────┴────────────────────────────────┐
│   MCP 客户端（Cherry Studio / Claude Desktop）         │
│   search_knowledge · ingest_document · list_docs      │
│   delete_document · web_search · get_time             │
└───────────────────────────────────────────────────────┘

数据存储：Chroma 向量库 · SQLite(注册表/用户) · FAISS(语义缓存)
质量门禁：RAGAS 评估 → GitHub Actions CI
```

## 🚀 快速开始

### 1. 环境要求
- Python 3.10+（推荐 conda）
- Node.js 18+（前端）

### 2. 安装依赖
```bash
git clone https://github.com/<your-username>/mcp-rag-assistant.git
cd mcp-rag-assistant
pip install -r requirements.txt

# 前端
cd frontend && npm install
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env：
#  - LLM_API_KEY / LLM_API_BASE    必填（对话与评估）
#  - JWT_SECRET                    建议配置（否则重启后 token 全部失效）
#  - AUTH_ENABLED                  鉴权开关（默认开启）
#  - LANGFUSE_PUBLIC_KEY/SECRET_KEY 可选（配置后启用 Tracing）
```

> 💡 首次运行会自动下载 BGE embedding 模型（约 400MB）。若网络受限，可设置 `HF_ENDPOINT=https://hf-mirror.com` 使用国内镜像。

### 4. 启动后端 API
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
- Swagger 文档：http://127.0.0.1:8000/docs
- 启动时自动预热模型、同步文档注册表（历史文档自动纳管）

### 5. 启动前端
```bash
cd frontend && npm run dev
```
浏览器访问 http://localhost:5173，注册账号（**首个注册用户自动成为 admin**）。

### 6. 启动 MCP Server（可选）
```bash
python -m mcp_server.server
```

### 7. 运行评估门禁（可选）
```bash
python -m evaluation            # RAGAS 评估 + 质量门禁（exit 1 拦截）
python -m evaluation --no-gate  # 仅评估，不拦截
```

## 🔐 鉴权说明

双通道认证，二选一：

| 通道 | 方式 | 适用 |
|------|------|------|
| JWT | `Authorization: Bearer <token>`（登录获取） | Web 前端 |
| API Key | `X-API-Key: sk-mcprag-xxx`（创建时一次性展示） | 服务/脚本集成 |

公开接口：`/health`、`/docs`、注册、登录。
`AUTH_ENABLED=false` 可关闭鉴权（本地调试用）。

```bash
# 注册（首个用户为 admin）
curl -X POST :8000/api/v1/auth/register -d '{"username":"admin","password":"your-pass"}'
# 登录换 JWT
curl -X POST :8000/api/v1/auth/token -d '{"username":"admin","password":"your-pass"}'
# 业务调用
curl -H "Authorization: Bearer <jwt>" :8000/api/v1/search ...
```

## 🔌 MCP 客户端接入

### Cherry Studio
1. 设置 → MCP 服务器 → 添加
2. 填写配置：

| 字段 | 值 |
|------|-----|
| 名称 | `mcp-rag-assistant` |
| 类型 | `STDIO` |
| 命令 | `<python 绝对路径>` |
| 参数 | `-m mcp_server.server` |
| 工作目录 | `<项目根目录>` |

3. 在对话中勾选 MCP 工具，即可提问触发工具调用

### Claude Desktop
将 `mcp_client_config/claude_desktop_config.json` 内容复制到：
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

## 📦 项目结构

```
mcp-rag-assistant/
├── config.py                 # 全局配置（含评估阈值/鉴权开关）
├── requirements.txt
├── .env.example              # 环境变量模板
├── rag_engine/               # RAG 引擎层
│   ├── loader.py             # 多格式文档加载
│   ├── splitter.py           # 递归切分
│   ├── embedder.py           # 向量化（BGE，离线加载）
│   ├── vectorstore.py        # Chroma 向量库
│   ├── retriever.py          # 混合检索 + RRF + 重排
│   └── cache.py              # LRU + FAISS 语义缓存
├── api/                      # FastAPI 服务层
│   ├── main.py               # 入口：lifespan 预热 + 中间件
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── deps.py               # 引擎单例依赖注入
│   ├── services.py           # 服务层：异步化 + AsyncOpenAI
│   ├── auth.py               # JWT + API Key 鉴权核心
│   ├── dedup.py              # 双重去重索引（文件级/片段级）
│   ├── registry.py           # SQLite 文档状态机
│   ├── worker.py             # 摄入任务队列（后台线程）
│   ├── observability.py      # structlog + 请求ID + Langfuse
│   └── routers/
│       ├── search.py         # 检索接口
│       ├── chat.py           # 对话接口（含 SSE 流式）
│       ├── documents.py      # 文档管理接口
│       └── auth.py           # 认证接口
├── frontend/                 # Vue3 前端
│   └── src/
│       ├── api/              # axios 封装 + SSE 流式解析
│       ├── stores/           # Pinia（JWT 状态）
│       └── views/            # Chat / SearchViz / Documents / ApiKeys
├── evaluation/               # RAGAS 评估 + 质量门禁
│   └── runner.py             # 25 题测试集 → 四指标 → 门禁
├── mcp_server/               # MCP Server 层
│   ├── server.py             # 6 个 MCP 工具注册
│   └── tools/external.py     # 联网搜索等外部工具
├── mcp_client_config/        # MCP 客户端配置示例
├── mcp_client_config/        # MCP 客户端配置示例
├── .github/workflows/ci.yml  # CI：lint + RAGAS 评估门禁
├── docs/                     # 文档（开发问题全记录等）
└── data/                     # 运行时数据（gitignore）
    ├── chroma/               # 向量库
    ├── docs/                 # 上传文档 + 示例文档
    ├── registry.db           # 文档注册表
    └── auth.db               # 用户与 API Key
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| API 服务 | FastAPI + Uvicorn + Pydantic |
| 前端 | Vue3 + Vite + Pinia + axios |
| MCP 协议 | MCP Python SDK (FastMCP) |
| RAG 框架 | LangChain |
| 向量库 | Chroma + FAISS |
| Embedding | BAAI/bge-base-zh-v1.5 |
| 重排 | BAAI/bge-reranker-base (CrossEncoder) |
| 评估 | RAGAS + LLM-as-Judge |
| 可观测 | structlog + Langfuse |
| 鉴权 | JWT (python-jose) + PBKDF2 |
| LLM | 兼容 OpenAI 接口（Qwen / DeepSeek / GPT 等） |

## 🔍 检索流程

```
用户提问
   │
   ├─→ 缓存命中检查（LRU 精确 + FAISS 语义近似，0.3ms）
   │        └─ 命中 → 直接返回
   │
   ├─→ 向量检索（BGE Embedding + Chroma）
   ├─→ BM25 关键词检索（jieba 分词）
   │
   ├─→ RRF 融合（Reciprocal Rank Fusion）
   ├─→ CrossEncoder 重排
   │
   └─→ 写入缓存 → 返回 Top-K
```

## 📊 实验数据

详见 `data/eval/`（RAGAS 评估报告）：

- 重排使 Top1 准确率 66.7% → 100%
- 混合检索命中率较单路向量提升 8.3%
- 缓存命中查询延迟 0.3ms（首查 2.4s）

## 📝 License

MIT
