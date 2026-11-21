# 发布就绪情况

|范围|结论|证据|
|---|---|---|
|Engineering Closure|PARTIAL|研究回归、SQLite 恢复、账号隔离和隔离 ES 链路通过。完整旧后端套件在本机存在固定集群依赖，远端 CI 仍需要 GitHub workflow 授权。|
|Research Quality Closure|PARTIAL|双篇前提和摘要原句可以复算，AI 完成 111 道来源判断。新论文的跨文综合 2/12，70 道有据可答题全部缺直接回答。|
|Product Closure|PARTIAL|浏览器完成创建、进度、字段、证据、导出和刷新。隔离服务完成真实 ES 业务流程，外部模型 G 场景缺项目凭据。|
|Release Readiness|BLOCKED|待真实提供方和远端 CI 验收，开放题漏答率仍高。当前交付为公开 fork 的独立 PR。|

## 下一次发布需要的证据

1. 用带 workflow 写入权限的仓库身份将 `infra/ci/agent-ci.yml` 放入 `.github/workflows/agent-ci.yml`，取得目标提交的真实 Actions 结果。此次推送该路径时 GitHub 拒绝，当前远端只含可审阅模板。
2. 在隔离环境运行 `python -m tools.research_eval.v6_model`。项目本地配置需要 AI_BASE_URL、AI_MODEL、AI_API_KEY，支持 AI_PROTOCOL。E10_MAX_USD 设置单次验收预算，E10_MAX_RATE_USD_PER_MTOK 填实际输入/输出两者中较高的每百万 Token 美元价格。脚本以 4 个请求、每请求 48000 字节和 1400 输出 Token 预留上限，还预留消息开销。供应方计费以账单为准。只有独立授权的测试凭据才进入进程环境。
3. 用新冻结的、具有充分来源的通用目标、方法、指标和条件题验证能否实质减少漏答，同时保留不可比和来源缺失题。人工 Gold 仍为 0。
4. 如需复核旧版 859 篇索引与混合向量的固定部署行为，准备对应版本的独立环境和别名。部署审批、分支合并是另一个交付步骤。

E10 在隔离实例显式开启 `SCHOLARLENS_RESEARCH_ENABLED=true` 和 `SCHOLARLENS_E10_ENABLED=true`。切换只用于新任务，既有任务继续使用持久化的策略及计划。回退时关闭 E10 开关，保留任务库与旧策略。
