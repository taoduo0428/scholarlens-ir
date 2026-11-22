# 依赖、工具权限与隔离

治理页使用当前账号角色鉴权。双会话验证中，匿名、普通账号、管理员分别获得 401、403、200，权限撤销后既有会话返回 403。发布库和冻结实验快照可只读挂入应用容器。任务导出按所有者和文件哈希验证内容。停用账号的离线删除会核对其他使用者、相关上传与在途任务。[治理验证](GOVERNANCE_VIEW.md) · [账号数据范围](ACCOUNT_ERASURE.md)

标准镜像和英文 OCR 镜像由 CI 分别构建、运行并扫描，同一镜像保存 Grype 原始匹配和与之核对过的镜像 ID。两个扫描结果分别保存在对应 GitHub Actions 运行的 `application-image-findings-standard` 和 `application-image-findings-pdf-ocr` 产物中。下文的 80 条 High 来自上一版标准镜像。

本批首次 Linux 实构中，标准镜像的 Critical 为 0、High 为 79，发行包版 OCR 为 10、161。10 条 Critical 来自 libcurl 的 8 条以及 libtiff、libxml2 各 1 条。工作台只向 OCR 传入本地 PNG。后续构建从 Debian 签名源取得 Leptonica 和 Tesseract，分别登记源码包及版本，仅启用所需解码路径，并在最终镜像检查运行时链接、英文识别和实际软件包清单。[首次构建与原始扫描](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45009622218)

2026-11-22，接入 OTLP 后，用 pip-audit 2.9.0 核对了后端、研究与 PDF 栈的 82 个锁定版本，审计报告的已知漏洞为 0。CycloneDX 清单逐项核对了 82 个包名和版本。基础镜像的系统包由 Grype 单独扫描。[Python 软件物料清单](python.cdx.json)

## PNG 专用 OCR 镜像复扫

2026-11-22，在 GitHub Actions 的两个 Linux/amd64 构建中，逐份核对了四份 Grype 原始报告的 SHA-256、镜像 ID 和严重度计数。发行包 OCR 的 10 条 Critical 分别匹配 libcurl4t64（8）、libtiff6（1）和 libxml2（1）。改用 Debian 源码包 leptonlib 1.84.1-4 和 tesseract 5.5.0-1，禁用 curl、archive 和 TIFF 支持。托管构建核对运行时包清单，并用本地 PNG 实测英文 TSV 输出。[首次构建](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45009622218) · [PNG 构建和扫描](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45010414520)

|镜像|发行包方案 Critical / High|PNG 专用方案 Critical / High|
|---|---:|---:|
|标准应用|0 / 79|0 / 79|
|英文 OCR|10 / 161|0 / 84|

计数单位为包与公告的匹配。标准镜像剩余的 79 条 High 和 OCR 镜像的 84 条 High 仍需结合服务用法复核。[逐镜像摘要及报告哈希](ocr-image-acceptance.json)

## 历史标准镜像复扫

2026-11-22，GitHub Actions 在 Ubuntu 上重新构建完整应用镜像，导出后计算配置 SHA-256，与 Grype 报告中的镜像 ID 一致。此次扫描共 247 条包与公告匹配，其中 Critical 0、High 80、Medium 95、Low 21、Negligible 51。上一版完整镜像为 96 条 High、27 个不同的 High 公告，本次为 80 条、24 个公告。libc6 和 libc-bin 均为 `2.41-12+deb13u5`。扫描器将剩余 High 中的 59 条列为 `wont-fix`，21 条列为 `not-fixed`。正式发布仍需评估这些包在服务中的使用及影响。[完整镜像扫描摘要](hosted-image-scan.json) · [运行与原始产物](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44983031422)

## Debian 13 修订核对

对照历史应用镜像和 Grype 报告的 SHA-256 后，按源包查询全部 27 个公告。2026-11-22 的 Debian 跟踪记录中，96 条 High 匹配有 88 条的已安装修订被发行版明确列为受影响。这些匹配包括 util-linux 40 条、OpenSSL 29 条、GCC 8 条、ncurses 4 条、SQLite 3 条、Perl 2 条和 ACL 2 条。另 8 条缺少对应的精确版本记录。复核命令为 `python -m tools.research_eval.v7_image_advisories <原始扫描 JSON> --output <新文件>`。[逐项发行版记录](image-triage.json)

glibc 的两个公告已有修订，分别涉及 libc6 和 libc-bin。构建时将两者升至至少 `2.41-12+deb13u5`，同时检查 gzip 的发行版修订。使用官方 Python 3.11 Trixie 的 amd64 文件系统、Debian 签名索引和独立挂载空间实际运行构建中的 APT 命令。glibc 从 deb13u4 升至 deb13u5，gzip 符合最低修订。全部三个版本检查通过，Python 在新 libc 上成功加载 TLS、查询 SQLite 并往返压缩数据，gzip 命令行回读通过。这次基础镜像试验验证了修订可以安装，完整应用的复扫结果见上节。[基础系统实测](debian-base-check.json) · [Debian glibc 公告一](https://security-tracker.debian.org/tracker/CVE-2026-19499) · [Debian glibc 公告二](https://security-tracker.debian.org/tracker/CVE-2026-5435)

扩展 Python 审计至可选 PDF 解析栈后，在 pdfminer.six 20250506 查到 PYSEC-2026-1761 与 PYSEC-2026-1762。已升级 pdfplumber 至 0.11.11、pdfminer.six 至 20260107，锁定其余依赖，用同一 PDF 和原回归复验。pip-audit 2.9.0 对最终 78 个锁定版本报告 0 个已知漏洞。前端 npm audit 报告 0 个已知漏洞。两个锁文件的软件物料清单可供复核。[Python SBOM](python.cdx.json) · [前端 SBOM](frontend.cdx.json)

服务端工具注册表验证输入、只读权限、超时和输出格式。超过 128000 UTF-8 字节的输出按既有契约拒绝，非法结构单独报错。全量测试曾发现尺寸校验被结构错误遮蔽，已在 `2befe4e` 调整顺序，原测试保留。真实浏览器中用另一个临时账号读取已存在的研究报告得到 404。敏感内容检查使用 Gitleaks 8.30.1，扫描开发分支相对 zjl 的新增提交，原始报告留在本地。

应用容器实测以 UID 10001 运行，根文件系统只读。Compose 使用宿主机回环映射、独立卷和内部搜索服务。Grype 0.122.1 使用 2026-11-21 的数据库扫描 Linux/amd64 应用镜像。Bookworm 版报告 419 条包与公告匹配，其中 Critical 4、High 106。换用 Trixie 并更新 OpenSSL 和 Python 打包工具后共 283 条，其中 Critical 0、High 96、Medium 105、Low 24、Negligible 58。机器记录按包、公告、命名空间和修复状态列出全部 High。其在本服务中的可达性及生产影响需逐项复核。扫描对象仅覆盖应用镜像。生产权限和真实模型安全评估仍待验收。[三版扫描结果](container-acceptance.json)
