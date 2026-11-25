# Elasticsearch 8.19.x 集成与升级验收报告

**验收日期**：2026-11-25  
**支持与验证版本**：本地 Windows 单节点 **8.19.23** · CI / Docker Compose **8.19.26** (`docker.elastic.co/elasticsearch/elasticsearch:8.19.26@sha256:d71769f4e1145dca3794a04ddcd67e12f1299048b3232025e55feda799904a5d`)  
**状态**：**PASS**

---

## 1. 语料、索引与检索能力验证

| 验证维度 | 本地 ASCII Worktree (ES 8.19.23) | GitHub Actions CI `integration` (ES 8.19.26) | 状态 |
| --- | --- | --- | --- |
| **集群与版本身份** | `scholarlens-acceptance-*`, `8.19.23` | `scholarlens-local`, `8.19.26` | **PASS** |
| **正式论文数量** | `859` 篇（离线复制完整卷 + delivery 校验） | 从 `data/paper_jsonl/papers_final.jsonl` 现场实时导入 `indexed: 859, bulk_failed: 0` | **PASS** |
| **语义向量切片** | `49,420` chunks（MiniLM ONNX 384 维余弦） | Compose 升级验证 `dense_vector` kNN 检索正常 | **PASS** |
| **六字段 BM25 & 高亮** | `title^3`, `authors^2`, `date`, `affiliation`, `address`, `fulltext` 全通过，`.cjk` 辅助字段对齐 | CI 实测 `test_search_integration.py`、`test_chinese_readiness.py` 全通过 | **PASS** |
| **上传独立索引与隔离** | `scholarlens-uploads-*` 与 `scholarlens-vectors-uploads-*` 独立构建并保留 859 篇基线不变 | `test_v21.py` 上传与权限隔离全部通过 | **PASS** |
| **跨版本卷保留与升级 (`8.19.23 -> 8.19.26`)** | — | CI `Build and scan (standard)` 从 `8.19.23` 写入带 `dense_vector` 文档并就地升级到 `8.19.26`，`cluster_uuid` 一致且 BM25 与 kNN 命中原始文档 | **PASS** |

---

## 2. 数据保真与重启保留核验

- **外部真实交付 API 重启保真 (`test_own_api_restart_preserves_real_index`)**：通过 `infra/start-backend1.ps1` 与 `infra/stop-backend.ps1` 对真实 ES 8.19.23 挂载的独立 8002 API 执行停止与二次拉起，重启前后 `/api/stats`（`status="real"`, `indexed=859`）与 `/api/papers/{id}` 读写响应完全一致。
- **只读与破坏防护**：本地全量夹具运行工具 `v6_vector_fixture.py` 验证运行前后源数据目录 SHA/mtime 签名 `source_unchanged=true` 且测试结束 `ports_closed=true`。
- **Compose 就绪探针联动**：空索引或缺失 `_meta` 元数据时 `/readyz` 严格返回 HTTP `503 unavailable`；导入合法 `_meta` 索引后切换为 HTTP `200 {"status": "ready"}`。
