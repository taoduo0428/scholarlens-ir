# 研究任务、存储与动作契约

由 EvoResearch 后端维护。输入为经过旧账户认证的当前用户与限定范围的研究目标。调用者不能自选其他用户。新的 API 前缀为 `/api/research`。研究功能开关为 `SCHOLARLENS_RESEARCH_ENABLED`，自进化与策略优化使用 `SELF_EVOLUTION_ENABLED` 和 `HARNESS_OPTIMIZATION_ENABLED`，三者缺省关闭。

## P1 存储契约

同一用户和幂等键只建立一个任务。同键、不同输入产生冲突。不同用户可使用同一幂等键。读取、事件增量、检查点与资料取回均以 owner 和 task 双重定位。事件序号从 1 起按任务递增。状态变更与伴随事件在同一 SQLite 事务提交，写入过期任务版本必须失败。独立的 research.sqlite3 通过 schema version 约束迁移，处理备份时使用 SQLite backup API。验收覆盖多连接并发创建、重开文件续读、事务回滚、分页、跨所有者读取和 schema 版本保护。

## 模型与持久化边界

作用域由公开语料及当前用户有效的论文范围构成。运行绑定语料 generation、模型、技能与策略版本。动作只能取 search/read/extract/replan/finish，经服务器端预算和授权校验。动作记录决策版本、状态摘要哈希、简短理由与实际执行耗时。证据引用保留 paper、chunk、locator、原文哈希和读取权限，引用材料独立存储。队列、事件和检查点仅接受白名单结构。API Key 在进程内短期使用。

## P3 HTTP 验收目标

创建返回 202。任务列表与详情、after_seq 事件补拉、暂停、恢复、取消、按权限查看 Artifact / 报告均使用真实后端状态。取消完成由 Worker 确认。运行中 Worker 重启时，用已确认的步骤和核验过的证据回到检查点；个人凭据失效时进入 awaiting_credentials。
