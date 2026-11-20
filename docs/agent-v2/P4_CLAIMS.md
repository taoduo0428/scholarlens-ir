# P4 结论与证据契约

研究报告将一条结论绑定到具体子任务、论文与字符区间。发布时再次读取任务专属证据文件，核对所有者、语料代、来源哈希和当前可见原文。结构化指标只接受与数值同一句明示的指标，并保留单位、数据集、设置和评价协议。摘录式语义判定要求整句一致。对无法识别的改写记录未验证；不同条件记录不可比；证据不足不补写数值。每份报告分别保存 JSON 和 Markdown，提供结论分区、逻辑图、缺失项、范围和来源明细。运行时不依赖收费模型。报告契约由本地后端维护者负责。

## 实现与验收

- `claim_verifier.py` 独立核对摘录命题、数字、单位及实验条件。英文数字词写成的 precision@k、recall@k 和常见显式指标可解析。段内 “it measured” 只继承紧邻上句明示的 benchmark。
- `evidence_graph.py` 建立 Subtask–Claim–Evidence–Paper 关系。计算两个数值的大小关系需要明确匹配数据集、指标、单位、设置和协议。实验条件不同则输出不可比。句子极性相反时保留双方来源。
- `reports.py` 发布前再次核对所有者、scope、artifact 哈希、语料代和 locator。回读消耗工具和时间预算。报告支持部分结果、账户隔离和两种导出。PDF 与全文可用性从各自的布尔状态读取。

`.venv/Scripts/python.exe -m pytest backend/tests/research/test_claim_report.py -q --basetemp .venv/p4-claims-post-drift` 在 Windows、Python 3.11.15 上退出 0，20 项通过，耗时 4.06 秒。测试覆盖字符与数值篡改、来源伪造、否定语义、不同协议、时间和工具限额、账户隔离以及资料状态。[测试记录](evidence/p4-claims/pytest-drift-window.txt)

冻结的 Cedar 和 Birch 经过完整 LangGraph 流程。报告复核 2 篇摘要产生 8 个子任务陈述，标出 1 个不可比项。Cedar 的结果为 Orchard、protocol A、precision@5=0.62。Birch 的结果为 Valley、protocol B、recall@10=0.71。[完整 JSON](evidence/p4-claims/cedar-birch-fullgraph.json) · [Markdown](evidence/p4-claims/cedar-birch-fullgraph.md)

复杂释义、未结构化表格和隐含实验条件仍需人工判断。该核验器采用确定性抽取与有限语义规则。面向未见真实问题的人工 Claim 支持率尚未评测。


发布竞态用例在最后一次逐字回读时切换语料代。任务可以保存暂停状态，保留已有证据供恢复。

## 实体问答验收

英文 which/what 命名实体问题应对同篇论文内所有已核验片段择句。验收要求陈述本身包含所问对象的名称和证据关系。遇到所指对象时可引用同一片段内逐字连续的两句。原文缺少可绑定名称时保留未解决项。负责人为研究报告后端维护者。

本轮回归覆盖同篇不同片段择句、同段指代解析、片段拼接、原始空格、否定与缺少名称的情况。初版在四个重点用例均失败。修正后，结论核验测试 27 项通过，研究后端测试 136 项通过、1 项跳过。实体识别使用有限的英文问句、名称形态和谓语线索，其他语言与隐含关系仍需评估。[原失败](evidence/p4-claims/entity-before.txt) · [专项测试](evidence/p4-claims/entity-after.txt) · [研究后端回归](evidence/p4-claims/entity-research-suite.txt)
