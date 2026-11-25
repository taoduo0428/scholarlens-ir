# ScholarLens 运维手册 (Operations Runbook)

本手册面向部署与系统运维人员，规范 **ScholarLens EvoResearch V9** 生产及独立验收环境的配置、启停、升级、回滚、备份恢复、监控追踪与故障排查。

---

## 1. 服务拓扑与运行约束

- **应用服务 (`api`)**：基于 Python 3.11 + FastAPI + Uvicorn 单 Worker 进程运行；负责检索 API、账户/工作台、上传审核、研究任务调度与同源静态前端托管（`FRONTEND_DIST`）。默认以非特权用户 `10001`、只读根文件系统、清空 Capabilities (`cap_drop: [ALL]`) 与禁止提权运行，持久化数据全部落于 `/var/lib/scholarlens` 卷。
- **检索服务 (`search`)**：Elasticsearch **8.19.26**（或本地 Windows 兼容节点 **8.19.23**）单节点，仅允许监听 `127.0.0.1` 或 Docker 内部网络，禁止直接暴露公网端口。
- **数据双库结构**：
  - `scholarlens.sqlite3`（Schema v4）：账户、会话哈希、收藏夹、阅读历史、上传审批队列。
  - `research.sqlite3`（User Version 1）：研究任务状态机、问题 DAG 密封哈希 (`plan_seals`)、事件游标、检查点、产物与项目记忆。
- **生产算法默认**：保持 `SCHOLARLENS_PRA_ARM=A`（V9 `R` 策略仅供显式评估配置，未经授权不设为默认）。

---

## 2. 关键环境变量清单

完整示例参见 [infra/.env.example](../../infra/.env.example)。严禁将任何密钥提交至 Git。

| 变量名 | 默认值 / 示例 | 用途说明 |
| --- | --- | --- |
| `ELASTICSEARCH_URL` | `http://127.0.0.1:9200` / `http://search:9200` | ES 接入地址 |
| `ELASTICSEARCH_INDEX` | `scholarlens-papers-real` | 主论文库索引别名 |
| `VECTOR_INDEX` | `scholarlens-vectors-real` | 语义向量切片别名 |
| `SCHOLARLENS_RUNTIME_DIR` | `/var/lib/scholarlens` | SQLite 数据库、上传文件、并发锁目录 |
| `EMBEDDING_MODEL_DIR` | `backend/.runtime/minilm` | 本地 CPU ONNX MiniLM 模型目录 |
| `SCHOLARLENS_RESEARCH_ENABLED` | `true` | 开启 `/api/research/*` 深度研究工作台 |
| `SCHOLARLENS_E11_ENABLED` | `true` | 开启 E11 研究架构与档案/关系编排 |
| `SCHOLARLENS_PRA_ARM` | `A` | 研究策略臂（`A` 为默认，`R` 为 V9 增强候选） |
| `SCHOLARLENS_MODEL_CAPACITY_DIR` | `/var/lib/scholarlens/model-capacity` | 多进程共享模型并发配额锁目录（全局 4 / 单主机 2） |
| `SCHOLARLENS_OTEL_ENABLED` | `false` / `true` | 开启 OpenTelemetry Trace 采集与 OTLP 导出 |
| `SCHOLARLENS_OTLP_TRACES_ENDPOINT` | `https://collector.example.org/v1/traces` | OTLP/HTTP protobuf 地址（仅允许 HTTPS 或回环 HTTP 且路径须为 `/v1/traces`） |
| `SCHOLARLENS_TESSERACT` | `/opt/scholarlens-ocr/bin/tesseract` | `pdf-ocr` 镜像内用于图像图例 OCR 的可执行文件路径 |
| `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY` | 留空 | 服务端全站 AI（默认关闭，推荐用户于会话内临时传入个人密钥） |

---

## 3. 容器部署、升级与回滚流程

### 3.1 首次启动 Standard 模式
```bash
docker compose -f infra/product.compose.yml config -q
docker compose -f infra/product.compose.yml build api
docker compose -f infra/product.compose.yml up -d search
# 导入或恢复已验收论文索引后启动 API：
SCHOLARLENS_E11_ENABLED=true docker compose -f infra/product.compose.yml up -d api
curl -fsS http://127.0.0.1:18001/healthz
curl -fsS http://127.0.0.1:18001/readyz
```
*注：若 ES 尚未创建合法 `_meta` 论文索引或 SQLite 不可达，`/readyz` 将诚实返回 HTTP `503 unavailable`。*

### 3.2 升级至 PDF OCR 模式并验证能力
```bash
docker compose -f infra/product.compose.yml -f infra/pdf-ocr.compose.yml build api
SCHOLARLENS_E11_ENABLED=true docker compose -f infra/product.compose.yml -f infra/pdf-ocr.compose.yml up -d api
docker compose -f infra/product.compose.yml -f infra/pdf-ocr.compose.yml exec -T api python -m backend.research.ocr_check
```

