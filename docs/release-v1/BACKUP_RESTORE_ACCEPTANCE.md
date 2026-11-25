# SQLite 迁移、备份、恢复与回滚验收报告

**验收日期**：2026-11-25  
**验收版本**：`gemini/final-release-closure`（基线 `origin/main` `160b84e1305d99f4ac58036a9879f229022e03d8`）  
**证据载体**：[drill-receipt.json](../../output/release-v1/backup-restore/drill-receipt.json) · [db_migrations.py](../../backend/db_migrations.py) · [store.py](../../backend/research/store.py)

---

## 1. 架构与恢复机制说明

ScholarLens 将用户/工作台状态与研究任务状态拆分在两套独立的 SQLite WAL 数据库中，避免高写入研究任务阻塞账户鉴权：
1. **账户与上传库（`scholarlens.sqlite3`，当前 Schema 版本 `VERSION = 4`）**
   - 由 `backend/accounts.py::Store` 初始化并调用 `backend/db_migrations.py::backup_before_upgrade()`。
   - 若检测到旧库 `schema_version < 4`，升级前自动在 `db-backups/before-v4-<uuid>.sqlite3` 执行一致性在线备份（`sqlite3.Connection.backup()` + `PRAGMA integrity_check == 'ok'`），并生成含源版本号、目标版本号与 SHA-256 摘要的 `.json` 元数据清单。
   - 恢复与回滚入口：`python -m backend.db_migrations --database <live.sqlite3> --restore <backup.sqlite3>`（需先停止 API 写进程）。恢复函数首先校验目标备份完整（`integrity_check`）且路径不同，随后在覆盖活动库前先将现行状态（含未合入 WAL 的全部变更）备份到同目录 `before-restore-<uuid>.sqlite3`，确保可一键回退恢复前现场。
2. **研究任务与报告库（`research.sqlite3`，`PRAGMA user_version = 1`）**
   - 由 `backend/research/store.py::ResearchStore` 管理，内建 `backup(destination)`（`O_CREAT | O_EXCL` + `0o600` 权限保护的线上一致性备份）与 `ResearchStore.restore(snapshot, runtime)`（只读连接校验 `user_version == 1`、`PRAGMA quick_check` 及核心四表 `tasks`/`events`/`checkpoints`/`artifacts` 存在性后，写入全新空目录，拒绝覆盖已有生产库）。

---

## 2. 本轮独立实战演练结果（PASS）

在隔离临时运行目录中执行了完整的账户库升级 + 研究库损坏与命令行恢复 + 双向回滚演练（实测输出留存见 `output/release-v1/backup-restore/drill-receipt.json`）：

| 演练步骤 | 操作内容 | 实际观察结果 | 状态 |
| --- | --- | --- | --- |
| **1. 旧版账户库自动升级前备份** | 构造 `schema_version = 0`（无 `email_verified` 列）的旧 `scholarlens.sqlite3`（用户 `drill_user`），初始化 `Store()` | 自动生成 `db-backups/before-v4-*.sqlite3` 及 `.json` 清单；SHA-256 校验通过（`d298de11...7ced81f20`）；表结构平滑升级至 `VERSION = 4` 且保留用户记录 | **PASS** |
| **2. 研究库一致性备份** | 创建 `ResearchStore` 任务（`idem-drill-1`），执行 `rstore.backup(r_backup)` | 备份文件安全生成，任务与事件写入完整 | **PASS** |
| **3. 模拟破坏与 CLI 恢复** | 直接 `DELETE FROM tasks` 清空活动库后，调用 `python -m backend.db_migrations --database ... --restore ...` | CLI 返回 `{"restored": true, "preserved_file": "before-restore-8d5e284b806b4ecf816e3275a0104697.sqlite3"}`；任务记录完整恢复；同时 `ResearchStore.restore()` 独立恢复到新目录校验通过 | **PASS** |
| **4. 双向回滚验收** | 使用生成的 `before-restore-*.sqlite3` 对账户库与研究库均执行反向回滚，再还原升级后状态 | 账户库先回滚至无 `email_verified` 的旧结构并保持 `PRAGMA integrity_check == ok`，随后再次还原为含 `browsing_history` 记录的 `v4` 结构；研究库精确切回并复原 | **PASS** |
| **5. 单元/契约回归** | `pytest -q backend/tests/test_v21_flows.py -k "migration_legacy or restore_preserves"` | 纳入 CI `verify` 门禁全绿通过 | **PASS** |

---

## 3. Elasticsearch 卷升级与保留验证

- 在 CI `Build and scan (standard)` 中，使用 Compose 启动 `elasticsearch:8.19.23` 创建带真实 `dense_vector` 映射与文档的 `scholarlens-fixture` 索引，记录 `cluster_uuid`，随后就地升级至 `elasticsearch:8.19.26` 并验证同一 `cluster_uuid`、BM25 关键词检索与 kNN 向量检索均命中原始文档，证明跨小版本卷数据与聚类标识完全兼容保留。
