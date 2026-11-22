# 研究治理与实验查看

研究后端维护者负责正式服务的只读管理接口。运维启用 `SCHOLARLENS_EVOLUTION_LAB=true`，在前端构建时启用 `VITE_EVOLUTION_LAB=true`。登录的管理员从深度研究工作台进入 Evolution Lab。

治理视图显示部署的技能与策略版本、程序发布登记、最近 20 条审批或回滚记录、允许的研究工具、模型协议和并发上限。运行时注册库取自服务启动配置 `SCHOLARLENS_APPROVED_REGISTRY`。版本批准和回滚由离线操作员执行。浏览器以只读方式访问已冻结的公开实验回放。实验库由 `SCHOLARLENS_LAB_DB` 指定，默认使用服务运行目录下的 `lab.sqlite3`。

服务逐次检查当前账号角色，对管理接口的响应设置私有缓存策略。运维日志记录固定操作名、请求方法、状态码以及可识别的账号编号。验收核对管理员可见性、匿名和普通账号访问、撤销管理员角色后的旧会话，以及读请求前后数据库内容的一致性。

管理员向 `GET /api/evolution-lab/governance` 提交已有会话。响应区分全局调优版本和 E11 发布时固定的技能、策略，展示工具登记名、模型协议和并发限制。程序版本需有匹配的发布收据和审批记录。回滚至内置基线后，该程序显示为“暂无”，历史仍可查看。注册库缺失或损坏时，版本视图返回 `unavailable`，其他部署信息仍可读取。实验回放单独读取，缺少实验库时返回 503。

## 2026-11-22 本地验收

在正式 `backend.app1.create_app` 入口运行了两个独立 Chrome 会话。Chrome 157.0.8103.79 通过账号页登录后回到实验室。管理员能从工作台进入治理页、展开 8 个工具登记名、查看包含 196 条运行记录的冻结实验库及同题对照。匿名请求返回 401，普通账号返回 403，管理员读取返回 200，向治理接口提交 POST 返回 405。

通过账号管理接口授予第二个账号管理员角色，再由该账号撤销原管理员角色。原管理员的已有会话立即收到 403，刷新后页面显示无权访问。新管理员刷新后可见治理面板。浏览器未记录页面异常，测试前后实验库 SHA-256 相同。所有账号、角色及服务端口均在临时回环环境中创建。

后端验收覆盖只读 OpenAPI 契约、缓存头、审计字段、离线发布回执和回滚，用独立临时注册库验证缺审批记录时的拒绝显示。治理接口与既有 Lab 测试合计 **6 项通过**。公网部署的网关和账号策略仍需线上验收。

在仓库根目录使用项目的研究依赖、Node.js Playwright 和 Chrome 复测。可用 `SCHOLARLENS_PLAYWRIGHT` 和 `SCHOLARLENS_CHROME` 指定已安装的模块和浏览器。

```powershell
python -m pytest -q backend/tests/research/test_governance_view.py backend/tests/research/test_workspace_lab.py
Push-Location frontend
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_API_BASE_URL = '/api'
$env:VITE_EVOLUTION_LAB = 'true'
$env:VITE_RESEARCH_ENABLED = 'true'
node node_modules/vite/bin/vite.js build --outDir ../output/v7/governance-browser-build
Pop-Location
python -m tools.research_eval.v7_governance_browser --dist output/v7/governance-browser-build --fixture-lab output/arena-final/lab.sqlite3
```

省略 `--fixture-lab` 时脚本创建空实验库，仍执行双账号角色变更和治理页面检查。
