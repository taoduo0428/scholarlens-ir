# 真实回放失败索引

证据条目列的是当次运行保留的来源窗口。字段和证据的对应关系须通过报告 bindings 查阅。首阻断取自运行记录，作者归属与语义相关性仍需逐条区分。索引正文只保留题目、定位、哈希和计数。

内部复现使用 `python -m tools.research_eval.v6_replay --policy E11 --pra-arm G --output output/handoff/failure-silver`。按 Case ID 打开 E11 下的逐题 JSON。内部权威摘要为 [G.jsonl](../agent-v8/ablation-final/G.jsonl) 和 [原题字段复核](../agent-v8/silver-field-review.json)。

## review-16-fact

For discrete scheduling, what problem does railway rescheduling constraints address and which input does it require? Quote the supporting passage and flag any unstated assumption.

- 论文 ID source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a、source-sha256:e1992dbd357f047934fd4862148948456eacd9979f882cc6bd7e6ed54c99bb8a、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:159dd9b89e78322c2e3ebada938ff16be144a54c14de4757764db2616e5f776b、source-sha256:d8efc63923d3a2e6cc108636ccdac77c45778508b0c2eda905d8e1ed279655d3、source-sha256:8c9ce7286f4c2ae814be45ec206261da5bfcb4f367ebb817149500a81112b568、source-sha256:01a4b1536dd09fe923a003b481d8c0a6eb0c4a1cc112f329ba5aa3ac96357230、source-sha256:bcb6f47d7e20eefaf178d83acecbb8e108196975c1940ab983992f908de7311a
- 所求字段 中断后的重调度问题、设施和行车约束、如何进入优化模型
- 实际输出 insufficient_evidence，0 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID 无。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-16-fact.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-d6164f9871a7e5ec0e5abf42d3bc4cb8067f94ae2823c768f1ca17cacd2d7b76` · `source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a` · `abstract:chars:0-897` · `6ec29c14e787d098661f52a41b3513f9b3e4a6b804c1c509bf4c21400e24d395`

## review-16-comparison

Prepare a design review comparing railway rescheduling constraints with job-shop policy gradients. Give the unit of analysis, data representation and objective for each. Identify which statements are explicit.

- 论文 ID source-sha256:4f4cb669ccb29cecb897d32a98b6562bb76679234af1a89724d9d8f1b1b58e7a、source-sha256:3e8e1c25a61b0b2c64f1c2a3d118b3f3412a8980a0e91f79547f861098902e2e、source-sha256:e1992dbd357f047934fd4862148948456eacd9979f882cc6bd7e6ed54c99bb8a、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:7e4d865c0ca86a81eaf6799329773da5ed2b41085105e23f5939749e6949c38a、source-sha256:159dd9b89e78322c2e3ebada938ff16be144a54c14de4757764db2616e5f776b、source-sha256:d4ca163ef14a990608eea6c939fee03a307712f01b68c2811bf7569587ae48f2、source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a
- 所求字段 列车基础设施、二进制约束与重调度、车间状态动作、策略梯度和调度
- 实际输出 partially_answerable，2 条直接陈述。首阻断 {'attribution_or_responsiveness': 4}。报告 Claim ID c-67a36580e25f44499c4d762a, c-b5620366daccea86f70b9b16。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-16-comparison.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 最终专项记录将六个字段中的已核验项从 2 增至 3。新增陈述是 c-88440d5fcd5e60eeed032608，原句哈希及位置见 [约束表示专项](../agent-v8/constraint-representation-results.json)。上面的字段状态属于原始消融记录。
- 保留窗口 `e-d6164f9871a7e5ec0e5abf42d3bc4cb8067f94ae2823c768f1ca17cacd2d7b76` · `source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a` · `abstract:chars:0-897` · `6ec29c14e787d098661f52a41b3513f9b3e4a6b804c1c509bf4c21400e24d395`
- 保留窗口 `e-7437a5a1fd9ec582618a6f03bc9457b2a2c5c1aaa0a08ff9fef2f1e199279ef2` · `source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4` · `abstract:chars:0-897` · `9cff136c9fbc4310917e4447f3621721bbfa5f5941812ba259f269936f821d86`

## review-16-multihop

Trace how the input for railway rescheduling constraints affects the proposed method, then relate that dependency to job-shop policy gradients. Cite each link and mark the cross-paper inference.

- 论文 ID source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:71c1180bf815b1922596889f90a8e8d524d98d926427b484e79190a8da555ff0、source-sha256:8c9ce7286f4c2ae814be45ec206261da5bfcb4f367ebb817149500a81112b568、source-sha256:4f4cb669ccb29cecb897d32a98b6562bb76679234af1a89724d9d8f1b1b58e7a、source-sha256:102cafeb0525eb29c0260c2c584b8378f098422b4514247d6bfdf043d8c02331、source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c、source-sha256:bcb6f47d7e20eefaf178d83acecbb8e108196975c1940ab983992f908de7311a、source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a
- 所求字段 行车约束到二进制表示、可变状态到循环策略、跨域桥接
- 实际输出 insufficient_evidence，0 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID 无。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-16-multihop.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-d6164f9871a7e5ec0e5abf42d3bc4cb8067f94ae2823c768f1ca17cacd2d7b76` · `source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a` · `abstract:chars:0-897` · `6ec29c14e787d098661f52a41b3513f9b3e4a6b804c1c509bf4c21400e24d395`

