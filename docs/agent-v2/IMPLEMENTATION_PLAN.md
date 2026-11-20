# 实施与验收顺序

原始规格的字节级副本为 [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md)，SHA-256 为 `2fac800c6ca06c943cb4f4650aecae5c63e88aef2fbd61b7c7e97d225df71e80`。以下索引用于定位交付，详细字段、20 个最低用例和授权边界见原件。

| 阶段 | 必须证明的行为 | 验收入口 |
|---|---|---|
| P0 | 四分支盘点、隔离开发、重现旧 API / 前端 / Harness 结果 | BASELINE_AUDIT.md |
| P1 | 幂等任务与所有权、持久化、typed state、离线评测及标注状态 | progress/P1.md |
| P2 | 分离论文与段落检索、回读核验、检索消融与资源测量 | progress/P2.md |
| P3 | 有界动态补检、停滞停止、恢复、凭据与任务控制 | progress/P3.md |
| P4 | 逐结论核验、不可比条件、报告和导出 | progress/P4.md |
| P5 | 真实工作台、断线补拉、桌面与 390px 验收 | progress/P5.md |
| P6 | 离线候选技能从轨迹生成到审批及回滚 | progress/P6.md |
| P7 | 受约束策略搜索、冻结集门禁和版本管理 | progress/P7.md |
| P8 | 全回归、固定基线消融、可操作演示与交付 | FINAL_HANDOFF.md |

用户没有提供人工标注。真实论文、机器核对的原文锚点、受控工程 fixture 和人工审定的相关性是不同的资料来源。评测输出应带标注状态与分母。只有满足相应条件才计算人工相关性及结论支持率。
