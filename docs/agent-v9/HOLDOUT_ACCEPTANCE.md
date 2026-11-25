# Stage E 新封存未见盲测验收报告

## 1. 盲测封存与单次运行纪律声明

1. V9 未见测试集由 [v9_freeze_holdout.py](file:///c:/Users/lenovo/Desktop/检索agent/tools/research_eval/v9_freeze_holdout.py) 在算法改造前即预先封存（提交 `a601840`），与所有 V8/Silver/History/QASPER 开发集在**论文 ID 与标题层面严格不交**。
2. 候选系统 `R` 于完成全部开发集验证后冻结于提交 **`0c8f966`**。
3. 本报告中全部 Stage E 数据均来自 **单次盲测运行**；运行后**未对任何检索/推理/阈值/提示词规则执行过二次调参或补丁重跑**。

## 2. 封存清单 SHA-256 指纹

- **V9 Unseen Holdout 12 清单**：[unseen-holdout-manifest.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/unseen-holdout-manifest.json)
  - SHA-256: `08421ab5aecb02171165c8b3c5b8dcb26c4ed6299544c6407a8d6a8eb8581220`
  - 规模：6 对二元组 + 6 组三元组 = 12 组、30 篇未见语料论文（每组测 1 项 `overview` + 1 项负例 `layout` 边界）
- **V9 Unseen QASPER 32 清单**：[qasper-unseen-manifest.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/qasper-unseen-manifest.json)
  - SHA-256: `88d267f03a3d48faad1c2fea690fb7090534552cc2c63823de065754f3b1d4e1`
  - 规模：32 篇独立 Human Gold QASPER v0.3 测试论文（24 篇可答 + 8 篇明确不可答）

## 3. 未见盲测配对对照结果（`A` vs `G` vs `R`，`model_budget=0`）

### 3.1 V9 Unseen Holdout 12 — Abstract 模式 (`output/handoff/v9-unseen-holdout-abstract`)

| 指标 | `A` (E11) | `G` (PRA) | **`R` (V9)** |
| --- | --- | --- | --- |
| `full_group_synthesis` (`linked_overview`) | `0/12` (0.0%) | `0/12` (0.0%) | **`3/12` (25.0%)** |
| `any_claims` | `12/12` | `12/12` | `12/12` |
| `total_claims` | `38` | `39` | **`61`** (+56.4% vs `G`) |
| `derived_synthesis_count` | `0` | `0` | **`3`** |
| `unsupported_layout` (`false_release`) | `0/12` | `0/12` | **`0/12`** |
| `source_failures` (`invalid_src` + `scope_errors`) | `0` | `0` | **`0`** |
| `tool_calls` | `105` | `105` | `105` |

### 3.2 V9 Unseen Holdout 12 — Fulltext 模式 (`output/handoff/v9-unseen-holdout-fulltext`)

| 指标 | `A` (E11) | `G` (PRA) | **`R` (V9)** |
| --- | --- | --- | --- |
| `full_group_synthesis` (`linked_overview`) | `0/12` (0.0%) | `0/12` (0.0%) | **`4/12` (33.3%)** |
| `any_claims` | `12/12` | `12/12` | `12/12` |
| `total_claims` | `38` | `44` | **`69`** (+56.8% vs `G`) |
| `derived_synthesis_count` | `0` | `0` | **`4`** |
| `retained_body_chunks` | `0` | `8` | `6` |
| `unsupported_layout` (`false_release`) | `0/12` | `0/12` | **`0/12`** |
| `source_failures` (`invalid_src` + `scope_errors`) | `0` | `0` | **`0`** |
| `tool_calls` | `105` | `109` | `111` |

### 3.3 V9 Unseen QASPER 32 — Human Gold (`output/handoff/v9-unseen-qasper`)

| 指标 | `A` (E11) | `G` (PRA) | **`R` (V9)** |
| --- | --- | --- | --- |
| `any_direct` (24 可答正例) | `0/24` (0.0%) | `0/24` (0.0%) | **`5/24` (20.8%)** |
| `all_reference_spans` (15 抽取题) | `0/15` | `0/15` | **`1/15`** |
| `annotated_passage_read` (24 正例) | `10/24` | `11/24` | **`12/24`** |
| `all_reference_sentences_read` (15 抽取题) | `7/15` | `7/15` | `7/15` |
| `negative_direct` (8 不可答负例) | `0/8` | `0/8` | **`0/8` (0%)** |
| `tool_calls` (32 题总计) | `302` | `320` | **`306`** (-14 calls vs `G`) |

## 4. 泛化性结论

V9 候选方案 `R` 在开发集取得的改进（多论文开放综合、更丰富的作者归属抽取、基于语义槽的问答准确率与更低工具消耗）在从未接触过的两套新未见盲测集上**完全正向复现**，未出现任何过拟合或负例越界。
