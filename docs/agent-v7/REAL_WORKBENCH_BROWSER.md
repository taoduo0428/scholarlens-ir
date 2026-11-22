# 本地真实论文工作台验收

2026-11-22，在正式应用入口和 Chrome 157.0.8103.79 上，用隔离的新账号完成注册、登录、论文检索、论文详情、限定论文范围提问、原文定位与报告下载。工作台入口为 [深度研究](http://127.0.0.1:18011/research)。

搜索使用英文论文标题 *Factors responsible for high arsenic concentrations in two groundwater catchments in Taiwan*。详情接口确认论文属于真实索引，统计接口返回 859 篇。测试核对了报告中每条引用的论文 ID、字段、字符范围和摘录，并从报告点开原文，验证浏览器定位提示。

| 问题 | 报告状态 | 核实的来源位置 | 下载的 Markdown |
| --- | --- | ---: | ---: |
| 英文询问摘要对台湾两个流域地下水砷的研究发现 | 部分完成，最终答案显示证据不足 | 5 | 6,278 字节 |
| 中文询问同一论文的研究目的、方法和主要发现 | 部分完成，最终答案显示证据不足 | 2 | 2,510 字节 |

两次均使用只读证据模式，模型调用为 0。页面无 JavaScript 运行异常。下载文件与后端报告中的 Markdown 逐字一致。英文报告 SHA-256 为 `0647272e80d669f2f248d09bf47bdd7b34386c7cd7d8280ff2f4859a8f2d4e33`，中文报告为 `44ed901acb476d061f2260724a5e080875fa4d46946e53246b8e4a18de11d081`。匿名读取任务报告返回 401。

## 个人模型的实际运行

同日使用新的浏览器会话，在个人 API 设置中点击“获取模型”，列表返回 28 个模型。选择并保存 `deepseek-v4.1-flash` 后，在研究工作台用同一篇论文提交英文问题。服务记录了 2 次模型调用和 1 条供应商用量回执。后端按完整回执计算任务总用量，该任务的输入和输出 token 合计均为未知。

报告给出 5 处可逐项核对的原文位置，答案状态为 `insufficient_evidence`。从页面下载的 Markdown 共 6,278 字节，SHA-256 为 `0647272e80d669f2f248d09bf47bdd7b34386c7cd7d8280ff2f4859a8f2d4e33`。这次与上表英文证据模式的报告内容逐字相同。工作台已验证个人模型配置、任务提交和供应商返回，关于该问题仍只能依据报告中列出的原文作答。

## 复测

启动已接入真实索引的本地应用，启用研究工作台，在仓库根目录运行以下命令。可设置 `SCHOLARLENS_PLAYWRIGHT` 与 `SCHOLARLENS_CHROME` 选择本地 Playwright 模块和 Chrome 可执行文件。

```powershell
$env:SCHOLARLENS_URL = 'http://127.0.0.1:18011'
$env:SCHOLARLENS_RESEARCH_OUTPUT = "output/v7/workbench-$(Get-Date -Format yyyyMMdd-HHmmss)"
node frontend/tests/real-workbench-live.mjs
```

脚本会在输出目录保存检索与报告截图、引用定位截图（有出处时）、下载的 Markdown 和 `journey.json`。可以用 `SCHOLARLENS_JOURNEY_GOAL` 指定要问的问题。

个人模型模式读取当前测试进程提供的 `AI_BASE_URL`、`AI_MODEL` 和 `AI_API_KEY`。设置 `SCHOLARLENS_JOURNEY_MODE=personal_model` 后运行同一脚本。它在设置页点击“获取模型”，选择并核对指定模型，再通过工作台启动一个标准深度任务。模型名单、任务提交和供应商推理分别验证，`journey.json` 记录目录大小、选中的模型、调用次数、用量回执条数以及所报告的 token 数。临时浏览器上下文在结束时清除个人配置。
