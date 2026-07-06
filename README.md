# MCP-RAG 智能知识库助手

基于 **MCP（Model Context Protocol）** 协议的智能知识库系统，融合 **RAG 检索增强**与**检索过程可视化**，支持多 MCP 客户端接入。

## ✨ 特性

- 🔌 **MCP 协议封装**：将 RAG 能力标准化为 6 个 MCP 工具，可被 Claude Desktop、Cherry Studio 等任意 MCP 客户端调用
- 🔍 **混合检索引擎**：向量检索 + BM25 关键词检索 + RRF 融合 + CrossEncoder 重排 + 语义缓存
- 📊 **检索过程可视化**：Streamlit 实时展示四阶段检索结果（向量 / BM25 / RRF / 重排）
- 💬 **多轮对话记忆**：支持历史上下文的对话问答，回答带引用标注
- 📁 **文档管理**：支持 PDF / Markdown / docx / txt 多格式文档加载入库

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│   MCP 客户端（Cherry Studio / Claude Desktop）    │
└──────────────────────┬───────────────────────────┘
                       │ MCP 协议 (stdio)
┌──────────────────────▼───────────────────────────┐
│                MCP Server 层                      │
│  search_knowledge · ingest_document · list_docs  │
│  delete_document · web_search · get_time         │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│   可视化前端 (Streamlit)                          │
│   检索过程可视化 · 多轮对话 · 文档管理            │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│                RAG 引擎层                         │
│  loader → splitter → embedder → vectorstore      │
│  (向量+BM25 混合检索 → RRF 融合 → 重排 → 缓存)    │
└──────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 环境要求
- Python 3.10+
- 推荐使用 conda 管理环境

### 2. 安装依赖
```bash
git clone https://github.com/<your-username>/mcp-rag-assistant.git
cd mcp-rag-assistant
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key（可选，不填则只展示检索片段）
```

> 💡 首次运行会自动下载 BGE embedding 模型（约 400MB）。若网络受限，可设置 `HF_ENDPOINT=https://hf-mirror.com` 使用国内镜像。

### 4. 启动可视化前端
```bash
streamlit run web_ui/app.py
```
浏览器访问 http://localhost:8501，点击侧边栏「📚 加载示例文档入库」即可开始检索。

### 5. 启动 MCP Server
```bash
python -m mcp_server.server
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
├── config.py                 # 全局配置
├── requirements.txt
├── .env.example              # 环境变量模板
├── rag_engine/               # RAG 引擎层
│   ├── loader.py             # 多格式文档加载
│   ├── splitter.py           # 递归切分
│   ├── embedder.py           # 向量化（BGE，离线加载）
│   ├── vectorstore.py        # Chroma 向量库
│   ├── retriever.py          # 混合检索 + RRF + 重排
│   └── cache.py              # LRU + FAISS 语义缓存
├── mcp_server/               # MCP Server 层
│   ├── server.py             # 6 个 MCP 工具注册
│   └── tools/external.py     # 联网搜索等外部工具
├── web_ui/
│   └── app.py                # Streamlit 可视化前端
├── mcp_client_config/        # MCP 客户端配置示例
└── data/docs/                # 示例文档
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| MCP 协议 | MCP Python SDK (FastMCP) |
| RAG 框架 | LangChain |
| 向量库 | Chroma + FAISS |
| Embedding | BAAI/bge-base-zh-v1.5 |
| 重排 | BAAI/bge-reranker-base (CrossEncoder) |
| 前端 | Streamlit |
| LLM | 兼容 OpenAI 接口（Qwen / DeepSeek / GPT 等） |

## 🔍 检索流程

```
用户提问
   │
   ├─→ 缓存命中检查（LRU 精确 + FAISS 语义近似）
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

## 📝 License

MIT