## review-16-metrics

Which quantitative evidence, bound or evaluation measure is actually reported for job-shop policy gradients? Record its value or definition, units, comparator and conditions, leaving missing fields unknown.

- 论文 ID source-sha256:2ec52ee8d62aceadfa0d2fa26e734ed4e03524926ece9a15c8bbf69e6b7e015b、source-sha256:02e20f2a21fd681bdab1fd35261b70f9bd03d98b4dc3414e30b6d104a0501beb、source-sha256:bcb6f47d7e20eefaf178d83acecbb8e108196975c1940ab983992f908de7311a、source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a、source-sha256:3ae8fe2942479dbfd0ee5dda186399756f34abdc424aafce2acc64e3a664dd88、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:71c1180bf815b1922596889f90a8e8d524d98d926427b484e79190a8da555ff0、source-sha256:0f580212a49da4e3ffbbe1afb3a48006c88efaad981fade7c33be718f7be1f2f
- 所求字段 求解时间和完工跨度、基线类型、测试实例与泛化条件
- 实际输出 insufficient_evidence，0 条直接陈述。首阻断 {'attribution_or_responsiveness': 4}。报告 Claim ID 无。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-16-metrics.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-7437a5a1fd9ec582618a6f03bc9457b2a2c5c1aaa0a08ff9fef2f1e199279ef2` · `source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4` · `abstract:chars:0-897` · `9cff136c9fbc4310917e4447f3621721bbfa5f5941812ba259f269936f821d86`

## review-16-comparability

Can measurements or bounds for railway rescheduling constraints and job-shop policy gradients decide what to use for an unplanned disruption? Compare inputs, objectives and evaluation protocols. Give a ranking only if the comparison is supported.

- 论文 ID source-sha256:4c4cdaed9fde6a3b7653e237dbf840964a408d59e86f0beb5b59395b9a50a25e、source-sha256:159dd9b89e78322c2e3ebada938ff16be144a54c14de4757764db2616e5f776b、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:4f4cb669ccb29cecb897d32a98b6562bb76679234af1a89724d9d8f1b1b58e7a、source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a、source-sha256:8c9ce7286f4c2ae814be45ec206261da5bfcb4f367ebb817149500a81112b568、source-sha256:13540ee791d83dcb22ffa4351367d28e8d6ba7aeb7d434e83cdd601e9c152b5f、source-sha256:d4ca163ef14a990608eea6c939fee03a307712f01b68c2811bf7569587ae48f2
- 所求字段 按原题逐项检查可比条件和限定
- 实际输出 not_comparable，0 条直接陈述。首阻断 {'binding': 1, 'retrieval': 2, 'attribution_or_responsiveness': 1}。报告 Claim ID 无。
- 证据边界与预期 保留不可比状态及可核验的逐篇事实。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-16-comparability.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-9f0319eb97725fa75189078f9186bdb89530dacbe220c66a588e969704f73da1` · `source-sha256:4c4cdaed9fde6a3b7653e237dbf840964a408d59e86f0beb5b59395b9a50a25e` · `abstract:chars:0-892` · `b5d63881d3ac3e90c708a807867251f6252b0e85f6976391154f4f5fa7e73257`
- 保留窗口 `e-31661bdebc7a7f571626abe16dc226ada0cd85b20de94dc7f960169a9c54dab7` · `source-sha256:159dd9b89e78322c2e3ebada938ff16be144a54c14de4757764db2616e5f776b` · `abstract:chars:0-841` · `3c3e3269b8733752c630459f99c08db92c5d4769b629273aaf10deb3e03c9a4f`
- 保留窗口 `e-edb09cbb41caf5d3232fce4caaa381d9ae7d2d02bf9e2709e89daa002bef4f6d` · `source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4` · `abstract:chars:797-1608` · `fdae68ba6fffe09a89d25c6f7b20c16788d6d3b603a9f6e4c0373b4a75ac3124`

