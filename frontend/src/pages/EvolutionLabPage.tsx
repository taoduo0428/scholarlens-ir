import {useEffect, useState} from "react";
import {Link} from "react-router-dom";
import {backend} from "../services/backend";
import {useAuth} from "../services/AuthContext";
import {GovernancePanel} from "../components/GovernancePanel";
import "./EvolutionLabPage.css";

interface Trial {
  split:string;task:string;variant:string;goal:string;answer:string;tools:number;max_tools:number;
  models:number;max_models:number;model:string;tokens:number|null;cost:number;ms:number;
  failures:{code:string;basis:string}[];sources:{evidence_id:string;locator:string;quote:string}[];
  actions:unknown[];plan:unknown;retained:string[];judgments:unknown;controller:unknown[];skill_steps:unknown[];
  claims?:unknown[];events?:unknown[];generation:string;suite:string;
}
interface Pair {first:Trial;second:Trial;matched_model:boolean;source_added:string[];source_removed:string[]}
interface Index {metrics?:{split:string;variant:string;tasks:number;tools:number;models:number;exact_hits:number;exact_total:number;abstentions:number;missing_total:number}[];runs:{split:string;task:string;variant:string}[];versions:{version:string;decision:string;policy:unknown}[];history:unknown[]}
const endpoint="/evolution-lab";
const distinct=(values:string[])=>Array.from(new Set(values));

function JsonDetails({label,value}:{label:string;value:unknown}){
  return <details><summary>{label}</summary><pre>{JSON.stringify(value,null,2)??"未记录"}</pre></details>;
}
function TrialPanel({trial}:{trial:Trial}){
  return <article className="research-panel"><h3>{trial.variant}</h3>
    <p>{trial.answer}</p>
    <dl className="lab-metrics">{[
      ["工具",trial.tools+" / "+trial.max_tools],["模型调用",trial.models+" / "+trial.max_models],
      ["模型",trial.model],["Token",trial.tokens??"未报告"],["成本",trial.cost],["耗时",trial.ms+" ms"]
    ].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    <h4>失败归因</h4>{trial.failures.length?<ul>{trial.failures.map(f=><li key={f.code}><strong>{f.code}</strong> · {f.basis}</li>)}</ul>:<p>没有命中归因规则。</p>}
    <details><summary>可回查来源 · {trial.sources.length}</summary>{trial.sources.map(s=><blockquote key={s.evidence_id}>{s.quote}<footer>{s.locator}</footer></blockquote>)}</details>
    <JsonDetails label="研究计划" value={trial.plan}/><JsonDetails label="执行动作" value={trial.actions}/>
    <JsonDetails label="检索与筛选过程" value={trial.events}/><JsonDetails label="保留的证据" value={trial.retained}/>
    <JsonDetails label="候选命题" value={trial.claims}/><JsonDetails label="逐项判定" value={trial.judgments}/>
    <JsonDetails label="决策与预算" value={trial.controller}/><JsonDetails label="技能触发" value={trial.skill_steps}/>
  </article>;
}
function Selector({label,options,value,change}:{label:string;options:string[];value:string;change:(v:string)=>void}){
  return <label>{label}<select value={value} onChange={e=>change(e.target.value)}>{options.map(v=><option key={v}>{v}</option>)}</select></label>;
}
function Explorer(){
  const [index,setIndex]=useState<Index|null>(null),[pair,setPair]=useState<Pair|null>(null);
  const [split,setSplit]=useState(""),[task,setTask]=useState(""),[left,setLeft]=useState("baseline"),[right,setRight]=useState("contract");
  const [error,setError]=useState("");
  useEffect(()=>{const c=new AbortController();
    backend<Index>(endpoint+"/index",{signal:c.signal}).then(data=>{if(!c.signal.aborted)setIndex(data);})
      .catch(e=>{if(!c.signal.aborted)setError(String(e));});return ()=>c.abort();},[]);
  const splits=distinct(index?.runs.map(r=>r.split)??[]),s=splits.includes(split)?split:splits[0]??"";
  const inSplit=index?.runs.filter(r=>r.split===s)??[],tasks=distinct(inSplit.map(r=>r.task)),t=tasks.includes(task)?task:tasks[0]??"";
  const variants=inSplit.filter(r=>r.task===t).map(r=>r.variant);
  const l=variants.includes(left)?left:variants[0]??"", alternatives=variants.filter(v=>v!==l);
  const r=alternatives.includes(right)?right:alternatives[0]??"";
  useEffect(()=>{if(!s||!t||!l||!r)return;const c=new AbortController();setPair(null);setError("");
    backend<Pair>(endpoint+"/compare?"+new URLSearchParams({split:s,task:t,left:l,right:r}),{signal:c.signal})
      .then(data=>{if(!c.signal.aborted)setPair(data);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return ()=>c.abort();},[s,t,l,r]);
  return <>{error&&<p role="alert">{error}</p>}{index?<><section className="research-panel"><h2>同任务对照</h2>
    <div className="lab-controls"><Selector label="评测分组" options={splits} value={s} change={setSplit}/>
    <Selector label="研究任务" options={tasks} value={t} change={setTask}/>
    <Selector label="左侧版本" options={variants} value={l} change={setLeft}/>
    <Selector label="右侧版本" options={alternatives} value={r} change={setRight}/></div>
    {pair&&<><p>{pair.first.goal}</p><p>{pair.matched_model?"模型及调用上限一致":"模型配置或调用上限不同"} · 新增来源 {pair.source_added.length} · 减少 {pair.source_removed.length}</p>
      <JsonDetails label="语料版本与证据差异" value={{generation:pair.first.generation,suite:pair.first.suite,added:pair.source_added,removed:pair.source_removed}}/></>}
    {!tasks.length&&<p>还没有已完成的实验。</p>}</section>
    <details className="research-panel"><summary>本组实验结果</summary><ul>
    {index.metrics?.filter(m=>m.split===s).map(m=><li key={m.variant}><strong>{m.variant}</strong> · {m.tasks} 题 · 摘录 {m.exact_hits}/{m.exact_total} · 拒答 {m.abstentions}/{m.missing_total} · 工具 {m.tools} · 模型调用 {m.models}</li>)}</ul></details>
    {pair&&<div className="lab-pair"><TrialPanel trial={pair.first}/><TrialPanel trial={pair.second}/></div>}
    <section className="research-panel"><h2>版本登记与审核</h2>
    {index.versions.map(v=><JsonDetails key={v.version} label={v.decision+" · "+v.version.slice(0,12)} value={v.policy}/>)}
    <JsonDetails label="审批历史" value={index.history}/></section></>:!error&&<p role="status">正在读取实验记录…</p>}</>;
}
export function EvolutionLabPage(){
  const {user,loading}=useAuth();
  return <main className="research-page lab-page"><Link to="/research">返回研究工作台</Link><h1>Evolution Lab</h1>
    {loading?<p>正在读取账户…</p>:user?.role==="admin"?<div key={user.id}><GovernancePanel/><Explorer/></div>:user?<p>该账户没有实验室访问权限。</p>:<Link to="/account?next=%2Fevolution-lab">登录实验室账户</Link>}</main>;
}
