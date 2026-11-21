# P0 旧后端与执行清单

## 验收契约

负责人为本地后端维护者。使用固定的 11 项清单逐项执行 pytest。每项必须收集并执行至少一个断言测试，参数化测试所有实例均须通过。无法收集、跳过、失败和异常均应在汇总中标为未通过。对于指定论文范围中无检索证据的输入，旧 Agent 必须返回 `insufficient_evidence`、空引用和空回答，并且不调用生成器。未限定范围的一般问答可返回标明来源类型的通用回答。

本次只使用工作区内的临时测试账号、受控 provider 和本地搜索依赖。执行结果与依赖边界见下方记录。
旧检索响应使用精确字段白名单限制输出。对照当前接口实现和受控数据，命中文献应同时包含发布日期、机构数组和地址数组。

## 本地运行环境

基线提交为 3e130b0。使用 Python 3.11.15 和后端锁文件指定的 49 个依赖，运行时安装在工作树的 .venv。旧启动脚本另使用 backend/.venv，同样按后端锁安装。Elasticsearch 8.19.23 ZIP 已与 Elastic 发布的 SHA-512 核对，单节点监听本机 9200。固定版本 MiniLM 采用本地 ONNX CPU 推理，四个资产均经过 SHA-256 验证。[依赖与环境（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-a787440126c0) · [ES 身份（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-7aadb3dbe8ed)

旧语料来自 feat/pdf-parser 的两个 Git blob。既有预处理器对旧批 859 篇执行校验和乱码隔离后，导入新的本机 ES 并生成 49,420 个 384 维片段。准备数据时给出 XML 检查目录，以区分文件缺失和没有检查。向量检查点和索引数据留在忽略目录中。运行时的三个功能开关默认关闭。[导入回执（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-303546301655) · [向量构建（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-5307aba0d599)

## 命令和结果

以下命令在隔离工作树根目录执行。真实交付路径、pytest 临时目录和启动器由本机准备过程创建。旧测试在 127.0.0.1:9200 使用可写测试集群，8001 使用本次专属 API，8002 由单项测试短暂占用。两个 API 端口结束后释放。

| 操作 | 退出码 | 结果及原始记录 |
|---|---:|---|
| uv venv --python 3.11 .venv；uv pip install --python .venv/Scripts/python.exe -r backend/requirements-lock.txt | 0 | 49 个包安装成功 [安装记录（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-dd75a2bf8099) |
| python tools/agent/run_harness.py --python .venv/Scripts/python.exe --output .venv/p0-harness-before | 1 | 10/11 通过，证据不足用例指定的测试节点缺失 [失败节点（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-d2b1e745a391) |
| 修复后使用全新的 --output 运行同一旧 Harness | 0 | 11/11，15 个参数化 pytest 实例实际执行通过 [逐项结果（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-c73092995e65) |
| python -m pytest backend/tests/test_agent.py backend/tests/test_ai_responses.py backend/tests/test_agent_harness_reporting.py --basetemp .venv/p0-provider-local-temp -q -rs | 0 | 163 passed，用时 10.66 秒 [输出（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-641d4477a6a6) |
| python -m pytest backend/tests --ignore=backend/tests/research --real-data-dir backend/.runtime/p0-delivery --basetemp .venv/p0-full-final-temp -q -rs | 0 | 414 passed，5 skipped，用时 210.45 秒；5 项有专用环境入口 [输出（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-f97c45cb1dd6) |
| python tools/audit/run-upload-integration.py | 0 | 另建本机 test ES/SQLite，正式 FastAPI 路由和 MiniLM，5 passed，26.38 秒。独立环境测试覆盖了主套件跳过的全部 5 项 [pytest（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-94524bbab09a) · [资源收尾（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-b5cde30a0216) |

## 复现问题和修复

1. 默认系统临时目录无法读取。指定工作树内独立 --basetemp 后可正常执行。旧 Harness 缺少 insufficient-evidence 节点，将现有 scoped 无来源测试恢复到登记名称，加入空引用、空证据和未接地回答断言。旧自然聊天保持原有结果类型。
2. 旧 Harness 对 pytest 的退出码 0 直接判绿。现在同时读 JUnit，要求实际执行的所有参数化实例均通过；新增 8 个判定用例，覆盖 XML 缺失、空集、失败、跳过和返回码错误。
3. 旧搜索接口的测试仍使用早期字段列表。逐项对照实际源码和原始 Mock 文献，更新允许字段并精确核对 date、affiliation、address 的值。试验没有扩大搜索端点返回的数据。
4. 第一轮真实集成受未建本地语料、主机磁盘水位和缺少固定向量等因素影响。新集群仅接收本任务数据。将其临时空闲空间保护低/高/只读水位设为 16/12/8 GB 后，索引分配恢复。设置前值保留在原始记录中。旧语料完整发布后，上传检索的依赖错误消失。[问题记录（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-e7a31835c977) · [水位变更（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-7ffd39c185dc)
5. 主套件通过真实 ES 索引读写、MiniLM、数据重建/回退、HTTP API 和本地账号。模型供应商交互用受控替身，真实收费生成未测。质量增益和覆盖所有真实文献的 PDF 可下载性未测。

## 升级完成后的旧后端复测

同一套 859 篇真实语料和独立 API 上，旧后端测试再次取得 414 项通过，耗时 183.34 秒。该套件跳过的 5 个上传集成组通过其独立入口全部复测通过，耗时 23.77 秒，覆盖 163 条路由断言。首次独立试验遇到高磁盘水位，测试 ES 的分片未能及时分配。复测时对新建的临时实例单独设置 16/12/8 GB 水位，完成后由测试程序关闭该实例及其端口。用于旧后端回归的 8001 服务也已停止。[旧后端 pytest（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-15fa945b2a15) · [上传首次试验（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-e70ef64126d7) · [上传复测 pytest（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-5a9213c2130f) · [临时实例收尾（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-df137d3139ef)
