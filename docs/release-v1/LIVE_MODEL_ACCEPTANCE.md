# 真实模型与受控模型工程验收报告

**验收日期**：2026-11-25  
**默认策略约束**：在线生产默认值保持 **`SCHOLARLENS_PRA_ARM=A`**（V9 `R` 保留为显式可选实验配置，未设为默认）。  
**本轮凭证状态**：当前运行环境变量 `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY` 未配置（并已在 2026-11-25 最终发布检查中再次核对 `.env`、`backend/.env`、`infra/.env` 均不存在），按规则不请求用户提供临时密钥、不写死任何历史凭证、不产生未授权付费调用，因此 **本轮实网复测状态保留为 `BLOCKED`**；受控 HTTP 与模型网关工程回归均 **实测 `PASS`**，同时引用 V9 已归档并经过服务端回读核验的 `deepseek-v4.1-flash` 实网 9/9 通过记录。

---

## 1. 受控 HTTP 端到端与模型网关工程验证（本轮实测 PASS）

执行命令（工作目录 `C:\work\scholarlens-final-release`）：
```powershell
.\.venv\Scripts\python.exe -m tools.research_eval.v7_live_research --controlled --output output/release-v1/model-engineering/controlled-http.json
```

实测结果摘要（完整 JSON 见 `output/release-v1/model-engineering/controlled-http.json`）：
- **运行模式**：`controlled_http`（4 次限流受控 HTTP 调用：`planning` / `decision` / `analysis` / `synthesis`，单次请求体上限 48,000 B，单次输出上限 1,400 tokens）
- **通过门禁**：**9/9 PASS**（`worker`, `planning`, `decision`, `retrieval`, `semantic_review`, `synthesis`, `publication`, `no_fallback`, `provider_receipts` 全部 `true`）
- **产物指标**：`workflow_state: "partial"`（2 篇 pinned arXiv 摘要因缺少跨论文可比较数值指标，系统诚实标出 `missing_fields: 1`，未编造对比数据），`two_paper_relations: 1`，`source_checked_model_fields: 1`，`provider_receipts: 4`。

模型工程安全与边界能力验证（全部随全量后端测试套件 1,028/1,028 通过）：
1. **Provider Config 与密钥注入边界（`backend/personal_ai.py`, `test_personal_ai.py`）**：个人配置仅在已登录请求头 `X-ScholarLens-AI-*` 中传递，严禁回显到日志、数据库或响应体；强制要求合法公共 HTTPS（443 端口），禁止明文 URL、内嵌认证信息或非 ASCII/控制字符；服务端通过 `PublicAITransport` 在拨号阶段解析 DNS 并拦截环回、内网、保留 IP 段（防止 SSRF / DNS Rebinding）。
2. **受信任代理边界（`test_trusted_model_proxy.py`）**：仅允许匹配 `SCHOLARLENS_TRUSTED_AI_BASE_URL` 与回环 `SCHOLARLENS_AI_LOOPBACK_PROXY` 精确前缀与路由的请求走回环 CONNECT 代理，其余外网路由剥离 `Proxy-Authorization` 并校验 TLS SNI 主机名。
3. **速率与并发控制（`backend/research/model_gateway.py`, `test_shared_capacity.py`）**：支持进程内与基于本地持久化卷文件锁（`SCHOLARLENS_MODEL_CAPACITY_DIR`）的多进程并发配额控制（默认全局并发 `4`、单模型主机并发 `2`），进程崩溃由内核自动回收文件锁，超限返回 `provider_rate_limited`。
4. **超时、非重试与自动降级（`backend/research/provider_adapter.py`, `test_budget_enforcement.py`）**：单阶段超时上限 20s，响应体硬上限 65,536 B，上游返回 429/非 200/超时/截断或模型响应泄露 `ai_api_key` 时立即中止并将该阶段降级为本地证据流水线（`automatic_provider_retries: 0`）。
5. **结构化输出校验与用量记账（`backend/ai_responses.py`, `backend/research/accounting.py`, `test_ai_responses.py`）**：严格剥离 Markdown 代码围栏后用 Pydantic `TypeAdapter` 校验 JSON Schema，拒绝未知字段与超深嵌套；`accounting.py` 区分真实回执 Token（`input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`）与未知用量（绝不将未报告用量的调用伪造为 0 成本）。

---

## 2. 本轮实网大模型复测状态（BLOCKED）与历史实网依据

| 验收模式 | 目标 | 本轮状态 | 说明与依据 |
| --- | --- | --- | --- |
| `--controlled` 受控 HTTP | 端到端四阶段决策与产物核验 | **PASS (9/9)** | 本轮实测完成，4 次回执 HTTP 200，0 warnings |
| 模型工程隔离单元测试 | 代理/SSRF/配额/超限/JSON/脱敏 | **PASS** | 覆盖 `test_trusted_model_proxy.py`, `test_personal_ai.py`, `test_ai_responses.py`, `test_budget_enforcement.py`, `test_shared_capacity.py`, `test_live_research_acceptance.py` |
| `--live --call-budget-only` 本轮实网复测 | 外部模型真实联网端到端 | **BLOCKED** | 缺少进程环境变量 `AI_BASE_URL`、`AI_MODEL`、`AI_API_KEY`（未在代码中保留或申请任何密钥） |
| **V9 历史实网验收基准（可追溯参考）** | `deepseek-v4.1-flash` 实网四臂对照 | **PASS (V9 H5/R: 9/9)** | 见 [docs/agent-v9/LIVE_MODEL_ACCEPTANCE.md](../agent-v9/LIVE_MODEL_ACCEPTANCE.md)：4/4 HTTP 200 回执，输入 7,109 tokens，服务端回读核验 5 个 `model_and_source_check` 档案字段，0 warnings |

### 复测解除 BLOCKED 所需环境变量与标准命令

部署验收负责人配置合法项目测试凭证后，可执行以下命令直接复验实网闭环（严格限制预算在 4 次调用以内）：

```powershell
$env:AI_BASE_URL = "https://<provider-endpoint>/v1"
$env:AI_MODEL = "<model-id>"
$env:AI_API_KEY = "<secret-key>"
$env:E10_MAX_USD = "0.20"
$env:E10_MAX_RATE_USD_PER_MTOK = "2.00"
python -m tools.research_eval.v7_live_research --live --output output/release-v1/model-live-retest.json
```
*(执行完毕后请立即清理终端内的 `AI_API_KEY` 环境变量，严禁将其写入仓库文件或 CI 日志。)*