## review-17-fact

For supervised classification, what problem does time-series features address and which input does it require? Quote the supporting passage and flag any unstated assumption.

- 论文 ID source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c、source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:102cafeb0525eb29c0260c2c584b8378f098422b4514247d6bfdf043d8c02331、source-sha256:e238d9c3e86968dd4bf8f62d45997f9e8f4718ec330f855551aa2723838028d0、source-sha256:5bd990fb4d95651a0db1a0ea93a0b7a49b4aa9c6bc095d2d355962acff160668、source-sha256:01a4b1536dd09fe923a003b481d8c0a6eb0c4a1cc112f329ba5aa3ac96357230、source-sha256:4f4cb669ccb29cecb897d32a98b6562bb76679234af1a89724d9d8f1b1b58e7a
- 所求字段 时间序列分类要解决的问题、训练序列与类别结构、特征和选择规则
- 实际输出 insufficient_evidence，0 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID 无。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-17-fact.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-4ff28368b72b7d67335a77a7c2946db00002f9b9247dfb603d58811df17af914` · `source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c` · `abstract:chars:0-897` · `d7eb1a504198b394e5bd299b7014ec72c0622bed5c492142bafa8bf6b7d77156`
- 保留窗口 `e-edb09cbb41caf5d3232fce4caaa381d9ae7d2d02bf9e2709e89daa002bef4f6d` · `source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4` · `abstract:chars:797-1608` · `fdae68ba6fffe09a89d25c6f7b20c16788d6d3b603a9f6e4c0373b4a75ac3124`
- 保留窗口 `e-5f356788daa5fe8d505a61751958c1367e8f1646da080f2cd9d8dbf4f4752812` · `source-sha256:102cafeb0525eb29c0260c2c584b8378f098422b4514247d6bfdf043d8c02331` · `abstract:chars:0-891` · `140039a0222f48aa771f92ccb5738324bad916e345b8ebe16ce49206c8aaa509`

## review-17-comparison

Prepare a design review comparing time-series features with class potential functions. Give the unit of analysis, data representation and objective for each. Identify which statements are explicit.

- 论文 ID source-sha256:09df7e348fcd202fc2c7539d4aeb70c4294fb1beba7cb7043272f051afceaa6f、source-sha256:e238d9c3e86968dd4bf8f62d45997f9e8f4718ec330f855551aa2723838028d0、source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057、source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c、source-sha256:953418436d41978961138995d39f4c537648e66a2ce38706c99686f7e84c3ad1、source-sha256:02e20f2a21fd681bdab1fd35261b70f9bd03d98b4dc3414e30b6d104a0501beb、source-sha256:06b11301de5517bd31dd048c2b4c2742d1447112ede0e662ad627979fb98af88、source-sha256:1e704aaeedef4af8f6f9cd56841c221d55760d413468ef0a447651d85937952a
- 所求字段 时序输入、经选特征与分类、样本、先验加权密度与势向量、各自目标
- 实际输出 partially_answerable，1 条直接陈述。首阻断 {'attribution_or_responsiveness': 5}。报告 Claim ID c-72f944263331fdb5f0d56d8e。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-17-comparison.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-4ff28368b72b7d67335a77a7c2946db00002f9b9247dfb603d58811df17af914` · `source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c` · `abstract:chars:0-897` · `d7eb1a504198b394e5bd299b7014ec72c0622bed5c492142bafa8bf6b7d77156`
- 保留窗口 `e-913daaad3f0c7d2ac17b1b76401dee6a3730df10bc29b12667514f069b241e9c` · `source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057` · `abstract:chars:0-896` · `32d61af7c248dbdf29bfb61db29f87fd8ea8be6960bc7f4fbf71b5b396afb0b5`
- 保留窗口 `e-54ac2a5846a5bdb76f00324f736f66c3157bc27da8666537dc6631e9bbd21a6b` · `source-sha256:e238d9c3e86968dd4bf8f62d45997f9e8f4718ec330f855551aa2723838028d0` · `abstract:chars:792-1193` · `d4a90423e464638c5eaa160514dbe760215c25ac186f94d0fe470a8feef8996a`

