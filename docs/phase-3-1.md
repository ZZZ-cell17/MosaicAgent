# 第三阶段补强：运行边界与安全加固

## 目标

在开发 React 工作台前，加固文件导入、服务端下载、配置兼容性和删除语义。此阶段不改变 MRAG 算法，也不引入评测框架或多 Agent。

## 问题判断

- 修复：关闭 TLS 校验、文件名路径穿越、远程地址无白名单、CORS 全开放、缺省切分配置崩溃、DOCX 图片后缀错误、Embedding 静默失败、知识库删除参数宽松和引用标记不一致。
- 保留设计：子块向量召回父块全文属于 small-to-large retrieval，不把父块 payload 改为子块文本。
- 配置化：当前 Qwen 服务需要 `enable_thinking` 参数，通过 `LLM_SEND_THINKING_OPTIONS` 和 `VLM_SEND_THINKING_OPTIONS` 控制，兼容其他 OpenAI 风格供应商。
- 延后：SSE 的同步迭代器由 Starlette 在线程池中消费，并非直接阻塞事件循环；是否改为全异步需要并发压测后决定。
- 清理：移除当前学习版没有入口的 LightRAG 残留，不处理无运行影响的历史 Prompt 和存储抽象。

## 完成内容

- 上传文件通过 `document_id + filename` 从受控本地存储入库，禁止目录穿越。
- 远程文件、网页和 Markdown 远程图片默认关闭，启用时必须配置主机白名单；Markdown 渲染同时拒绝绝对路径、目录穿越和协议相对图片，并转义原始 HTML。
- 所有服务端下载校验 HTTP/HTTPS、TLS、重定向目标和最大体积，并使用临时文件原子落盘。
- 查询图片限制数量与可信主机，CORS 默认仅允许本地前端开发地址。
- 知识库、分页、切块和文件请求增加约束；重复创建、删除不存在资源返回明确状态码。
- 删除文件和知识库时同步清理三类向量与关联文件元数据，并报告实际删除数量。
- 修复 Markdown 切分参数、DOCX 图片格式、VLM MIME 判断、Embedding 失败传播和向量写入失败传播。
- Prompt 与上下文统一使用 `〔N〕` 引用；日志不再输出完整 Prompt、向量检索结果或稀疏向量。
- 补齐 README 的导入契约、安全默认值和 API 清单。

## 验收口径

- 单元与接口测试覆盖安全默认值、路径穿越、私网 URL、下载大小、配置错误、删除语义、切分、图片 MIME、Embedding 失败和引用格式。
- Python 全量编译通过，`git diff --check` 通过。
- 服务重启后 `/ready`、本地上传、Markdown/图片入库、LLM/VLM 查询和删除链路均需再次实测。

## 验收结果

- `uv run pytest -q -p no:cacheprovider`：35 项测试通过，仅有一条来自 Starlette TestClient 的上游弃用警告。
- Python 全量编译和 `git diff --check` 通过。
- 重启后的 `/ready` 返回 200；本地 Qdrant 与 LLM、VLM、文本 Embedding、多模态 Embedding、Reranker 均为 ready。
- 临时知识库 `mosaic-phase31-check` 成功上传并入库 Markdown 与 PNG 文件。
- 额外创建纯文本 DOCX，经真实 API 上传、解析和向量化后状态为 `SUCCESS`，临时知识库随后清理成功。
- 文本问题第一轮证据充足，文本稠密、BM25 和页面通道均有命中，路由选择 LLM 并返回引用。
- 依赖架构图视觉布局的问题执行三轮检索，页面通道持续命中，路由选择 VLM，实际使用一项页面视觉证据并完成回答。
- 删除临时知识库返回 `deleted_files=2`；随后知识库列表不再包含它，文件列表计数为 0。

`t_kb_file.doc_count` 是继承自原项目但未接入实际统计的占位字段，目前仍为 0；它不代表入库失败，前端不将其展示为向量或切块数量。若后续需要统计，应直接从各集合按 `kb_id/file_id` 计数并定义清楚指标口径。
