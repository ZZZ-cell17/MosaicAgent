# MosaicAgent 项目上下文与开发交接

> 用途：供新的项目对话快速了解当前仓库、已完成工作、真实运行链路、重要代码和代码阅读顺序。
>
> 更新时间：2026-09-04
>
> 定位说明：MosaicAgent 对外是一个可写入项目经历的个人工程项目，不是学习 Demo；本文档保留代码阅读与学习建议，仅用于帮助项目维护者掌握实现。

## 1. 项目一句话定位

MosaicAgent 是面向企业软件项目技术资料的、从 JoyAgent-JDGenie 的 MRAG 模块中抽取并独立工程化的多模态 RAG 单 Agent 知识问答项目。

它解决两个核心问题：

1. 将 PDF、DOCX、Markdown、TXT 和图片处理成文本、独立图片、完整页面三类可检索证据。
2. 由一个有边界的 Agent 进行查询扩展、四路检索、证据充分性判断、多轮改写、文本重排、LLM/VLM 路由和带引用回答。

项目目标不是复刻完整 JoyAgent 平台，而是围绕多模态文档问答重新定义产品边界，保留 MRAG + 单 Agent 核心链路，并补齐独立运行、安全边界、可观测性和轻量前端，形成完整的个人工程项目。

## 2. 仓库与 Git 状态

- 当前仓库：本文档所在的 MosaicAgent 仓库根目录
- 原项目参考：JoyAgent-JDGenie MRAG，上游链接见 `README.md`
- 第一阶段移出内容备份：保存在本地仓库外，不纳入 Git
- 当前完整分支：`feat/phase-4-react-workbench`
- 注意：`main` 仍停留在第一阶段基线，不包含后续完整功能。开发和运行时不要误切回 `main`。

关键提交按时间排列：

```text
b9d6aeb chore: establish MosaicAgent phase 1 baseline
4833ada feat: add local MRAG runtime workflow
dfed41a fix: complete the real MRAG workflow
32c862e fix: delete vectors from every modality
5876428 feat: add observable single-agent runtime
dc3c3fe fix: harden MRAG ingestion and runtime boundaries
506b7fc feat: add lightweight React MRAG workbench
41b371f fix: improve frontend runtime resilience
```

创建本文件前，工作区是干净的。

## 3. 从原项目保留和删除了什么

### 保留

- MRAG 文档解析、切分、OCR、Caption 和页面渲染
- 文本 Embedding、BM25 稀疏向量、多模态 Embedding
- 文本、独立图片、完整页面三类索引
- 查询扩展、四路召回、证据摘要、充分性判断、查询改写
- 多轮检索、去重、Reranker、LLM/VLM 动态路由
- Qdrant 向量存储和 SQLite 元数据
- FastAPI、SSE 流式协议、本地文件存储
- 原项目 MRAG 架构图、示例图、许可证和第三方声明

### 删除

- Data Agent、Table RAG、NL2SQL、Deep Search
- Analysis、Report、Code Interpreter、SOP
- 原多 Agent 任务编排
- Java 后端和原完整 Web UI
- 与上述能力绑定的模型、Prompt、数据库表、依赖和通用文件服务

删除这些模块是为了让项目聚焦多模态文档问答，避免 Data Agent、NL2SQL 和复杂多 Agent 编排扩大产品边界，并降低部署依赖和维护成本。

## 4. 当前项目结构