## review-17-multihop

Trace how the input for time-series features affects the proposed method, then relate that dependency to class potential functions. Cite each link and mark the cross-paper inference.

- 论文 ID source-sha256:4f4cb669ccb29cecb897d32a98b6562bb76679234af1a89724d9d8f1b1b58e7a、source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c、source-sha256:3ae8fe2942479dbfd0ee5dda186399756f34abdc424aafce2acc64e3a664dd88、source-sha256:02e20f2a21fd681bdab1fd35261b70f9bd03d98b4dc3414e30b6d104a0501beb、source-sha256:ed9c8e662ba2736268c20972aa92889a283e61b40e3ac8e02dbad6cef596ebec、source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4、source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057、source-sha256:3e8e1c25a61b0b2c64f1c2a3d118b3f3412a8980a0e91f79547f861098902e2e
- 所求字段 序列到训练特征及筛选、样本到类势向量、组合假设
- 实际输出 insufficient_evidence，0 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID 无。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-17-multihop.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-4ff28368b72b7d67335a77a7c2946db00002f9b9247dfb603d58811df17af914` · `source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c` · `abstract:chars:0-897` · `d7eb1a504198b394e5bd299b7014ec72c0622bed5c492142bafa8bf6b7d77156`
- 保留窗口 `e-57bd3cccbe281a53f16cbbdbe63ab9cea17a1ea572a58110fd65f80fb8570301` · `source-sha256:3ae8fe2942479dbfd0ee5dda186399756f34abdc424aafce2acc64e3a664dd88` · `abstract:chars:797-1193` · `daa9c1e42ba97154352ec67145d29fbb5251829685f5c464c960ca71e9db1e50`
- 保留窗口 `e-edb09cbb41caf5d3232fce4caaa381d9ae7d2d02bf9e2709e89daa002bef4f6d` · `source-sha256:7f15a9599d65cf32b32598e57077ef187289b1c6b73ecbe8bf51be5ec2fc9ac4` · `abstract:chars:797-1608` · `fdae68ba6fffe09a89d25c6f7b20c16788d6d3b603a9f6e4c0373b4a75ac3124`

## review-17-metrics

Which quantitative evidence, bound or evaluation measure is actually reported for class potential functions? Record its value or definition, units, comparator and conditions, leaving missing fields unknown.

- 论文 ID source-sha256:184f3224a86285e8f8519a0dbb98aaad5f5735d64bc7e85b26140afe6d1632fe、source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c、source-sha256:6c876c317735777f7154a78a92c6e9e1ab879b13d12858529d13ad37f2f3246e、source-sha256:953418436d41978961138995d39f4c537648e66a2ce38706c99686f7e84c3ad1、source-sha256:5bd990fb4d95651a0db1a0ea93a0b7a49b4aa9c6bc095d2d355962acff160668、source-sha256:fc75f0187e83f038debe28b9ade46da2b14dad75cba2c0c9276e213266923ba3、source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057、source-sha256:c7710c8f346447efa743290cb2dbd56b476bb3b47416c52915a1f6ce8db253c6
- 所求字段 势函数定义和一致性界限、对照、验证条件及样本数、性能数值
- 实际输出 partially_answerable，1 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID c-618cb0e33680fe1ba72813a1。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/review-17-metrics.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-913daaad3f0c7d2ac17b1b76401dee6a3730df10bc29b12667514f069b241e9c` · `source-sha256:85e1ade5fd2aababaf942100a797547040344e3752e44035eb6f7ced9ea58057` · `abstract:chars:0-896` · `32d61af7c248dbdf29bfb61db29f87fd8ea8be6960bc7f4fbf71b5b396afb0b5`
- 保留窗口 `e-44fbb7490a92ede1e6ad385b0bab88ba05a619f35562640f287a4d11037786f6` · `source-sha256:c7710c8f346447efa743290cb2dbd56b476bb3b47416c52915a1f6ce8db253c6` · `abstract:chars:1588-1854` · `eff1ab23c3d940ee3eb9ec9ef9d3089c1485b20de3964fca73e05908b375f5f6`
- 保留窗口 `e-4ff28368b72b7d67335a77a7c2946db00002f9b9247dfb603d58811df17af914` · `source-sha256:a0c9931c795a6f0ab3f1f97e944047610880c7fd053667446ec80ee5707d8b6c` · `abstract:chars:0-897` · `d7eb1a504198b394e5bd299b7014ec72c0622bed5c492142bafa8bf6b7d77156`