### 3.3 镜像快速回滚（例如 PDF OCR -> Standard 或回退上一版本）
保留现有 `research-data` 和 `search-data` 持久化卷不变：
```bash
export SCHOLARLENS_IMAGE=<previous-verified-image-digest>
docker compose -f infra/product.compose.yml up -d --no-build --wait api
curl -fsS http://127.0.0.1:18001/readyz
```

### 3.4 开启 Governance 治理视图（可选只读挂载）
确保宿主目录 `SCHOLARLENS_APPROVALS_DIR` 与 `SCHOLARLENS_LAB_SNAPSHOT_DIR` 对 UID `10001` 只读可读：
```bash
docker compose -f infra/product.compose.yml -f infra/governance.compose.yml up -d --build api
```

---

## 4. 备份与灾难恢复 SOP

### 4.1 在线一致性备份（无需停机）
1. **研究库备份**：
   ```python
   from pathlib import Path
   from backend.research.store import ResearchStore
   ResearchStore(Path("/var/lib/scholarlens")).backup(Path("/backups/research-YYYYMMDD.sqlite3"))
   ```
2. **账户库备份**：在升级前会由 `backup_before_upgrade()` 自动落盘于 `db-backups/`；日常定时快照可使用 Python `sqlite3.Connection.backup()` 至隔离备份盘。
3. **上传原件与 ES 数据**：同步打包 `/var/lib/scholarlens/uploads/files`，并为 ES 索引创建只读 Snapshot 或滚动备份。

### 4.2 停机恢复演练步骤
1. **停止写流量**：先 `docker compose -f infra/product.compose.yml stop api`（确保 Worker 无活跃锁）。
2. **恢复研究库（须使用新空目录或专用恢复入口）**：
   ```python
   from pathlib import Path
   from backend.research.store import ResearchStore
   ResearchStore.restore(Path("/backups/research-YYYYMMDD.sqlite3"), Path("/var/lib/scholarlens-restored"))
   ```
3. **恢复账户库（CLI 自动保留恢复前副本以便回退）**：
   ```bash
   python -m backend.db_migrations --database /var/lib/scholarlens/scholarlens.sqlite3 --restore /backups/scholarlens-YYYYMMDD.sqlite3
   ```
4. **重启并核验**：启动 `api`，检查 `/readyz` 返回 `200 ready`，使用两个测试账号分别验证登录、原有研究报告哈希及跨账号 `404` 隔离。

---

## 5. OpenTelemetry、Jaeger 链路追踪与故障排查

1. **开启追踪与对接 Jaeger**：
   - 将后端环境变量配置为 `SCHOLARLENS_OTEL_ENABLED=true`、`SCHOLARLENS_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces`（同机或网关侧 HTTPS Collector）；构建前端时可传入 `VITE_JAEGER_UI_PATH=/jaeger` 并由同源反向代理严格校验权限后转发 Jaeger 查询接口。
   - **链路关联结构**：API 受理 `POST /api/research/tasks` 时创建根 span `research.api` 并写入 `submission_trace`；Worker 线程接管任务时续接同一 `trace_id`，依次发射 `research.task` → `research.workflow` → `research.plan` → `research.retrieve` / `research.tool` / `research.verify` / `research.model` → `research.synthesis` → `research.publication`；全部子 span 携带 `outcome` 与 `error.category`（`timeout`/`validation`/`dependency`）属性，并在 `GET /api/research/tasks/{tid}` 返回 `trace_ids` 列表供排障定位。
   - **安全排障**：应用内置保护，导出失败时仅打印脱敏告警 `Research trace export failed`，绝不输出 Collector URL、鉴权头或研究正文。
2. **常见故障处置表**：
   - **`/readyz` 返回 503**：排查 ES 容器是否健康（`curl http://localhost:9200/_cluster/health`）、`ELASTICSEARCH_INDEX` 别名是否仅指向单一含合法 `_meta` 的索引、SQLite 目录权限是否属于 UID 10001。
   - **研究任务长期卡在 `queued` 或启动报错 `research_worker_already_running`**：检查同运行时目录是否同时运行了第二个进程持有 `research.worker.lock`；停止多余实例后重新启动。
   - **模型任务返回 `awaiting_credentials` / `provider_rate_limited`**：`personal_model` 模式重启后不落盘个人密钥，需用户恢复任务时重新传入；若为并发受限，核查 `SCHOLARLENS_MODEL_CAPACITY_DIR` 文件锁或降低上游并发。
   - **上传 PDF 返回 `pdf_requires_ocr`**：说明上传 PDF 无可选文本层，需提示用户改传文本型 PDF 或由管理员借助 OCR 管线提取文本后再行入库。