```text
mosaic-agent/
├── PROJECT_CONTEXT.md             # 本交接文档
├── README.md                      # 使用说明和 API 总览
├── docs/
│   ├── agent-runtime.md           # Agent 事件协议和运行边界
│   ├── phase-1.md                 # MRAG 独立化记录
│   ├── phase-2.md                 # 真实入库问答闭环
│   ├── phase-3.md                 # 可观测单 Agent
│   ├── phase-3-1.md               # 安全和健壮性加固
│   ├── phase-4.md                 # React 工作台
│   └── img/mrag/                  # MRAG 架构和示例图
├── examples/knowledge/            # 最小 Markdown 示例
├── genie-tool/
│   ├── server.py                  # FastAPI 入口、health、ready、CORS
│   ├── scripts/demo.py            # 真实端到端演示
│   ├── tests/                     # 后端与 MRAG 测试
│   └── genie_tool/tool/mrag/
│       ├── api/routes/            # 文档和问答 API
│       ├── document/              # Parser、Splitter、Processor
│       ├── embedding/             # 文本、BM25、多模态 Embedding
│       ├── query/                 # 单 Agent 主循环和决策
│       ├── retrieval/             # 文本、图片、页面召回
│       ├── rerank/                # 文本重排
│       ├── generation/            # LLM、VLM 和 Prompt
│       ├── storage/               # Qdrant、SQLite、统一存储接口
│       ├── init/                  # 数据库与集合初始化
│       └── utils/                 # 文件、URL、安全、日志等工具
└── web/
    ├── src/App.tsx                # 前端状态和业务编排
    ├── src/api.ts                 # HTTP API 和 SSE 解析
    ├── src/components/            # 左栏、问答区、轨迹栏、Dialog
    ├── src/styles.css             # 三栏和响应式样式
    └── package.json               # 前端脚本和依赖
```

## 5. 整体架构心智模型

不要按文件名顺序学习。先把项目理解成两个业务闭环和三个横向支撑层。

```text
闭环 A：知识入库
文件 -> 上传 -> 解析 -> 切块/OCR/Caption -> Embedding -> Qdrant
                                      -> 文件/知识库状态 -> SQLite

闭环 B：Agent 问答
问题/图片 -> 规划 -> 四路检索 -> 证据判断 -> 必要时继续检索
          -> 去重/重排 -> LLM/VLM 路由 -> 引用 + 流式答案

横向支撑：
API 与校验 | 配置与模型客户端 | SSE 事件与 React 可视化
```

## 6. 知识入库主链路

### 6.1 两步上传契约

前端不会把任意本地路径直接交给处理器，而是执行：

```text
POST /v1/documents/upload
  -> 文件保存到受控本地目录
  -> 返回 document_id、filename、permanent_url

POST /v1/documents/add_files
  -> 请求只提交 document_id + filename + kb_id
  -> 创建 PENDING 文件元数据
  -> 后台执行真正的解析和向量化
```

入口文件：`genie-tool/genie_tool/tool/mrag/api/routes/document.py`

关键符号：

- `upload_document()`：校验扩展名和大小，保存原始文件。
- `add_files()`：校验受控文件引用，创建任务记录，加入 BackgroundTasks。
- `add_file()`：状态从 `PENDING -> RUNNING -> SUCCESS/FAILED`。

### 6.2 DocumentProcessor

核心文件：`genie-tool/genie_tool/tool/mrag/document/processor.py`

`DocumentProcessor` 是入库总协调器：

1. 构造时根据扩展名选择 Parser。
2. `pre_process()` 将不同格式归一化为 Markdown、图片和页面。
3. `_process_text()` 处理文本块、子块、文本向量和 BM25。
4. `_process_image()` 处理独立图片、多模态向量、OCR 和 Caption。
5. `_process_page()` 处理整页视觉内容，并保留布局信息。
6. `_mrag_process()` 顺序调用文本、图片、页面三条处理通道。

一个容易忽略的实现细节：`DocumentProcessor.__init__()` 会立即调用 `pre_process()`；随后路由再调用 `processor.process()` 完成向量化。

### 6.3 Parser、Splitter 与 small-to-large

- Parser 入口：`document/parser.py:get_document_parser()`
- Splitter 入口：`document/splitter.py:get_text_splitter()`
- 默认切分类型：Markdown 结构切分
- 默认大块：`CHUNK_SIZE=500`，重叠 `CHUNK_OVERLAP=100`
- 默认开启子块增强：`ENABLE_SUB_CHUNK_ENHANCE=true`
- 默认子块长度：`SUB_CHUNK_SIZE=100`

