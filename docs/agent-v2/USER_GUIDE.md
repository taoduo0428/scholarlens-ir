# 本地深度研究工作台

> 当前用户流程为检索论文、打开来源、登录后发起研究、回读引用并导出。个人模型配置属于账号会话的使用条件。模型不可用时可使用证据模式。运行与发布状态见 [最终验收](../final/ENGINEERING_COMPLETION_REPORT.md)。

在项目根目录打开 PowerShell，使用 Python 3.11、Node 24 和项目内的虚拟环境。安装后构建启用了深度研究入口的客户端。以下命令将演示构建放在单独的输出目录。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt -r backend/research/requirements.txt
npm --prefix frontend ci --no-audit --no-fund
$env:VITE_DATA_SOURCE='api'
$env:VITE_API_BASE_URL='/api'
$env:VITE_RESEARCH_ENABLED='true'
Push-Location frontend
node node_modules/vite/bin/vite.js build --outDir ../output/research-demo-ui
Pop-Location
.venv/Scripts/python.exe -m tools.research_demo --corpus fixture --frontend output/research-demo-ui
```

打开 [本地工作台](http://127.0.0.1:8765/research)，点「登录研究账户」，在账户页面注册自己的本地演示账号。重新打开「深度研究」。账户库、研究库和任务检查点保存在 `output/research-demo`。端口冲突时可加 `--port 0`，终端会输出实际地址。停止演示按 Ctrl+C。下次使用同一 runtime 可继续查看已有任务。

## 做一次比较研究

1. 在「研究问题」输入 `Compare Cedar and Birch ranking trial method, dataset, metric and protocol`。
2. 在「本库论文范围」填 `fixture:cedar,fixture:birch`，保留「只读证据」模式并点击「开始研究」。
3. 展开「任务树」下的子任务，查看执行状态、完成条件和缺口。「执行记录」列出服务端事件和实际耗时。刷新页面保留当前任务。暂停与取消先提交请求，执行器确认后更新状态。
4. 在报告的「结论与证据矩阵」展开子任务查看各条结论。点开来源可读逐字引文，点击「定位到论文原文」，新标签页会高亮对应字符区间。出现冲突时，「冲突结论」可展开另一项主张及其原文。展开「方法与实验对照」可并排核对指标与协议。「导出 Markdown」下载服务端生成的原稿。
5. 部分完成时查看「待解决问题」。如需换一组条件，使用下一项研究任务保留前一次结果。

`fixture` 使用两篇明确标识为合成材料的论文。若要研究本库真实论文，把启动参数改为 `--corpus seed --runtime output/research-demo-seed`。该模式读取项目锁定的 Git LFS 语料，校验哈希后载入种子样本。它需要本机已有相应 Git LFS 对象。进入 `/api/research-demo/info` 可查看本次语料版本、论文数及两个可选论文 ID。

独立演示只接受本机回环连接和证据模式。正式应用的个人模型配置沿用证据助手，工作台在明确选择个人模型后才携带账户本次会话的配置。运行中丢失模型凭据时，在证据助手重新配置，再回工作台恢复任务。

## 复现浏览器验收

保持本地 fixture 演示运行。在另一个 PowerShell 中进入 `frontend`，设置实际演示地址和已安装的 Playwright 包位置，执行浏览器脚本。脚本注册两名随机的演示账户，验证研究任务、逐字引文、Markdown 导出、账户隔离与 390px 布局。验收机使用 Google Chrome，可通过 `SCHOLARLENS_CHROME` 指定另一份 Chromium 可执行文件。

```powershell
Set-Location frontend
$env:SCHOLARLENS_URL='http://127.0.0.1:8765'
$env:SCHOLARLENS_PLAYWRIGHT='C:/Users/lenovo/.codex/tools/jev-playwright/node_modules/playwright'
node tests/research-workbench-live.mjs
```
