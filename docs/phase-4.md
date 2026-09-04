# 第四阶段记录：轻量 React 工作台

## 定位

为精简后的单 Agent MRAG 提供一个可操作、可观察的单页工作台。界面只覆盖学习项目的主闭环，不复制原项目面向 Data Agent、多 Agent 和报告生成的完整 Web UI。

## 页面结构

- 左栏：MosaicAgent 标识、知识库列表、创建/删除知识库、文件列表、上传和入库状态。
- 中栏：当前知识库、建议问题、Markdown 答案、图片提问、引用证据、停止生成和清空对话。
- 右栏：SSE 运行轨迹，将查询规划、多路召回、证据判断、重排、模型路由和耗时转换为时间线。
- 移动端：左栏和轨迹栏改为抽屉，主问答区保持单列；不把两个侧栏同时挤在窄屏中。

## 与后端契约

- 本地文件按 `upload -> document_id -> add_files` 两步提交，前端轮询 `/list_kb_files` 直到 `SUCCESS` 或 `FAILED`。
- 图片提问先走受控本地上传，再把服务返回的 `permanent_url` 作为 `image_urls` 发送给 Agent。
- 问答使用 POST `/v1/mrag/query`，前端手动解析 SSE 分包并消费结构化事件，不依赖浏览器原生 EventSource。
- 前端不实现跨请求记忆；切换知识库时清空当前界面会话，避免不同知识库的证据混淆。

## 采用的范围

- React + TypeScript + Vite
- `lucide-react` 图标、`react-markdown` + GFM 答案渲染
- 原生 `fetch`、AbortController 和轻量轮询
- 无登录、无复杂设置、无评测仪表盘、无多 Agent 编排

## 验收结果

- `npm run build`：通过。
- `npm run test`：4 项测试通过，覆盖 SSE 分包、503 状态保留和客户端 ID 降级。
- `npm run lint`：通过。
- API 503 会显示“服务未就绪”，网络故障显示“无法连接”；客户端 ID 在非安全上下文中有降级生成路径。
- 真实浏览器桌面检查：加载 `mosaic-demo`、两份已入库文件，完成一次真实 Agent 问答并展示 VLM 路由、引用和运行轨迹。
- 真实浏览器移动端检查：390×844 下知识库抽屉、轨迹抽屉和新建知识库弹窗布局正常。
- Vite 开发服务：<http://127.0.0.1:5173>。