子块增强采用 small-to-large retrieval：

- 向量由更短的子块文本生成，以提高细粒度召回。
- Qdrant payload 中保存对应父块全文，以便召回后给模型更完整的上下文。
- 因此“向量文本”和 payload 全文不完全相同是有意设计，不是数据错位 Bug。

## 7. 三个 Qdrant 集合与四路检索

实际使用三个 1024 维集合：

| 集合 | 数据 | 向量类型 |
| --- | --- | --- |
| `mosaic_mrag_text_vectors` | 文本块、OCR、Caption | 文本稠密向量 + BM25 稀疏向量 |
| `mosaic_mrag_image_vectors` | 文档内独立图片 | 多模态稠密向量 |
| `mosaic_mrag_page_vectors` | 完整页面截图 | 多模态稠密向量 |

四路检索是：

1. `text_dense`：文本集合中的稠密向量检索。
2. `text_sparse`：同一文本集合中的 BM25 稀疏检索。
3. `image_dense`：独立图片集合检索。
4. `page_dense`：完整页面集合检索。

所以“三个集合”和“四路检索”并不矛盾：文本集合同时承担稠密与稀疏两条检索通道。

统一存储入口：`storage/vector_store.py:VectorStore`

Qdrant 底层：`storage/qdrant_vector_store.py`

四路并发入口：`retrieval/retriever.py:BaseRetriever.retrieval_by_texts_with_trace()`

额外注意：独立上传的一张 PNG 会被 `ImageParser` 当作完整页面处理，因此主要进入页面集合；它的 OCR 和 Caption 会进入文本集合。这就是演示数据中图片集合可能为 0、页面集合却有数据的原因。

## 8. 单 Agent 每轮问答步骤

最核心文件：`genie-tool/genie_tool/tool/mrag/query/agent.py`

最核心函数：`AgenticRAG._execute()`

普通知识问答按以下顺序执行：

1. 创建 `run_id`，发出 `run_started`。
2. 如果用户带图片，先用 VLM 生成图片描述。
3. 判断问题是否完全不需要知识库；如果不需要，直接走 LLM。
4. 判断是否是只依赖用户图片的简单问题；如果是，直接走 VLM。
5. 对普通知识问题执行查询扩展，限制每轮子问题数量。
6. 对每个子问题并发执行文本稠密、BM25、图片、页面四路召回。
7. 为每个子问题总结证据。
8. 判断证据是否充分；不足则产生 `rewrite_query` 进入下一轮。
9. 到达充分、无改写问题或最大轮数时停止检索。
10. 合并所有轮次结果，并按文本、图片、页面去重。
11. 对文本证据调用 Reranker；失败时保留原召回顺序。
12. 根据问题和视觉证据决定使用 LLM 还是 VLM。
13. 构建 `〔N〕` 引用上下文和结构化引用列表。
14. 流式生成答案，发出多个 `answer_delta`。
15. 发出 `run_completed`；异常则发出 `run_failed`。

### 为什么它是 Agent，而不是普通 RAG

它会自主做四类受约束决策：

- 是否需要检索。
- 应该生成哪些检索问题。
- 当前证据是否充分，是否继续下一轮。
- 最后应该使用 LLM 还是 VLM。

### 为什么它仍然是单 Agent

只有 `AgenticRAG` 维护一次请求的控制流。Retriever、Reranker、LLM、VLM 是它调用的工具，不是拥有独立目标、状态和消息循环的 Agent。

未来升级轻量多 Agent 时，可以把查询规划、证据审查或答案生成拆成角色，但当前版本没有这样做。

## 9. Agent SSE 事件协议

事件模型：`query/models.py`

正常主序列：

```text
run_started
-> query_planned
-> retrieval_completed
-> evidence_evaluated
-> rerank_completed
-> route_selected
-> generation_started
-> answer_delta ...
-> run_completed
```

主要事件含义：

