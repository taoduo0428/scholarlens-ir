# 发布准入与就绪评估 (Final Release Readiness)

**评估版本**：`v1.0.0`（分支 `gemini/final-release-closure` / PR `#47`）  
**评估日期**：2026-11-25  
**线上生产策略默认值**：`SCHOLARLENS_PRA_ARM=A`（V9 `R` 保留为显式可选实验配置）  
**当前发布决策**：**创建 GitHub Draft Release（`v1.0.0` 草稿），等待安全风险签核与实网模型复测后方可转正为正式公开发布**（严格遵循“无未处置/无签核的高危风险与未解除 BLOCKED 不得伪造正式发布 PASS”）。

---

## 1. 十八项发布验收状态总表

| # | 验收模块 / 事项 | 状态 | 实测核心依据与结论 |
| --- | --- | --- | --- |
| **1** | **全量后端测试** | **PASS** | 本地纯 ASCII Worktree ES 8.19.23 跑通 **1,028/1,028（0 failed, 0 skipped, 444.523s）**；CI `verify` **446/446**；CI `integration` ES 8.19.26 **963 passed, 0 failed, 1 Windows-only skipped** |
| **2** | **Elasticsearch 集成与升级** | **PASS** | 本地 8.19.23 859 篇 + 49,420 向量；CI 8.19.26 现场导入 `papers_final.jsonl`（859 篇）；Compose `8.19.23 -> 8.19.26` `cluster_uuid` 与 BM25/kNN 保留 |
| **3** | **Docker Standard 构建与运行** | **PASS** | `sha256:9cd90123...`；非特权 `UID 10001`、只读根、`cap_drop ALL`、裁剪 `pytest/ruff`；Compose 重建容器后账户与数据保留 |
| **4** | **Docker PDF OCR 构建与验收** | **PASS** | `sha256:19d820b9...`；内置自定义无多余依赖 `scholarlens-tesseract 5.5.0`；`ocr_check` 与内嵌光栅图例 PDF OCR 提取（`River`, `Lake`, `Forest`）实测通过 |
| **5** | **Compose 升级与回滚** | **PASS** | CI 实测 `Standard -> PDF OCR -> Standard` 同卷原地升级、报告校验、跨账号 `404`、SQLite 恢复与回滚全部 `PASS` |
| **6** | **SQLite 迁移/备份/恢复/回滚** | **PASS** | `Store` v0→v4 自动升级前 SHA-256 备份 + `ResearchStore.backup/restore` + `python -m backend.db_migrations --restore` 双向回滚演练 `PASS` |
| **7** | **安全扫描与 CVE 分级排查** | **CONDITIONAL (Needs Sign-Off)** | 应用依赖（`pip-audit=0`, `npm audit=0`）、全历史密钥（`Gitleaks=0`）、Critical CVE（**全 0**）均过；剩余 `82` (`standard`) / `87` (`pdf-ocr`) Debian Trixie OS `not-fixed`/`wont-fix` High 及 `5` 条 ES 8.19.26 `guava` High 需运维/负责人风险签核（详见 [SECURITY_TRIAGE.md](SECURITY_TRIAGE.md)） |
| **8** | **真实大模型实时联网验收** | **BLOCKED (V9 Historical PASS)** | 本轮运行时环境未配置 `AI_BASE_URL`/`AI_MODEL`/`AI_API_KEY`，如实标记 `BLOCKED`；受控 `V9` 历史 `deepseek-v4.1-flash` 实网验收保持 **9/9 PASS** 记录 |
| **9** | **受控模型工程与限流网关** | **PASS** | `v7_live_research --controlled` **9/9 PASS**；覆盖代理白名单、SSRF DNS 钉扎、文件锁并发、超时无重试降级、Schema 校验、用量记账与密钥脱敏 |
| **10** | **OpenTelemetry 与 Jaeger 追踪** | **PASS** | CI 实时对接 `jaegertracing/all-in-one:1.60` 接收 OTLP `/v1/traces`，按 `trace_id` 查回 9 条父子完整 span（`research.api` 至 `research.publication`） |
| **11** | **前端工程化与单元测试** | **PASS** | `tsc --noEmit`、`vite build`（`build:production`）、结构校验及原生 `node --test` **47/47 PASS**，`npm audit` 0 漏洞 |
| **12** | **真实后端 Playwright 浏览器 E2E** | **PASS** | 对接真实 ES 8.19.23 (859 篇) + FastAPI + Chrome 158，通过 `real-workbench-live.mjs` 与 `stage7-release-e2e.mjs`（12 项核心流程 + 移动端 `390x844` + 6 张截图，0 `pageerror`） |
| **13** | **权限隔离、审核上传与防泄露** | **PASS** | 未登录 `401`、普通账号调管理/Lab 接口 `403`、跨用户读研究任务 `404`、上传路径遍历与 20 MiB 上限中间件拦截全部实测通过 |
| **14** | **研究算法冻结与默认参数合规** | **PASS** | E11/PRA/V9 H1–H5 代码、提示词、参数、Frozen Benchmark 与评分零修改；`SCHOLARLENS_PRA_ARM=A` 为唯一生产默认值 |
| **15** | **CI/CD 全门禁自动化** | **PASS** | GitHub Actions Run `45566748805` 全部 **5/5 Jobs 绿灯**（`verify`, `integration`, `standard`, `pdf-ocr`, `security`），上传 JUnit、SBOM、Grype、Jaeger、Gitleaks 全部制品 |
| **16** | **运维、用户手册与发布文档** | **PASS** | 完成 `README.md`、`CHANGELOG.md`、`infra/.env.example` 与 `docs/release-v1/` 全部 11 份结构化交付件 |
| **17** | **主干 859 篇数据资产完整性** | **PASS** | PR #47 仅触及工程/CI/测试/文档，完全未修改 `data/paper_jsonl/*` 与 `scripts/*` |
| **18** | **GitHub Release 发布门禁结论** | **DRAFT RELEASE** | 依据第 6.4/10.3 条准则，创建 GitHub **Draft Release (`v1.0.0`)**，待下方签核项全部确认后即可正式公开发布 |

