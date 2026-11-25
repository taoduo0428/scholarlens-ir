# 真实模型与受控 HTTP 协作验收报告 (`deepseek-v4.1-flash`)

## 1. 测试拓扑与安全边界

依据 [v7_live_research.py](file:///c:/Users/lenovo/Desktop/检索agent/tools/research_eval/v7_live_research.py) 契约执行双模（`--controlled` 与 `--live --call-budget-only`）端到端验收：
- **核心任务**：2 篇 pinned arXiv 摘要跨论文综述（要求给出方法、结果、共享方法推理与可比性缺失标注）。
- **硬性交通预算**：`CALLS=4`（planning / decision / analysis / synthesis）、`REQUEST_BYTES=48000`、`OUTPUT_TOKENS=1400`。
- **真实测试供应方**：测试网关 `wb-api.lingion.cc.cd/v1`，模型 `deepseek-v4.1-flash`，协议 `chat_completions`，参数 `max_tokens`。
- **密钥隔离审计**：测试密钥仅通过进程内临时环境变量 `$env:AI_API_KEY` 注入，单次运行结束后即销毁环境变量并全盘检测输出产物，确认密钥字符串在全部追踪文件和代码仓库内出现次数为 **0**。

## 2. 受控 HTTP (`--controlled`) 对照结果

| 实验臂 | 状态 (`status`) | 通过门禁 (`gates`) | `source_checked_model_fields` | `two_paper_relations` | `warnings` | 耗时 (`elapsed_ms`) |
| --- | --- | --- | --- | --- | --- | --- |
| `A` | **`PASS`** | 9/9 | `0` | `1` | `[]` | `4469` |
| `G` | **`PASS`** | 9/9 | `1` | `1` | `[]` | `3984` |
| `H5` | **`PASS`** | 9/9 | `1` | `1` | `[]` | `4781` |
| **`R`** | **`PASS`** | 9/9 | `1` | `1` | `[]` | `7000` |

## 3. 真实模型 (`deepseek-v4.1-flash`, `--live --call-budget-only`) 四臂对比

| 指标 | `A` (基线) | `G` (PRA 基线) | **`H5`** | **`R` (`H1–H5` 组合)** |
| --- | --- | --- | --- | --- |
| 总验收结论 (`status`) | `PARTIAL` | `PARTIAL` | **`PASS` (9/9)** | **`PASS` (9/9)** |
| `planning` (DAG 骨架强对齐) | `false` | `false` | **`true`** | **`true`** |
| `decision` | `true` | `true` | `true` | `true` |
| `retrieval` | `true` | `true` | `true` | `true` |
| `semantic_review` | `false` | `false` | **`true`** | **`true`** |
| `synthesis` | `true` | `true` | `true` | `true` |
| `publication` | `true` | `true` | `true` | `true` |
| `no_fallback` | `false` | `false` | **`true`** | **`true`** |
| `provider_receipts` | `true` (4 HTTP 200) | `true` (4 HTTP 200) | `true` (4 HTTP 200) | `true` (4 HTTP 200) |
| `warnings` | `workspace_analysis_fallback`, `workspace_analysis_provider_output_limit` | `workspace_analysis_fallback`, `workspace_analysis_provider_output_limit` | **`[]`** | **`[]`** |
| `grounded_labels` / `proposed_profiles` | `0` / `0` | `0` / `0` | `4` / `4` | **`6` / `6`** |
| `source_checked_model_fields` | `0` | `0` | `4` | **`5`** |
| `two_paper_relations` | `1` | `1` | `1` | **`1`** |
| 4 阶段输出 Tokens `[plan, dec, ana, syn]` | `[245, 61, 1400(截断), 118]` | `[236, 61, 1400(截断), 116]` | `[192, 61, 674, 118]` | `[209, 61, 1003, 119]` |
| 总输入 Tokens | `6009` | `6884` | `7035` | `7109` |
| 端到端耗时 (`elapsed_ms`) | `23500` | `25765` | **`20766`** | **`22890`** |

## 4. 服务端最终裁决权验证

- 当 `deepseek-v4.1-flash` 在 `H5` / `R` 下输出 `selections` 候选字段角色时，服务端在 `research_profile.py` 与 `workspace_model.py` 中逐项复核：
  1. 必须命中受控原文精确字符偏移区间与 SHA-256 摘要；
  2. `support_span` 必须同时逐字存在于被审主张与对应原文摘要；
  3. 仅允许作者归属（`origin=="authors"`）且无 `GUARDS`/`PRIOR`/否定谓词的语句进入受核验档案 (`model_and_source_check`)。
- 在 `R` 中，真实模型成功帮助发布 **`5` 个**经过服务端严格回读验证的研究档案字段，且当发现两篇摘要缺乏可比较实验性能数据时如实保持 `missing_fields=1`（`workflow_state="partial"`），未编造对比数字。
