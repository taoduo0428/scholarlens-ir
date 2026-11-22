# 单一模型供应方的回环代理

在需要本地 HTTP 代理访问模型服务的环境，运维可同时配置以下两个进程变量。每个进程只承认一个模型基址。

| 变量 | 格式示例 |
| --- | --- |
| SCHOLARLENS_TRUSTED_AI_BASE_URL | https://provider.example/v1 |
| SCHOLARLENS_AI_LOOPBACK_PROXY | http://127.0.0.1:8080 |

基址使用实际供应方公开 HTTPS 域名、443 端口及 API 前缀。代理地址使用回环 IP 字面量和显式端口。匹配的 GET models、POST chat/completions 和 POST responses 请求通过该代理按域名 CONNECT。应用先核验本机 DNS 返回的所有地址均为公网单播地址，再验证供应方域名对应的 TLS 证书。代理负责 CONNECT 的目标解析，应由运维控制。其他公开供应方请求使用原有的 IP 固定直连路径。

负责人为服务运维。验收覆盖方法、精确路径和域名边界，两条路由共享传输尝试上限。撤销任一变量并重启应用即可恢复全部直连。
