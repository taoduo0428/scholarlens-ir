# ScholarLens EvoResearch V9 最终研发交付报告

**工作分支**：`gemini/evoresearch-quality`（基于交接基准提交 `136763f76ec2c0bf4a3e1836721f952a0e0a4af8`）
**候选冻结提交**：`0c8f966`（`R = H1 + H2 + H3 + H4 + H5`），工程作用域修复后最新提交：`b799ae2`
**默认在线安全开关**：`SCHOLARLENS_PRA_ARM="A"`（支持环境变量切换 `"A"` / `"G"` / `"R"`）

---

## 一、十三个核心交付问题完整答复

### 1. 基线重跑是否完整复现，历史快照与当前代码差异是否解释清楚？
是。已完成 Stage A 全套复现并归档于 `output/handoff/baseline/run_ledger.json`：
- **精确分离历史快照与重跑结果**：历史冻结 `docs/agent-v8/ablation-final/metrics.json`（`fe9932f`）中 `G` 为 `20/70` `at_least_one`、`22/273` 系统字段、`27` 主张（`case_file_sha256: f6ffa12b...`）；而当前基准 `136763f` 重跑中 `G` 为 `20/70` `at_least_one`、`23/273` 系统字段、`28` 主张（`case_file_sha256: a379b913...`），`A` 在两侧均为 `15/70`、`16/271`、`20`。
- History 28 (`1/28` `linked`, `27/28` 摘录)、v8 Holdout 12 (`0/12` `linked`, `47/51` 主张)、QASPER B1–B3 (`A=1/72`, `G=3/72`)、Controlled HTTP (`PASS`) 与 Live `deepseek-v4.1-flash` (`A/G PARTIAL`) 均完整重现。

### 2. H1–H5 的算法研究结论与具体改动代码在哪里？
全部 5 项假设已在真实源码实现并通过专项单测及同预算消融验证：
- **H1（子句级归属与跨句锚点）**：[discourse_attribution.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/discourse_attribution.py)、[research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py)、[profile_frames.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/profile_frames.py)、[field_gate.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_gate.py)。
- **H2（结构化语义槽与 4-Gate 校验）**：[semantic_slots.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/semantic_slots.py)、[claim_verifier.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/claim_verifier.py)、[field_gate.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_gate.py)。
- **H3（开放域跨论文综合与 3 跳因果）**：[open_relations.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/open_relations.py)、[overview.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/overview.py)、[multihop_fields.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/multihop_fields.py)、[field_publication.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_publication.py)。
- **H4（完整句边界窗口与 VoI 预算控制）**：[passages.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/passages.py)、[registry.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/registry.py)、[graph.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/graph.py) 及全链路 `aligned` 透传。
- **H5（模型骨架强约束与紧凑协同审校）**：[provider_adapter.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/provider_adapter.py)、[workspace_model.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/workspace_model.py)、[research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py)。

### 3. 是否发现了超过 H1–H5 之外的通用关键技术？
是。研发与调试中验证了三项高杠杆通用机制：
1. **研究档案与综合依赖双向兼容过滤**（H3 `open_relations._compatible_paper_claims` 同步 `field_gate` `q1` 规则），消除全组综合被上游 `dependency_open` 静默吞没的问题；
2. **仅限单篇内部的 VoI 重排 + `focus` 标题信号召回非标题窗口**（H4），在绝不破坏跨论文 BM25/IDF 排序的前提下提升核心信息密度；
3. **句级去重与高信号作者句轮转采样（<=24 句）**（H5），使 1400 output token 预算内也能完成高质量多标签+档案协作。

### 4. 同预算消融结果：各自贡献与组合候选 `R` 表现如何？
- **H1**：单臂将 Silver 111 研究档案填充单元由 `736 -> 1086`（+47.6%），直答主张 `28 -> 40`，全字段完成任务翻倍（`1 -> 2`）。
- **H2**：单臂将 Silver 111 直答任务由 `20/70 -> 27/70`（+35.0%）、QASPER Dev 72 题直答由 `3/72 -> 25/72`（8.3x），且保持 `0/41`（Silver）与 `0/24`（QASPER）零误报。
- **H3**：单臂将 History 28 全组综合由 `1/28 -> 10/28`，v8 Holdout Abstract/Fulltext 由 `0/12 -> 5/12` 与 `6/12`。
- **H4**：单臂在节省工具调用的同时将 QASPER B2 抽出句完整读回由 `2/17 -> 7/17`（+250%），Silver 档案单元提升至 `778`。
- **H5**：单臂将 `deepseek-v4.1-flash` 端到端验收从 `PARTIAL` 推至 **9/9 `PASS`**。
- **统一候选 `R`** 展现明显协同超越：Silver 111 达 **`28/70`**（`lost=0`）、系统字段 **`42/273`**（+82.6%）、直答主张 **`60`**（+114.3%）、档案单元 **`1193`**；History 28 综合达 **`13/28`**；QASPER Dev 达 **`26/72`**（省 73 次工具调用）。

