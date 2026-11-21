# ScholarLens V4 本地交付

当前开发分支为 `feat/research-workspace-v4`。基线是用户公开 fork 的 `zjl` 提交 `b81a435`。研究运行时、Lab 和页面分别见 `0338ffd`、`605cef8`、`9a67e01`。V1 仍是默认策略。演示程序只监听本机，使用独立账户和任务数据库，支持离线使用。

## 查看两个工作台

在本地演示的 `/research` 注册并登录。查看示例时，选本库论文范围，填写 `fixture:cedar`，输入 `Quote the first complete sentence of the abstract of "Cedar ranking trial".`。任务报告给出原文第一句、来源位置、证明事项和状态。研究报告可以导出 Markdown。

实验室路径为 `/evolution-lab`。它使用同一登录会话和服务端管理员角色，生产应用没有挂载这个实验入口。需要实验室权限的本机操作者可以在注册自己的测试账户后，将 `SCHOLARLENS_RUNTIME_DIR` 设为刚启动的本地演示目录，再执行 `python -m backend.accounts --promote <本地测试用户名>`。进入后选择分组、同一题和两个版本，即可检查每个命题、原文、执行记录、预算和失败原因。展开“本组实验结果”查看分母和总量，页面底部可查看两项候选的审核记录。

在本次 Windows 工作树中，从项目根目录运行以下 PowerShell 命令即可重新构建和启动。换机器时，请先安装项目声明的后端依赖和前端依赖，并将 Python 路径指向相应虚拟环境。

```powershell
$python = 'C:/Users/lenovo/Desktop/ScholarLens-EvoResearch/.venv/Scripts/python.exe'
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_API_BASE_URL = '/api'
$env:VITE_RESEARCH_ENABLED = 'true'
$env:VITE_EVOLUTION_LAB = 'true'
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
$env:SCHOLARLENS_WORKSPACE_V4 = 'true'
$env:SCHOLARLENS_EVOLUTION_LAB = 'true'
$env:SCHOLARLENS_LAB_DB = (Resolve-Path output/workspace-release/lab.sqlite3).Path
& $python -m tools.research_demo --port 0 --runtime output/v4-local-preview --corpus fixture
```

端口由系统分配，启动日志输出实际地址。关闭 V4 开关后新任务走默认策略。关闭 Lab 开关后重启演示进程，两条实验 API 会返回 404。删除前端开关并重新构建可隐藏实验页面路由。现有任务按创建时的策略和语料代次恢复。

## 独立评测

新套件按主题和论文分组，训练、开发和独立组各 14 道，每组包含 7 种题型。三组各运行 7 种配置，共 294 条逐题记录。相同任务绑定相同公开摘要、允许论文和 10 次工具上限。离线模式模型上限为 0，两个受控 HTTP 组同用 `controlled-http/1`、深度模式及最多 4 次模型调用。开发回执及代码和策略摘要在开启独立组前锁定。

| 独立组，每组 14 题 | 摘取正确首句 | 缺失/干扰时拒答 | 来源复核 | 工具调用 | 模型调用 | 累计运行秒数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V1 | 1/2 | 0/4 | 17/17 | 80 | 0 | 8.27 |
| V5 | 1/2 | 0/4 | 25/25 | 86 | 0 | 7.53 |
| W4 答案契约 | 2/2 | 4/4 | 25/25 | 92 | 0 | 7.64 |
| W4 受控模型 | 2/2 | 4/4 | 25/25 | 92 | 56 | 8.25 |
| W4 同模型规划和决策对照 | 2/2 | 4/4 | 25/25 | 92 | 28 | 7.52 |
| W4 加候选技能 | 2/2 | 4/4 | 25/25 | 92 | 0 | 6.48 |
| W4 加候选技能和检索配额 | 2/2 | 4/4 | 25/25 | 92 | 0 | 7.53 |

W4 对 29 条候选命题进行了机械支持性判断，仅 2/14 个问题达到整题发布门槛。该组有 7 道题触发无新增证据的调用规则，有 4 道触发比较条件不足规则。每类规则记录的是可回查现象，其归因仍可复核。其余复杂题的正确拒答率和最终成功率有待人工标注。受控模型的 Token 用量为空，外部模型调用和实际模型费用均为 0。候选技能在独立组触发了 6 道题，两个候选均被拒绝晋升。真实模型和人工科研质量均待验证。

旧 18 题是已开启的历史回归，结果见 [基线审计](V4.0.md)。逐组实验摘要、策略配置、浏览器尺寸回执和内容摘要见 [验收数据](evidence/receipt.json)。完整公开轨迹和逐题失败说明保存在本地实验库，账户、真实用户任务、原始论文和模型配置不进入版本库。

## 重现实验

需要本地 Git LFS 中的固定公开语料，读取时核对 SHA-256。每次回放使用一个全新的输出目录。独立组已经开启，之后重跑只能算作复现。未来调参应使用新的独立组。

```powershell
$out = New-Item -ItemType Directory -Path ('output/replay-' + [guid]::NewGuid())
$env:TEMP = (New-Item -ItemType Directory -Force output/v4-tmp).FullName
$env:TMP = $env:TEMP
foreach ($split in 'train','dev','independent') {
    & $python -m tools.research_eval.workspace_arena --db "$out/lab.sqlite3" --policy "$out/policy.json" --split $split --output "$out/$split.json"
    if ($LASTEXITCODE -ne 0) { throw "Replay failed for $split" }
}
& $python -m tools.research_eval.workspace_registry --db "$out/lab.sqlite3" history
```

## 验收和边界

- 后端研究、既有 Agent、个人模型、PDF 与上传防护等回归共 399 项通过。另有 4 项新增归因及恢复专项通过。1 项需要显式启用的本地 ES 集成跳过。验证全部使用隔离存储。
- 前端 45 项测试通过。结构检查和 TypeScript/Vite 构建通过。Chrome 在 1440、820、390 像素宽度分别从账户创建研究、读取答案契约并对照版本，均能展开执行动作且整页无横向溢出。iPad 和安卓使用对应尺寸的浏览器视口验证。
- 第二个真实演示账户读取其他用户的报告返回 404，访问 Lab 返回 403。未登录访问实验室返回 401。Web 端只读，候选审批与回滚在本地操作。研究中断后保持账户、证据和任务契约。模型返回无效计划或决策失败时按确定性策略回退。
- 当前对属性、因果、多篇方法和矛盾的证明仍偏保守。正反例覆盖了主体与属性错配、因果中间环节、方法描述和条件一致的相反报告。独立组证明了摘录和指定缺失题的表现，尚未证明通用语义问答成功率或复杂研究的质量提升。
