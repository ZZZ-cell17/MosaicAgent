# 第二阶段记录：真实 MRAG 最小闭环

## 阶段目标

让 MosaicAgent 从“可以独立启动”进入“可以重复完成多模态入库与单 Agent 问答”的状态。

## 已完成

- 增加 `QDRANT_MODE=local`，默认将向量数据持久化到 `genie-tool/data/qdrant`
- 保留 `QDRANT_MODE=server`，用于后续 Docker 或远程 Qdrant
- 修正文档 ID 字段索引类型和字符串精确过滤
- 初始化命令不再依赖已经启动的 API
- 增加 `/ready`，只报告缺失配置名称，不显示密钥值
- 模型配置不完整时，MRAG 查询返回明确的 HTTP 503
- 后台入库失败时记录 `FAILED` 和错误摘要
- 修复远程图片转 Base64 后临时目录未清理的问题
- 增加 Markdown + 架构图的最小多模态样例和自动演示脚本
- 增加本地 Qdrant 写入、过滤和检索的集成测试
- `/add_files` 在响应中返回 `file_id`，演示脚本按任务 ID 跟踪真实状态
- FastEmbed 使用可配置的 Hugging Face 镜像并将 BM25 资源缓存到 D 盘项目目录

## 端到端验收结果

真实模型最小调用均已通过，文本与多模态 Embedding 都返回 1024 维。`scripts/demo.py` 已完整执行：Markdown 和 PNG 入库成功，Agent 在一轮检索后得到 2 个文本证据和 1 个页面证据，经 Reranker 后由 VLM 生成带图片引用的流式答案。

清理重复验收数据后，`mosaic-demo` 当前包含 18 条文本向量、0 条独立图片向量和 1 条页面向量。单张 PNG 由 `ImageParser` 作为页面处理，所以进入页面集合；其 OCR 和 Caption 进入文本集合。

文件删除会同步清理文本、图片和页面三个集合中的对应向量，并有本地 Qdrant 回归测试覆盖。

第二阶段真实 MRAG 最小闭环完成。
