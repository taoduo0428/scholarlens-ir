# P0 旧前端基线

2026-11-20 在 Windows 隔离 worktree、基线 `3e130b0` 上执行。Node 24.18.0，npm 11.16.0，Vite 6.4.5，Chrome 157.0.8103.79，Playwright 1.63.0。本次依赖锁文件 SHA-256 为 `17c69d4705f6e12af0a4490ef0e9a077c12623d650bdde27520825f291467691`。所有命令的输出及桌面、390px 引用弹窗截图在 [evidence/p0-frontend](evidence/p0-frontend/)。

| 命令 | 退出码 | 本次结果 | 原始输出 |
|---|---:|---|---|
| `npm --prefix frontend ci --no-audit --no-fund` | 0 | 按锁文件安装 78 包，npm 提示 esbuild postinstall 审批，随后构建成功 | npm-ci.txt |
| `npm --prefix frontend test` | 0 | 45 通过，0 失败、取消或跳过，387 ms | npm-test.txt |
| `npm --prefix frontend run typecheck` | 0 | TypeScript 检查通过 | npm-typecheck.txt |
| `npm --prefix frontend run build` | 0 | demo 构建处理 1,652 个模块，Vite 报 2.35 秒 | npm-build.txt |
| `npm --prefix frontend run verify:structure` | 0 | 44 文件、24 源码模块、8 核心路由加 404、18 条显式合成样本 | npm-structure.txt |
| `npm --prefix frontend run test:browser` | 1 → 0 | 复现并修复一条旧侧栏导航断言。复验经过搜索、收藏和备份、本地 PDF 与审核、禁用的未配置助手、评测导航、404、阅读记录和手机几何检查 | browser-demo.txt、browser-demo-fixed.txt |
| `node tests/assistant-citations-browser.mjs` | 0 | 6 组。打开独立论文标签页并逐字对照引用高亮，覆盖问答、总结、比较、历史、390px、特殊字符与未知来源 | browser-assistant-citations.txt |
| `node tests/assistant-composer-browser.mjs` | 0 | 9 组。覆盖等待、失败、重试、取消、草稿和 390px | browser-assistant-composer.txt |
| `node tests/personal-models-browser.mjs` | 0 | 7 组。覆盖个人配置、模型目录、错误处理和账户隔离的客户端行为 | browser-personal-models.txt |
| `git diff --check -- frontend/tests/browser-smoke.mjs` | 0 | 变更通过空白检查 | |

## 发现与修改

旧浏览器 smoke 断言侧栏有四个工具，随后在侧栏寻找评测链接。实际 `Layout.tsx` 的 `TOOL_NAV` 仅公开 PDF 工作区和证据助手，页脚提供检索评测入口。保留原始失败输出，修改 `frontend/tests/browser-smoke.mjs` 精确验证两个公开路径并实际点击页脚进入评测。应用代码和锁文件保持原版本。

## 浏览器复现

在 `frontend` 下启动以下两个回环 preview，各占一个终端。第一个使用默认 demo 构建，在另一个终端设置 `SCHOLARLENS_URL=http://127.0.0.1:19466` 后执行 `npm run test:browser`。第二个使用单独的 API 模式静态产物，三个 Mock 浏览器脚本拦截 API 并返回各自的受控响应。

```powershell
# 终端一，demo 模式
$env:VITE_DATA_SOURCE='demo'
npm run build
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 19466 --strictPort

# 终端二，API 客户端
$env:VITE_DATA_SOURCE='api'
$env:VITE_API_BASE_URL='/api'
node node_modules/vite/bin/vite.js build --outDir ../output/p0-api-client
node node_modules/vite/bin/vite.js preview --outDir ../output/p0-api-client --host 127.0.0.1 --port 19467 --strictPort

# 终端三，运行现有脚本。该路径是验收机上的既有 Playwright 包
$env:SCHOLARLENS_URL='http://127.0.0.1:19467'
$env:SCHOLARLENS_PLAYWRIGHT='C:/Users/lenovo/.codex/tools/jev-playwright/node_modules/playwright'
node tests/assistant-citations-browser.mjs
node tests/assistant-composer-browser.mjs
node tests/personal-models-browser.mjs
```

本次浏览器交互使用独立 headless Chrome 和合成论文。真实 ES、账户服务、收费模型、真实 PDF 以及手机实体机均未在该前端专项中验证。记录的 Vite 构建和单测用时仅描述本次运行。P5/P8 应重新运行这些命令并以同一份旧接口与定位契约作回归对照。
