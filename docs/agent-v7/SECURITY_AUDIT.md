# 依赖、工具权限与隔离

扩展 Python 审计至可选 PDF 解析栈后，在 pdfminer.six 20250506 查到 PYSEC-2026-1761 与 PYSEC-2026-1762。已升级 pdfplumber 至 0.11.11、pdfminer.six 至 20260107，锁定其余依赖，用同一 PDF 和原回归复验。pip-audit 2.9.0 对最终 78 个锁定版本报告 0 个已知漏洞。前端 npm audit 报告 0 个已知漏洞。两个锁文件的软件物料清单可供复核。[Python SBOM](python.cdx.json) · [前端 SBOM](frontend.cdx.json)

服务端工具注册表验证输入、只读权限、超时和输出格式。超过 128000 UTF-8 字节的输出按既有契约拒绝，非法结构单独报错。全量测试曾发现尺寸校验被结构错误遮蔽，已在 `2befe4e` 调整顺序，原测试保留。真实浏览器中用另一个临时账号读取已存在的研究报告得到 404。敏感内容检查使用 Gitleaks 8.30.1，扫描开发分支相对 zjl 的新增提交，原始报告留在本地。

应用容器实测以 UID 10001 运行，根文件系统只读。Compose 使用宿主机回环映射、独立卷和内部搜索服务。Grype 0.122.1 使用 2026-11-21 的数据库扫描 Linux/amd64 应用镜像。Bookworm 版报告 419 条包与公告匹配，其中 Critical 4、High 106。换用 Trixie 并更新 OpenSSL 和 Python 打包工具后共 283 条，其中 Critical 0、High 96、Medium 105、Low 24、Negligible 58。机器记录按包、公告、命名空间和修复状态列出全部 High。其在本服务中的可达性及生产影响需逐项复核。扫描对象仅覆盖应用镜像。生产权限和真实模型安全评估仍待验收。[三版扫描结果](container-acceptance.json)
