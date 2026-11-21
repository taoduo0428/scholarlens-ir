# 运行证据

本次运行目录为 `output/agent-v3/e0-20261121-013913`。每个独立命令保存同名 .log 与 .exit。Git 只保存摘要。核心证据如下。

|文件|内容|
|---|---|
|matched-budget-dev.json|六道开发题 B0/B2 逐任务原始结果|
|dev-publication.json|默认预算下的报告回查|
|trace-v1.json|相同上限下逐候选、逐次动作、账本和实际发布来源|
|retrieval-ablation.json|本地 MiniLM、TinyBERT 与关键词实验|
|harness/summary.json|11 个真实 pytest 子进程及 JUnit|
|backend-isolated.log|剔除外部写索引集成测试的后端回归|

另有本次实际执行的 V0–V7 冻结结果、公开训练程序来源、逐题轨迹和人工待评材料。便于复查的 SHA-256 汇总在同目录的 [运行回执](RUN_RECEIPT.json)。命令从项目根目录运行，先激活交接指南中的 Python 环境。在 PowerShell 中选择新输出目录。

```powershell
$out = "output/agent-v3/replay-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssfff'))"
New-Item -Type Directory -Path $out -ErrorAction Stop | Out-Null
```

|产物（相对本次运行目录）|如何解释|
|---|---|
|trace-v1.json、trace-v2.json、trace-v2-union.json|同预算 V1、首次 V2 和保留原规则后的回查记录|
|question-plans.json、claim-dev.json、fresh-claim-dev.json|规划和发布层的前后两个代码快照。最终 DEV 规则支持 4 条、证据不足 2 条|
|dev-ablation/summary.json、locked-unseen/summary.json|冻结配置、任务级输出、原文校验、权限、资源和错误数|
|dev-ablation/policy.json、skill-decision.json|候选程序、训练轨迹摘要、成本和拒绝理由|
|native-questions.json、read-only-es.log|同一具体本机 ES 索引上的三类研究问题以及只读工具验收|
|final-core.log、final-lint.log、final-web-test.log、final-web-build.log|最终核心回归、Ruff、前端单测与带类型检查的生产构建|
|ui-api.log、screens/、final-live-ui.log、live-screens/|受控路由的三个实际视口，以及真正连接本机 Worker 的 Chrome 原文跳转、下载和账户隔离验收|
|review-36/run.json、review-36/reviewer-sheet.json、review-36/source-materials.json、review-36/pending-scores.json|真实执行输出、未签核空表、公开摘要及定位、待评指标|
|verified-isolated-backend.log|全后端隔离运行，5 个上传组与 587 个其他测试通过，17 项有明确跳过原因。所属 ES 实例与端口已释放|
|isolated-native-6.log|独立节点 5 组上传与 9 项依赖复验，XML 详见交接文档|

以下开发命令需要本机已经具备锁定 LFS 对象。无该对象也可按交接指南在两篇内置资料上启动工作台。

```powershell
python -m tools.research_eval.matched_budget --output "$out/matched-budget-dev.json"
python -m tools.research_eval.dev_publication --output "$out/dev-publication.json" --runtime-parent $out
python -m tools.research_eval.trace_loss --baseline "$out/matched-budget-dev.json" --candidate "$out/matched-budget-dev.json" --output "$out/trace-v1.json"
python -m tools.research_eval.trace_loss --baseline "$out/matched-budget-dev.json" --candidate "$out/matched-budget-dev.json" --policy V2 --output "$out/trace-v2.json"
python -m tools.research_eval.question_graph_eval --split dev --output "$out/plans.json"
python -m tools.research_eval.claim_eval --split dev --output "$out/claims.json"
python -m tools.research_eval.agent_ablation --configs V0,V1,V2,V3,V4,V5,V6,V7 --split dev --output "$out/dev"
python -m tools.research_evolution.evaluate_skill --candidate "$out/dev/policy.json" --split dev --output "$out/skill.json"
python -m tools.research_eval.review_pack verify
python -m tools.research_eval.prepare_review --output "$out/review-36"
```

原独立验收使用相同的 agent_ablation 命令，参数为 `--split unseen --freeze-policy <开发结果>/policy.json` 并指定全新目录。该分组现已开启，后续代码应另冻结独立任务用于验收。人工任务按六个类别各取六道，依照固定哈希选择，排序定义为工具首次实际观察到论文的顺序，未对未选论文填充虚拟名次。由两位评审员独立填写签核空表，再按[盲评协议](../../agent-v2/ANNOTATION_GUIDE.md)导入。
