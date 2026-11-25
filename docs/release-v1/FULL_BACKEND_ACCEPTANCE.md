# 全量后端测试验收报告

**验收日期**：2026-11-25  
**分支与基线**：`gemini/final-release-closure`（基线 `origin/main` `160b84e1305d99f4ac58036a9879f229022e03d8`）  
**状态**：**PASS**（本地 Windows ASCII Worktree **1,028 / 1,028**；CI Ubuntu `integration` 真实 ES 8.19.26 **963 passed / 0 failed / 1 Windows-only skipped**；CI `verify` **446 / 446**）

---

## 1. 本轮解决的工程障碍（均不修改研究算法）

在接手核查时，全量后端测试在本地历史中文路径工作区曾因环境启动与测试兼容性问题出现报错，本轮彻底定位并修复以下 3 个纯工程与脚本兼容问题：
1. **Windows 中文路径触发 Elasticsearch Java Entitlement Agent GBK 异常**：OpenJDK 27 Entitlement Agent 在解析含中文路径 `检索agent` 时按 GBK 乱码而无法启动。本轮在独立纯 ASCII Worktree `C:\work\scholarlens-final-release`（完整安装 Python 3.11.15 `.venv`、锁定 `backend/requirements-lock.txt`、`backend/research/requirements.txt`、`backend/research/pdf-layout-requirements.txt` 与 `tools/audit/requirements.txt`）运行并持久化隔离夹具副本，问题彻底消除。
2. **Windows 启动/停止脚本 `.venv` 路径不兼容（`infra/start-backend1.ps1` & `infra/stop-backend.ps1`）**：两处脚本此前硬编码仅查找 `backend/.venv/Scripts/python.exe`，在根目录使用 `.venv` 的 Worktree 中运行 `test_real_data.py::test_own_api_restart_preserves_real_index` 时先因找不到解释器报错、随后 `stop-backend.ps1` 因进程 `ExecutablePath` 校验失败抛出异常。现已统一为优先查找 `backend/.venv/Scripts/python.exe`、缺失时安全回退 `.venv/Scripts/python.exe`，进程树安全校验保持不变。
3. **Elasticsearch 8.19.23 与 8.19.26 小版本断言对齐**：`test_search_integration.py`、`test_papers_integration.py`、`test_upload_integration_isolated.py` 与 `research/test_research_tools_loopback.py` 原先写死 `== "8.19.23"`，已放宽为同时接受已锁定的两个合法补丁版本 `{"8.19.23", "8.19.26"}`，使完全一致的集成用例可同时在本地 ES 8.19.23 与 GitHub Actions ES 8.19.26 上执行。

*算法冻结证明：所有改动均不涉及 E11、PRA、V9 H1–H5 算法逻辑、提示词、检索权重、Answerability/Publication Gate 或冻结 Benchmark，线上默认策略保持 `SCHOLARLENS_PRA_ARM=A`。*

---

## 2. 双环境实测执行矩阵

| 验证环境 | 测试入口 / 命令 | Total | Passed | Failed | Errors | Skipped | Deselected | 耗时 | 证据文件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **本地 Windows 11 ASCII Worktree (ES 8.19.23)** | `.\.venv\Scripts\python.exe -m tools.research_eval.v6_vector_fixture --es-home ...\elasticsearch-8.19.23 --offline-fixture ...\data --full-suite --delivery ...\p0-delivery` | **1,028** | **1,028** | **0** | **0** | **0** | 0 | `444.523s` | [counts.json](../../output/release-v1/backend-full/counts.json) · [result.json](../../output/release-v1/backend-full/result.json) |
| **CI Ubuntu `verify` (Run `45566748805`)** | 单元测试 + 契约 + V9 (`test_v9_*.py`) + SQLite 迁移回滚 + Scorecard | **446** | **446** | **0** | **0** | **0** | 0 | `30.116s` | [unit-counts.json](../../output/release-v1/ci-final/agent-unit-counts/unit-counts.json) |
| **CI Ubuntu `integration` (Run `45566748805`, ES 8.19.26 + Jaeger 1.60)** | 导入 859 篇真实论文 + OTLP 链路实测 + `pytest backend/tests`（排除 6 个需未入库 MiniLM ONNX 模型或 Windows `.ps1` 的文件） | **964** | **963** | **0** | **0** | **1*** | 1 | `74.988s` | [integration-counts.json](../../output/release-v1/ci-final/backend-integration-es/integration-counts.json) |

*\*注：CI Ubuntu 上唯一的 1 条 skipped 用例为 `test_upload_runner_guards.py::test_timeout_stops_owned_child_and_grandchild_with_unicode_space_paths`（显式标注为 Windows 原生进程生命周期测试），该用例已在本地 Windows 全量 1,028/1,028 运行中实际通过。*

---

## 3. 本地 ES 8.19.23 全量隔离核验细节

从 `output/release-v1/backend-full/result.json` 读取的原始运行时核验指标：
- `tests_exit`: `0`
- `scope`: `"offline copied fixture"`（从停止的 `elasticsearch-8.19.23/data` 复制到临时隔离目录运行）
- `papers`: `859`（与正式论文全集一致）
- `vectors`: `49420`（全部 MiniLM ONNX 向量切片写入并计数一致）
- `source_unchanged`: `true`（运行前后源 fixture 所有文件大小与 `mtime_ns` 字节签名 100% 不变）
- `ports_closed`: `true`（运行结束后临时 ES HTTP 与 Transport 端口彻底释放）
