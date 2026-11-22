# E11 研究程序的发布与回滚

后端维护者通过离线发布命令把独立审核过的研究程序绑定为 E11 的可用版本。输入为有限步骤程序、冻结语料版本、配对回放和实验室审批记录。发布产生不可变收据。提交任务时固定此收据，Worker 恢复任务时按同一版本加载程序。回滚决定后续新任务的版本。

## 2026-11-22 冻结实验

在热学与自动机的两个独立论文组上，将相同的 14 个问题各回放两次。两组使用相同 E11 执行图、语料、基础技能、策略和预算。候选程序 `rs-5a7929dd6e8ff7b0abb9` 由公开训练轨迹编译而来。

| 指标 | E11 基线 | E11 加候选 |
| --- | ---: | ---: |
| 任务 | 14 | 14 |
| 触发候选步骤 | 0 | 2 |
| 工具调用 | 93 | 93 |
| 模型调用 | 0 | 0 |
| 回读核验的来源 | 28/28 | 28/28 |
| 与基线相比，研究输出有变化的任务 | — | 0/14 |

两次回放的答案、直接陈述、主张、字段判定和来源完全相同。候选 `7abec987f73a0e1627f2a85e16a1b0e13aa41efb28d9d6f5480adbdc5eb7c26f` 在隔离实验库登记为 `rejected`。实验账本记录了 `unchanged_research_output` 和 `awaiting_signed_independent_quality`。生效版本仍为基线。

## 重放和维护

在仓库根目录使用项目 Python 和研究依赖。将下述实验放在新的本地目录；语料沿用冻结的公开 LFS 对象。离线环境需要先具备该对象。

```powershell
python -m tools.research_evolution.program_release stage --lab output/e15-run/lab.sqlite --output output/e15-run/stage
python -m tools.research_evolution.program_release register --lab output/e15-run/lab.sqlite --candidate output/e15-run/stage/candidate.json
```

`stage` 导出候选和回归摘要。对于有质量收益的新候选，在登记时提供 `--review review.json`。独立评审应填入评审者、候选摘要，以及每题包含基线判断、候选判断和来源依据的 `tasks` 记录。登记会产生不可变的处置记录，请在证据准备完成后登记。维护者在可信主机上执行后续操作，文件系统权限控制实验库和发布库的写入。将发布库目录以只读方式提供给 Worker，并设置 `SCHOLARLENS_APPROVED_REGISTRY`。

```powershell
python -m tools.research_eval.workspace_registry --db $Lab approve --version $Candidate --reviewer $Approver
python -m tools.research_evolution.program_release publish --lab $Lab --candidate $Candidate --registry $Registry --operator $Operator --expected $Current
python -m tools.research_evolution.program_release rollback --registry $Registry --operator $Operator --expected $Release
```

首次发布的 `$Current` 为 `baseline-v1`。命令输出新版本。每次发布和回滚都在同一事务内比较当前版本并写入审计事件。Worker 用 `release-<sha256>` 固定研究程序、测试过的基础技能和策略。发版后变动的回放、与冻结任务不符的语料范围、缺少来源证明的行、超预算、没有执行过的程序，以及把相同产物标为改善的评审都会阻止发布。

## 正式入口集成验收

```powershell
python -m pytest backend/tests/research/test_program_release.py backend/tests/research/test_evolution_gates.py backend/tests/research/test_workspace_lab.py -q
```

本轮 19 项通过。集成测试使用正式 `create_app`、实际账号注册与登录、研究 API、SQLite 任务存储和 Worker，将搜索适配到隔离的本地语料。测试用的审批与质量判断采用合成夹具。普通用户提交任务时由服务端选定版本，跨账号读取返回 404。重建应用并回滚后，重启前排队的任务按固定版本执行两个程序步骤，随后创建的任务执行基线。发布审计损坏时新建任务返回 503。工程验收证明了发布与回滚链路，公开冻结实验给出了本次候选的质量结果。
