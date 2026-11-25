# V9 算法研究报告（H1–H5 与组合候选 R）

## 1. H1：子句级话语归属与段落上下文共指 (`discourse_attribution.py`)

### 问题诊断
原 `research_profile.py` 存在 4 类系统性错杀：
1. **整句扫描覆盖所有从句**：`While Smith et al. [1] used static graphs, we propose DynamicGNN...` 因前半句命中 `PRIOR` 被整句判作 `prior_work`，直接丢失作者方法。
2. **关键词 `can` / `if` / `not` 全局拒绝**：如 `only if ...` 条件或局部能力描述导致真实作者研究目标或结论落入 `speculation`/`background`。
3. **跨句主语断链**：作者仅在第 $k$ 句声明主语，第 $k+1, k+2$ 句用无显式 `"we/our"` 的被动语态或模块专有名词继续描述方法与结果。

### 算法实现
- [discourse_attribution.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/discourse_attribution.py) 在子句级分解对比/让步连接词，隔离让步前件中的 `PRIOR` 引文与对比否定尾，避免污染主句 `AUTHOR` 归属。
- 识别命题否定作用域 (`has_propositional_negation`) 与认知推测 (`is_epistemic_speculation`)，防止 `if`/`can` 非推测句式被误拒。
- 在 [research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py) 中维护段落级作者锚点窗口（最多 3 句、`keeps_anchor`、遇 `\n\n` 与 `prior_work` 断点重置）传递 `attribution_sentence_id`，同时同步至 [profile_frames.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/profile_frames.py) 的 `body_profile_supports(..., discourse=True)`。

---

## 2. H2：结构化语义槽对齐与 4-Gate 神经符号校验 (`semantic_slots.py`)

### 问题诊断
- 原 `subject_facts.py` 与 `quantitative_evidence.py` 过度依赖 `re.fullmatch` 整句正则。
- 复合提问、被动/倒装表达（`X is evaluated on Y`, `BEA stands for ...`, `We address X in Y`）及单篇长文本问答（QASPER）中问题与原文措辞不同导致大规模误拒 (`false_refusals`)。

### 算法实现
- 在 [semantic_slots.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/semantic_slots.py) 构建通用谓词-论元槽提取器与 **4-Gate 神经符号门禁**：
  1. **门禁 1（作用域与安全过滤）**：严禁进入前人研究、假设、将来时、`GUARDS` 及否定谓词 (`has_predicate_negation`，豁免尾部 `rather than / instead of` 对比尾以避免误杀比较题)。
  2. **门禁 2（题目需求分解 `decompose_question`）**：识别定语/缩写/方法/数据集/数量/实体/机制/对比槽类型，排除指示性元指令（`denominator/baseline/external-validity`）。
  3. **门禁 3（跨句邻接主语组合）**：仅在 H1/H2 模式下支持 `adjacent_author_pairs` 保留同段上下文完整主张，且确保原文逐字可追溯。
  4. **门禁 4（严格论元约束）**：数量槽要求主体词根命中且单位/计数名词对齐（拒绝泛词误配）；单篇 QA 仅限于 `len(scope.paper_ids) == 1` 且无复杂多跳限定词时放行。

---

## 3. H3：开放域跨论文关系对齐与多跳推理 (`open_relations.py`)

### 问题诊断
- 原 `pra_relations.py` 仅匹配有限词表并强要求固定句式；全组综述任务在 `History 28` 上仅 `1/28` 达成 `linked_overview`，在 `v8 Holdout 12` 上甚至只有 `0/12`。
- 原多跳链路 `causal_edge` 缺乏对通用因果动词（`induces / triggers / enables / drives`）的支持。

### 算法实现
- 在 [open_relations.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/open_relations.py) 构建开放域方法家族对齐与全组综合引擎：
  - 定义 **8 个有根词法方法家族**（图模型/嵌入、优化/规划、概率/贝叶斯推理、神经/深度学习、时序/序列建模、统计/特征工程、聚类/图划分、决策/控制），与具体研究任务分离匹配。
  - 提供 `verify_open_synthesis` 对派生结论的每条 `premise_claim_ids`、`evidence_ids`、SHA-256 哈希与语料版本号执行二次严格闭环核验，不合格立即撤回。
  - 对齐 `_compatible_paper_claims` 与 [field_gate.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/field_gate.py) `q1` 全文过滤规则（`body_profile_supports` + `Methods:` 更正检查），保证 `overview` 的所有前提主张 100% 绑定上游依赖，杜绝 `dependency_open`。
