import {useEffect, useState} from "react";
import {backend} from "../services/backend";

interface Governance {
  registry: {status: "builtin" | "configured" | "unavailable"; skill: string | null; policy: string | null;
    program: string | null; program_basis: {skill:string; policy:string} | null;
    history: {seq:number; kind:string; version:string; action:string}[]};
  tools: string[];
  model: {protocols:string[]; capacity_scope:string; global_concurrency:number; per_host_concurrency:number};
}

export function GovernancePanel() {
  const [data, setData] = useState<Governance | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const ctrl = new AbortController();
    backend<Governance>("/evolution-lab/governance", {signal:ctrl.signal})
      .then(value => {if (!ctrl.signal.aborted) setData(value);})
      .catch(cause => {if (!ctrl.signal.aborted) setError(cause instanceof Error ? cause.message : "读取失败");});
    return () => ctrl.abort();
  }, []);
  return <section className="research-panel"><h2>研究治理</h2>
    {error && <p role="alert">{error}</p>}
    {!error && !data && <p role="status">正在读取部署配置…</p>}
    {data && <>
      <h3>运行时版本</h3>
      {data.registry.status === "unavailable" ? <p>审批登记库暂不可用。</p> :
        <dl className="lab-metrics">
          <div><dt>默认技能</dt><dd>{data.registry.skill}</dd></div>
          <div><dt>默认策略</dt><dd>{data.registry.policy}</dd></div>
          <div><dt>已登记程序发布</dt><dd>{data.registry.program ?? "暂无"}</dd></div>
          {data.registry.program_basis && <div><dt>程序固定的技能和策略</dt>
            <dd>{data.registry.program_basis.skill} / {data.registry.program_basis.policy}</dd></div>}
        </dl>}
      <details><summary>已登记的研究工具（{data.tools.length}）</summary>
        <ul>{data.tools.map(tool => <li key={tool}><code>{tool}</code></li>)}</ul></details>
      <p>模型协议 {data.model.protocols.join("、")}。{data.model.capacity_scope === "local_volume" ? "共享运行目录内" : "单进程内"}并发上限 {data.model.global_concurrency}，每个模型主机 {data.model.per_host_concurrency}。</p>
      <details><summary>最近审批记录</summary>
        {data.registry.history.length ? <ol>{data.registry.history.map(row =>
          <li key={row.seq}>#{row.seq} · {row.action} · {row.kind} · <code>{row.version}</code></li>)}</ol> :
          <p>{data.registry.status === "unavailable" ? "记录暂不可用。" : "暂无审批记录。"}</p>}
      </details>
      <p>版本批准与回滚由离线操作员执行。</p>
    </>}
  </section>;
}
