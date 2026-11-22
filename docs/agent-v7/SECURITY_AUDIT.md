# 依赖、工具权限与隔离

## 托管构建镜像复扫

2026-11-22，GitHub Actions 在 Ubuntu 上重新构建完整应用镜像，导出后计算配置 SHA-256，与 Grype 报告中的镜像 ID 一致。此次扫描共 247 条包与公告匹配，其中 Critical 0、High 80、Medium 95、Low 21、Negligible 51。上一版完整镜像为 96 条 High、27 个不同的 High 公告，本次为 80 条、24 个公告。libc6 和 libc-bin 均为 `2.41-12+deb13u5`。扫描器将剩余 High 中的 59 条列为 `wont-fix`，21 条列为 `not-fixed`。正式发布仍需评估这些包在服务中的使用及影响。[完整镜像扫描摘要](hosted-image-scan.json) · [运行与原始产物](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44983031422)

## Debian 13 修订核对

对照历史应用镜像和 Grype 报告的 SHA-256 后，按源包查询全部 27 个公告。2026-11-22 的 Debian 跟踪记录中，96 条 High 匹配有 88 条的已安装修订被发行版明确列为受影响。这些匹配包括 util-linux 40 条、OpenSSL 29 条、GCC 8 条、ncurses 4 条、SQLite 3 条、Perl 2 条和 ACL 2 条。另 8 条缺少对应的精确版本记录。复核命令为 `python -m tools.research_eval.v7_image_advisories <原始扫描 JSON> --output <新文件>`。[逐项发行版记录](image-triage.json)

glibc 的两个公告已有修订，分别涉及 libc6 和 libc-bin。构建时将两者升至至少 `2.41-12+deb13u5`，同时检查 gzip 的发行版修订。使用官方 Python 3.11 Trixie 的 amd64 文件系统、Debian 签名索引和独立挂载空间实际运行构建中的 APT 命令。glibc 从 deb13u4 升至 deb13u5，gzip 符合最低修订。全部三个版本检查通过，Python 在新 libc 上成功加载 TLS、查询 SQLite 并往返压缩数据，gzip 命令行回读通过。这次基础镜像试验验证了修订可以安装，完整应用的复扫结果见上节。[基础系统实测](debian-base-check.json) · [Debian glibc 公告一](https://security-tracker.debian.org/tracker/CVE-2026-19499) · [Debian glibc 公告二](https://security-tracker.debian.org/tracker/CVE-2026-5435)

扩展 Python 审计至可选 PDF 解析栈后，在 pdfminer.six 20250506 查到 PYSEC-2026-1761 与 PYSEC-2026-1762。已升级 pdfplumber 至 0.11.11、pdfminer.six 至 20260107，锁定其余依赖，用同一 PDF 和原回归复验。pip-audit 2.9.0 对最终 78 个锁定版本报告 0 个已知漏洞。前端 npm audit 报告 0 个已知漏洞。两个锁文件的软件物料清单可供复核。[Python SBOM](python.cdx.json) · [前端 SBOM](frontend.cdx.json)

服务端工具注册表验证输入、只读权限、超时和输出格式。超过 128000 UTF-8 字节的输出按既有契约拒绝，非法结构单独报错。全量测试曾发现尺寸校验被结构错误遮蔽，已在 `2befe4e` 调整顺序，原测试保留。真实浏览器中用另一个临时账号读取已存在的研究报告得到 404。敏感内容检查使用 Gitleaks 8.30.1，扫描开发分支相对 zjl 的新增提交，原始报告留在本地。

应用容器实测以 UID 10001 运行，根文件系统只读。Compose 使用宿主机回环映射、独立卷和内部搜索服务。Grype 0.122.1 使用 2026-11-21 的数据库扫描 Linux/amd64 应用镜像。Bookworm 版报告 419 条包与公告匹配，其中 Critical 4、High 106。换用 Trixie 并更新 OpenSSL 和 Python 打包工具后共 283 条，其中 Critical 0、High 96、Medium 105、Low 24、Negligible 58。机器记录按包、公告、命名空间和修复状态列出全部 High。其在本服务中的可达性及生产影响需逐项复核。扫描对象仅覆盖应用镜像。生产权限和真实模型安全评估仍待验收。[三版扫描结果](container-acceptance.json)
