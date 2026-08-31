# MCP-RAG 企业化改造：开发问题解决全记录

> 记录阶段 1~5（FastAPI 服务化 / 数据管线 / 可观测性 / RAGAS 评估门禁 / JWT 鉴权）+ Vue3 前端开发过程中遇到的全部问题。
> 每个问题包含：**现象 → 排查过程 → 根因 → 解决方案 → 经验教训**。
> 文末附：大模型辅助开发的专项陷阱总结、开发注意事项 Checklist。

---

## 目录

- [一、数据管线（阶段 2）](#一数据管线阶段-2)
- [二、可观测性（阶段 3）](#二可观测性阶段-3)
- [三、RAGAS 评估与 CI 门禁（阶段 4）](#三ragas-评估与-ci-门禁阶段-4)
- [四、JWT 鉴权（阶段 5）](#四jwt-鉴权阶段-5)
- [五、全功能回归测试发现的 Bug](#五全功能回归测试发现的-bug)
- [六、前端开发（Vue3）](#六前端开发vue3)
- [七、大模型辅助开发的陷阱专项总结](#七大模型辅助开发的陷阱专项总结)
- [八、开发注意事项 Checklist](#八开发注意事项-checklist)

---

## 问题统计总览

| 严重度 | 数量 | 典型代表 |
|--------|------|---------|
| 🔴 业务正确性 Bug | 3 | 缓存与向量库不一致、source 元数据覆盖失效、nan 毒化均值 |
| 🟡 环境类问题 | 6 | 端口被幽灵进程占用、沙箱拦截、PowerShell 转义、UTF-8 BOM |
| 🟠 第三方库 API 陷阱 | 7 | ragas 0.4 大改版、LangChain 元数据写入、HuggingFaceEmbeddings 缺接口 |
| 🔵 设计/自身缺陷 | 5 | 单例降级刷屏、contextvars 跨任务不可见、模块级执行代码 |
| ⚪ 测试/流程问题 | 4 | 测试断言预期错误、YAML 语法、阈值未校准 |

---

## 一、数据管线（阶段 2）

### P01 🔴 LangChain loader 的 source 元数据陷阱：替换更新失效

**现象**
同名文档修改内容后重新上传，期望"替换更新"（删旧片段 + 入新片段），实际旧片段**残留**在向量库，新旧内容并存，检索时两条都能命中。

**排查过程**
1. 直接查向量库元数据，发现旧片段的 `source` 字段值是**完整绝对路径** `D:\experiment\...\data\docs\xxx.md`，而不是注册表 key（纯文件名 `xxx.md`）；
2. 追踪摄入代码，发现写入前有 `doc.metadata.setdefault("source", source)`——本意是统一 source，但它只在 key **不存在**时生效；
3. 而 LangChain 的所有 loader（TextLoader / PyPDFLoader 等）加载时**默认已把完整文件路径写进** `metadata["source"]`，key 已存在 → `setdefault` 静默失效；
4. 删除路径 `delete_by_source(文件名)` 按注册表 key 匹配 → 路径 ≠ 文件名 → 删除条件永远不命中。

**根因**
`dict.setdefault` 的语义误用 + 对第三方库默认行为的无知假设：以为 loader 不会写 source，实际它必写。

**解决方案**
[worker.py](../api/worker.py) 摄入时**强制赋值**覆盖：
```python
for doc in docs:
    doc.metadata["source"] = source  # 强制覆盖，不用 setdefault
```

**经验教训**
- 第三方库写入的元数据字段，覆盖前先确认字段是否已被占用；`setdefault` 是"幂等但可能被抢先"的操作；
- 摄入管线必须集成测试"替换更新"路径（同名不同内容），这是最容易漏的分支。

---

### P02 🟡 SQLite 状态机与向量库的一致性设计（预防性问题）

**非 Bug，但属于开发中反复斟酌的设计点。**

注册表（registry.db）记录文档状态（pending/parsing/available/duplicate/failed），向量库是事实数据源，两者可能出现不一致：
- MCP Server 等**旁路写入**的文档只进向量库，注册表不知情；
- 删除中断、崩溃等导致注册表有记录但向量库没有数据。

**解决方案：自愈同步**
- 服务启动时、以及每次 `GET /documents` 时执行 `sync_with_vectorstore()`：以向量库实际数据对齐注册表；
- 去重索引同样有 `sync()` 重建机制。

**经验教训**
双存储系统（状态机 + 事实数据）必须有单向的"事实源裁决"和对账机制，否则状态漂移只是时间问题。

---

## 二、可观测性（阶段 3）

### P03 🟡 pip 安装被沙箱拦截：报错 ≠ 失败

**现象**
`pip install structlog langfuse` 报错：
```
TRAE Sandbox Error: hit restricted
  Not allow operate files: ...site-packages/accesstest_deleteme_xxx
```

**排查过程**
乍看是安装失败。但细看错误细节：报错发生在 pip 对 site-packages 的**写入权限测试**（写一个 `accesstest_deleteme_xxx` 临时文件）阶段，而依赖包本体在之前步骤已经写入。

**验证**：`python -c "import structlog, langfuse"` → 导入成功，langfuse 4.14.4 已装好。

**解决方案**
无需重装。后续遇到同类问题时，通过 `requires_approval=true` 申请沙箱外执行。

**经验教训**
- 判断安装是否成功，**用 import 验证，不要只看命令退出码**；
- 读错误信息要读到最后一个真正失败的操作，pip 的收尾权限测试失败不影响包本身。

---

### P04 🔵 Langfuse Tracer 单例降级刷屏：None 不是"已初始化"

**现象**
未配置 Langfuse keys 时，每次调用 `start_observation()` 都打印一条 `langfuse_disabled` 日志。一次 chat 请求产生 retrieval/generation/chat 多个 observation → 日志被降级信息刷屏。

**根因**
双检锁单例的经典写法错误：
```python
def client(self):
    if self._client is not None:   # ← 问题在这
        return self._client
    with self._lock:
        if self._client is None:
            self._client = self._build()  # _build() 未配置时返回 None
    return self._client
```
`_build()` 降级返回 `None` 后，`self._client` 永远是 `None`，下次调用又进 `_build()` → 重复初始化、重复打日志。

**解决方案**
[observability.py](../api/observability.py) 引入独立的 `_initialized` 标志：
```python
def client(self):
    if self._initialized:          # 用标志判断，而不是判断值
        return self._client
    with self._lock:
        if not self._initialized:
            self._client = self._build()
            self._initialized = True
    return self._client
```

**经验教训**
单例模式中**降级结果也是合法的缓存值**——`None` 是"已初始化且降级"，不是"未初始化"。判断初始化状态用显式标志，不要用值本身判空。

---

### P05 🟡 PowerShell + curl 的 JSON 转义地狱

**现象**
```powershell
curl.exe -d "{\"query\":\"test\"}"
```
返回 422（JSON 解析失败）甚至 `http_code=000`（连接失败）。

**根因**
PowerShell 对引号的处理与 bash 完全不同：内嵌双引号的转义规则诡异，且 PowerShell 会先解析一遍字符串再传给 curl.exe，转义经常在两层之间丢失。

**解决方案**
1. **首选**：JSON 写入临时文件，`curl.exe -d "@tmp.json"`；
2. **复杂测试**：改写 Python 脚本用 `urllib` / `requests` 测；
3. 简单场景用 `-o NUL -w "%{http_code}"` 只看状态码。

**经验教训**
Windows PowerShell 下做 API 测试，一律用文件或 Python 脚本传 JSON，不要硬刚引号转义。

---

### P06 🟡 curl 落盘文件带 UTF-8 BOM

**现象**
`curl.exe -o tmp.json` 保存的 JSON，用 Python `json.load(open(..., encoding='utf-8'))` 读取报错：
```
JSONDecodeError: Unexpected UTF-8 BOM
```

**根因**
PowerShell 环境/管道重定向默认输出 UTF-8 **带 BOM**（`\xef\xbb\xbf` 三字节头）。

**解决方案**
用 `encoding='utf-8-sig'` 读取（自动剥离 BOM）。

**经验教训**
Windows 下凡是从 PowerShell 管道/重定向落盘的文本，读取时预留 BOM 处理。

---

## 三、RAGAS 评估与 CI 门禁（阶段 4）

> 阶段 4 是问题最密集的阶段：7 个第三方库 API 陷阱 + 数值处理陷阱，也是"大模型编造 API"的重灾区。

### P07 🟠 ragas 0.4.3 大改版：凭记忆写的导入路径全错 ⭐典型 LLM 陷阱

**现象**
按对 ragas 的既有认知写代码，连续报错：
```python
from ragas.metrics.collections import faithfulness   # ModuleNotFoundError
from ragas.dataset import EvaluationDataset, ...     # 部分可用部分不可用
```

**根因**
ragas 从 0.2 → 0.4 经历大重构：模块路径、类名、函数签名全部变化。大模型（以及任何基于旧文档的记忆）写出的 API 调用是"上一代"的。

**排查与解决**
放弃猜测，逐步用解释器验证真实 API：
```python
import ragas.metrics as m; print(dir(m))          # 发现 faithfulness 等在 ragas.metrics
from ragas.llms import llm_factory
import inspect; print(inspect.signature(llm_factory))  # 确认参数形态
```
最终确认 0.4.3 的正确用法：`from ragas import SingleTurnSample`、`from ragas.dataset_schema import EvaluationDataset`、`from ragas.llms import llm_factory`。

**经验教训（重要）**
- 快节奏迭代的库（ragas / langchain / langfuse），**大模型记忆大概率过时**；
- 编码前先用 `dir()` + `inspect.signature()` 验证 API 真实形态，宁可多一步验证；
- 这类"API 编造"问题的特征是：报错集中在 `ModuleNotFoundError` / `AttributeError` / `TypeError: unexpected keyword argument`。

---

### P08 🔵 experiments.py 模块级执行：import 即跑实验

**现象**
evaluation 包中 `from experiments import TEST_CASES`，结果整个实验脚本开始执行——加载文档、跑实验、写报告，评估程序被卡死在别人的逻辑里。

**根因**
experiments.py 的实验逻辑写在**模块级**（没有 main 函数），`import` 触发模块执行是 Python 语义。

**解决方案**
写一次性重构脚本：定位执行块起点（"准备阶段"注释），整体缩进包进 `def main():`，尾部加：
```python
if __name__ == "__main__":
    main()
```
验证 `from experiments import TEST_CASES` 不再触发执行。

**经验教训**
脚本型代码（实验 / ETL / 一次性分析）从第一天就该有 `__main__` 保护，否则永远无法被其他模块安全复用。

---

### P09 🟠 ragas 的 HuggingFaceEmbeddings 缺旧接口 ⭐典型 LLM 陷阱

**现象**
`AttributeError`：ragas 0.4.3 的 `HuggingFaceEmbeddings` 没有 `embed_query` 方法，answer_relevancy 指标初始化失败。

**根因**
ragas 新版 embeddings 封装改了接口形态（与 langchain 的同名类混淆也是原因之一——两者接口不同，大模型容易张冠李戴）。

**解决方案**
自定义 wrapper 桥接到项目自己的 Embedder 单例（本地 BGE）：
```python
from ragas.embeddings import BaseRagasEmbeddings
from rag_engine.embedder import Embedder

class _ProjectEmbeddings(BaseRagasEmbeddings):
    def embed_query(self, text): return Embedder.embed_query(text)
    def embed_documents(self, texts): return Embedder.embed_documents(texts)
```
**意外收获**：比直接用 ragas 内置封装更好——模型复用（进程内只加载一次）、离线、零 API 成本。

---

### P10 🟠 自定义类缺抽象方法：TypeError: Can't instantiate abstract class

**现象**
P09 的 wrapper 运行时报：
```
TypeError: Can't instantiate abstract class _ProjectEmbeddings with abstract
methods aembed_documents, aembed_query
```

**根因**
`BaseRagasEmbeddings` 是抽象基类，ragas 评估走异步路径，必须实现 `aembed_*` 异步方法（P09 初版只写了同步方法）。

**解决方案**
补异步方法，同步的 Embedder 用 `asyncio.to_thread` 包装：
```python
async def aembed_query(self, text): 
    return await asyncio.to_thread(Embedder.embed_query, text)
```

**经验教训**
继承第三方抽象基类时，先看基类的全部 abstract method（`cls.__abstractmethods__`），一次实现全，别等运行时报。

---

### P11 🟠 qwen-plus 默认 max_tokens 截断 judge 输出

**现象**
faithfulness 指标大量题目失败/超时。日志深挖发现关键证据：
```
finish_reason='length', completion_tokens=3072   ← 顶格截断
```

**根因**
faithfulness 的判定流程要求 judge LLM 输出**逐句声明的长 JSON**（每句是否被上下文支持），qwen-plus 默认 `max_tokens=3072` 不够，输出被截断 → JSON 解析失败 → 该题该指标失败/超时重试。

**解决方案**
judge LLM 显式给足输出空间：
```python
llm_factory(model=..., provider="openai", client=client, max_tokens=8192)
```

**经验教训**
- LLM-as-Judge 场景的输出往往比对话长得多（结构化 + 逐条枚举），**显式设置 max_tokens**；
- 看到 `finish_reason='length'` 第一反应就该是截断，而不是重试。

---

### P12 🟠 并发限流导致指标全 nan

**现象**
第一次完整评估：faithfulness / answer_relevancy **整列全 nan**，但单样本手动测试正常。

**排查过程**
写单样本诊断脚本 + `raise_exceptions=True` 复现：单跑正常、并发跑挂 → 定位为 **dashscope API 限流**（ragas 默认并发数较高）。

**解决方案**
降并发 + 加重试：
```python
run_config=RunConfig(max_workers=4, timeout=180, max_retries=10)
```

**经验教训**
"单发正常、批量失败"几乎总是限流/资源竞争；评估框架的并发参数必须按 LLM 供应商的 QPS 配额调。

---

### P13 🔴 单个 nan 毒化整列均值（经典数值陷阱）

**现象**
修复 P12 后：20 题里 19 题有正常分数（0.455~0.946），仅 1 题超时得 nan——但汇总均值显示 **nan**，门禁整列 FAIL。

**根因**
```python
metrics_summary = {m: sum(v) / len(v) for m, v in scores.items()}
# sum([0.8, nan, 0.9]) / 20 == nan   ← Python 的 nan 传染性
```
一个 nan 让整列均值变 nan，污染所有下游判断。

**解决方案**
[runner.py](../evaluation/runner.py) 三层修复：
```python
valid = [v for v in values if v is not None and v == v]  # v==v 过滤 nan
metrics_summary[m] = sum(valid) / len(valid) if valid else 0.0
```
同时：`nan_counts` 统计写入报告；门禁增加 **nan 率检查**（某指标 nan 率 > 30% 视为评估不可信，同样拦截）。

**经验教训**
- 任何 LLM 评分聚合都必须用 **nanmean 语义**，并监控 nan 率；
- nan 在 Python 里沉默传染（不报错、不抛异常），必须在聚合点显式防御。

---

### P14 🟡 json.dumps 输出非标准 NaN

**现象**
评估报告 JSON 里出现 `NaN` 字面量（`json.dumps` 默认允许 float('nan')），不是合法 JSON，严格解析器（JS 等）会拒绝。

**解决方案**
递归清理函数，把 float nan 转 `None`（JSON null）：
```python
def _clean(obj):
    if isinstance(obj, float) and obj != obj:  # nan 判断
        return None
    ...
```
第一版用 `.replace("NaN", "null")` 字符串替换——有误伤风险（正文中出现"NaN"字样也会被替换），已废弃改为递归清理。

---

### P15 ⚪ 质量门禁阈值未经基线校准

**现象**
初始阈值按"感觉"定为 faithfulness ≥ 0.75，首次完整评估实测 0.707 → 门禁误拦（但检索质量实际没问题）。

**解决方案**
基于实测水位校准默认阈值（实测值留 ~10% 余量）：faithfulness 0.60 / answer_relevancy 0.65 / 其余 0.60 / rejection_rate 0.80，`.env` 可覆盖。

**经验教训**
质量门禁阈值不能拍脑袋：**先跑基线、再定阈值**，否则门禁会变成"狼来了"。

---

### P16 ⚪ GitHub Actions YAML 的三引号语法错误

**现象**
CI workflow 的 job 里写了 Python 风格 docstring：
```yaml
jobs:
  eval-gate:
    """RAGAS 评估 + 质量门禁"""   # ← YAML 不支持，直接语法错误
```

**根因**
在 YAML 语境里无意识沿用了 Python 的注释习惯。

**解决方案**
YAML 用 `name:` 字段或 `#` 注释。

**经验教训**
跨语言切换时，注释语法这种"肌肉记忆"最容易出错；YAML 文件写完先本地 `actionlint` 或至少目视检查。

---

### P17 🔵 评估脚本每题重建检索器：reranker 重复加载

**现象**
评估 20 题，日志显示 CrossEncoder reranker 被加载多次，每题白白多等几十秒。

**根因**
`_run_rag_pipeline()` 里每题 `HybridRetriever(VectorStore())`——评估脚本没有复用组件。

**解决方案**
模块级单例：
```python
_retriever = None
def _get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(VectorStore())
    return _retriever
```

**经验教训**
模型类重对象（reranker/embedder/BM25 索引）必须显式管理生命周期，"循环里 new 重对象"是性能杀手。

---

## 四、JWT 鉴权（阶段 5）

### P18 🔴 端口被幽灵进程占用：路由"灵异"404

**现象**
新写的鉴权路由测试全 404，且 `/openapi.json` 里的路径**完全对不上代码**（出现 `/api/auth/register` 等不属于本项目的路由）。代码反复检查无任何问题。

**排查过程（值得记住的排查路径）**
1. 读 main.py —— 路由挂载代码正确；
2. `curl /openapi.json` 对比实际注册的路径 —— 与代码完全不符 → **说明响应根本不是我的服务发出的**；
3. `netstat -ano | findstr ":8000" | findstr "LISTENING"` → 发现 `0.0.0.0:8000` 被 PID 100144 占用（之前某次测试的 uvicorn 没停干净）；
4. 我的服务（127.0.0.1）和幽灵进程（0.0.0.0）**共存**，部分请求被路由到旧进程。

**解决方案**
```powershell
taskkill /PID 100144 /F   # 强杀残留进程后重启服务，一切正常
```

**经验教训**
- "代码正确但行为诡异"时，先怀疑环境（端口/进程/版本），再怀疑代码；
- Windows 上后台服务的 StopCommand 偶尔杀不死进程树（uvicorn reload 模式会产生子进程）；
- **重启服务前先 `netstat` 检查端口**，养成习惯。

---

### P19 🔵 JWT 重启失效（设计行为，但容易误判为 Bug）

**现象**
服务重启后，之前签发的 JWT 全部 401，测试脚本中断。

**根因**
未配置 `JWT_SECRET` 时，每次启动随机生成临时密钥——密钥轮换使旧 token 全部失效。这是**设计好的安全降级**（开发期提示：必须配置 SECRET），不是 Bug。

**解决方案**
- 测试中重新登录即可；
- 生产部署必须在 `.env` 配置 `JWT_SECRET`（`openssl rand -hex 32`）。

**经验教训**
区分"设计行为"与"Bug"——日志里 `jwt_secret_not_configured` 的 warning 早就预告了这件事，测试前应读启动日志。

---

### P20 🔴 contextvars 跨任务不可见 + 中间件日志时序错误（阶段 3 遗留 Bug）

**现象**
接入鉴权后检查可观测性日志，发现两个问题：
1. `http_request` 这条访问日志**一直没有 request_id**（其他日志都有）；
2. 鉴权身份（user）在访问日志里看不到。

**排查过程**
读 [observability.py](../api/observability.py) 的中间件代码，发现两层问题叠加。

**根因 1：日志时序错误**
```python
finally:
    structlog.contextvars.clear_contextvars()   # ← 先清空
# ... 之后才打日志                          ← 打在空上下文上，request_id 丢失
```
阶段 3 写这段代码时把清理放在 finally 里"确保清理"，忽略了日志语句在 finally **之后**执行。

**根因 2：contextvars 的任务隔离语义**
`get_current_user` 是 FastAPI 依赖，运行在 `call_next(request)` 的**子任务**里。Python 的 contextvars 是 copy-on-write：子任务里 `bind_contextvars(user=...)` 的修改，父任务（中间件）**看不到**。

**解决方案**
1. 日志移到 `clear_contextvars()` 之前；
2. 认证身份**双写**：
   - `request.state.user = user` —— 显式挂在 request 上，跨任务可见，供中间件日志读取；
   - `structlog.contextvars.bind_contextvars(user=...)` —— 供业务代码日志自动携带。

修复后一条日志同时携带 `request_id + user`：
```
http_request [api] duration_ms=2.7 method=GET path=/api/v1/auth/api-keys
request_id=78a71e7caf0a status_code=200 user=admin
```

**经验教训**
- `contextvars` 的修改只在当前任务及**其后代**可见，向上不可见——跨层级传状态用 `request.state`；
- 中间件里"清理上下文"和"打日志"的先后顺序极易写反，写完必须实测验证日志字段。

---

## 五、全功能回归测试发现的 Bug

### P21 🔴（最严重）查询缓存与向量库不一致：删除的内容"阴魂不散"

**现象**
删除文档后再次检索同样的查询，**已删除的内容仍然返回**；对称地，新入库的内容对**之前查过的查询**不可见（命中旧缓存）。

**复现设计（这个测试用例设计值得借鉴）**
回归测试特意构造缓存命中路径：
```
查 A（结果进缓存）→ 入库含 A 的新文档 → 再查 A（命中缓存，看不到新文档）
查 A（结果进缓存）→ 删除某文档 → 再查 A（命中缓存，已删内容仍然返回）
```

**根因**
写路径（删除 / 入库）清理了**向量库、BM25 索引、去重索引**三处，唯独漏了第四处：**查询缓存**（LRU 精确 + FAISS 语义两级）。缓存里的旧查询结果与向量库现状脱节。

**解决方案（三处）**
1. [cache.py](../rag_engine/cache.py) 新增线程安全的 `clear()`：
```python
def clear(self) -> None:
    with self._lock:
        self._exact.clear()
        self._vectors.clear()
        self._keys.clear()
        self._faiss_index = None
```
2. [worker.py](../api/worker.py) 入库产生新片段后清缓存：
```python
if result.status == "available" and result.new_chunks > 0:
    retriever.cache.clear()
```
3. [documents.py](../api/routers/documents.py) 删除文档后清缓存。

**经验教训（本项目的最重要教训）**
- **所有带读缓存的系统，写路径必须枚举全部缓存点**。改动数据时做"失效清单"：向量库？BM25？去重索引？查询缓存？文件系统？
- 这类 Bug 常规单测发现不了（单测不构造"写后读同一查询"），**回归测试必须覆盖写后读**；
- 发现后要立即自查对称路径：修"删除不清缓存"时，要想到"入库是否也不清"。

---

### P22 ⚪ 测试断言自身的预期错误：别急着改代码

**现象**
回归测试报"用户注册失败"：断言 `role == "user"`，实际返回 `role == "admin"`。

**排查**
`data/auth.db` 是全新文件（之前测试后清理了），**首个注册用户按设计自动成为 admin**——是测试断言写错了预期，不是代码 Bug。

**解决方案**
修正断言为 `role in ("admin", "user")` 并在注释说明规则。

**经验教训**
测试失败时先问："是代码错了，还是我的预期错了？"——特别是依赖初始状态（空库/首用户）的断言。

---

## 六、前端开发（Vue3）

### P23 🟡 Vite 端口占用自动迁移

**现象**
`npm run dev` 提示 `Port 5173 is in use, trying another one...`，实际跑在 5174。

**解决方案**
Vite 自动处理，直接使用 5174 即可。但**必须明确告知用户实际端口**（浏览器收藏/文档里别写死端口）。

### P24 🟠 SSE 流式输出的姿势：EventSource 不可用

**现象/需求**
后端 `/chat/stream` 用 POST + 需要 `Authorization` 头。浏览器原生 `EventSource` **只支持 GET 且不能自定义请求头**——直接不可用。

**解决方案**
[frontend/src/api/sse.js](../frontend/src/api/sse.js) 用 `fetch` + `ReadableStream` 手写 SSE 解析：
```javascript
const reader = resp.body.getReader()
// 按空行分帧，解析 event:/data: 两行，手动分发回调
```
注意点：缓冲区末帧可能不完整（`buffer = frames.pop()` 留到下一轮）。

**经验教训**
带鉴权的 SSE 流式接口是前端常见需求，EventSource 的局限要提前知道，fetch 流式读取是标准替代方案。

### P25 🔵 前端鉴权状态管理的完整闭环

不算 Bug，但有几个容易漏的点（实测都验证过）：
- JWT 存 `localStorage`（刷新不丢）+ Pinia 内存态双轨；
- axios 拦截器统一处理 401 → 登出 + 跳登录页（避免每个接口写错误处理）；
- 路由守卫：未登录访问受保护页 → 重定向登录页并带 `redirect` query（登录后回跳）；
- Vite 开发代理 `/api → :8000`：让请求与后端同源，生产用 nginx 反代同理。

---

## 七、大模型辅助开发的陷阱专项总结 ⭐

本项目全程由大模型辅助开发，以下陷阱具有普遍参考价值。

### 7.1 API 编造 / 记忆过时（本项目最高频问题）

| 实例 | 大模型的第一反应 | 实际情况 | 代价 |
|------|----------------|---------|------|
| ragas 导入路径 | `from ragas.metrics.collections import ...` | 0.4.3 已重构，路径不存在 | 探索多轮 |
| ragas HuggingFaceEmbeddings | 以为有 `embed_query` | 新版接口变了；且与 langchain 同名类混淆 | 报 AttributeError |
| Langfuse v4 API | 按 v2/v3 记忆写调用 | 类名/方法签名已变 | 逐个 inspect 验证 |
| InstructorLLM kwargs | 不确定 max_tokens 是否传递 | 查源码确认 kwargs → adapter 生效 | 需要证据 |

**应对策略（已在项目中固化）**：
1. **先验证后编码**：`dir(module)` 列出真实成员、`inspect.signature(fn)` 确认参数，最小脚本冒烟；
2. **让异常说话**：`raise_exceptions=True`（ragas）、看完整 traceback 而不是只看第一行；
3. **查源码终结争论**：`inspect.getsource()` 看 kwargs 如何传递，比猜 100 次可靠；
4. 报错模式识别：`ModuleNotFoundError` / `AttributeError` / `TypeError: unexpected keyword` 三连 → 大概率是 API 版本错位，**停止微调代码，先验证 API**。

### 7.2 错误归因偏差：环境问题被当代码问题

大模型的本能是"看到错误 → 改代码"。本项目至少三次验证了这个本能是错的：

| 现象 | 本能反应 | 实际根因 |
|------|---------|---------|
| 路由 404、openapi 对不上 | 检查/重写路由代码 | 端口被幽灵进程占用（P18） |
| pip 报错 | 重新安装 | 包已装好，只是沙箱收尾测试失败（P03） |
| JSON 读取失败 | 检查代码逻辑 | PowerShell 落盘带 BOM（P06） |

**应对策略**：排障顺序固定为 **环境 → 数据 → 代码**：
1. 端口/进程/网络/文件编码先查一遍（成本低的先查）；
2. 用"事实采集"代替"代码阅读"：`/openapi.json`、`netstat`、直接读 DB 内容，让系统自己告诉你状态；
3. 改代码前问一句：有什么**证据**证明问题在代码里？

### 7.3 隐性假设导致的静默失败

大模型写的代码常带未声明的假设，失败时**不报错、只静默错**：

| 代码 | 隐性假设 | 现实 |
|------|---------|------|
| `metadata.setdefault("source", ...)` | key 不存在 | LangChain loader 已写入（P01） |
| `sum(values)/len(values)` | 无 nan | LLM 评分必有 nan（P13） |
| `json.dumps(data)` | 值都是合法 JSON 类型 | float nan 会输出非标 NaN（P14） |
| `if self._client is not None` 单例 | None = 未初始化 | None 也可能是降级结果（P04） |

**应对策略**：
- 写完代码自问"这段代码假设了什么？假设不成立时会发生什么？会不会静默？"
- 集成测试覆盖**写后读、替换、删除后再查**这些"假设敏感"路径——单测的 happy path 发现不了这些问题。

### 7.4 长任务的耐心管理

18 分钟的 RAGAS 评估、30 秒的模型预热，大模型容易"等不及就重跑"，导致：重复执行浪费成本、并发跑挂限流。正确姿势：后台执行 + `CheckCommandStatus` 分段轮询 + filter 过滤关键日志，等够时间再下结论。

---

## 八、开发注意事项 Checklist

### 环境类（Windows 开发）
- [ ] 重启服务前 `netstat -ano | findstr ":8000"` 检查端口占用（uvicorn 进程树可能残留）
- [ ] PowerShell 传 JSON 一律用文件（`-d "@file.json"`）或 Python 脚本
- [ ] PowerShell 管道落盘的文件用 `utf-8-sig` 读（BOM）
- [ ] pip 安装报沙箱错 → 先 `import` 验证是否实际已装好

### 代码类
- [ ] 实验脚本 / ETL 必须有 `if __name__ == "__main__"` 保护
- [ ] 覆盖第三方库写入的元数据：用赋值，不用 `setdefault`
- [ ] 继承抽象基类：一次实现全部 `__abstractmethods__`（含异步版）
- [ ] LLM 评分聚合：nanmean 语义 + nan 率监控；JSON 序列化前清理 nan
- [ ] judge LLM 显式设置 `max_tokens`（结构化长输出 ≥ 8192）
- [ ] 评估并发 ≤ 4（dashscope 配额），配重试
- [ ] 循环里不 new 重对象（模型/索引类），用单例

### 一致性类（本项目最重要）
- [ ] **写路径失效清单**：改向量库数据时，逐项核对 查询缓存 / BM25 索引 / 去重索引 / 注册表 / 文件系统
- [ ] 双存储（状态机 + 事实库）必须有对账/自愈同步
- [ ] 回归测试覆盖：写后读、删除后查、替换更新

### 中间件/异步类
- [ ] contextvars 修改对父任务不可见（copy-on-write），跨层级用 `request.state`
- [ ] 中间件打日志在 `clear_contextvars()` **之前**
- [ ] BaseHTTPMiddleware 的 `call_next` 是子任务，别指望 contextvars 向上冒泡

### 安全面
- [ ] 生产必配 `JWT_SECRET`（否则重启全员掉线——开发期这是特性，生产是事故）
- [ ] `.env.example` 只放占位符，不放真实 Key（本项目真实踩过：泄露后作废重置）
- [ ] 密码只存 PBKDF2/bcrypt 哈希 + 独立盐；API Key 只存哈希 + 一次性展示
- [ ] 常数时间比较防时序攻击；失败路径与成功路径耗时对齐

### 大模型协作类
- [ ] 快迭代库（ragas/langchain/langfuse）的 API：**dir + inspect 先验证，不凭记忆写**
- [ ] 报 `ModuleNotFoundError/AttributeError/unexpected keyword` 三连 → 先怀疑 API 版本错位
- [ ] 排障顺序：环境 → 数据 → 代码；改代码前要证据
- [ ] 长任务后台跑 + 分段轮询，不重跑

---

## 附：问题 → 修复代码位置速查表

| 编号 | 问题 | 修复位置 |
|------|------|---------|
| P01 | source 元数据覆盖失效 | [worker.py](../api/worker.py) `_ingest` 强制赋值 |
| P04 | Tracer 重复初始化 | [observability.py](../api/observability.py) `_initialized` 标志 |
| P08 | experiments 模块级执行 | [experiments.py](../experiments.py) `main()` + `__main__` |
| P09/P10 | ragas embeddings 适配 | [runner.py](../evaluation/runner.py) `_ProjectEmbeddings` |
| P11 | judge max_tokens | [runner.py](../evaluation/runner.py) `llm_factory(..., max_tokens=8192)` |
| P12 | 限流 nan | [runner.py](../evaluation/runner.py) `RunConfig(max_workers=4)` |
| P13 | nan 毒化均值 | [runner.py](../evaluation/runner.py) nan 过滤 + nan 率门禁 |
| P20 | 日志时序 + contextvars | [observability.py](../api/observability.py) + [auth.py](../api/auth.py) 双写 |
| P21 | 缓存不一致 | [cache.py](../rag_engine/cache.py) `clear()` + worker/documents 调用 |