## v3-quantum-multihop

For “The cross-sectional stock return predictions via quantum neural network and tensor network”, trace the stated problem to the proposed approach. Which links across the two papers would require additional evidence?

- 论文 ID source-sha256:eaae9792bae8f616ea68d5c8feea72c2dd1c77bf4dfce270d8c6941d17eed720、source-sha256:df8e2b9c3845bc1cf4ad254b738dd9ef99fb9f8ed1a6e560de9a188d717f59c5
- 所求字段 预测问题、两种候选模型和经典对照、组合评估和市场证据、跨论文链接的性质
- 实际输出 partially_answerable，3 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID c-5bbed7ab05a54cc1f0c2398d, c-5fe4e3d367e971eaa368799f, c-919d35b2ec5ca9bbefa0a7db。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/v3-quantum-multihop.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-533011a86eb7e636b95102450847bffd206bc454d7c6ba3bf95ca700fcf7e015` · `source-sha256:eaae9792bae8f616ea68d5c8feea72c2dd1c77bf4dfce270d8c6941d17eed720` · `abstract:chars:0-897` · `3624c58168345f6629db3f7090061371884ace1b9d9c2674f6bfadfbb22ee956`
- 保留窗口 `e-17604708efcc6fcace83937041239b86ffd8bf321a2ee4b09a00890458ab44c4` · `source-sha256:df8e2b9c3845bc1cf4ad254b738dd9ef99fb9f8ed1a6e560de9a188d717f59c5` · `abstract:chars:0-895` · `b5b2a29b7578fd0beb3be37feec9276e2c64a3ee0b8718395acefba8a2b47c7e`
- 保留窗口 `e-7d524f1cde2648e77ead2b05893be7ba818f0d7207585785c0431d355023b85a` · `source-sha256:eaae9792bae8f616ea68d5c8feea72c2dd1c77bf4dfce270d8c6941d17eed720` · `abstract:chars:797-905` · `afaf06a4f8d7ea6820e91b9035342de36e0509a334fed6c4e62584446966c67c`

## v3-routing-multihop

For “Post-Earthquake Restoration of Electricity-Gas Distribution Systems with Damage Information Collection and Repair Vehicle Routing”, trace the stated problem to the proposed approach. Which links across the two papers would require additional evidence?

- 论文 ID source-sha256:ffade048f17466903d4c9c491395bc337f6e42160f1a0b84386bbf8e6fc18403、source-sha256:5799f9efc5086eeaf04159a4d2545042c8bd2f81ba25eb8aa26ceef9943db028
- 所求字段 不完全损坏信息、POMDP 与现场行动、信念树搜索与评估、跨域推论
- 实际输出 partially_answerable，1 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID c-aff2769434c488ffaf3a2fbb。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/v3-routing-multihop.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-52df01f46d9e14c8f79a8f265bdf9a55c8e45e65ec303600f819e53acbe50266` · `source-sha256:ffade048f17466903d4c9c491395bc337f6e42160f1a0b84386bbf8e6fc18403` · `abstract:chars:0-896` · `7f06f6d8dec699387177bb481880f60452464b7cf656ffcead6951ca95dfe697`
- 保留窗口 `e-feea73d370c340126e09dd5eed44951ea4fb171bc6730327177d0e17e168859e` · `source-sha256:5799f9efc5086eeaf04159a4d2545042c8bd2f81ba25eb8aa26ceef9943db028` · `abstract:chars:0-891` · `bbc1dba614ac462d0db8b690fafcdb8aab60c4f3fefad2cc3feda5106ab559db`
- 保留窗口 `e-737aa12d12f1fec8b1b852c69091bcfcd8af795607fa715191cddbc0aa1797c8` · `source-sha256:ffade048f17466903d4c9c491395bc337f6e42160f1a0b84386bbf8e6fc18403` · `abstract:chars:796-1106` · `e861f748a7da6ea2f5832d4834f6b7e4884b99f4174c67b753294fdf4bf28d39`

