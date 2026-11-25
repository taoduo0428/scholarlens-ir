# ScholarLens EvoResearch V9 研究智能总体架构

## 1. 架构目标与不变性原则

ScholarLens V9（分支 `gemini/evoresearch-quality`）在不更换既有技术栈（Python 3.11、FastAPI、LangGraph、SQLite、Elasticsearch 8.19、MiniLM、React、OpenTelemetry）与不降低 Evidence Verification / Publication Gate 任何确定性校验标准的前提下，将系统从“原文定位与单句摘录的 Evidence Retrieval Agent”升级为具备复杂学术推理、子句归属、跨论文综合与人机协同能力的 Evidence-driven Research Reasoning Agent。

系统保留以下核心安全与发布不变量：
- **原文定位与 Hash 强绑定**：任何引用片段必须经过 `verify_source_quote`（`paper_id`、`chunk_id`、`locator`、`quote`、`source_hash`、`corpus_generation` 六元组精确匹配），并满足 `tools/research_eval/v7_independent_verifier.py` 独立回读验证。
- **权限与作用域隔离**：私有上传受 `owner_id` 与 `include_own_uploads` 门禁控制；跨篇推断不得越出任务作用域。
- **服务端主控发布权**：模型仅提供规划建议（`plan_questions`）、句角色提名与证据关联标签（`SourceReview`）和排序提示（`Narrative`），最终真伪认定、归属裁决与 Publication Gate 发布裁决完全掌握在服务端确定性校验器手中。
- **零侵入在线回滚与多臂隔离**：通过 `backend/research/arms.py` 将历史基线 `A`（E11）、`B..G`（PRA 各组件）与 V9 实验假设 `H1..H5` 及组合候选 `R` 完全正交隔离；线上默认 `SCHOLARLENS_PRA_ARM` 维持 `"A"`。

## 2. 模块化实验臂设计 (`backend/research/arms.py`)

`PraArm` 扩展至 `Literal["A", "B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "H5", "R"]`，其中：
- `A`：E11 原始基线，不开启 PRA 与 H1–H5；
- `B..G`：PRA 既有六条消融臂，行为严格保持与基线 `136763f` 一致；
- `H1..H5`：在 `G`（完整 PRA）基础上单因子叠加对应改进；
- `R`：`H1 + H2 + H3 + H4 + H5` 统一组合候选臂（冻结提交 `0c8f966`）。

## 3. V9 核心增强模块与数据流

```
用户复杂研究目标 (TaskInput)
   │
   ▼
[1. 计划与需求编译] questions.py + provider_adapter.py (H5 skeleton 强对齐)
   │               └─▶ node_fields.py 编译字段与能力约束 (text / measurement / layout)
   ▼
[2. 自适应检索与预算环] graph.py (_retrieve / _critique) + pra_gaps.py
   │  ├─ H4: 单篇显式 scope 跳过冗余 search_papers
   │  ├─ H4: sentence_complete=True 使用完整句对齐窗口 sentence_windows_for (<=980 chars)
   │  ├─ H4: 论文内 VoI 重排 (_voi_rank_rows) + 单篇 Round-1 预算保留 (free_calls>=3)
   │  └─ 全保留片段强制 verify_source_quote 双重核验
   ▼
[3. 研究档案与语义核验层] field_gate.py + claim_verifier.py
   │  ├─ H1: discourse_attribution.py 子句级归属 (AUTHOR / PRIOR / SPECULATIVE / NEGATED / 跨句主语链)
   │  ├─ H2: semantic_slots.py 结构化语义槽对齐 + 4-Gate 神经符号校验 (去除无效整句 fullmatch)
   │  └─ H5: workspace_model.py 紧凑 SourceReview 提名 + research_profile.py 服务端强归属裁决
   ▼
[4. 跨论文关系与综合推理层] overview.py + open_relations.py + multihop_fields.py + field_publication.py
   │  └─ H3: 8 大词法方法家族对齐、共享任务/对比结论推理、3 跳开放因果链接与 derived_synthesis 溯源绑定
   ▼
[5. Publication Gate 与结构化报告] reports.py (verified_direct / derived_synthesis / unknown_or_insufficient)
```

## 4. 新增与改动核心文件清单

- 实验控制与路由：[arms.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/arms.py)
- H1 子句级话语归属与共指：[discourse_attribution.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/discourse_attribution.py)、[research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py)、[profile_frames.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/profile_frames.py)
- H2 结构化语义槽与四门禁校验：[semantic_slots.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/semantic_slots.py)、[claim_verifier.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/claim_verifier.py)、[field_gate.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_gate.py)
- H3 开放域跨论文综合与多跳：[open_relations.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/open_relations.py)、[overview.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/overview.py)、[multihop_fields.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/multihop_fields.py)、[field_publication.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_publication.py)
- H4 完整句检索窗口与预算控制：[passages.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/passages.py)、[registry.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/registry.py)、[evidence_graph.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/evidence_graph.py)、[subject_facts.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/subject_facts.py)、[quantitative_evidence.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/quantitative_evidence.py)、[graph.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/graph.py)
- H5 模型协作与提示稳定性：[provider_adapter.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/provider_adapter.py)、[workspace_model.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/workspace_model.py)
- V9 专项测试与评估工具：`backend/tests/research/test_v9_*.py`、[v9_freeze_holdout.py](file:///c:/Users/lenovo/Desktop/检索agent/tools/research_eval/v9_freeze_holdout.py)、[v9_quality_scorecard.py](file:///c:/Users/lenovo/Desktop/检索agent/tools/research_eval/v9_quality_scorecard.py)
