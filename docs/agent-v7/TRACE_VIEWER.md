# 工作台任务追踪

前端维护者负责「深度研究 → 任务追踪」。任务详情接口校验当前账号的所有权。页面从该响应读取 32 位十六进制 trace ID，供用户复制。账号或任务切换后，入口随当前详情更新。剪贴板写入失败时可手动选择 ID。

运维可在构建前端时设置 `VITE_JAEGER_UI_PATH=/jaeger`，将同源的 `/jaeger/` 交由有访问控制的 Jaeger 网关提供。每段路径只接受英文字母、数字、下划线和短横线。留空或填写无效路径时，页面提供复制功能。Compose 构建同样接受此变量，更改后须重建前端镜像。

点击「在 Jaeger 查看」会在新标签页打开 `/jaeger/trace/<trace-id>`。链接仅包含部署路径和 trace ID，浏览器省略来源页面地址。运维通过 Jaeger 网关独立控制每位访问者可查看的链路。同源代理须同时保护 UI、静态资源和查询 API。采集端地址由后端单独配置。

验收从已登录用户的任务进入查看器，核对 Jaeger 返回的 trace ID、打开失败时的复制操作，以及切换账号后的任务访问结果。

## 2026-11-22 本机验收

Chrome 157.0.8103.79 中，已登录用户从任务追踪区打开 Jaeger v2.23.0。原生界面显示 `research.api`，查询接口返回该任务的 21 个 span。该任务使用 2 篇真实种子论文。点击的顶层请求只包含部署路径和任务的 trace ID，浏览器记录的查询参数、Authorization 和 Referer 均为空。模拟网关拒绝后，新标签页显示 403，原页仍能复制。

默认构建中，点击复制后从浏览器剪贴板读回的 ID 与任务详情一致，访问网关次数为 0。两种构建中均模拟了剪贴板不可用，并验证手动复制提示。使用同一浏览器退出并登录另一个账号，原任务详情返回 404，页面没有显示原账号的 ID 或链接。验收中的 403 是通过该浏览器会话的路由规则模拟的，生产网关权限需在部署环境验收。

复验使用本地研究依赖、已下载的 seed 语料、Jaeger 可执行文件及 Node Playwright。可用环境变量 `SCHOLARLENS_PLAYWRIGHT` 指定 Playwright 模块，`SCHOLARLENS_CHROME` 指定 Chrome 可执行文件。在仓库根目录通过 PowerShell 顺序运行。

```powershell
Push-Location frontend
node --test tests/trace-viewer.test.mjs
node node_modules/typescript/bin/tsc --noEmit
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_RESEARCH_ENABLED = 'true'
$env:VITE_JAEGER_UI_PATH = '/jaeger'
node node_modules/vite/bin/vite.js build --outDir ../output/v7/trace-viewer-build-enabled
$env:VITE_JAEGER_UI_PATH = ''
node node_modules/vite/bin/vite.js build --outDir ../output/v7/trace-viewer-build-default
Pop-Location
$jaeger = (Resolve-Path 'output/v7/jaeger-2.23.0/jaeger.exe').Path
python -m tools.research_eval.v7_trace_viewer_browser $jaeger output/v7/trace-viewer-build-enabled configured
python -m tools.research_eval.v7_trace_viewer_browser $jaeger output/v7/trace-viewer-build-default default
```