### 5. 多维研究质量指标：完整性、正确性、关系综合、错误拒答改善？
见 [RESEARCH_QUALITY_REPORT.md](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/RESEARCH_QUALITY_REPORT.md) 与 [SCORE_COMPARISON_V9.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/SCORE_COMPARISON_V9.json)：`Silver 111` 阳性错误拒答 (`no_direct_on_answerable`) 由 `G` 的 `50/70`（`A` 为 `55/70`）降至 **`42/70`**；全组跨论文关系综合在各多篇集实现零到双位数/30%–46% 的突破；全套核验负例误报 **`0`**。

### 6. 在新的未见 Holdout（以及 QASPER）上实际提升如何？
详见 [HOLDOUT_ACCEPTANCE.md](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/HOLDOUT_ACCEPTANCE.md)：
- **V9 Unseen Holdout 12 Abstract**：`linked_overview` 由 `A/G` 的 **`0/12` -> `3/12`**，总主张 `39 (G) -> 61 (R)`（+56.4%）。
- **V9 Unseen Holdout 12 Fulltext**：`linked_overview` 由 `A/G` 的 **`0/12` -> `4/12`**，总主张 `44 (G) -> 69 (R)`（+56.8%）。
- **V9 Unseen QASPER 32（Human Gold）**：`pos_direct` 由 `A/G` 的 **`0/24` -> `5/24` (20.8%)**，`neg_false = 0/8`，工具数由 `320 -> 306`。

### 7. 真实大模型参与研究过程的验收情况如何？
已在 `wb-api.lingion.cc.cd/v1`（`deepseek-v4.1-flash`, 限次与 `1400` output token 门控）上完成验证，见 [LIVE_MODEL_ACCEPTANCE.md](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/LIVE_MODEL_ACCEPTANCE.md)：`H5` 与 `R` 均获 **`PASS`（9/9 门禁全过，warnings=[]）**；`R` 产出 `grounded_labels=6`, `source_checked_model_fields=5`, `two_paper_relations=1`。

### 8. AI Silver、内部迁移与 Human Gold 是否明确区分？
完全区分，详见 [SCORE_COMPARISON_V9.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/SCORE_COMPARISON_V9.json) 顶层 `evidence_distinction` 字段及各报告独立分节表格，绝不以 AI Silver 或内部迁移替代第三方 Human Gold (`QASPER`)。

### 9. Evidence Verification 和 Publication Gate 标准是否保持严格？
严格保持未降级：所有证据保留依然强制执行 6 元组 `verify_source_quote`、跨篇边界与不可比条件拦截、`contradicted_edges` 撤回，且 `v7_independent_verifier` 在全部分支中实现 `removed_claims = 0`、`invalid_source_claims = 0`。

### 10. 原有工程功能是否全部通过回归？
- `backend/tests/research/`：**`574 passed, 11 skipped, 0 failed`**（含 `test_pdf_layout.py` 与 `test_otlp_delivery.py`）；
- `frontend`：`47/47` 单测、结构校验、生产构建（`VITE_RESEARCH_ENABLED=true`）全过；
- `v6_ci`（9 文件）、`v6_silver --public-only`（111 题）、`pra_scorecard` 不变性、`ruff`（V9 全文件）全过；
- **坦诚标注受限项**：因宿主机目录含中文 `检索agent`，Elasticsearch 8.19.23 Java Entitlement Agent 无法启动，`v6_vector_fixture --full-suite` 未能在本路径启动 ES 节点（故全量 `backend/tests` 中依赖 9200 端口的 ES 测试产生 89 errors + 2 fails）；宿主机未安装 `docker` CLI。

### 11. 如何配置、启用或回滚新研究智能能力？
在线代码默认 `SCHOLARLENS_PRA_ARM="A"`（[api.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/api.py#L98)）。运行时可通过环境变量秒级切换或回滚：
```powershell
# 启用 V9 候选方案 R (H1+H2+H3+H4+H5)
$env:SCHOLARLENS_PRA_ARM = "R"
# 一键回滚至 PRA 基线 G 或原始 E11 基线 A
$env:SCHOLARLENS_PRA_ARM = "G"   # 或 "A"
```

### 12. 还有哪些未解决的问题与下一阶段方向？
1. **表格/公式跨模态直接抽取与全链路推理**：目前 `QASPER` 中答案位于纯公式/Markdown 表格单元格或隐含多段结论的任务尚未被纯句子窗口覆盖，下一步可在 `R` 基础上结合已有的 `pdf_layout`/`layout_binding` 引入受控表格行语义对齐（H6）。
2. **跨论文定量实验对齐与模型辅助关系提议**：目前 `model_budget=0` 下跨论文主要依赖 8 大家族词法对齐；后续可在服务端校验下开放受限的模型关系图谱提案与更多真模型家族测试。
3. **ASCII 部署/测试路径兼容**：CI 或本地运行 ES 8.19.23 向量全套测试应在纯 ASCII 路径进行，以规避 Windows OpenJDK Entitlement Agent GBK 路径故障。

### 13. Git 交付与仓库状态
- 全系列改动以清晰功能提交保存在独立分支 `gemini/evoresearch-quality`（`a601840`, `db4d166`, `99cc0b5`, `fbaddfa`, `a169c5b`, `5915835`, `0c8f966`, `6fbba46`, `b799ae2`, 以及本轮报告提交）。
- 未合并 `main` 或 `zjl`，未执行强制推送或线上生产部署；测试密钥经全盘扫描确认 **0** 残留。
