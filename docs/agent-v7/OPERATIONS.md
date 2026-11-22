# 单 worker 环境的安装、备份与回滚

本轮本地验收使用 Python 3.11、Node 24、Elasticsearch 8.19.23 和 SQLite。API、账号和研究队列共享一个运行目录。搜索需要已有数据的索引别名，语义检索还需要匹配的向量模型和向量索引。

## 在隔离环境准备服务

从仓库根目录运行以下命令。创建全新的卷时先恢复经授权的 Elasticsearch 快照或按数据交付说明导入索引，并把 `SCHOLARLENS_INDEX` 指向已验收别名。空索引会让就绪探针返回 503。研究 UI 使用同源 API，请在构建时启用研究入口。

```sh
docker compose -f infra/product.compose.yml config -q
docker compose -f infra/product.compose.yml build api
docker compose -f infra/product.compose.yml up -d search
# 恢复索引后启动 API
SCHOLARLENS_E11_ENABLED=true docker compose -f infra/product.compose.yml up -d api
curl -fsS http://127.0.0.1:18001/healthz
curl -fsS http://127.0.0.1:18001/readyz
```

Compose 使用命名卷保存应用数据和 Elasticsearch，主机映射默认仅回环可访问。使用真实模型时从部署环境的秘密存储注入项目凭证并设预算。生产运维记录应保存应用镜像摘要、ES 快照名称及数据库备份校验和。

需要识别英文彩色图例时，运维可在构建和启动命令中同时指定 `-f infra/product.compose.yml -f infra/pdf-ocr.compose.yml`。OCR 镜像包含 Tesseract、英文语言包以及图例识别用的程序路径。首次安装可在该镜像中运行 `python -m backend.research.ocr_check`，从生成的三行彩色图例核对输出。服务仍以应用账号运行。运维负责保管所用镜像的摘要与扫描记录。

管理员需要查看已批准版本和冻结的实验记录时，设置主机目录 `SCHOLARLENS_APPROVALS_DIR` 和 `SCHOLARLENS_LAB_SNAPSHOT_DIR`，分别放入一致性快照 `approved.sqlite3` 和 `lab.sqlite3`。容器账号 10001 需有读取权限。加入 `-f infra/governance.compose.yml` 后，Compose 将两个目录只读挂载到 `/srv/approvals` 和 `/srv/experiments`，并在构建时启用管理页面。先以 `docker compose -f infra/product.compose.yml -f infra/governance.compose.yml config -q` 检查参数，再按当前环境的发布流程构建和部署。[审批与回滚说明](PROGRAM_RELEASE.md) · [治理页面验收](GOVERNANCE_VIEW.md)

## 同一主机上的模型并发

Compose 已将 `SCHOLARLENS_MODEL_CAPACITY_DIR` 设为应用数据卷中的 `/var/lib/scholarlens/model-capacity`。同机的其他研究执行进程可将该变量指向同一个绝对目录。该本地文件系统须支持操作系统文件锁，并允许服务账号读写。共享进程合计最多同时调用模型四次，每个模型主机两次。能力接口的 `capacity_scope` 显示 `local_volume`。直接启动且使用默认配置的进程显示 `process`。

运行目录固定使用四个名额，按带随机密钥的摘要匹配主机，正常退出调用时清空主机标记。异常退出进程的锁由操作系统释放，下一次使用名额时会覆盖旧标记。目录不可用时，研究网关返回 `provider_rate_limited`。已测本机 Windows 和 Linux 的进程终止恢复。

## 按任务查运行追踪

需要导出时，在 Compose 环境设置 `SCHOLARLENS_OTEL_ENABLED=true` 和 `SCHOLARLENS_OTLP_TRACES_ENDPOINT=https://collector.example.org/v1/traces`。把示例地址替换为运维管理的 OTLP/HTTP protobuf 接收端。明文 HTTP 仅支持回环 IP，容器内的回环地址指向容器自身。远端 TLS 证书须受系统信任，认证可由同一网络命名空间的本地代理处理。仅启用追踪且留空地址时，继续使用进程已有的 OpenTelemetry Provider。

登录后打开工作台的“任务追踪”，或读取任务详情的 `trace_ids`，用该 ID 到接收端查 API 提交、Worker 和工作流。未采样时列表可以为空。应用以最多 64 条 span 为一批，每 2 秒发送，队列最多暂存 256 条。正常停机会先等待 Worker 完成，再排空队列。接收端离线、拒收或队列满时可能缺少记录，运维可检查应用的 `Research trace export failed` 日志及接收端状态。任务库中的 trace ID 表示已采样，交付以接收端查到的记录为准。

应用 span 记录阶段名、结果和出错类别。保护部署环境的导出程序和收集器访问权限。首次升级前用现有 ResearchStore 备份流程保存数据库，升级会增加可按任务删除的关联表。

## 在临时卷演练升级和回退

在空的独立 Compose 项目中运行以下命令。先用对应 Git 提交的 Dockerfile 构建两个镜像，将其标签或摘要分别填入 `PREVIOUS` 和 `CANDIDATE`。在同一个 shell 中执行，三个阶段复用同一项目名和命名卷。

```sh
export COMPOSE_PROJECT_NAME="scholarlens-check-$(date +%s)"
export COMPOSE_FILE=infra/product.compose.yml
export SCHOLARLENS_INDEX=scholarlens-fixture SCHOLARLENS_PORT=0 SCHOLARLENS_E11_ENABLED=true
export SCHOLARLENS_IMAGE="$PREVIOUS"
docker compose up --wait --no-build
docker compose exec -T api python - initialize < tools/research_eval/container_probe.py
export SCHOLARLENS_IMAGE="$CANDIDATE"
docker compose up --wait --no-build
docker compose exec -T api python - upgrade < tools/research_eval/container_probe.py
export SCHOLARLENS_IMAGE="$PREVIOUS"
docker compose up --wait --no-build
docker compose exec -T api python - rollback < tools/research_eval/container_probe.py
```

初始化时，脚本检查空索引返回 503，随后写入一篇合成论文，创建两个测试账号和一份研究报告。每次切换后复核账号登录、报告内容、跨账号隔离和 SQLite 快照恢复。演练结束后，在同一个测试 shell 中运行 `docker compose down --volumes` 清理本次测试项目。

## 恢复演练

研究数据库支持 SQLite 一致性备份。以维护账号操作，先将运行目录和备份目录设置为仅维护者可访问。恢复时选一个新的空目录，程序遇到同名数据库会拒绝覆盖。

```python
from pathlib import Path
from backend.research.store import ResearchStore

live = Path("/var/lib/scholarlens")
snapshot = Path("/backups/research-20261122.sqlite3")
if not (live / "research.sqlite3").is_file():
    raise FileNotFoundError("请选择已有研究运行目录")
ResearchStore(live).backup(snapshot)
restored = ResearchStore.restore(snapshot, Path("/restore/rehearsal-20261122"))
```

研究快照覆盖任务、事件与报告。整站备份还要在维护窗口停止应用写入，保存账号数据库、上传文件和其他应用卷，另建 Elasticsearch 快照，并单独保存加密环境配置。回滚应用时使用上一镜像和与其 schema 兼容的数据快照。在独立目录恢复后，以两个测试用户核对报告哈希、权限、论文数和向量数，再切换入口。保留原卷直到恢复验收通过。
