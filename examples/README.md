# 最小多模态样例

默认样例由一份 Markdown 知识文档和 `docs/img/mrag/mrag_struct.png` 架构图组成。

先在 `genie-tool` 目录完成配置和存储初始化：

```powershell
Copy-Item .env_template .env
uv run python -m genie_tool.tool.mrag.init.init_db
uv run uvicorn server:app --host 127.0.0.1 --port 1601
```

另开一个 PowerShell 窗口执行：

```powershell
cd genie-tool
uv run python scripts/demo.py
```

脚本会执行健康与配置检查、创建知识库、上传两个样例文件、等待入库完成，并发起一次 SSE 流式问答。

已有数据时只运行 Agent 查询：

```powershell
uv run python scripts/demo.py --query-only
```
