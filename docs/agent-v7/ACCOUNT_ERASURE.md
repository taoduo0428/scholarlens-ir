# 停用账号的离线删除

维护者在停止应用及上传、研究 Worker 后，使用明确的运行目录和数字账号 ID 预览影响。预览输出各类记录数和本次选择的摘要。以该摘要确认后，工具重新核对账号仍已停用、研究任务均已结束、当前数据和预览一致，再清理私有数据。现有网页停用流程仍可恢复，永久删除由离线操作员执行。

验收覆盖账号资料、会话、收藏、工作区、浏览和查询历史、通知、对话、本人验证码、头像、研究状态与图检查点，核对第二个账号及共享论文引用。存在上传、参与审核、未知表、关联不明、最后管理员或运行中任务时，工具报告阻塞原因，保留原始记录。备份、外部日志、搜索服务及客户端保存的副本由各自的保留策略管理。

## 维护命令

在离线运行目录完成一致性备份，核对待处理账号 ID。以下命令从仓库根目录运行，`RUNTIME`、`OWNER_ID` 与 `PREVIEW_SHA256` 分别替换为实际值。

```text
python -m tools.account_erasure --runtime RUNTIME --owner OWNER_ID
python -m tools.account_erasure --runtime RUNTIME --owner OWNER_ID --confirm PREVIEW_SHA256
```

第一条返回 `applied: false`、逐表数量以及摘要。摘要绑定运行目录、账号和本批记录内容。第二条在研究 Worker 文件锁及数据库写事务内重新生成摘要。条件变化时报错，退出码为 2。成功时输出 `applied: true`，退出码为 0。工具只输出数字 ID 和数量，账号内容不进入日志。

有上传记录的账号可能关联原始 PDF、解析文件和 Elasticsearch 索引。遇到 `upload_files_and_index_require_review` 时，需要核对这些资产及其保留策略。曾审核他人上传会得到 `shared_upload_review`。这两种情况都在清理前返回。对于同一邮箱上没有账号归属的验证码、无法确定归属的头像或研究检查点，也需核实后再预览。

工具先提交图检查点库，再提交研究库，最后提交账号库。任一步写入失败时，以当前运行目录重新预览、复核余项并重新确认。注册接口使用仅保存一个最大已删除 ID 的计数表，新用户取得新的数字 ID。恢复服务时应使用带此分配逻辑的版本。删除范围为在线应用的逻辑记录及该账号的头像，历史备份和离线导出另行管理。

## 隔离回归

```text
python -m pytest -q backend/tests/research/test_account_erasure.py backend/tests/research/test_task_lifecycle.py backend/tests/test_admin_boundaries_isolated.py backend/tests/test_account_credentials_isolated.py
```

测试在临时目录注册两个账号，使用 SQLite 账号库、正式研究存储及 LangGraph 检查点表。覆盖摘要变化、文件锁、同一用户名重新注册、两人收藏同一论文、终态任务的旧模型调用记录，以及在账号库提交时注入故障后的重新预览和恢复。