| 事件 | 前端展示内容 |
| --- | --- |
| `query_planned` | 当前输入问题和扩展后的子问题 |
| `retrieval_completed` | 四个通道的命中数、耗时和状态 |
| `evidence_evaluated` | 证据是否充分、原因、是否继续 |
| `rerank_completed` | 重排前后文本数量和分数 |
| `route_selected` | LLM/VLM 路由、原因、视觉证据数量 |
| `generation_started` | 是否 grounded、引用列表 |
| `answer_delta` | 答案增量文本 |
| `run_completed` | 轮数、耗时、停止原因、答案长度 |

任何单一检索通道失败会标记为 `degraded`，其他通道继续；四路全部失败才结束为 `run_failed`。

## 10. 模型与外部能力分工

本地 `.env` 已经配置完成，但该文件被 Git 忽略。任何文档和提交都不应包含真实 Key。

| 能力 | 配置组 | 当前用途 |
| --- | --- | --- |
| LLM | `LLM_*` | 查询判断、查询扩展、证据总结、充分性判断、路由、文本回答 |
| VLM | `VLM_*` | OCR、图片 Caption、直接图片问答、多模态答案 |
| 文本 Embedding | `TEXT_EMBEDDING_*` | 文本、问题、OCR、Caption 的 1024 维向量 |
| 多模态 Embedding | `DASHSCOPE_*` | 图片和页面的 1024 维向量 |
| Reranker | `TEXT_RERANKER_*` | 最终文本证据重排 |
| BM25 | FastEmbed 本地模型 | 稀疏检索，模型文件缓存到项目数据目录 |

当前 `OCR_TYPE=vlm-ocr`，OCR 复用 VLM 配置；不需要 DeepSeek OCR Key。DeepSeek OCR 只是保留的可选实现。

`LLM_SEND_THINKING_OPTIONS` 和 `VLM_SEND_THINKING_OPTIONS` 控制是否发送 Qwen/特定供应商的 thinking 参数；更换 OpenAI 兼容供应商时可以关闭。

## 11. React 工作台

访问地址：`http://127.0.0.1:5173`

页面结构：

- 左栏：知识库创建、切换、删除，文件上传、状态和删除。
- 中栏：建议问题、文字/图片提问、Markdown 答案、引用、停止生成。
- 右栏：Agent SSE 运行轨迹。
- 窄屏：知识库和轨迹变成左右抽屉。

关键文件：

- `web/src/App.tsx`：页面状态和业务编排。
- `web/src/api.ts`：后端请求、两步上传、POST SSE 解析。
- `web/src/components/KnowledgePanel.tsx`：知识库和文件管理。
- `web/src/components/ChatPanel.tsx`：问答和引用。
- `web/src/components/TracePanel.tsx`：Agent 轨迹时间线。

前端没有模型 Key。开发时通过 Vite 将 `/health`、`/ready` 和 `/v1` 代理到 1601 后端。

前端不实现长期记忆。切换知识库会清空当前界面对话，避免不同知识库的证据混在一起。

## 12. 已完成的工程化与安全加固

- 服务端下载启用 TLS 校验。
- 限制 HTTP/HTTPS scheme、重定向次数和下载体积。
- 远程文件、网页和 Markdown 远程图片默认关闭，并要求主机白名单。
- 文件名、document_id 和本地存储路径防目录穿越。
- Markdown 拒绝绝对路径、协议相对图片和目录穿越，并转义原始 HTML。
- 查询图片限制 4 张，并限制为服务端/OSS/显式可信主机。
- CORS 默认只允许本地 React 开发地址。
- Embedding 空向量和无效响应立即失败，不再静默传递。
- Parser、向量写入失败会传播到文件 `FAILED` 状态。
- DOCX 图片保留真实格式，VLM 按文件内容判断 MIME。
- 知识库和文件删除同步清理文本、图片、页面三类向量。
- 日志不输出完整 Prompt、检索 payload、稀疏向量或 API Key。
- 前端区分“服务未就绪”和“无法连接”。
- 前端在非安全 HTTP 环境中为 `crypto.randomUUID()` 提供非加密降级 ID。