## v3-privacy-multihop

For “FROM PRIVACY TO TRUST IN THE AGENTIC ERA: A TAXONOMY OF CHALLENGES IN TRUSTWORTHY FEDERATED LEARNING THROUGH THE LENS OF TRUST REPORT 2.0”, trace the stated problem to the proposed approach. Which links across the two papers would require additional evidence?

- 论文 ID source-sha256:88aecb0914ec204d30f36d2766bcd558771789568c77b8e32fab42ca408771f3、source-sha256:3301149441ddb28a434220d6df31a280eaefaba64854e5fa6b66411d288882f1
- 所求字段 隐私保证的局限、系统层信任要求、分类、协调与保证记录、跨文献界限
- 实际输出 partially_answerable，2 条直接陈述。首阻断 {'attribution_or_responsiveness': 3}。报告 Claim ID c-00bea3d455fd6bbc500149a3, c-75424e164484f073046425c3。
- 证据边界与预期 按原问题逐项核验并发布有独立依据的答案，缺失项注明原因。逐篇证据不得替代跨篇关系，原文条件与所问对象一致才能绑定。
- 诊断入口 `backend/research/field_gate.py` 核对归属、响应和绑定，`backend/research/node_fields.py` 核对原始义务。复现后按字段核实首阻断，完整根因以最小对照为准。
- 原始轨迹 `output/v8/pra/G9/diagnostic/E11/v3-privacy-multihop.json`（本机忽略路径，摘要已提交）。改动风险是把背景引句、子路径或不同条件量值提升为直接回答。
- 保留窗口 `e-adfc5bdf15b1e4b2a2e4f5dad98ce245353b05bbcac15049872c87dff9156414` · `source-sha256:88aecb0914ec204d30f36d2766bcd558771789568c77b8e32fab42ca408771f3` · `abstract:chars:0-892` · `49981f9baccb7b5dde5c034e172b9dd1a990070d462206215231ce8164289595`
- 保留窗口 `e-7c5f5eebf991d8e78cff212539005dc203ec594324e14d6018949cf42898f09f` · `source-sha256:3301149441ddb28a434220d6df31a280eaefaba64854e5fa6b66411d288882f1` · `abstract:chars:0-889` · `0e4eb72707cf606d30fc8e0b69e3cb654e3e97b9c7dedc80d334a8269b6b029f`
- 保留窗口 `e-a6a6fd61bf989873e358fed5bf4a7243cb8f4965a757574eb06afbed9d69853d` · `source-sha256:88aecb0914ec204d30f36d2766bcd558771789568c77b8e32fab42ca408771f3` · `abstract:chars:792-1100` · `47b61887dd5af8912fc5bc1c2424d3ef1a8c8c2bec765495d11551408a4ae106`

## QASPER-1-9a7aeecbecf5e30ffa595c233fca31719c9b429f

What package was used to build the ngram language models?

- 论文 `1704.08390`，所求字段 原题要求的事实及其人工参考范围。
- 该轮实际输出 0 条直接陈述，读到标注段落 True，Claim ID 无。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 0906ae63d8e99844f5cab164a11ae97727889bc098adae8223bc0e973d05ef8d。按论文与 question_id 在官方测试归档定位并复跑。
- 已观察到人工段落重合而未发布答案。先核窗口是否包含完整参考片段，再查作者归属、字段提取和发布检查。具体根因待复跑。
- 预期为能从原文核验的字段给出来源与定位。段落重合只用于定位损失。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/failure-qasper-1`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。

## QASPER-1-c8f8ecac23a991bceb8387e68b3b3f2a5d8cf029

What metrics are used?

- 论文 `2003.12660`，所求字段 原题要求的事实及其人工参考范围。
- 该轮实际输出 0 条直接陈述，读到标注段落 True，Claim ID 无。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 63aab1471e52a70da2f9ccb9b9ad35132e7974da4358bea259ff41cdaba7bc1f。按论文与 question_id 在官方测试归档定位并复跑。
- 已观察到人工段落重合而未发布答案。先核窗口是否包含完整参考片段，再查作者归属、字段提取和发布检查。具体根因待复跑。
- 预期为能从原文核验的字段给出来源与定位。段落重合只用于定位损失。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/failure-qasper-1`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。

