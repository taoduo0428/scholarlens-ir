# P2 本地真实检索实验

从固定的 859 篇旧批数据按 paper_id 加盐哈希排序，选出 100 篇标题和摘要完整的论文，向 MiniLM 输入标题与摘要。使用一组固定的 8 个历史查询、每路预热一次、串行 3 轮。ES 8.19.23 接收 100 条相同的 384 维向量。两个独立索引分别使用精确余弦扫描和 float HNSW，M=16，ef_construction=100，num_candidates=30。RRF(k=60) 融合两路前 20 名，TinyBERT 对融合前 10 篇成对打分。两种编码均使用 ONNX CPU 两线程。24 次每路径的原始排名、时间、索引和全部 paper_id 已保存。[原始报告](evidence/p2-experiment/retrieval.json)

| 路径 | P50 ms | P95 ms |
|---|---:|---:|
| BM25 | 4.54 | 5.33 |
| 精确 MiniLM | 7.57 | 9.53 |
| HNSW | 7.59 | 9.08 |
| BM25 + 精确 MiniLM + RRF | 12.28 | 14.74 |
| RRF + TinyBERT Cross-Encoder | 37.77 | 43.37 |

HNSW 相对精确 top 10 找回 237/240，平均 Recall@10 为 0.9875。三个未命中都来自同一查询的重复执行。重排改变了全部八个查询的结果顺序。人工 qrels 为 0，P@5 和 nDCG@10 为 null。范围限于本机 100 篇子集。测量包含各路径的查询嵌入、搜索和排名融合或重排，冷启动与离线导入另计。路径总耗时由同轮各必要步骤的墙钟相加，报告另存各步骤原始耗时。运行时 P0 回归可能在同机运行。

100 篇向量编码耗时 3.89 秒。精确索引占用 1,014,222 字节，HNSW 索引占用 1,017,795 字节。两者均含 2 个 segment。向量裸数据各 153,600 字节，ES 的 segment memory 计数返回 0。独立 HNSW 页缓存驻留量未测。

## 复现

### 子问题分解、重排与补检的分项对照

冻结开发集和独立 smoke 各 6 题，同一问题的六种方案共享 10 次工具、4 轮、10 条证据和 0 次模型 API 调用的上限。每次入选证据均经项目工具读回原文。实验使用真实本地 MiniLM 向量、RRF、TinyBERT 交叉编码器。在这个范围较小的对照中，检索器为项目本地 BM25 和精确余弦实现。每个任务最多指定两篇论文。延迟包含查询编码、搜索、重排及来源核验；文献向量在每个划分开始时预先计算一次。

| 配置 | dev 参考块 | dev 新增论文 / 块 | dev 工具数 | dev P95 ms | smoke 参考块 |
|---|---:|---:|---:|---:|---:|
| 单轮 keyword | 7/7 | 0 / 0 | 23 | 1.51 | 4/7 |
| 单轮 hybrid | 6/7 | 1 / 1 | 22 | 12.13 | 5/7 |
| 子问题 keyword | 5/7 | 0 / 1 | 26 | 2.58 | 4/7 |
| 子问题 hybrid | 5/7 | 0 / 1 | 26 | 23.44 | 5/7 |
| 子问题 hybrid + TinyBERT | 6/7 | 1 / 3 | 28 | 54.37 | 5/7 |
| 上述组合 + 缺口补检 | 6/7 | 3 / 5 | 38 | 75.24 | 5/7 |

新增量按题与单轮 keyword 的集合求差再求和。一篇论文在不同任务中可分别计数。dev 上 TinyBERT 多命中 1 个参考块，继续补检带来了更多可读的来源，目标块命中数维持 6/7。这里的分母取冻结任务的预置锚点。人工标注为 0，相关性和事实支持率均为 null。命令为 `python -m tools.research_eval.retrieval_ablation --output <新实验结果.json>`。[逐题来源增量、工具、重排及延迟](evidence/p2-experiment/retrieval-ablation.json)

在项目虚拟环境中使用仅绑定 loopback 的独立测试 ES。对从实例负责人取得的 UUID、集群名、版本执行核验后，程序新建两个带 UUID 的专用索引，保留结果供核查。选取新的本地 JSON 输出文件。

```powershell
python -m tools.research_eval.retrieval_experiment_ce --download backend/.runtime/evo-p2-tinybert
python -m tools.research_eval.retrieval_experiment --cluster-uuid <本地测试集群UUID> --papers 100 --repeats 3 --cross-encoder-dir backend/.runtime/evo-p2-tinybert --output <新报告.json>
python -m pytest backend/tests/research/test_retrieval_experiment.py -q
```

MiniLM revision 为 `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`，TinyBERT revision 为 `81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`。首次下载后者出现 httpx 读超时，带下载参数的固定发布 URL 成功，文件通过上游 LFS SHA-256 和 tokenizer Git blob 校验。首次 bulk 请求超时，allocation explain 显示 ES 的 90% 高水位使新主分片无法分配。实例负责人恢复本地测试分片分配后，重试使用全新索引通过。实验测试 6 passed，退出 0。[首次导入日志](evidence/p2-experiment/run.txt) · [成功运行](evidence/p2-experiment/run-final.txt) · [测试](evidence/p2-experiment/pytest.txt)
