# ScholarLens EvoResearch V9 — 最终工程交付与验收总报告

**报告日期**：2026-11-25  
**交付分支**：`gemini/final-release-closure`（合入 PR `#47` 至 `main`）  
**基线分支**：`origin/main` (`160b84e1305d99f4ac58036a9879f229022e03d8`)  
**CI 全绿运行**：[GitHub Actions Run `45566748805`](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45566748805)（**5/5 Jobs PASS**）

---

## 1. 阶段执行总览与核心原则遵守情况

本轮以 **“零算法改动、全链路工程验证、实测证据优先、诚实暴露阻断项”** 为最高原则，圆满完成了八大阶段的全部可执行工作：
1. **严格冻结研究算法与参数**：未对 E11、PRA、V9 H1–H5、Paper Research Profile、Evidence Graph、Pairwise Reasoning、Gap Controller、Answer Compiler、Retrieval Policy、Answerability、Publication Gate、Frozen Benchmarks 或评分体系做任何修改；在线默认值严格维持 **`SCHOLARLENS_PRA_ARM=A`**。
2. **完整工程审计与精准修复（阶段 1）**：
   - 在纯 ASCII Git Worktree `C:\work\scholarlens-final-release` 开展全部审计与实测（完整保护了原含中文路径工作区及未提交本地缓存）。
   - 对 20 项工程子域实施源码级排查：`ruff --select E9,F63,F7,F82` **0 致命语法/作用域错误**，AST 静态扫描 **0 bare except / 0 敏感日志输出**，`pip-audit` **0 漏洞**，`npm audit` **0 漏洞**。
   - 修复了 3 项非研究算法类工程问题：Windows `.venv` 启动/停止路径兼容性（`infra/start-backend1.ps1`、`infra/stop-backend.ps1`）、4 处 ES 补丁版本断言兼容（`8.19.23` 与 `8.19.26`）、以及 CI 运行环境补齐项（`.github/workflows/agent-ci.yml` 与经核实非秘密的 `.gitleaksignore`）。
3. **全量后端与 Elasticsearch 8.19.x 双环境集成（阶段 2）**：
   - 本地 Windows 11 ASCII Worktree 针对真实隔离 ES 8.19.23（859 篇真实论文 + 49,420 个 MiniLM 向量 + 交付 API 重启回归）：**`1,028 passed, 0 failed, 0 skipped`（`444.523s`，退出码 `0`）**。
   - GitHub Actions `ubuntu-latest` 独立 `integration` 作业启动实时 Elasticsearch 8.19.26 与 Jaeger 1.60 容器，现场导入 859 篇 `papers_final.jsonl` 并拉取锁定历史 Git LFS 对象：`964` 项测试 **`963 passed, 0 failed, 0 errors, 1 Windows-only skipped`**（详见 [FULL_BACKEND_ACCEPTANCE.md](FULL_BACKEND_ACCEPTANCE.md)）。
4. **Docker Standard / PDF OCR 镜像、升级与回滚 + SQLite 恢复演练（阶段 3）**：
   - 在 GitHub Actions Linux Docker 宿主机实测通过 `Standard`（ES `8.19.23 -> 8.19.26` 卷保留 + 重建持久化）及 `Standard -> PDF OCR -> Standard` 原地升级、容器内 `ocr_check` + 合成光栅图例 PDF OCR 提取（`River`, `Lake`, `Forest`）与回滚全流程（详见 [DOCKER_DEPLOYMENT_ACCEPTANCE.md](DOCKER_DEPLOYMENT_ACCEPTANCE.md)）。
   - 本地独立完成账户库（`schema_version=0 -> 4`）与研究任务库（`user_version=1`）在线一致性备份、模拟损坏、CLI（`python -m backend.db_migrations --restore`）恢复及双向回滚实测（详见 [BACKUP_RESTORE_ACCEPTANCE.md](BACKUP_RESTORE_ACCEPTANCE.md)）。
5. **全量安全扫描、SBOM 与逐条 CVE 排查（阶段 4）**：
   - `pip-audit` 0 漏洞、`npm audit` 0 漏洞、Gitleaks v8.30.1 扫描全仓库 229+ 提交历史 **0 真实密钥泄露**，Syft v1.57.2 为 `standard` 与 `pdf-ocr` 产出完整 SPDX SBOM。
   - Grype 实测扫描 `standard`（`0 Critical / 82 High`）、`pdf-ocr`（`0 Critical / 87 High`）、`elasticsearch:8.19.26`（`0 Critical / 5 High`），全部逐条分析可达性与缓解措施归档于 [SECURITY_TRIAGE.md](SECURITY_TRIAGE.md)。
6. **模型配置工程验证与受控 HTTP（阶段 5）**：
   - `v7_live_research --controlled` 实测 **9/9 PASS**；代理边界、SSRF DNS 钉扎、文件锁共享并发、结构化 JSON 检验及 Token/成本统计全面验证。因运行环境未配置实网 API Key，本轮实网复测诚实标为 **`BLOCKED`**，保留 V9 `deepseek-v4.1-flash` 实网 **9/9 PASS** 归档（详见 [LIVE_MODEL_ACCEPTANCE.md](LIVE_MODEL_ACCEPTANCE.md)）。
7. **监控、OpenTelemetry、Jaeger 与运维手册（阶段 6）**：
   - 在 CI 中启动实时 `jaegertracing/all-in-one:1.60` 验证由 FastAPI API 提交跨 Worker 线程异步导出的 OTLP/HTTP trace，成功在 Jaeger 查询接口按 `trace_id` 检出完整 **9 个关联 Span**（`research.api` 至 `research.publication`），并撰写系统 [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) 与 [USER_GUIDE.md](USER_GUIDE.md)。
8. **真实后端 Playwright 浏览器端到端验收（阶段 7）**：
   - 连接真实隔离 ES 8.19.23（859 篇）+ 真实 FastAPI（`uvicorn backend.app1:app`）+ 生产构建前端（`VITE_RESEARCH_ENABLED=true`, `VITE_EVOLUTION_LAB=true`），使用 headless Chrome 158 连续跑通官方 `real-workbench-live.mjs` 与全量 `stage7-release-e2e.mjs`：覆盖未登录 `401`、普通用户越权管理/Lab `403`、跨账号读取任务 `404`、注册/登录刷新保持、收藏与文献库刷新保持、PDF 上传队列、双论文深度研究（含项目统计、问题 DAG、逐篇档案、报告、Markdown & ZIP 导出、任务追踪与可读原文跳转）、缺失页面错误态、空状态、管理员控制台、Evolution Lab 治理面板及 `390x844` 移动端适配，`page_errors: []`，`console_errors: []`，全部 **PASS**。

---

## 2. 版本与发布交接决定

由于上游 Debian Trixie OS 包及 `elasticsearch:8.19.26` 内置 `guava` 存在尚未由发行版/供应商修复的高危匹配（`0 Critical`），且本轮受环境密钥策略约束未执行实网大模型二次重跑，依据发布工程纪律：
- 代码合并至 `main`（完整保留原 859 篇正式论文数据资产与脚本）；
- 创建 **GitHub Draft Release (`v1.0.0`)**，待项目负责人完成 [FINAL_RELEASE_READINESS.md](FINAL_RELEASE_READINESS.md) 中列明的 4 项风险签核后即可正式转正发布。
