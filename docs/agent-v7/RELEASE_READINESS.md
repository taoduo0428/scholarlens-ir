# 发布状态

本轮按维护者确认的范围交付可操作的全栈工作台，接受当前问答质量，提分留到后续。Chrome 在真实索引上完成了取模型、选择模型、执行研究、打开引文和下载报告。冻结 Silver 正例有 12/70 道给出直接答案，人工 Gold 为 0。[浏览器实测](REAL_WORKBENCH_BROWSER.md) · [研究质量](RESEARCH_QUALITY_REPORT.md)

2026-11-22，对象追问版本 `ae694c8` 通过全量后端 754 项测试。17 道对象问题在报告中完整收录的标注区间由 12/25 增至 16/25，111 题中有直接答案的正例仍为 8/70。ChemTEB 个案及两项负对照见[研究质量报告](RESEARCH_QUALITY_REPORT.md)。

|闭环|状态|依据|
|---|---|---|
|Research Intelligence|PARTIAL|28 组综述有 27 组给出直接事实，2 组完整列出逐篇观察，1 组形成覆盖全组的建模关系。另抽 24 对论文，覆盖整组的关系为 0/24。本批 111 题 Silver 回放直接回答了 12/70 道正例，负例直接发布 0/41。人工 Gold 为 0。|
|Agent Engineering|PARTIAL|单 Worker 多账号并发、同机进程接替和模型限额已验证。真实 Jaeger 接收并查回 21 个 span，20 条父子关系均可追至任务提交。审批过的程序可固定到任务并跨重启回放。固定两篇真实摘要的供应商试验发出 4 次请求，取得 3 份用量，Worker 完成但规划、决策、语义核验与综合未达标。实际美元费用未知。生产收集端仍待验收。[模型回执](live-research-acceptance.json)|
|Production Software|PARTIAL|前一版隔离 ES 后端通过 805 项。本批前端通过 47 项，Chrome 验证治理视图、追踪和 ZIP 导出。跨页表的 199 个非空值与出版社原表一致。正常页面自动读出 12/14 个参考图例标签，多余 0 个。已登记标尺的图中，22 个参考终点读出 8 个。个人模型专项 39 项通过。生产规模恢复及镜像剩余 High 仍待验收。|
|Public Release|BLOCKED|真实模型评测为 PARTIAL。最新托管扫描中标准镜像为 0 Critical、79 High，PNG 专用英文 OCR 镜像为 0 Critical、84 High。剩余 High 的影响、真实模型全流程质量和生产演练仍待正式发布验收。[镜像复扫](SECURITY_AUDIT.md)|

个人 fork 使用 zjl 接收验收后的开发改动，再通过独立 PR 同步 main。工作流发布于 `.github/workflows/agent-ci.yml`。2026-11-22 首次托管 PR 验收在 Ubuntu 上通过 230 项后端测试、冻结基准核验、前端测试与构建、Compose 配置、Docker 构建和依赖审计。[首次成功运行](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44981973205)

本批共收集 891 个后端用例。首轮修正一条受负载影响的限时测试。修正后的全套运行有 873 个通过，Windows 提交内存耗尽导致隔离 ES 退出。给新建的测试 ES 限定 JVM 编译资源，在新的同版索引副本重跑受影响的三个模块，24 项全部通过。按完整用例名核对，两轮覆盖 891/891，未跳过用例。两份索引副本均包含 859 篇论文和 49,420 条向量，原索引清单一致，临时端口已释放。[逐轮验收与 JUnit 摘要](batch-acceptance.json)

## main 安全整合

核对的 main 为 `ec3ef9f`，当时 zjl 为 `f4733a2`，共同祖先为 `212ce45`。main 独有 4 个提交，涉及 7 个文件。论文 JSONL 的 Git blob 为 `b786ea88a9e0`，来源清单为 `0c849f367b19`。数据目录说明、去重和 TEI 脚本及其说明共 4 个文件，在当时 zjl 的对应路径均缺失。剩余文件为双端都编辑过的 `docs/03_DATA_SCHEMA.md`。

2026-11-22，[PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9) 将已验收应用合入 `zjl`（`1981579`）。[独立整合 PR #8](https://github.com/taoduo0428/scholarlens-ir/pull/8) 将相同应用合入默认分支 `main`（`b19046a`）。6 个原有数据及脚本文件逐字节一致。论文 JSONL 的 859 个唯一 ID 与来源清单的 859 个 ID 完全匹配。该次整合保留了默认分支的数据资产。当前发布门槛见上表。

已对开发提交 `99bc99c` 与该 main 执行 `git merge-tree --write-tree`。只有数据协议出现内容冲突。候选树中的数据目录和三个脚本路径与 main 的逐字节 Git 比较退出码为 0。
