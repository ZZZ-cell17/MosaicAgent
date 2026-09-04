# 第一阶段记录：MRAG 服务独立化

## 目标

从 JoyAgent-JDGenie 中隔离出可独立阅读、安装和启动的 MRAG 单 Agent 服务，不改动原始下载副本。

## 已保留

- MRAG 文档处理、Embedding、Retrieval、Rerank、Generation、Storage、AgenticRAG
- FastAPI 文档管理、MRAG 查询和本地文件访问路由
- Qdrant、SQLite、模型 API 配置
- MRAG 架构图与示例图
- 原许可证和第三方声明

## 已移出

- `genie-backend`、`genie-client`、`ui`
- Data Agent、Table RAG、NL2SQL、Deep Search、Analysis、Report、Code Interpreter、SOP
- 通用 `model`、`prompt`、`db`、`util` 和文件工具路由
- 原平台 README、部署脚本、IDE 配置与非 MRAG 图片

第一阶段移出内容保存在本地仓库外的备份目录中，不纳入 Git。

## 独立化修改

- 新增 `/health` 和 `/v1/mrag/query`
- 通用文件服务替换为 MRAG 内置本地文件存储
- PDF 页面预览改用 PyMuPDF，基础链路不再要求 Poppler
- MinerU/S3 默认关闭，失败时仍保留 PDF 本地解析路径
- `aigent.py` 更名为 `agent.py`
- Agent 最大检索轮数由 `MRAG_MAX_ROUNDS` 控制
- 依赖和环境变量缩减到 MRAG 范围
- 清除源码中的硬编码 API Key 示例

## 下一阶段建议

第二阶段集中做可运行配置、完整入库问答样例和链路级日志，不在这一阶段引入多 Agent 或长期记忆。
