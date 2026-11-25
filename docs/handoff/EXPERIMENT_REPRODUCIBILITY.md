# ScholarLens 实验复现

工程基线 `e5bda5f33bb52bcd3c15cc1bf37efb4791423ef4`。本手册命令从仓库根运行，输出使用新目录。先执行可离线重建的验收表。

```text
python -m tools.research_eval.pra_scorecard --out gemini-scorecard.json
```

比较该文件与 [PRA_SCORECARD.json](../agent-v8/PRA_SCORECARD.json) 的 JSON 内容。源报告计数、逐题摘要、配对差异和 Gate 判定应一致。保留历史耗时作为环境相关数据。

## 环境

CI 用 Python 3.11、Node.js 22.18.0。安装 Git LFS 后验证历史语料对象。命令中的 upstream 可替换为持有所需对象的远端。

PowerShell：

```powershell
py -3.11 -m venv .venv-handoff
.\.venv-handoff\Scripts\python.exe -m pip install -r backend/requirements-lock.txt -r backend/research/requirements.txt -r backend/research/pdf-layout-requirements.txt
git lfs fetch origin 82a3a083a07833892a2d7bd8d2436e6cee644b60
$env:VITE_RESEARCH_ENABLED = 'true'
Push-Location frontend
npm ci --ignore-scripts
npm test
npm run verify:structure
npm run build:production
Pop-Location
```

Linux/macOS shell：

```sh
python3.11 -m venv .venv-handoff
.venv-handoff/bin/python -m pip install -r backend/requirements-lock.txt -r backend/research/requirements.txt -r backend/research/pdf-layout-requirements.txt
git lfs fetch origin 82a3a083a07833892a2d7bd8d2436e6cee644b60
(cd frontend && npm ci --ignore-scripts && npm test && npm run verify:structure && VITE_RESEARCH_ENABLED=true npm run build:production)
```

后续用该虚拟环境的 Python。冻结语料由 `tools/research_eval/inputs.py` 从 Git LFS 对象缓存读取。来源提交 `82a3a083a07833892a2d7bd8d2436e6cee644b60` 的指针在 `data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl`。语料代次为 `local-jsonl-sha256:49c1062bd28ecb6a0216256d8aa0d02001e4ee174bfb2ce5e61c3d96ed46187c`。若 fork 不提供历史 LFS 对象，经授权从原始远端补取。获取失败即记 BLOCKED，记录缺项。

## 回放矩阵

Silver 使用冻结的 111 条任务及 `docs/agent-v6/e10/silver-labels.jsonl`，70 条正例和 41 条负例。其字段级事后复核是单次 AI。历史组为 24 对加 4 个三篇组，每组综述、引文、版面三类。PRA 独立组以 `scholarlens-pra-transfer-v1` 哈希排序选出 30 篇论文，固定 12 组。QASPER 使用发布方测试集 v0.3，公开人工参考，早期选样使用 `scholarlens-qasper-v1:`，新验收重放清单中的确定性选择。Silver 回放不随机抽样。离线回放共享 `trace_loss.execute`，每任务 10 工具、0 模型、120 秒。先执行任务再连接标签。

```sh
python -m tools.research_eval.v6_ci
python -m tools.research_eval.v6_silver
python -m tools.research_eval.v6_replay --policy E11 --pra-arm A --output output/handoff/A/diagnostic
python -m tools.research_eval.v6_replay --policy E11 --pra-arm G --output output/handoff/G/diagnostic
python -m tools.research_eval.v7_compare --policies E11 --pra-arm A --output output/handoff/history-A
python -m tools.research_eval.v7_compare --policies E11 --pra-arm G --output output/handoff/history-G
python -m tools.research_eval.pra_holdout --manifest docs/agent-v8/holdout.json --out output/handoff/holdout --arms A B G
python -m tools.research_eval.pra_holdout --fulltext --out output/handoff/holdout-body --arms A G
```

A–G 消融对 B–F 使用与 A/G 相同命令和匹配目录名。评分器与逐题报告输出如下。

```sh
python -m tools.research_eval.pra_summary --root output/handoff --out output/handoff/summary --arms A=A B=B C=C D=D E=E F=F G=G
```

回放生成 `diagnostic/E11/scores.json` 和逐题轨迹。与 [最终消融](../agent-v8/ablation-final/metrics.json)、[独立留出](../agent-v8/holdout-results.json)、[全文留出](../agent-v8/fulltext-transfer-results.json) 对照。先核逐题新增、丢失、误发和引用，再核汇总。历史全组的 1/28 采用报告关系覆盖口径。保存不同代码轮次的运行目录。

## QASPER

下载[官方测试归档](https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz)，放入 `output/handoff/qasper-test-and-evaluator-v0.3.tgz`。脚本验证 SHA-256 `72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72`。冻结第三批清单提取与回放如下。

