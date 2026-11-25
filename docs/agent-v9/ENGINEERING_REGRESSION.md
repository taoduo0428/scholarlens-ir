# Stage G 全量工程回归与安全审计报告

本报告如实记录 Stage G 在 Windows 宿主机（仓库路径含中文：`C:\Users\lenovo\Desktop\检索agent`）上执行的全部工程回归命令、范围、通过数量及客观环境局限。

## 1. 工程回归结果总表

| 检查项 | 执行命令 / 范围 | 结果 | 说明与证据 |
| --- | --- | --- | --- |
| **研究核心测试全集（修复 `graph.py` 作用域后重跑）** | `pytest backend/tests/research -q` | **`574 passed, 11 skipped, 0 failed`** (`exit 0`, 170.66s) | 覆盖 H1–H5 单测、E11/PRA 编译与多跳、受控模型协作、PDF 布局 (`test_pdf_layout.py` 1 passed)、OTLP (`test_otlp_delivery.py` 5 passed, 8 skipped)。11 个 skip 均因本地未启动 Jaeger / 外部服务。 |
| **PDF 布局可选依赖** | `uv pip install -r backend/research/pdf-layout-requirements.txt` | **`INSTALLED`** (`exit 0`) | 已安装 `pdfplumber==0.11.11`, `pypdfium2==5.15.2`, `pdfminer-six==20260107`, `cffi==2.1.1`, `cryptography==50.0.2`, `pycparser==3.12`。 |
| **隔离 ES 8.19.23 向量夹具 (`v6_vector_fixture`)** | `python -m tools.research_eval.v6_vector_fixture --es-home infra/.runtime/elasticsearch-8.19.23 --offline-fixture infra/.runtime/elasticsearch-8.19.23/data --full-suite --delivery backend/.runtime/p0-delivery` | **`BLOCKED` (环境路径阻塞)** (`exit 1`) | ES 8.19.23 Java JVM 附加 Entitlement Agent 时因路径包含中文 `检索agent` 出现 GBK 编码损坏（`Unable to attach entitlement agent [...\妫€绱gent\...elasticsearch-entitlement-agent-8.19.23.jar]`），导致测试夹具未能启动（原夹具目录未受损）。 |
| **全量后端测试 (`pytest backend/tests -q`，无 ES 服务)** | `pytest backend/tests -q` | `901 passed, 32 skipped, 6 failed, 89 errors` (`exit 1`) | 89 个 error 全部及 2 个非 research failure（`test_title_highlight_noise_and_full_author_metadata`、`test_porter_comparison_is_ephemeral`）均为连接 `http://127.0.0.1:9200` 失败；另 4 个 research 失败已在随后的独立研究全套测试修复 `b799ae2` 后清零（`574 passed, 0 failed`）。 |
| **冻结基准字节校验 (`v6_ci`)** | `python -m tools.research_eval.v6_ci` | **`PASS`** (`exit 0`) | `9 frozen files verified`（与 `5dd0cbce...` 字节完全一致）。 |
| **公开 Silver 校验 (`v6_silver`)** | `python -m tools.research_eval.v6_silver --public-only` | **`PASS`** (`exit 0`) | `task_count=111`, SHA-256 `d2f257fe...` 校验无误。 |
| **V8 评分卡不变性 (`pra_scorecard`)** | `python -m tools.research_eval.pra_scorecard --records docs/agent-v8 --out ...` | **`PASS`** (`exit 0`) | 与 [PRA_SCORECARD.json](file:///c:/Users/lenovo/Desktop/检索agent/docs/agent-v8/PRA_SCORECARD.json) 逐字段比较 `pra_scorecard_identical = True`。 |
| **V9 改动代码静态检查 (`ruff`)** | `ruff check <all V9 modified/added backend & eval files>` | **`PASS`** (`exit 0`) | `All checks passed!`（全仓未改动旧文件共 95 处历史存量样式提醒未越权修改）。 |
| **前端单测 / 结构校验 / 生产构建** | `npm test`; `npm run verify:structure`; `VITE_RESEARCH_ENABLED=true npm run build:production` | **`PASS`** (`exit 0` x3) | `tests 47 pass 0 fail`；`44 files` 结构校验通过；Vite 生产构建 1663 modules `✓ built in 8.36s`。 |
| **Docker Compose 校验** | `Get-Command docker` | **`UNAVAILABLE`** | 当前 Windows 宿主机未安装 Docker CLI，未运行容器编排校验。 |

## 2. 默认配置与敏感信息防泄露审计

- **在线默认参数**：[api.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/api.py#L98) 与 [schemas.py](file:///c:/Users/lenovo/Desktop/检索agent/backend/research/schemas.py#L239) 保持 `pra_arm = "A"`，确保未显式指定环境变量时线上零影响、随时可在 `"A"` / `"G"` / `"R"` 间即时切换或回滚。
- **全仓及 Git 历史密钥扫描**：执行全工作区与 Git 历史前缀匹配扫描，确认代码、测试、文档、配置与 Git 提交历史中测试 API Key 出现次数均为 **0**。
