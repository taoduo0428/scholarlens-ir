# 安全审计

审查范围包括账号权限、上传与研究任务所有权、个人 Provider 配置、应用与搜索服务网络边界、密钥和运行文件的交付范围。覆盖依据为 FastAPI 路由和 SQLite 所有权检查、Provider 传输层、Compose 与 Docker 构建上下文、现有隔离回归。部署环境中的身份、密钥库、遥测接收端和公网配置需要各自的验收。

| 边界 | 源码依据与处置 |
|---|---|
| 账号和管理员 | `backend/accounts.py` 与 `backend/app1.py` 的角色检查和上传归属检查。相关回归在隔离账号与临时 SQLite 上执行。 |
| 研究任务 | `backend/research/api.py` 和 `backend/research/store.py` 校验任务所有者及产物；后台工作进程使用任务的用户与来源上下文。 |
| Provider 与密钥 | `backend/personal_ai.py` 在已认证请求内处理凭证，由传输层约束目标。凭证、真实用户库和 PDF 排除于容器构建上下文。Provider 实网验收状态为 BLOCKED。 |
| 运行隔离 | API 容器 UID 10001、只读根、清空 Linux capabilities、禁止提权。Compose 的 ES 无宿主机端口且默认关闭 ES 认证，整个 Docker 主机及其网络成员必须可信。原 PDF 是外部输入，OCR 使用专用 PNG 路径。 |
| 供应链 | 软件锁与 Grype 扫描保留独立证据。CI 用实际导出配置的哈希绑定扫描对象。High 必须通过可达性及上游修订复核后才能放行。 |

## 镜像剩余风险

在交付分支修改生产依赖前，标准与 OCR 镜像扫描分别为 0 Critical / 79 High、0 Critical / 84 High。匹配以包与公告对计数。标准镜像 24 条 High 标为 not-fixed，55 条标为 wont-fix。OCR 镜像相应为 24 和 60。扫描记录未给出 High 的可用修复版本，标签仅代表扫描数据库。以本次构建产物及上游发行版记录判断可用补丁。[审计作业](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45343814183)

- OpenSSL、SQLite 和 libc 属于服务实际依赖，分别涉及外部 TLS、持久数据与进程运行。现有隔离措施仍保留残余风险。
- util-linux、登录工具、终端库、Perl 和 GCC 运行库按各自包的链接或执行路径评估。未逐条建立可达性，继续列为发布风险。
- OCR 额外 5 条 High 指向 Tesseract 打包项。PNG 输入和低权限运行约束了输入及权限范围，风险状态仍待逐条确认。
- 裁剪测试工具后重建，标准与 OCR 镜像分别有 23 和 28 个不同的 High 公告，包与公告匹配数仍为 79 和 84，Critical 均为 0。原始报告与镜像配置 SHA-256 绑定。更换基础镜像与修补业务依赖需要针对性兼容验证。[复扫与对应产物](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45345079394)

[扫描摘要与 SHA-256](image-scan-summary.json)

裁剪后的 OCR 镜像包含标准镜像的 79 条 High，再加 5 条 OCR 条目。按源包和已安装版本查询 Debian 13 安全跟踪器，84 条匹配均查到受影响记录，未查到对应 Trixie 渠道的修复版本。[逐条匹配及版本记录](image-advisory-review.json)

Compose 固定的 Elasticsearch 8.19.23 镜像经独立配置哈希绑定扫描，结果为 0 Critical、16 High。其中 JDK 6 条、Java 包 7 条、系统包 3 条，扫描器均列出了组件修复版本。现有 Compose 将搜索留在内部网络。JDK 和 Java 包随搜索进程运行，发布前需获得包含补丁的受支持 Elastic 镜像，并验证索引恢复、搜索和向量路径。[ES 扫描清单](elasticsearch-scan-summary.json) · [CI](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45347880238)

安全闭环为 BLOCKED。当前证据不足以完成残余 High 的逐条接受。