## QASPER-1-9f1e60ee86a5c46abe75b67ef369bf92a5090568

By how much do they outperform previous state-of-the-art in terms of top-n precision?

- 论文 `1911.11899`，所求字段 原题要求的事实及其人工参考范围。
- 该轮实际输出 0 条直接陈述，读到标注段落 True，Claim ID 无。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 aa1588505c138efed91b9a38268825b9c2f8393348f59ffc9932392ae06af2b5, dc710bfe1e927414e1db7f7f736d0801ac42a65da89dbd93ed80d00868f1c8b2。按论文与 question_id 在官方测试归档定位并复跑。
- 已观察到人工段落重合而未发布答案。先核窗口是否包含完整参考片段，再查作者归属、字段提取和发布检查。具体根因待复跑。
- 预期为能从原文核验的字段给出来源与定位。段落重合只用于定位损失。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/failure-qasper-1`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。

## QASPER-1-4542b162a5be00206fd14570898a7925cb267599

Which languages are covered in the corpus?

- 论文 `1911.12893`，所求字段 原题要求的事实及其人工参考范围。
- 该轮实际输出 0 条直接陈述，读到标注段落 True，Claim ID 无。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 51a1cc4bff462b64adeed7936df9d8a00ea5a8573d457f1d0d82fc5b20a97e29, 73ba8fff68fef48e1e1dfa13a69116c29a11c7584872fa37d33661c35654d2e6。按论文与 question_id 在官方测试归档定位并复跑。
- 已观察到人工段落重合而未发布答案。先核窗口是否包含完整参考片段，再查作者归属、字段提取和发布检查。具体根因待复跑。
- 预期为能从原文核验的字段给出来源与定位。段落重合只用于定位损失。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/failure-qasper-1`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。

## QASPER-1-58df55002fbcba76b9aeb2181d78378b8c01a827

Which part of their architecture provides the most speedup in comparison to existing approaches?

- 论文 `1910.09942`，所求字段 原题指定的表现比较与匹配实验条件。
- 该轮实际输出 1 条直接陈述，读到标注段落 False，Claim ID c-7d72475fbfa0413e6231069d。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 无可登记人工证据段。按论文与 question_id 在官方测试归档定位并复跑。
- 已见缺证误发的性能比较检查 `research_intent.py` 与 `field_gate.py`。已读段落却未形成答案的题优先检查 `research_profile.py` 与 `field_gate.py`，具体失败节点待完整轨迹验证。
- 预期保留缺证结论并避免把方法介绍当成性能比较。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 1 --out output/handoff/failure-qasper-1`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。

## QASPER-2-b0edb9023f35a5a02eb8fb968e880e36233e66b3

How does this result compare to other methods KB QA in CCKS2019?

- 论文 `1910.12477`，所求字段 原题指定的表现比较与匹配实验条件。
- 该轮实际输出 1 条直接陈述，读到标注段落 False，Claim ID c-9f4cf4d4e55495dace6de18d。公开摘要没有系统 Evidence ID。
- 公开人工证据段 SHA-256 无可登记人工证据段。按论文与 question_id 在官方测试归档定位并复跑。
- 已见缺证误发的性能比较检查 `research_intent.py` 与 `field_gate.py`。已读段落却未形成答案的题优先检查 `research_profile.py` 与 `field_gate.py`，具体失败节点待完整轨迹验证。
- 预期保留缺证结论并避免把方法介绍当成性能比较。
- [历史逐题结果](../agent-v8/qasper-human-results.json) · [同题复测](../agent-v8/qasper-same-case-reruns.json)。复现用 `python -m tools.research_eval.pra_qasper --archive output/handoff/qasper-test-and-evaluator-v0.3.tgz --batch 2 --out output/handoff/failure-qasper-2`，同批目录只运行一次。修复时保持参考答案仅用于离线计分。