- 在 [multihop_fields.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/multihop_fields.py) 开启 `open_links=has_h3(arm)`（保持 `contradicted_edges` 否定边撤回）。

---

## 4. H4：完整句边界检索窗口与 VoI 预算控制 (`passages.py`, `registry.py`, `graph.py`)

### 问题诊断
- 原 900 字符固定步长切分 (`chunks`) 在任意空白处截断句子；并且 `sentence_spans(text, offset)` 在 `offset > 0` 时默认丢弃窗口首句，导致 QASPER 长文关键句无法被抽取式验证器读取。
- 单篇显式作用域任务仍调用冗余 `search_papers` 浪费 1 次工具额度。

### 算法实现
- 在 [passages.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/passages.py) 新增 `sentence_windows_for(doc, max_chars=980)`：基于 `sentence_boundaries` 贪心打包完整句至 `<= 980` 字符（安全低于 `VerifyRequest.quote` 的 1000 字符上限），相邻窗口重叠最后 1 个短句保留跨句上下文；使用 `chunk:sw1-`（完整句首）和 `chunk:swraw-`（超长单句安全切片）两种稳定定位 ID，严格维持 `doc[field][offset_start:offset_end] == quote`。
- 在 [research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py) 增加 `is_sentence_aligned(row)` 并在各证据检查模块透传 `aligned` 参数，使 `chunk:sw1-` 窗口首句安全恢复读取。
- 在 [registry.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/tools/registry.py) 为 `PassageRequest` 新增 `sentence_complete: bool = False`，并在 `focus` 主题检索开启 `sentence_complete` 时纳入标题信号以锁定相关论文，同时仍选返回其非标题摘要/正文切片；`_read_paper_chunks` 与 `_verify_source_quote` 完整兼容 `chunk:sw*` 查找与字节检验。
- 在 [graph.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/graph.py) 启用三项预算机制（仅限 `has_h4`）：
  1. 单篇显式作用域 (`len(paper_ids) == 1`) 直接跳过冗余 `search_papers`；
  2. `_voi_rank_rows` **严格保持跨论文 BM25/focus 序**，仅在单篇论文内部将非 `metadata`、命中主体词元及 `offset_start == 0` 的窗口优先；
  3. 单篇 Round 1 保留预算底线 `free_calls >= 3`，为 Round 2 `pra_gaps` 精准读取章节留出空间，所有保留片段仍 100% 执行 `verify_source_quote`。

---

## 5. H5：真实模型语义协作与提示稳定性 (`provider_adapter.py`, `workspace_model.py`, `research_profile.py`)

### 问题诊断
Stage A 对真实 `deepseek-v4.1-flash` 的验收暴露两大真实瓶颈：
1. **规划阶段 (`planning`)**：模型常篡改 `skeleton` 中的 `min_papers`（如将 `1` 改为 `2`）导致确定性 DAG 验证拒收；
2. **语义审校 (`semantic_review`)**：在 48 句候选与 `OUTPUT_TOKENS=1400` 硬限制下，`SourceReview` 输出过长触发截断 (`OutputTokenLimit`)，引发 `workspace_analysis_fallback`。

### 算法实现
- [provider_adapter.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/provider_adapter.py) 在 `plan_questions` 中强化 `skeleton` 逐字段复制强约束与 `<=120` 字符简洁指令。
- [workspace_model.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/workspace_model.py) 在 `propose` 中将 `analysis` 提示词收紧为 `1–3` 个高精度 `labels`（4–12 词同时命中 claim 与 source 的逐字 `support_span`）、最多 `4` 个 `selections` 与紧凑单行 JSON（`<500` tokens）；`publication_suggestions` 在 `has_h5` 下优先作者高信号句并上限 `24` 句。
- [research_profile.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/research_profile.py) 在 `h5_mode` 下对模型提议档案增加严格服务端二次裁决：严禁越权覆盖 `prior_work`、否定谓词或受限高风险字段，保证模型提议始终受服务端事实绑定监管。
