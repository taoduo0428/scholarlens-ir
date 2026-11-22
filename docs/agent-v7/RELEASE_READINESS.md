# 发布状态

镜像原有 96 条 High 匹配已逐一对照 Debian 13 公告，88 条对应发行版明确列为受影响的安装版本。基础镜像中的 glibc 已实测升至 deb13u5，覆盖两个公告的修订。托管复扫确认完整应用镜像剩余 80 条 High，涉及 24 个公告。[发行版复核](SECURITY_AUDIT.md)

2026-11-22，对象追问版本 `ae694c8` 通过全量后端 754 项测试。17 道对象问题在报告中完整收录的标注区间由 12/25 增至 16/25，111 题中有直接答案的正例仍为 8/70。ChemTEB 个案及两项负对照见[研究质量报告](RESEARCH_QUALITY_REPORT.md)。

|闭环|状态|依据|
|---|---|---|
|Research Intelligence|PARTIAL|28 组综述中，27 组有直接事实，2 组有完整逐篇观察，覆盖全组的关系为 0 组。12 对富集证明陈述的论文中，1 对识别出共同研究手段。70 道可答或部分可答题中有 9 道形成直接答案，另 41 道负例中直接发布为 0。另取 16 对论文，7 次给出了指定论文的原文事实。|
|Agent Engineering|PARTIAL|单 worker 并发、跨进程接替恢复四份报告及同机共享模型限额通过。受控 HTTP 接收端测得两个进程对同一主机的并发峰值为 2。API 提交和后台发布可按同一追踪 ID 查到。真实供应方和部署端远程追踪仍待验收。|
|Production Software|PARTIAL|当前后端 776/776 通过，最近前端 45/45 通过。跨页表的 199 个非空值与出版社原表一致。6 幅论文图像和题注与出版社素材一致。三个预选图例区域识别到 14 个参考标签和 12 个额外词元。此前两版镜像实测了升级和回退。应用镜像剩余的 80 条 High 匹配和生产规模恢复仍待验收。|
|Public Release|BLOCKED|GitHub Actions 的研究测试、前端构建、Docker 构建和依赖审计已通过。真实模型供应方、应用镜像安全发现和研究质量仍待发布验收。|

个人 fork 使用 zjl 接收验收后的开发改动，再通过独立 PR 同步 main。工作流发布于 `.github/workflows/agent-ci.yml`。2026-11-22 首次托管 PR 验收在 Ubuntu 上通过 230 项后端测试、冻结基准核验、前端测试与构建、Compose 配置、Docker 构建和依赖审计。[首次成功运行](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44981973205)

## main 安全整合

核对的 main 为 `ec3ef9f`，当时 zjl 为 `f4733a2`，共同祖先为 `212ce45`。main 独有 4 个提交，涉及 7 个文件。论文 JSONL 的 Git blob 为 `b786ea88a9e0`，来源清单为 `0c849f367b19`。数据目录说明、去重和 TEI 脚本及其说明共 4 个文件，在当时 zjl 的对应路径均缺失。剩余文件为双端都编辑过的 `docs/03_DATA_SCHEMA.md`。

2026-11-22，[PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9) 将已验收应用合入 `zjl`（`1981579`）。[独立整合 PR #8](https://github.com/taoduo0428/scholarlens-ir/pull/8) 将相同应用合入默认分支 `main`（`b19046a`）。6 个原有数据及脚本文件逐字节一致。论文 JSONL 的 859 个唯一 ID 与来源清单的 859 个 ID 完全匹配。该次整合保留了默认分支的数据资产。当前发布门槛见上表。

已对开发提交 `99bc99c` 与该 main 执行 `git merge-tree --write-tree`。只有数据协议出现内容冲突。候选树中的数据目录和三个脚本路径与 main 的逐字节 Git 比较退出码为 0。
