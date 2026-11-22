# 发布状态

镜像原有 96 条 High 匹配已逐一对照 Debian 13 公告，88 条对应发行版明确列为受影响的安装版本。基础镜像中的 glibc 已实测升至 deb13u5，覆盖两个公告的修订。托管复扫确认完整应用镜像剩余 80 条 High，涉及 24 个公告。[发行版复核](SECURITY_AUDIT.md)

2026-11-22，对象追问版本 `ae694c8` 通过全量后端 754 项测试。17 道对象问题在报告中完整收录的标注区间由 12/25 增至 16/25，111 题中有直接答案的正例仍为 8/70。ChemTEB 个案及两项负对照见[研究质量报告](RESEARCH_QUALITY_REPORT.md)。

|闭环|状态|依据|
|---|---|---|
|Research Intelligence|PARTIAL|28 组综述有 27 组给出直接事实，2 组完整列出逐篇观察，1 组形成覆盖全组的建模关系。另抽 24 对论文，覆盖整组的关系为 0/24。最近一次 111 题 Silver 回放在 70 道正例中直接回答 9 道，在 41 道负例中直接发布 0 道。|
|Agent Engineering|PARTIAL|单 Worker 多账号并发、同机进程接替和模型限额已验证。真实 Jaeger 接收并查回 21 个 span，20 条父子关系均可追至任务提交。生产收集端、真实模型供应方和账单待验收。|
|Production Software|PARTIAL|本轮隔离 ES 后端 805 项通过，另在最终导出修复上通过 15 项追踪检查。前端 45 项通过。跨页表的 199 个非空值与出版社原表一致。正常页面自动读出 12/14 个参考图例标签，多余 0 个。生产规模恢复、图表数值和镜像剩余 High 仍待验收。|
|Public Release|BLOCKED|GitHub Actions 的研究测试、前端构建、Docker 构建和依赖审计已通过。真实模型供应方、应用镜像安全发现和研究质量仍待发布验收。|

个人 fork 使用 zjl 接收验收后的开发改动，再通过独立 PR 同步 main。工作流发布于 `.github/workflows/agent-ci.yml`。2026-11-22 首次托管 PR 验收在 Ubuntu 上通过 230 项后端测试、冻结基准核验、前端测试与构建、Compose 配置、Docker 构建和依赖审计。[首次成功运行](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44981973205)

## main 安全整合

核对的 main 为 `ec3ef9f`，当时 zjl 为 `f4733a2`，共同祖先为 `212ce45`。main 独有 4 个提交，涉及 7 个文件。论文 JSONL 的 Git blob 为 `b786ea88a9e0`，来源清单为 `0c849f367b19`。数据目录说明、去重和 TEI 脚本及其说明共 4 个文件，在当时 zjl 的对应路径均缺失。剩余文件为双端都编辑过的 `docs/03_DATA_SCHEMA.md`。

2026-11-22，[PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9) 将已验收应用合入 `zjl`（`1981579`）。[独立整合 PR #8](https://github.com/taoduo0428/scholarlens-ir/pull/8) 将相同应用合入默认分支 `main`（`b19046a`）。6 个原有数据及脚本文件逐字节一致。论文 JSONL 的 859 个唯一 ID 与来源清单的 859 个 ID 完全匹配。该次整合保留了默认分支的数据资产。当前发布门槛见上表。

已对开发提交 `99bc99c` 与该 main 执行 `git merge-tree --write-tree`。只有数据协议出现内容冲突。候选树中的数据目录和三个脚本路径与 main 的逐字节 Git 比较退出码为 0。
