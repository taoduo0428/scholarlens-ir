# ScholarLens E10 研发与验收 · 2026-11-21

此分支交付研究策略、111 题证据裁决、逐题回放数据和隔离业务测试。E10 在 12 组未见论文的跨文综述中通过 2 组。真实模型验收和 GitHub Actions 运行仍缺外部条件。工程、研究质量和产品闭环评为 PARTIAL，正式发布为 BLOCKED。

[评测报告](EVALUATION_REPORT.md) · [六组逐题诊断](FAILURE_ANALYSIS.md) · [安全与恢复](SECURITY_REPORT.md) · [发布条件](RELEASE_READINESS.md) · [机器可读结果](acceptance.json)

## 变更与版本

基线 `5dd0cbce22635c891e704aba851733cc67869dbf`，开发分支 `codex/e10-research-closure`。冻结协议 604e5f8，研究策略 a83bf84，独立评审 00e798b，CI 与隔离工具 a711cfc，运行时 b24d162，同题结果 ab04bed。PR 头部记录最终提交及完整变更。目标分支为 zjl，main 与基线 zjl 各有 4 和 105 个独有提交。研究分支和公开交付在 [PR #5](https://github.com/taoduo0428/scholarlens-ir/pull/5) 查看。

保留原有图执行器、持久任务和账户边界。E10 从同篇摘要中提取作者归属明确的方法与结果，跨论文结论须关联双方原文和可比维度。新增 E10 实验开关和两张按任务关联的 SQLite 表。旧任务的图进入次数可为 null。个人模型可以评审字段候选与排序，来源和发布权限仍由服务器检查。完整变更见[变更日志](CHANGELOG.md)。

## 独立阅读与实验

两名来源盲评者和第三名裁决者在分离上下文复核 40 篇摘要，完成 111/111 题。有 58 道可答、12 道部分可答、20 道不可比、21 道缺少证据。103 道初评状态一致、8 道状态有分歧、共 33 道有实质分歧，裁决后未留未决争议。已检验每处来源定位与哈希。三个上下文属同一模型家族，人工 Gold 为 0。详见[评审清单](e10/review-manifest.json)。

五版策略完成 290 次冻结/配对回放和 555 次 Silver 回放。开发论文综述从 E9.1 的 0/6 提升到 2/6，未见组从 1/12 到 2/12。未见组中有一个旧版成功例退步。111 题中 E10 的题级可答性判断命中 34，70 道可答或部分可答题均缺少直接主张。证据窗口与标签有交集、工具执行完毕均不能替代所问字段的成功发布。

## 实际命令与结果

以下从仓库根目录运行，frontend 命令在前端目录执行。测试数据库、pytest 临时目录、浏览器测试账户与 Elasticsearch 均使用独立路径。命令中的 PY 是对应项目虚拟环境解释器，TMP 是每次新建的测试目录，ES_HOME 是产品指定版本在 ASCII 路径的临时安装。历史复现需要本地已授权语料和测试模型资产。未单独计时的项记 N/A。

|检查|执行命令或入口|退出码|通过 / 失败 / 跳过或阻塞|耗时|
|---|---|---:|---|---|
|基线|PY -m pytest，基线研究及相关用例；npm test|0 / 0|408 / 0 / 1；前端 45 / 0 / 0|65.24 秒；0.26 秒|
|完整后端首次执行|PY -m pytest -q backend/tests --basetemp TMP|1|559 通过，3 失败，89 个 setup 错误，22 跳过|627.57 秒|
|最终研究、Agent、响应、恢复、安全|PY -m pytest -q backend/tests/research backend/tests/test_agent*.py backend/tests/test_ai_responses.py --basetemp TMP（文件通配符由调用端展开）|0|417 / 0 / 1；跳过的是固定 9200 的可选只读探测|84.66 秒|
|隔离 859 篇旧套件|PY -m tools.research_eval.v6_legacy --es-home ES_HOME --seed backend/.runtime/p0-delivery/papers_index_ready.jsonl|1|旧模块 111 过、1 失败、11 跳过。该夹具只有原始检索索引，缺少基础向量别名|163.42 秒|
|缺失向量的 12 项复验|PY -m tools.research_eval.v6_vector_fixture --es-home ES_HOME --offline-fixture infra/.runtime/elasticsearch-8.19.23/data|0|12 / 0 / 0。隔离副本有 859 篇及 49,420 条向量，原文件签名由大小和修改时间核对|23.08 秒|
|真实 ES、账户与 Research API|PY -m tools.research_eval.v6_native --es-home ES_HOME|0|5 / 0 / 0，163 项上传和账户路由断言。另验实际 BM25、研究任务、原句、重复提交与版本标识|上传 5 组 48.35 秒|
|浏览器业务流程|PY -m tools.research_eval.v6_browser --fixture-lab DEMO_LAB --dist DEMO_FRONTEND --output TMP|0|e9-field-release 与 workspace-v4-live 两条流程通过|N/A|
|受控模型|PY -m tools.research_eval.v6_model --controlled|0|规划、动态决策、分析、综合四阶段均调用，报告保有双方前提|见运行回执|
|外部模型|PY -m tools.research_eval.v6_model|2|BLOCKED，缺项目 AI 配置和价格上限，供应方调用 0 次|N/A|
|来源与冻结|PY -m tools.research_eval.v6_silver；PY -m tools.research_eval.v6_ci|0 / 0|111 题通过源定位核验、9 个冻结文件一致|N/A|
|前端|npm test；npm run verify:structure；npm run typecheck；npm run build|0 / 0 / 0 / 0|45 项测试通过，结构、类型和构建通过|0.92 / 0.52 / 6.53 / 11.14 秒|
|静态与依赖|PY -m ruff check backend tools/research_eval --select E9,F63,F7,F82；新模块 Ruff；npm audit --audit-level=moderate；pip-audit --no-deps --disable-pip 对锁定版本|0|检查通过，前端 0 个已知漏洞，Python 72 项锁版本的已知漏洞为 0|npm audit 3.97 秒，其余 N/A|
|远端 CI|gh run list 及 gh pr view；workflow 路径推送|推送 1|BLOCKED，当前 OAuth token 缺 workflow 权限，PR 的远端运行记录为 0|N/A|

按 JUnit 的测试文件、测试名和参数逐一关联，完整后端首次执行中所有 92 个失败或错误的用例均在后续验收中获得通过记录。发布截止时间测试首次出现线程调度时序断言失败，在单独及最终研究套件均通过。这份结果保留分组和首次失败，完整后端的一次全绿运行仍待取得。

首次原生 ES 测试因中文路径下 JVM entitlement agent 加载失败。将相同 ZIP 暂放 ASCII 路径后启动成功，使用回环随机端口并核验 cluster UUID、alias、generation 和程序所有权。两个 ES 验收方式分别使用合成材料与已有论文数据的隔离副本。受控模型首次运行只完成规划和决策，因发表前没有把已核验字段候选供给语义环节。修复后四阶段通过回归。浏览器验收使用授权演示库快照、一致的报告 ID 和经认证的 API 核对下载内容。

## 业务场景

|场景|验收范围|结论|
|---|---|---|
|A 单篇研究|实际登录、检索、图执行、引文核验和报告读取，真实 ES 与浏览器两次独立运行。|PASS|
|B 双篇对比|受控对比和双来源绑定通过，未见论文综述 2/12。|PARTIAL|
|C 原句与 PDF 坐标|浏览器显示原句已核验、版面缺口明确。字段展开、桌面及移动布局、刷新恢复、导出内容均通过。|PASS|
|D 证据冲突|受控来源关系测试区分实验条件差异与真正冲突，缺少自然冲突论文的独立语义评审。|PARTIAL|
|E 中断恢复|实际子进程中断后重开，已提交证据哈希和预算保留，图执行记录两次。|PASS|
|F 跨用户|第二个测试身份访问第一人的任务、事件、报告和证据均获 404。实际账户上传隔离另外验证。|PASS|
|G 外部模型|受控 HTTP 完成四阶段；外部凭据不足，真实供应方验收受阻。|BLOCKED|
|H 故障反馈|修复实际发现的模型候选遗漏，回归验证四阶段，保留最初失败和最终结果。|PASS|

## 交付边界

项目仍在原桌面工作区。临时 ES 安装、矢量索引副本、测试运行库和本轮回滚副本经核验移入回收站。保留原始研究数据、盲审原件、845 份完整轨迹、日志以及 XML 作为复核依据。PR 面向 zjl，合并和生产发布属于单独步骤。工作流在本地标准路径就绪，仓库提供逐字相同的 infra/ci/agent-ci.yml。
