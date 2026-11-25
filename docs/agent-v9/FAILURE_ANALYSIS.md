# V9 失败案例深度分析与工程缺陷溯源报告

## 1. 研发期捕获并通用化修复的四类核心失败根因

### 1.1 H2：比较句型 `rather than` 与无作用域问答泛化风险
- **失败表现**：首轮 H2 在 `v3-privacy-compare` 触发假冲突，并在早期消融里导致 6 例 Silver 负例与 7 例 QASPER 负例产生假阳性直答。
- **根因定位**：
  1. `discourse_attribution.has_propositional_negation` 把结尾的 `rather than ...` 对比描述当成全句否定从而引发假冲突；
  2. `slot_qa_witnesses` 被意外应用于 8 篇论文的 `insufficient` 边界请求（如请求 `denominator, baseline and external-validity evidence`）；
  3. 数量词提取将 `four labels` / `four language-pairs` 误当成被询问的 `annotators` / `parameters` 计数。
- **通用修复**：新增 `has_predicate_negation` 剥离对比从句尾再校验否定作用域；将 `slot_qa_witnesses` 严格限定于单篇任务 (`len(scope.paper_ids) == 1`) 并补充元指令屏蔽词与强计数名词对齐；复测后 Silver 负例 **`0/41`**、QASPER B1–B3 负例 **`0/8`**。

### 1.2 H4：跨论文排序颠倒与 `metadata` 占位问题
- **失败表现**：首版 H4 在 `Silver 111` 出现 2–3 例退化（`review-09-comparison`, `review-12-metrics`, `review-17-comparison`），`at_least_one` 一度由 `20` 降至 `18`。
- **根因定位**：
  1. `_voi_rank_rows` 初版跨论文重排并把 `source_kind=="metadata"`（即仅含标题的行）排在 `abstract` 之前，导致 `fair_rows` 浪费论文首轮槽位；
  2. 多篇研究 `focus` 主题检索过滤了 `title`，使标题直指主题的论文在 `sentence_windows_for` 切分后被长尾摘要干扰文超越；
  3. 所有格 `"network's conduciveness"` 未能通过字面子串 `s in folded` 命中 `"network conduciveness"`。
- **通用修复**：保留跨论文 BM25 顺序仅在单篇内部排序、将 `metadata` 压至末位并启用词元化主题匹配；在 `sentence_complete=True` 下允许 `focus` 通道参考标题信号选取非标题窗口；限制 `reserve_floor=3` 仅作用于单篇任务。修复后 Silver 111 `lost=[]` 零失配，且 QASPER B2 `full_sents` 保持 `2/17 -> 7/17` 增益。

### 1.3 H5：真实模型 `deepseek-v4.1-flash` 规划改写与长输出截断
- **失败表现**：`A` 与 `G` 在 `v7_live_research --live` 中同时在 `planning` 与 `semantic_review` 失败。
- **根因定位**：`deepseek-v4.1-flash` 在 `planning` 时自行上调 `min_papers` 违背 `Blueprint == view["skeleton"]` 严校验；在 `analysis` 阶段面对 48 句输入尝试逐句输出，超出了 `OUTPUT_TOKENS=1400` 硬封顶引发 `OutputTokenLimit`。
- **通用修复**：在提示词中强化 `skeleton` 逐字段镜像，并将 `analysis` 限制为 `1–3` 条短 `support_span` 标签 + `<= 4` 条 `selections`（`<=24` 条高信号句入参），无需放宽服务端任何验证门槛即实现 `H5` 与 `R` 全 **9/9 `PASS`**。

### 1.4 Stage G 回归捕获：`graph._retrieve` 的 `Read`/`Extract` 分支 `UnboundLocalError`
- **失败表现**：全量 `backend/tests/research/` 回归发现 `test_scope_coverage.py::test_typed_decision_closes_a_missing_paper`（仅在受控 `Read` / `Extract` 动作路径下触发）报 `UnboundLocalError: cannot access local variable 'has_h4'`。
- **根因定位**：`has_h4` 与 `question_fields` 此前仅在 `else:` (`Search`) 分支内部绑定，执行 `Read`/`Extract` 时绕过了该分支。
- **修复**：提交 `b799ae2` 将 `has_full_pra, has_gap_arm, has_h4` 提升至 `graph.py` 顶层导入，将 `question_fields` 提升至 `if isinstance(action, Read):` 之前。修复后全套研究单元测试 **`574 passed, 11 skipped, 0 failed`**。

---

## 2. `R` 仍未攻克的边界与剩余损失拆解

基于 [SCORE_COMPARISON_V9.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v9/SCORE_COMPARISON_V9.json) 中 `R` 的实测数据，当前能力边界主要集中在以下四类客观情形：

| 评估集 | 未回答/未全组综合原因 | 实测分布与机制说明 |
| --- | --- | --- |
| **Silver 111** (`42/70` 无直答) | `loss_on_unanswered_positives`: `attribution_or_responsiveness=146`, `read=4`, `binding=2` | 1) 大量负向/对比类题面要求两篇以上论文同时具备同口径显式定量实验与指标；2) 原始抽象/方法表述未采用显式实体主语或存在未消解代词跨段跳跃；3) `model_budget=0` 下纯确定性规则不对未确认措辞强行改写。 |
| **History 28 & Unseen Holdout 12** | 未达成 `linked_overview`（如 Unseen Abstract `9/12`、Fulltext `8/12` 未全联接） | 1) 同组论文彼此属于完全不相交的技术家族且摘要未同时提供可比较实验条件；2) 某篇论文虽入库但仅提供了背景或研究目标，缺少明确作者方法或发现句，被门禁安全保留为“证据不足”。 |
| **QASPER Unseen 32** (`19/24` 未直答) | `passage_read=12/24`, `full_sents=7/15`, `pos_direct=5/24` | 1) 部分人类金标准答案分布于全文长表格、公式块或非 `sentence_boundaries` 标准标点分隔的多段落落款；2) `model_budget=0` 下系统仅提取可精确字面定位的陈述，对“跨多句隐含推断但无单句直接回答”的开放题坚持保守拒答（保证 `0/8` 零幻觉）。 |
| **Live `deepseek-v4.1-flash`** (`workflow_state=partial`, `missing_fields=1`) | 仅 2 篇摘要且均不含“可比较实验指标”要求 | `GOAL` 明确要求“mark missing evidence about comparable performance”；两篇 PINNED 摘要确实缺少可比评测协议，`R` 按实标注 `missing_fields=1`（完全符合学术诚信与证据充分性门槛）。 |
