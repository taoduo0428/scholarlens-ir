# P2 受控检索工具

`backend/research/tools/` 提供 `LocalCorpus`、`EsCorpus` 和 `ToolRegistry`。调用者先以已认证账户、新任务 scope 和固定 generation 建立 registry，再调用 `call(name, payload)`。检索参数、返回体大小和工具白名单由服务端校验。

| 工具 | 输入 | 输出 |
|---|---|---|
| search_papers | query、strategy、paper_ids、year_from / year_to、limit | 去重论文元数据，含全文状态和 PDF 可用状态 |
| search_passages | 同上，可加 slot | 原文、稳定 chunk_id、locator、SHA-256、来源与匹配的章节 |
| read_paper_metadata | paper_id | 有界元数据 |
| read_paper_chunks | paper_id、chunk_ids | 逐段从指定论文读回 |
| verify_source_quote | paper_id、chunk_id、locator、quote、source_hash、corpus_generation | verified、reason |
| extract_method_results | paper_id、query、slots | 按槽位返回原文候选段落，供后续 Claim Verifier 判断 |
| get_research_state | 空参数 | 当前账户、当前 generation 的运行摘要，由认证回调提供 |

ES 使用原 BM25 查询构造器、MiniLM 本地编码器、RRF 和原分块规则。主论文、上传和向量索引的具体版本在请求开始前解析。各索引分别读取，上传 ID 再与旧账户库中本人的 indexed 状态取交集。删除已固定的索引会触发 generation 错误。可注入 PDF 可用性回调；只有记录中的路径时返回 unknown。离线适配器支持标准 BM25、按段余弦聚合到论文、按排名融合和受约束的 Top-N 重排。外部 metadata 入口只消费许可证与域名符合配置的本地 fixture。

## 验收记录

2026-11-20，Windows、Python 3.11.15、ES 8.19.23。首轮综合用例 6 通过、1 失败。经复现，旧的本地论文 dense 候选使用标题和摘要，导致遗漏仅存在于全文的证据。改为按原始段落排名后再对论文去重。后续加入账户 ACL 撤回、更改纸张 PDF 状态的授权顺序与本地 ES 集成。独立验收最终 10 通过，耗时 1.48 秒。原始输出在 [evidence/p2-tools](evidence/p2-tools/)。

在本机只读调用 `scholarlens-papers-real-5a3d535543e4`，查询 `magnetic resonance imaging` 返回 5 篇，定向召回 3 段并逐一原文核验通过。该次论文发现、段落检索和三段回读分别为 616.1、34.2、12.2 毫秒，包含首次旧模块加载。单次测量适用于功能验收，统计性能和排序质量见独立检索实验。

```powershell
New-Item -ItemType Directory -Force -Path output/p2-test-temps | Out-Null
$env:EVO_TEST_LOOPBACK_ES='1'
$env:SCHOLARLENS_RUNTIME_DIR=(Join-Path (Get-Location).Path 'output/p2-live-runtime')
.venv/Scripts/python.exe -m pytest backend/tests/research/test_research_tools.py backend/tests/research/test_research_tools_loopback.py --basetemp=output/p2-test-temps/final-v2 --tb=short -s -q
.venv/Scripts/ruff.exe check backend/research/tools backend/tests/research/test_research_tools*.py
```

实测过的本地 ES 路径使用公开关键词索引。隔离测试覆盖 ES 语义检索索引选择、私有上传撤回、跨账户读回、索引切换、缺失 PDF、原文子区间及外部元数据限制。真实私有上传、付费模型及公网 API 均未纳入该专项。