## 13. 已验收结果

后端：

- `uv run pytest -q -p no:cacheprovider`：35 项通过。
- Python 全量编译通过。
- `git diff --check` 通过。
- `/ready` 返回 ready，五类模型配置均就绪。
- Markdown、PNG、纯文本 DOCX 真实 API 入库成功。
- 文本问题真实走过 LLM 路由。
- 依赖架构图的问题真实走过 VLM 路由并使用页面视觉证据。
- 临时知识库、文件元数据和三类向量删除通过。

前端：

- `npm run build` 通过。
- `npm run test`：4 项通过。
- `npm run lint` 通过。
- 真实浏览器完成一次 SSE 问答，能显示路由、引用、检索轮次和耗时。
- 1280×720 桌面布局通过。
- 390×844 移动端布局、双抽屉和 Dialog 通过。

曾经启动并验证的地址：

- 后端：`http://127.0.0.1:1601`
- Swagger：`http://127.0.0.1:1601/docs`
- 前端：`http://127.0.0.1:5173`

不要假设换一个会话或重启电脑后进程仍然运行，应先访问 `/ready` 检查。

## 14. 已知边界与暂不处理事项

这些不是当前主链路阻断项：

- 没有跨请求长期对话记忆。
- 没有多 Agent 编排。
- 没有登录、租户和权限体系，默认只绑定本机地址。
- 没有正式评测集和自动化 RAG 指标系统。
- 没有 Docker Compose、CI/CD 和生产监控。
- 本地 Qdrant 模式只适合单进程；多进程要切换 Qdrant Server。
- SSE 使用同步生成器；Starlette 会在线程池中消费，目前未做全异步改写，应在并发压测后决定。
- `t_kb_file.doc_count` 是原项目遗留占位字段，当前始终为 0，前端不展示它。
- FAILED 入库文件没有 Retry API；当前做法是删除后重新上传。
- Dialog 有 Escape 和遮罩关闭，但没有完整焦点陷阱。
- 用户用于提问的图片会进入本地文件存储，目前没有 TTL 清理策略，长期使用可能积累文件。
- 网页导入和 Markdown 远程图片虽然默认关闭，但它们不属于当前核心应用链路，默认不建议开启。

## 15. 代码规模与真正核心

统计不包含 `package-lock.json`、文档和生成目录：

| 范围 | 文件数 | 物理行数 | 非空行 |
| --- | ---: | ---: | ---: |
| 应用源码（后端 + 前端） | 79 | 11,564 | 9,801 |
| MRAG 后端模块 | 63 | 8,382 | 6,972 |
| 前端 `src/`（不含测试） | 10 | 2,845 | 2,545 |
| 全部测试 | 5 | 914 | 718 |
| 第一轮核心算法 | 6 | 1,500 | 1,323 |
| 核心算法 + API/存储边界 | 9 | 2,577 | 2,229 |

第一轮核心文件：

| 文件 | 行数 | 责任 |
| --- | ---: | --- |
| `query/agent.py` | 540 | 单 Agent 主循环 |
| `query/query_processor.py` | 272 | 查询扩展、证据判断、路由 |
| `retrieval/retriever.py` | 144 | 四路并行检索和降级 |
| `retrieval/text_retriever.py` | 66 | 文本稠密和 BM25 |
| `retrieval/image_retriever.py` | 89 | 图片和页面检索 |
| `document/processor.py` | 389 | 多模态入库编排 |

大文件不等于第一阅读优先级：

- `web/src/styles.css` 约 1456 行，主要是样式。
- `document/parser.py` 约 1375 行，主要因为支持多种文件格式。
- `storage/qdrant_vector_store.py` 约 752 行，属于数据库底层封装。
- `generation/prompt_manager.py` 约 392 行，大部分是 Prompt 文本。

