# 发布状态

|闭环|状态|依据|
|---|---|---|
|Research Intelligence|PARTIAL|独立评测仅 2/28 次满足跨篇综合判据。70 道可答或部分可答题中仍有 65 道未形成直接答案。|
|Agent Engineering|PARTIAL|单 worker 并发、恢复、工具约束、浏览器档案与受控 HTTP 链路已验证。真实模型、多进程模型并发治理与全链路追踪缺完整验收。|
|Production Software|PARTIAL|后端与前端已在本地实测，完整后端 706/706 通过，前端 45/45 通过，Docker 配置及探针已实现。容器构建、镜像扫描、容器内备份和镜像回滚尚待实测。|
|Public Release|BLOCKED|GitHub Actions 运行数为 0。真实供应方、容器和研究质量仍待发布验收。默认分支源码与论文资产已完成整合。|

个人 fork 使用 zjl 接收验收后的开发改动。GitHub 当前登录身份有 repo scope，缺 workflow scope。向开发分支写入标准工作流路径时，GitHub Contents API 返回 HTTP 404，Git 推送也明确返回缺少 workflow scope。CI 模板在 `infra/ci/agent-ci.yml`。启用后的目标是实际检查 E11、前端构建、Compose、镜像构建及依赖审计。

## main 安全整合

核对的 main 为 `ec3ef9f`，当时 zjl 为 `f4733a2`，共同祖先为 `212ce45`。main 独有 4 个提交，涉及 7 个文件。论文 JSONL 的 Git blob 为 `b786ea88a9e0`，来源清单为 `0c849f367b19`。数据目录说明、去重和 TEI 脚本及其说明共 4 个文件，在当时 zjl 的对应路径均缺失。剩余文件为双端都编辑过的 `docs/03_DATA_SCHEMA.md`。

2026-11-22，[PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9) 将已验收应用合入 `zjl`（`1981579`）。[独立整合 PR #8](https://github.com/taoduo0428/scholarlens-ir/pull/8) 将相同应用合入默认分支 `main`（`b19046a`）。6 个原有数据及脚本文件逐字节一致。论文 JSONL 的 859 个唯一 ID 与来源清单的 859 个 ID 完全匹配。正式 Release 待托管 CI、容器回滚、真实模型和研究质量验收。

已对开发提交 `99bc99c` 与该 main 执行 `git merge-tree --write-tree`。只有数据协议出现内容冲突。候选树中的数据目录和三个脚本路径与 main 的逐字节 Git 比较退出码为 0。