---

## 2. 将 Draft Release 转正为正式 Release 所需的负责人签核清单

1. **Debian Trixie 运行库残留 High CVE 风险签核**：确认接受当前 Debian 13 (Trixie) 上游未发布补丁的 `not-fixed` / `wont-fix` OS 包（重点涉及外呼 TLS 链路使用的 `openssl`/`libssl3t64`、C 运行库 `libc6` 与按 `ldd` 最小化裁剪并限制输入仅限 450px PNG 图例的 `scholarlens-tesseract`）。
2. **Elasticsearch 8.19.26 模块 `guava` High 告警签核**：确认在 `xpack.security`/`xpack.ml`/`watcher`/`repository-gcs` 关闭且 ES 仅监听 `127.0.0.1`/内部 Docker 网络前提下，按上游官方镜像策略暂缓篡改 Elastic 内置 JAR，待 Elastic 8.19.x 后续补丁版本整体升级。
3. **部署目标环境实网大模型与密钥库复验（如启用全站模型模式）**：由运维人员在目标受控环境注入合法 `AI_BASE_URL`/`AI_MODEL`/`AI_API_KEY` 与预算上限，执行 `LIVE_MODEL_ACCEPTANCE.md` 中的 `--live` 命令完成实网 4 次调用验收；若目标环境仅运行 `evidence_only` 只读证据模式则无需外部模型密钥。
4. **公网生产环境部署窗口授权（如需同步更新 `scholarlens.lingion.cc.cd`）**：需另行单独下达生产部署指令（本轮已严格遵守“不执行公网生产发布”指令）。
