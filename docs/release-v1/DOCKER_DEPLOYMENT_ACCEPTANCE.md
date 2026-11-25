# Docker 容器构建、Compose 部署、PDF OCR 升级与回滚验收报告

**验收日期**：2026-11-25  
**验证环境**：GitHub Actions `ubuntu-latest`（Run [`45566748805`](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45566748805)）  
**状态**：**PASS**（`Standard` 与 `PDF OCR` 构建、加固、Compose 升级、OCR 提取与回滚全链路实测通过）

---

## 1. 镜像构建产物与摘要

| 镜像目标 | 基准配置 ID (`scanned-image-id.txt`) | 打包加固检查（`--network none --read-only`） | Syft v1.57.2 SPDX SBOM |
| --- | --- | --- | --- |
| **`standard`** (`infra/ScholarLens.Dockerfile --target standard`) | `sha256:9cd9012322594f297ecd8f7c989281625d861d30661f4eb36733c1d8456a40d4` | `os.getuid() == 10001`、`pytest`/`ruff` 已从运行镜裁剪、SQLite/SSL/gzip/chart_registry 正常、OpenAPI `/api/research/tasks` & `/api/evolution-lab/governance` 路由存在 | `sbom-standard.spdx.json` (`3,097,584` B) |
| **`pdf-ocr`** (`infra/ScholarLens.Dockerfile --target pdf-ocr`) | `sha256:19d820b959efe4549443ea19e04c663b13d6ebfbaea1da4be3ac548d77bb61f3` | 同上加固 + `ldd /opt/scholarlens-ocr/bin/tesseract` 验证零缺失依赖且无多余 `curl`/`tiff`/`xml2`/`archive` 链接 + `python -m backend.research.ocr_check` 通过 | `sbom-pdf-ocr.spdx.json` (`3,126,670` B) |
| **`elasticsearch:8.19.26`** | `sha256:d71769f4e1145dca3794a04ddcd67e12f1299048b3232025e55feda799904a5d` | Compose 健康检查、单节点、只暴露内部 Docker 网络，不开放宿主机公网端口 | 与 `infra/product.compose.yml` digest 锁定一致 |

---

## 2. Standard Compose 验收（`Build and scan (standard)`）

执行栈：`infra/product.compose.yml`（`api` 只读根文件系统、`cap_drop: [ALL]`、`no-new-privileges:true`、命名卷 `research-data` 与 `search-data`）：
1. **Elasticsearch 跨版本卷保留**：先以 `elasticsearch:8.19.23` 启动并创建带 `dense_vector` 映射的 `scholarlens-fixture` 索引，记录 `cluster_uuid` 并写入测试论文；随后升级到 `8.19.26` 确认同一 `cluster_uuid` 且 BM25 + kNN 查询仍精准命中该文档。
2. **API 生命周期与重启持久性**：验证 `GET /readyz` 返回 `200 {"status": "ready"}`、`GET /` 返回构建前端页面、`GET /openapi.json` 包含 `/api/research/tasks`；通过 `/api/auth/register` 注册测试账户后强制重建 `api` 容器（`--force-recreate --no-deps`），确认重连后 `/api/auth/login` 与 `/readyz` 仍 200 通过。

---

## 3. PDF OCR Compose 升级、实测抽取与回滚验收（`Build and scan (pdf-ocr)`）

依据 CI 制品 [pdf-ocr-compose-receipt.json](../../output/release-v1/ci-final/application-image-findings-pdf-ocr/pdf-ocr-compose-receipt.json)，在同项目命名卷内完整实测 **Standard → PDF OCR → Standard** 三阶段热切换：

| 阶段 | 执行脚本与命令 | 实测结果摘要 | 状态 |
| --- | --- | --- | --- |
| **1. `standard_init`** | 以 `standard` 镜像启动 Compose，运行 `container_probe.py initialize` | 创建 2 个隔离账号与 1 个研究报告，保存一致性 SQLite 快照；`uid=10001`, `health=200`, `ready=200`, `frontend=200`, 跨账号越权返回 `404`, `report_restored=true`, `verified_claims=1` | **PASS** |
| **2. `pdf_ocr_upgrade`** | 叠加 `-f infra/pdf-ocr.compose.yml` 就地升级为 `pdf-ocr` 镜像并运行 `container_probe.py upgrade` | 升级后既有账户登录、原报告哈希、`404` 跨账号隔离与 SQLite 恢复校验全部 `PASS` | **PASS** |
| **3. 容器内实测 OCR 能力** | 容器内执行 `python -m backend.research.ocr_check` 并现场构造内嵌 RGB 图例光栅 PDF 调用 `backend.research.pdf_layout.page_evidence()` | `ocr_check` 通过；合成 PDF 精准触发 `"ocr": "figure_legend_labels"`，成功识别 `3` 条图例与精确文字 `["River", "Lake", "Forest"]` 及 PDF 坐标与 SHA-256 | **PASS** |
| **4. `standard_rollback`** | 移除 `pdf-ocr` overlay 回滚至 `standard` 镜像并运行 `container_probe.py rollback` | 回滚后卷内账户、报告哈希、越权隔离与 SQLite 恢复仍 100% 完好 (`uid=10001`, `verified_claims=1`) | **PASS** |

*注：Windows 本机未安装 Docker Desktop，以上全部容器构建、Compose 编排、升级、OCR 实测与回滚均在 GitHub Actions 官方 `ubuntu-latest` Linux Docker 宿主机真实运行并留存制品回执。*
