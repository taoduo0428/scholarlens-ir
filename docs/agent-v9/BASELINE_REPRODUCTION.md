# Stage A 基线完整复现与历史快照核对报告

## 1. 复现环境与契约基准

- **基线分支**：`codex/gemini-research-handoff`
- **基线提交 SHA**：`136763f76ec2c0bf4a3e1836721f952a0e0a4af8`
- **语料版本 (`corpus_version`)**：`local-jsonl-sha256:49c1062bd28ecb6a0216256d8aa0d02001e4ee174bfb2ce5e61c3d96ed46187c`
- **评分版本**：`pra-scorecard/1`
- **基线存档目录**：`output/handoff/baseline/`（总账本 `output/handoff/baseline/run_ledger.json`）

## 2. 历史冻结快照 (`fe9932f`) vs `HEAD` (`136763f`) 漂移对照

遵照交接纪律，报告严格区分早期历史冻结快照（`docs/agent-v8/ablation-final/`）与 `136763f` 当前代码实际重跑输出，二者绝不混用：

| 评估对象 | 指标项 | 历史冻结 (`fe9932f`) | `HEAD` (`136763f`) 实测重跑 | 差异说明 |
| --- | --- | --- | --- | --- |
| Silver 111 `A` (E11) | `at_least_one` / 系统字段 / 直答主张 | `15/70` / `16/271` / `20` | `15/70` / `16/271` / `20` | 逐题完全一致 |
| Silver 111 `G` (PRA) | `at_least_one` / 系统字段 / 直答主张 | `20/70` / `22/273` / `27` | `20/70` / `23/273` / `28` | `HEAD` 实跑多发布 1 个系统字段与 1 条主张 |
| Silver 111 `A` & `G` | `negative_direct` / `removed_claims` | `0/41` / `0` | `0/41` / `0` | 无假阳性、无独立溯源剔除 |

> 审计核实：`case_file_sha256` 明确分离：`G` 在 `fe9932f` 为 `f6ffa12bc8...`，在 `136763f` 为 `a379b91339...`。

## 3. 全套 Stage A 基线重跑明细（`model_budget=0`, `tool_budget=10`, `E11`）

### 3.1 Silver 111（AI Silver）与独立来源核验

- **执行命令**：
  - `python -m tools.research_eval.v6_replay --policy E11 --pra-arm A --output output/handoff/baseline/A`
  - `python -m tools.research_eval.v6_replay --policy E11 --pra-arm G --output output/handoff/baseline/G`
  - `python -m tools.research_eval.pra_summary --root output/handoff/baseline --out output/handoff/baseline/silver-summary --arms A=A G=G`
- **结果**：
  - `A`: `at_least_one=15/70`, `all_positive_system_fields_published=1/70`, `published=16/271`, `direct_claims=20`, `filled_profile_field_cells=648`, `tools=994`, `negative_direct=0/41`, `removed_claims=0`。
  - `G`: `at_least_one=20/70`, `all_positive_system_fields_published=1/70`, `published=23/273`, `direct_claims=28`, `filled_profile_field_cells=736`, `tools=991`, `negative_direct=0/41`, `removed_claims=0`。

### 3.2 History 28 与 PRA v8 Holdout 12（内部迁移基线）

- **History 28**：
  - `A`: `overview_linked=1/28`, `quote_exact=27/28`, `layout_false=0/28`, `tools=383`
  - `G`: `overview_linked=1/28`, `quote_exact=27/28`, `layout_false=0/28`, `tools=378`
- **PRA v8 Holdout 12 (`manifest sha256: 5963667f...`)**：
  - Abstract：`A` (`linked=0/12`, `claims=43`, `false_layout=0`, `invalid_src=0`)；`G` (`linked=0/12`, `claims=47`, `false_layout=0`, `invalid_src=0`)
  - Fulltext：`A` (`linked=0/12`, `claims=43`, `false_layout=0`, `invalid_src=0`)；`G` (`linked=0/12`, `claims=51`, `retained_body=4`, `false_layout=0`, `invalid_src=0`)

### 3.3 QASPER v0.3 开发三批次（Human Gold，每批 24 正例 + 8 负例）

- **Batch 1**: `A` (`pos_direct=0/24`, `passage_read=15/24`, `full_sents=10/20`, `neg=0/8`, `tools=310`); `G` (`pos_direct=2/24`, `all_spans=2/20`, `passage_read=15/24`, `full_sents=10/20`, `neg=0/8`, `tools=312`)
- **Batch 2**: `A` (`pos_direct=0/24`, `passage_read=11/24`, `full_sents=2/17`, `neg=1/8`, `tools=308`); `G` (`pos_direct=0/24`, `passage_read=11/24`, `full_sents=2/17`, `neg=0/8`, `tools=314`)
- **Batch 3**: `A` (`pos_direct=1/24`, `all_spans=1/17`, `passage_read=15/24`, `full_sents=6/17`, `neg=0/8`, `tools=315`); `G` (`pos_direct=1/24`, `all_spans=1/17`, `passage_read=15/24`, `full_sents=6/17`, `neg=0/8`, `tools=320`)

### 3.4 Controlled HTTP 与 Live `deepseek-v4.1-flash` 基线诊断

- **Controlled HTTP (`v7_live_research --controlled`)**：`A` 与 `G` 均为 **`PASS`**（9/9 门禁全过）。
- **Live `deepseek-v4.1-flash` (`v7_live_research --live --call-budget-only`)**：
  - `A`: **`PARTIAL`** — 4 次请求 HTTP 200，但 `planning=false`（模型更改 `min_papers` 骨架约束）、`semantic_review=false`、`no_fallback=false`（`analysis` 阶段触及 `OUTPUT_TOKENS=1400` 截断上限触发 `workspace_analysis_provider_output_limit`）。
  - `G`: **`PARTIAL`** — 同样因 `planning=false`、`semantic_review=false`（`output_tokens=1400` 截断）与 `no_fallback=false` 而未完全通过。

## 4. 阻塞瓶颈与 V9 新未见盲测清单一封存

基于 Stage A 复现结果，`Silver 111` 负向损失中 `attribution_or_responsiveness` 在 `G` 仍占 `170` 次，且在多篇研究、`QASPER` 长文本问答及真实 LLM 并发结构化阶段暴露核心瓶颈。因此 V9 预先使用 [v9_freeze_holdout.py](file:///c:/Users/lenovo/Desktop/检索agent/tools/research_eval/v9_freeze_holdout.py) 封存了与所有开发集严格论文不交的新未见盲测清单：
- [unseen-holdout-manifest.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/unseen-holdout-manifest.json)（SHA-256 `08421ab5aecb02171165c8b3c5b8dcb26c4ed6299544c6407a8d6a8eb8581220`，12 组 / 30 篇论文）
- [qasper-unseen-manifest.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/qasper-unseen-manifest.json)（SHA-256 `88d267f03a3d48faad1c2fea690fb7090534552cc2c63823de065754f3b1d4e1`，32 篇论文：24 可答 + 8 不可答）