```sh
python -c "import json,pathlib; p=pathlib.Path('docs/agent-v8/qasper-acceptance.json'); pathlib.Path('output/handoff/qasper-manifest.json').write_text(json.dumps(json.loads(p.read_bytes())['manifest']), encoding='utf-8')"
python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --manifest output/handoff/qasper-manifest.json --out output/handoff/qasper-third
python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/qasper-first
python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 2 --out output/handoff/qasper-second
```

用当前提交运行早期批次属于同题复测。首次盲测结果和修复后结果见 [QASPER 结果](../agent-v8/qasper-human-results.json) 和 [同题复测](../agent-v8/qasper-same-case-reruns.json)。第三批历史运行提交为 `c352436d4a92dd1b4e917c8d57d3c09f7a1856d0`。比较读到人工证据、完整参考片段、来源可回读、负例误发和工具调用。每题的原问题可按问题 ID 读公开归档。

## 浏览器与完整工程

研究构建产物从 frontend 的实际输出目录取，真实产品 runner 需要 Chrome 与已配置的回环隔离环境 identity，禁止连接共享数据卷。

```sh
python -m tools.research_eval.pra_product --identity output/handoff/isolated-identity.json --dist frontend/dist --out output/handoff/product
python -m tools.research_eval.v6_vector_fixture --es-home "REPLACE_WITH_ES_8.19.23_HOME" --offline-fixture infra/.runtime/elasticsearch-8.19.23/data --full-suite --delivery backend/.runtime/p0-delivery
```

第二条为历史 Windows 真实验收入口，ES 程序目录使用 ASCII 路径，源索引必须处于停止状态，runner 启动数据副本并隔离端口。Linux/macOS 可按部署手册与 CI 启动独立 Compose，随后运行 `python -m pytest -q backend/tests` 并记录缺少外部条件的项目。Compose 搜索镜像是 8.19.26。pytest 的统计不得冒用 Windows 验收数字。检查产品日志中注册 201、登录 200、检索、报告和导出、匿名 401。详见 [工程测试](../final/TEST_RESULTS.md) 与 [部署验收](../final/DEPLOYMENT_ACCEPTANCE.md)。

## Provider

兼容 API 使用 Provider 官方 HTTPS API base 和该账号可用的模型 ID。例如 DeepSeek 兼容端点用其官方 base、实际账户目录中的模型 ID，协议选 `chat_completions`。交互配置通过用户的个人 Provider 界面。CLI live runner 从进程环境读取 `AI_BASE_URL`、`AI_MODEL`、`AI_API_KEY`，可选 `AI_PROTOCOL`、`AI_TOKEN_PARAMETER`。切换时记录模型、协议和 Token 参数，使用环境注入密钥。真实验收优先配置 `E10_MAX_USD` 与 `E10_MAX_RATE_USD_PER_MTOK`。每轮最多 4 请求、每请求 48,000 字节及 1,400 输出 Token。

```sh
python -m tools.research_eval.v7_live_research --controlled --output output/handoff/model-controlled.json
python -m tools.research_eval.v7_live_research --live --output output/handoff/model-live.json
```

PowerShell 用 `$env:SCHOLARLENS_PRA_ARM='G'` 设置候选，POSIX 用 `export SCHOLARLENS_PRA_ARM=G`。调用预算模式需显式加 `--call-budget-only`，历史真实尝试缺配置退出 2、请求 0。受控 HTTP 用 in-process transport，历史四阶段均有回执。定位失败优先核对 planning/decision 的结构绑定与回退，再看 analysis 的原文窗口与 ID，最后检查 synthesis 的陈述排序及截止时间。诊断查看报告 `provider_usage`、阶段 receipts、trace IDs、Token usage 和 gates。缺 usage 时费用留空，价格上界估计与实际账单独立记录。

## 材料取得

- Git 已提交 [消融逐题结果](../agent-v8/ablation-final)、[外部验收](../agent-v8/qasper-acceptance.json)、[工程结果](../final/TEST_RESULTS.md)。
- 历史语料依赖 Git LFS，QASPER 归档依赖另行下载。完整数据卷 `infra/.runtime/elasticsearch-8.19.23/data`、交付环境 `backend/.runtime/p0-delivery`、Chrome identity、运行时模型文件、本机完整追踪和 PDF 不随交接提交。
- 历史只在本机的 `output/v8/pra/` 原始回放、抽取式 ONNX 试验和部分实验产物，以及 `output/final-20261124/` 的原始日志均按 Git 忽略规则处理。对只有摘要的条目，优先使用已提交的 JSON 及公开档案再运行。Provider secret 需由操作者从授权来源配置。
