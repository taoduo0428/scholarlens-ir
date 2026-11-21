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

Compose 使用命名卷保存应用数据和 Elasticsearch，主机映射默认仅回环可访问。使用真实模型时从部署环境的秘密存储注入项目凭证并设预算。生产运维记录应保存应用镜像摘要、ES 快照名称及数据库备份校验和。本次已静态解析 Compose，并在本机 API 上实测探针。容器命令仍待有 Docker 的环境验收。

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
