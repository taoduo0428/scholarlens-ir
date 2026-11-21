# P0 源码、语料与历史性能审计

2026-11-20。在隔离 worktree 读取 Git 对象和本地 LFS 实物。以下源码行号固定到 `3e130b0`。四个分支的完整 SHA、资产计数和语料摘要见 [原始统计（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-830e3682cffd)。

## 四分支基线

| 远端分支 | SHA | 跟踪文件 | 检查结果 |
|---|---|---:|---|
| main | ec3ef9f | 24 | 后端、前端为占位目录，有旧批 JSONL、TEI 转换和去重脚本 |
| feat/pdf-parser | 82a3a08 | 28 | 两批正式语料及来源 CSV，新增 arXiv 分批资产，尚无应用后端和前端 |
| jwj | 1660f60 | 336 | 包含 RAG、Agent、个人模型、MCP、检索后端以及 React 前端 |
| zjl | 3e130b0 | 345 | 以 jwj 为祖先，新增 14 个提交。模型协议、引用修复、前端、扩库及运维工具已有实质增量 |

本地复查使用 `git for-each-ref refs/remotes/origin`、`git ls-tree -r --name-only origin/<分支>`、`git rev-list --left-right --count origin/jwj...origin/zjl`（结果 0 与 14）以及 `git diff --stat origin/jwj..origin/zjl`（38 文件）。实现从 zjl 派生，正式数据从 feat/pdf-parser 的 Git 对象读取。

## 旧系统兼容点和复用风险

| 能力 | 实现与必须保留的行为 | 位置 |
|---|---|---|
| 有界 Agent | 最多 3 查询、10 工具调用、10 证据、1 次引用修复，120 秒。先拟定候选查询，依次检索，达到数量就提前停止，再读回来源和校验生成。现有 trace 记在单次调用对象中。V2 的跨轮缺口决策和恢复另建 | `backend/agent_runtime.py:38–56,99–121,132–199` |
| 旧问答入口 | ask、summarize、compare、evidence 均由 `/api/agent/run` 服务。总结限 1 篇，比较限 2–10 篇。无证据、未限定论文且已配置模型的普通问答可返回标记为 general_answer 的通用答复。已核对来源在模型问题时可保留。旧前端 ask 和证据均传 keyword | `backend/rag.py:690–731,795–801`，`frontend/src/services/ai.ts:28,34` |
| 引用与阅读 | 旧版按 paper/chunk 重新生成片段，在块内查逐字子串，并用源块 locator 回填。比较逐篇检查引用。指定论文总结/比较抽首、中、尾块。V2 应按所需指标定向检索，并保留旧 ID；逐字匹配只证明引文存在 | `backend/rag.py:593–656`，`backend/chunks.py:6–43` |
| 检索 | 真 ES BM25、MiniLM 精确余弦、RRF(k=60)，论文候选窗口 1000。dense 默认按 paper_id 折叠，非折叠分支可返回限长片段。向量映射检查 base_generation 和模型 revision；V2 全程使用首次授权的具体 generation | `backend/retrieval.py:11–32,58–102,133–145`，`backend/app1.py:235–257` |
| 账户与个人模型 | 旧 Store 独立 SQLite WAL。authenticate 验证 session 到期和用户启用状态。个人配置按请求认证后建立 settings 副本，支持 Responses/Chat Completions，限制 HTTPS 443，传输前验证公有 IP。V2 复用认证和模型边界，Worker 凭据丢失时需重新提供 | `backend/accounts.py:189–207,307–321`，`backend/personal_ai.py:12–74`，`backend/rag.py:443–456,658–667` |
| 上传、检索与 MCP | 上传记录和预览查 owner/admin。旧公开搜索在 real 模式可拼接已索引的上传别名，read_paper 也会回查该别名。MCP 只连 loopback，有 3 个只读工具，其中 read/带 ID 的 retrieve 限定 source-sha256 前缀；未带 ID 的 search/retrieve 转调旧公共 API。V2 授权需逐来源核对，尤其在未指定 paper_ids 时，不能把旧公共召回的所有结果自动授权给私人任务 | `backend/uploads.py:247–260,315–345`，`backend/app1.py:253–288,366–392`，`backend/mcp_server.py:16–64` |

## 离线语料、PDF 与可重现入口

- 两批正式 JSONL 已从本机逐行解析，共 **4,000 个唯一 paper_id**。旧批 859 条，39,226,615 字节；新增 3,141 条，151,152,468 字节。两批 ID 交集为 0。两批 `fulltext` 非空数分别为 859 和 3,141，文本可用质量需单独审计。新增 LFS 实物 SHA-256 已与 Git 指针核对。
- 复查旧批用 `git cat-file -s origin/feat/pdf-parser:data/paper_jsonl/papers_final.jsonl`。新增指针用 `git show origin/feat/pdf-parser:data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl`，实物验证用 `git lfs fsck --objects origin/feat/pdf-parser`。流式解析、核验引用的实现应从具体 ref 解析 Git 数据或 LFS OID，无需把数据提交到工作分支。
- 四个分支树中，PDF 仅见 jwj/zjl 的浏览器上传 fixture，路径为 `frontend/tests/fixtures/browser-upload.pdf`。2026-11-03 部署记录中有 859 份旧原件，新增 3,141 篇原件缺失，同日服务使用 236,947 个 384 维片段。此审计只复核本地 Git 与 LFS，线上 PDF、ES 或索引状态未实测。历史数量与资源约束见 `docs/operations/16_CORPUS_4000_20261103.md:3–7,24–32,42–56`。
- 可断网运行的接口 fixture 在 `backend/tests/test_agent.py:24–76`，它使用受控文档、检索、生成和 planner 替身。`python -m pytest backend/tests/test_agent.py -q` 覆盖本地代理契约，`python tools/agent/run_harness.py --python <测试解释器>` 执行按 case 映射的 pytest 节点。真实研究评测还需独立的任务标签、查询和证据判断。

## 八查询历史延迟

2026-10-27 Windows 11、Python 3.11.9、ES 8.19.23、512 MB 堆、单分片、MiniLM CPU 两线程。对应 **859 篇 / 49,420 片段**。固定 8 查询，每种模式预热 1 次，串行 3 轮，每种模式 24 请求。时间覆盖本机 HTTP、嵌入、ES 和序列化。返回 top 5，P95 按 nearest-rank。

| 模式 | 平均 ms | P50 ms | P95 ms |
|---|---:|---:|---:|
| keyword | 39.172 | 36.092 | 79.001 |
| semantic | 509.002 | 505.846 | 557.710 |
| hybrid | 584.131 | 544.096 | 794.262 |

数据来自 `docs/development/backend/SEARCH_EVALUATION.md:5–36`。计时逻辑见 `backend/evaluate_search.py:13–79`。原逐查询运行 JSON 位于历史运行目录，未纳入此版本 Git 树。本次没有重测 ES 延迟。无人工 qrels，P@5/nDCG@10 保持 null。P2 的 4,000 篇表现或 ANN 对照须使用各自版本、环境、固定查询和独立结果。
