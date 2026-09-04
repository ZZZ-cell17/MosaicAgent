# Agent 运行时设计

MosaicAgent 保留 JoyAgent-JDGenie MRAG 的查询扩展、多路检索、子问题摘要、证据充分性判断、文本重排和 LLM/VLM 生成机制，将其收敛为一个有边界、可观测的单 Agent。

## 单次请求状态流

```text
START
  -> 判断是否需要知识库
  -> PLAN：生成并规范化子查询
  -> RETRIEVE：四路并行检索
  -> EVALUATE：摘要证据并判断充分性
       -> 不充分且未达上限：使用 rewrite_query 返回 PLAN
       -> 充分或达到上限：进入 RERANK
  -> ROUTE：选择 LLM 或 VLM
  -> GENERATE：流式生成并返回引用
  -> COMPLETE
```

每次请求有独立的 `run_id`，不保存跨请求记忆。`MRAG_MAX_ROUNDS` 和 `MRAG_MAX_SUBQUERIES` 分别限制检索轮数和每轮查询数；`MRAG_SUMMARY_MAX_CHUNKS` 限制每个子查询进入摘要 Prompt 的去重文本数量。

## 四路检索

| 通道 | 原项目实现 | 作用 |
| --- | --- | --- |
| `text_dense` | `TextRetriever.vector_search` | 文本语义召回 |
| `text_sparse` | `TextRetriever.sparse_search` | BM25 关键词召回 |
| `image_dense` | `ImageRetriever.text2image_search` | 独立图片召回 |
| `page_dense` | `ImageRetriever.text2page_search` | 文档整页召回 |

四路检索并发执行。单路失败不会中断其他通道，并在 `retrieval_completed` 中标记 `degraded`；四路全部失败时终止本次运行并返回 `run_failed`。

## SSE 事件

每个事件的 `data` 都是 JSON，公共字段为 `event`、`run_id`、`timestamp` 和可选的 `round_no`。

| 事件 | 关键数据 |
| --- | --- |
| `run_started` | 知识库、原问题、最大轮数、输入图片数 |
| `query_planned` | 当前输入查询、规范化后的子查询 |
| `retrieval_completed` | 四路命中数、耗时、状态和合并命中数 |
| `evidence_evaluated` | 是否充分、简短依据、改写查询、是否继续 |
| `rerank_completed` | 输入/输出数量、阈值、Top 分数或降级策略 |
| `route_selected` | LLM/VLM、路由依据、检索与实际使用的证据数 |
| `generation_started` | 路由、是否有知识依据、结构化引用 |
| `answer_delta` | 与模型供应商无关的文本增量 |
| `run_completed` | 停止原因、轮数、路由、引用数、总耗时 |
| `run_failed` | 稳定错误码和面向调用方的安全错误信息 |

请求参数 `include_trace=false` 时，只返回 `answer_delta`、`run_completed` 和 `run_failed`。

## 停止与降级

- 证据充分：以 `evidence_sufficient` 停止检索。
- 达到轮数上限：以 `max_rounds_reached` 停止检索。
- 模型未给出有效改写：以 `missing_rewrite_query` 停止检索。
- 没有可用证据：使用受约束的无证据 Prompt，不调用模型自身知识补写事实。
- Reranker 失败：保留原始召回顺序，并在事件中标记 `degraded`。
- 模型 JSON 输出不合规：记录错误类型并采用有界的安全回退，不让解析异常击穿 SSE 连接。

事件只公开执行状态和简短决策依据，不公开模型的隐藏思维过程，也不返回底层模型供应商的原始响应对象。