## 16. 推荐学习顺序

### 第一阶段：先懂一次 Agent 请求

1. `api/routes/query.py:query()`
2. `query/models.py`
3. `query/agent.py:AgenticRAG._execute()`
4. `retrieval/retriever.py:retrieval_by_texts_with_trace()`
5. `query/query_processor.py`

学习目标：能够对照右侧 Agent Trace，说清每一个 SSE 事件由哪段后端代码产生。

### 第二阶段：再懂一份文件如何入库

1. `api/routes/document.py:upload_document()`
2. `api/routes/document.py:add_files()` 和 `add_file()`
3. `document/processor.py`
4. `document/splitter.py`
5. 只选择一种 Parser 阅读，例如先看 Markdown，再看 PDF/DOCX。

学习目标：能够说清一份 Markdown 或 PDF 最终为什么会出现在文本、图片、页面集合中。

### 第三阶段：理解存储与模型边界

1. `storage/vector_store.py`
2. `storage/qdrant_vector_store.py`
3. `storage/store_factory.py`
4. `embedding/`、`rerank/`、`generation/`

学习目标：能够区分 SQLite 元数据、Qdrant payload、稠密向量、稀疏向量和原始文件。

### 第四阶段：理解前后端事件契约

1. `web/src/api.ts`
2. `web/src/App.tsx:handleSend()`
3. `web/src/components/TracePanel.tsx`

学习目标：能够解释为什么 POST SSE 不能直接使用浏览器 EventSource，以及事件如何变成界面状态。

## 17. 初学时暂时不要先读

- 不要先通读 1375 行 `parser.py`。
- 不要先研究 Qdrant 底层每个 CRUD 封装。
- 不要先背所有 Prompt。
- 不要先看 1456 行 CSS。
- 不要先增加多 Agent、记忆或评测框架。

先沿一条真实请求追踪数据，再按问题深入对应实现。

## 18. 启动与验证命令

### 后端

```powershell
cd genie-tool
uv run python -m genie_tool.tool.mrag.init.init_db
uv run uvicorn server:app --host 127.0.0.1 --port 1601
```

### 前端

```powershell
cd web
npm install
npm run dev
```

### 测试

```powershell
cd genie-tool
uv run pytest -q -p no:cacheprovider

cd web
npm run build
npm run test
npm run lint
```

### 真实演示

```powershell
cd genie-tool
uv run python scripts/demo.py
```

演示脚本会创建/复用 `mosaic-demo`，上传 Markdown 和架构图，等待入库，然后执行一次真实流式 Agent 问答。该操作会调用已配置的外部模型 API，产生少量费用。

## 19. 新项目对话的推荐开场提示

可以在新的项目对话中直接发送：

```text
请先完整阅读仓库根目录 PROJECT_CONTEXT.md，然后核对其中提到的真实代码。
我准备按推荐学习顺序学习 MosaicAgent。请先从
genie-tool/genie_tool/tool/mrag/api/routes/query.py 的 query()
进入，再逐段讲解 query/agent.py 的 AgenticRAG._execute()。
先建立运行顺序和数据结构，不要修改代码，也不要一次展开 Parser、Qdrant 底层和前端样式。
每次讲解都引用当前仓库中的真实函数和调用关系。
```

## 20. 最终学习目标

完成学习后，应能够独立解释：

1. 为什么多模态 RAG 需要文本、独立图片和完整页面三类证据。
2. 为什么三个 Qdrant 集合可以提供四路检索。
3. small-to-large retrieval 中为什么子块向量对应父块 payload。
4. Agent 如何判断是否继续检索，以及如何避免无限循环。
5. Agent 如何在 LLM 与 VLM 之间动态路由。
6. 引用、降级和 SSE 事件如何让一次回答可追踪。
7. 前端如何消费 POST SSE 并把后端状态映射成运行轨迹。
8. 当前为什么选择单 Agent，以及未来如何低成本升级为轻量多 Agent。
