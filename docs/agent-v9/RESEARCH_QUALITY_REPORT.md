# V9 多维研究质量综合评估报告

本报告依据 [SCORE_COMPARISON_V9.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/SCORE_COMPARISON_V9.json) 与 [EXPERIMENT_MANIFEST_V9.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/EXPERIMENT_MANIFEST_V9.json)，从四大正交维度客观评估候选 `R`（`H1–H5` 组合）相较基线 `A`（E11）与 `G`（PRA）的质量演化。

## 1. 四维标签与证据可信度声明

遵照科研与工程严格界限，所有指标按标签来源显式分层：
1. **AI Silver (`Silver 111`)**：AI 辅助评测集；其中 209 个原始细粒度字段的旧基线人工/AI 后验表冻结于 `docs/agent-v8/silver-field-review.json`（仅对应 `A` 与 `G` 历史版本）；对 `H1–H5` 与 `R` 不重新做主观 AI 覆写，严格使用系统字段、直答主张、研究档案单元及独立确定性溯源核验对照。
2. **内部迁移集 (`History 28`, `v8 Holdout 12`, `V9 Unseen Holdout 12`)**：确定性结构、引用精确性与跨论文关系门禁检验。
3. **Human Gold (`QASPER B1–B3` 96 题 + `V9 Unseen QASPER 32`)**：第三方人类学术标注黄金评测集（包含不可答负例）。
4. **Live Model (`Controlled HTTP` + `Live deepseek-v4.1-flash`)**：真实服务端-大模型闭环调用与结构化门禁验证。

## 2. 维度一：研究完整性与推理覆盖 (`Research Completeness`)

| 数据集与指标 | `A` (E11) | `G` (PRA) | **`R` (V9)** | 相对 `G` 增益 |
| --- | --- | --- | --- | --- |
| Silver 111 至少 1 项直答 (70) | `15` (21.4%) | `20` (28.6%) | **`28` (40.0%)** | **+40.0%** (`+8` 题，`lost=0`) |
| Silver 111 全系统字段发布 (70) | `1` (1.4%) | `1` (1.4%) | **`3` (4.3%)** | **+200.0%** |
| Silver 111 已发布系统字段 (273) | `16/271` (5.9%) | `23/273` (8.4%) | **`42/273` (15.4%)** | **+82.6%** |
| Silver 111 直答主张数 (`direct_claims`) | `20` | `28` | **`60`** | **+114.3%** |
| Silver 111 研究档案填充单元 | `648` | `736` | **`1193`** | **+62.1%** |
| History 28 全组综合 (`linked_overview`) | `1/28` (3.6%) | `1/28` (3.6%) | **`13/28` (46.4%)** | **13x** |
| v8 Holdout Abstract 全组综合 | `0/12` | `0/12` | **`5/12` (41.7%)** | **0 -> 5/12** |
| v8 Holdout Fulltext 全组综合 | `0/12` | `0/12` | **`5/12` (41.7%)** | **0 -> 5/12** |
| V9 Unseen Abstract 全组综合 | `0/12` | `0/12` | **`3/12` (25.0%)** | **0 -> 3/12** |
| V9 Unseen Fulltext 全组综合 | `0/12` | `0/12` | **`4/12` (33.3%)** | **0 -> 4/12** |
| QASPER Dev (72 正例) | `1/72` (1.4%) | `3/72` (4.2%) | **`26/72` (36.1%)** | **8.67x** |
| **QASPER Unseen 32 (24 正例, Gold)** | `0/24` | `0/24` | **`5/24` (20.8%)** | **0 -> 5/24** |

## 3. 维度二：证据真实性与门禁守恒 (`Grounding & Safety`)

在全部评测集中，`R` 提升研究完整性的同时未牺牲任何一条安全防线：
- **Silver 111**：`negative_direct = 0/41`，`v7_independent_verifier` 独立回读 `removed_claims = 0`（对 `60` 条直答主张 100% 通过字节-哈希一致性验证）。
- **History 28**：`quote_exact = 27/28`，`unsupported_layout = 0/28`。
- **v8 Holdout & V9 Unseen Holdout（Abstract + Fulltext）**：`unsupported_layout = 0/12`、`source_failures = 0`（即 `invalid_source_claims=0`, `scope_errors=0`）。
- **QASPER Dev (24 负例) + Unseen (8 负例)**：`negative_direct = 0/32`（`A` 在 Batch 2 曾有 `1/8` 误报，`G` 与 `R` 均为 `0/32`）。

## 4. 维度三：工具预算、全文读回与运行效率 (`Budget & Efficiency`)

- **QASPER Dev 72+24**：`R` 总工具调用由 `G` 的 `946` 降至 **`873`**（节省 `73` 次）；抽出句完整读回率 (`all_reference_sentences_read`) 由 `18/54` 增至 **`23/54`**（Batch 2 由 `2/17` 升至 **`7/17`**）。
- **QASPER Unseen 32**：`R` 工具调用由 `G` 的 `320` 降至 **`306`**，参考段落覆盖由 `11/24` 升至 **`12/24`**。
- **Silver 111**：`R` 总工具 `1005`（vs `G=991`，+1.4% 极低开销），却实现了直答主张翻倍（+114.3%）；中位延迟 `691.08ms` / `p95 = 1453.68ms`。

## 5. 维度四：真实模型协作有效性 (`Live Model Collaboration`)

在 `v7_live_research --live --call-budget-only` 真实受限接口（每次最大 `1400` output tokens、`4` 次上限调用）下，`A` 与 `G` 均在 `planning` 与 `semantic_review` 阶段失败（状态 `PARTIAL`），而 **`R` 实现 9/9 门禁 `PASS`**：
- `grounded_labels = 6`、`proposed_profiles = 6`、`source_checked_model_fields = 5`、`two_paper_relations = 1`、`warnings = []`、`elapsed_ms = 22890ms`。
