import {useEffect, useRef, useState, type FormEvent} from "react";
import {Link, useSearchParams} from "react-router-dom";
import {useAuth} from "../services/AuthContext";
import {BackendError} from "../services/backend";
import {loadPersonalAi} from "../services/personalAi";
import {research, slotLabels, subtaskLabels, type Command, type ResearchEvent, type ResearchReport, type ResearchSource,
  type ResearchState, type TaskInput, type TaskItem} from "../services/research";
import {PdfCellPicker} from "../components/PdfCellPicker";
import {TaskTraceViewer} from "../components/TaskTraceViewer";
import {TaskDataActions} from "../components/TaskDataActions";
import {QuestionPlan} from "../components/QuestionPlan";
import {ReportPanel, ResearchSourceDetail} from "../components/ResearchReport";

const statusLabel:Record<string,string>={queued:"排队中",running:"运行中",paused:"已暂停",awaiting_credentials:"等待模型凭据",
  awaiting_input:"等待补充资料",completed:"已完成",partial:"部分完成",cancelled:"已取消",failed:"失败"};
const eventLabel:Record<string,string>={created:"创建",started:"开始执行",step:"执行一步",round:"结束本轮",
  pause_requested:"已请求暂停",cancel_requested:"已请求取消",paused:"暂停",cancelled:"取消",resumed:"恢复",
  completed:"完成",partial:"部分完成",failed:"失败",awaiting_credentials:"等待凭据",recovered:"恢复检查点"};
const terminal = new Set(["completed","partial","cancelled","failed"]);
const message=(e:unknown)=>e instanceof Error ? e.message : "服务暂时不可用";
const labels=(values:string[])=>values.map(value=>slotLabels[value]||value).join("、");

function CreateForm({owner,onCreated}:{owner:number;onCreated:(id:string)=>void}){
  const [project,setProject]=useState("");
  const [goal,setGoal]=useState(""),[paperIds,setPapers]=useState(""),[own,setOwn]=useState(false);
  const [depth,setDepth]=useState<TaskInput["depth"]>("standard"),[mode,setMode]=useState<TaskInput["mode"]>("evidence_only");
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const previous=useRef({input:"",key:""});
  const personal=loadPersonalAi(owner);
  async function submit(e:FormEvent){
    e.preventDefault();
    if(busy)return;
    const ids=[...new Set(paperIds.split(/[\s,，]+/u).filter(Boolean))];
    if(ids.length>40){setError("论文范围最多 40 篇。");return;}
    if(mode==="personal_model"&&!personal){setError("请先在证据助手中配置个人模型。");return;}
    const body:TaskInput={goal:goal.trim(),scope:{paper_ids:ids,include_own_uploads:own,library_only:true},depth,mode};
    const cell=new FormData(e.currentTarget as HTMLFormElement).get("pdf_cell");
    if(typeof cell==="string") body.pdf_cell=JSON.parse(cell);
    if(project.trim()) body.research_project={workspace:"personal",project:project.trim()};
    const value=JSON.stringify(body);
    if(previous.current.input!==value)previous.current={input:value,key:crypto.randomUUID()};
    setBusy(true);setError("");
    try{
      const reply=await research.create(body,previous.current.key,mode==="personal_model"?personal:null);
      previous.current={input:"",key:""};setGoal("");onCreated(reply.task_id);
    }catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <form className="research-panel research-form" onSubmit={submit}>
    <h2>创建研究任务</h2>
    <label>研究问题<textarea required minLength={2} maxLength={3000} rows={3} value={goal} onChange={e=>setGoal(e.target.value)}
      placeholder="比较几篇论文的实验方法、数据集和指标，列出缺少的证据。"/></label>
    <label>研究项目（可选）<input value={project} maxLength={64} pattern="[a-zA-Z0-9_\-]{1,64}"
      onChange={e=>setProject(e.target.value)} placeholder="项目标识，如 optics-review"/></label>
    <div className="research-fields">
      <label>研究深度<select value={depth} onChange={e=>setDepth(e.target.value as TaskInput["depth"])}>
        <option value="standard">标准</option><option value="deep">深入</option></select></label>
      <label>研究模式<select value={mode} onChange={e=>setMode(e.target.value as TaskInput["mode"])}>
        <option value="evidence_only">只读证据</option><option value="personal_model">使用个人模型</option></select></label>
    </div>
    {mode==="personal_model"&&<p>{personal?"已配置模型 "+personal.model:"尚未配置个人模型。"} <Link to="/assistant">个人模型设置</Link></p>}
    <details><summary>本库论文范围</summary>
      <p>仅检索本库已收录的论文。</p>
      <label>限定论文 ID<input value={paperIds} onChange={e=>setPapers(e.target.value)} placeholder="用逗号分隔，留空搜索本库"/></label>
      <label className="research-check"><input type="checkbox" checked={own} onChange={e=>setOwn(e.target.checked)}/>包括本账户已入库上传</label>
    </details>
    <PdfCellPicker key={paperIds} papers={[...new Set(paperIds.split(/[\s,，]+/u).filter(Boolean))]}/>
    {error&&<p role="alert">{error}</p>}
    <button className="button button-primary" disabled={busy||goal.trim().length<2||(mode==="personal_model"&&!personal)}>{busy?"正在创建…":"开始研究"}</button>
  </form>;
}

function Run({id,owner,onUpdate,onDeleted}:{id:string;owner:number;onUpdate:()=>void;onDeleted:()=>void}){
  const [state,setState]=useState<ResearchState|null>(null),[events,setEvents]=useState<ResearchEvent[]>([]);
  const [report,setReport]=useState<ResearchReport|null>(null),[error,setError]=useState(""),[network,setNetwork]=useState("");
  const [pending,setPending]=useState(false),[requested,setRequested]=useState<Command|null>(null);
  const [source,setSource]=useState<ResearchSource|null>(null);
  const [traces,setTraces]=useState<string[]>([]);
  const [reload,setReload]=useState(0);
  const cursor=useRef(0), lastRev=useRef(-1), lastStatus=useRef("");
  const updateList=useRef(onUpdate);
  updateList.current=onUpdate;
  useEffect(()=>{
    let alive=true, timer=0;
    const ctl=new AbortController();
    async function poll(){
      try{
        const latest=await research.detail(id,ctl.signal);
        if(!alive)return;
        if(latest.state.user_id!==owner)throw new Error("无权查看此任务。");
        const rows=await research.events(id,cursor.current,ctl.signal);
        if(!alive)return;
        const added=rows.events.filter(e=>e.seq>cursor.current);
        if(added.length){
          if(added.some((e,i)=>e.seq!==cursor.current+i+1))throw new Error("事件序号有缺口，正在重新连接。");
          cursor.current=added[added.length-1].seq;
          setEvents(old=>[...old,...added]);
        }
        const status=latest.state.status;
        if(latest.revision>=lastRev.current){
          lastRev.current=latest.revision;setState(latest.state);setTraces(latest.trace_ids??[]);
          if(status!==lastStatus.current){lastStatus.current=status;setRequested(null);updateList.current();}
        }
        setNetwork("");
        if(terminal.has(status)){
          if(status==="completed"||status==="partial"){
            const result=await research.report(id,ctl.signal);
            if(alive)setReport(result);
          }
          if(added.length<100)return;
        }
      }catch(e){
        if(!alive)return;
        if(e instanceof BackendError && [401,403,404].includes(e.status)){
          setState(null);setReport(null);setEvents([]);setSource(null);setError("任务不存在或当前账户无权查看。");return;
        }
        setNetwork("连接中断，保留已接收的进度。 "+message(e));
      }
      if(alive)timer=window.setTimeout(poll,1200);
    }
    void poll();
    return ()=>{alive=false;window.clearTimeout(timer);ctl.abort();};
  },[id,owner,reload]);
  async function control(action:Command){
    setError("");setPending(true);
    try{
      const personal=state?.task.mode==="personal_model"&&action==="resume"?loadPersonalAi(owner):null;
      if(state?.status==="awaiting_credentials"&&!personal)throw new Error("请先重新提供个人 API 配置，再恢复研究。");
      await research.control(id,action,personal);setRequested(action);setReload(n=>n+1);onUpdate();
    }catch(e){setError(message(e));}finally{setPending(false);}
  }
  async function readArtifact(aid:string){
    setError("");
    try{const result=await research.artifact(id,aid);setSource(result);}
    catch(e){setError(message(e));}
  }
  const active=state?.status==="queued"||state?.status==="running";
  const canResume=state&&["paused","awaiting_credentials","awaiting_input"].includes(state.status);
  return <div className="research-run">
    {error&&<p role="alert" className="research-notice">{error}</p>}
    {network&&<p role="status" className="research-notice">{network} <button onClick={()=>setReload(n=>n+1)}>立即重连</button></p>}
    {!state&&!error&&<p role="status">正在读取任务…</p>}
    {state&&<>
      <section className="research-panel"><div className="research-panel-heading"><h2>{state.task.goal}</h2><span className="research-state">{statusLabel[state.status]}</span></div>
        <p>研究轮次 {state.budget.rounds_used}/{state.budget.max_rounds} · 工具调用 {state.budget.tool_calls_used}/{state.budget.max_tool_calls}</p>
        <details><summary>任务版本</summary><p>语料 {state.corpus_generation} · 模型 {state.model_id}</p></details>
        <TaskTraceViewer taskId={id} traces={traces}/>
        <TaskDataActions taskId={id} revision={lastRev.current} terminal={terminal.has(state.status)}
          onDeleted={onDeleted} onConflict={()=>setReload(n=>n+1)}/>
        {state.task.research_project&&<ProjectDashboard workspace={state.task.research_project.workspace}
          project={state.task.research_project.project} revision={lastRev.current}/>}
        {state.status==="awaiting_credentials"&&<p>恢复前请重新配置个人模型。 <Link to="/assistant">配置个人模型</Link></p>}
        {state.stop_reason&&<p>停止原因 · {state.stop_reason}</p>}
        {state.warnings.map((w,i)=><p key={i}>{w}</p>)}
        {requested&&<p role="status">已提交{requested==="cancel"?"取消":requested==="pause"?"暂停":"恢复"}请求，等待执行器确认。</p>}
        <div className="research-buttons">
          {active&&<button className="button button-secondary" disabled={pending||requested!==null} onClick={()=>void control("pause")}>暂停任务</button>}
          {canResume&&<button className="button button-primary" disabled={pending||requested!==null} onClick={()=>void control("resume")}>恢复任务</button>}
          {!terminal.has(state.status)&&<button className="button button-secondary" disabled={pending||requested!==null} onClick={()=>void control("cancel")}>取消任务</button>}
        </div>
      </section>
      {state.answer_contract&&<section aria-label="答案契约" className="research-panel">
        <h2>答案契约</h2><p>{state.answer_contract.goal}</p>
        <p>预期答案 · {state.answer_contract.answer_type}</p>
        {state.answer_contract.constraints.map(value=><p key={value}>{value}</p>)}
        <ol>{state.answer_contract.obligations.map(o=><li key={o.id}><strong>{o.requirement}</strong>
          <p>{o.evidence.join(" · ")} {o.prerequisites.length>0&&" ｜ 前置 "+o.prerequisites.join("、")}</p>
          <span>{report?.answer_proof?.obligations[o.id]?.status==="met"?"已满足":report?"证据有缺口":"等待核验"}</span></li>)}</ol>
      </section>}
      <QuestionPlan state={state}/>
      <section className="research-panel" aria-label="研究计划"><h2>研究计划</h2>
        {state.subtasks.length===0?<p>等待执行器生成计划。</p>:<details className="research-tree" open>
          <summary>任务树 · {state.subtasks.length} 个子任务</summary>
          <ul>{state.subtasks.map(s=><li key={s.id}><details data-plan-subtask={s.id}>
            <summary>{s.goal} · {subtaskLabels[s.status]||s.status}</summary><p>完成条件 · {labels(s.required_slots)}</p>
            <p>{s.missing_slots.length?"缺口 · "+labels(s.missing_slots):"当前所需槽位已覆盖"}</p>
          </details></li>)}</ul></details>}</section>
      <section className="research-panel"><h2>执行记录</h2>
        <ol className="research-events">{events.map(e=><li key={e.seq} data-event-seq={e.seq}>
          <time dateTime={e.created_at}>{new Date(e.created_at).toLocaleTimeString()}</time> {eventLabel[e.kind]||e.kind} · {statusLabel[e.status]}</li>)}</ol>
        {state.actions.length>0&&<details><summary>工具调用明细</summary><ul>{state.actions.map(a=><li key={a.seq}>
          {a.tool} · {a.status} · {a.elapsed_ms} ms {a.error_code||""}</li>)}</ul></details>}</section>
      {state.evidence_refs.length>0&&<section className="research-panel"><h2>已读取证据</h2>
        <ul>{state.evidence_refs.map(r=><li key={r.evidence_id}>{r.paper_id} · {r.locator}</li>)}</ul>
        {state.artifact_refs.filter(a=>a.startsWith("evidence-")).map((a,i)=><button className="button button-secondary"
          key={a} onClick={()=>void readArtifact(a)}>读取证据 {i+1}</button>)}
        {source&&<ResearchSourceDetail source={source}/>}</section>}
      {report&&<ReportPanel report={report} taskId={id} subtasks={state.subtasks}/>}
    </>}
  </div>;
}

function ProjectDashboard({workspace,project,revision}:{workspace:string;project:string;revision:number}){
  const [opened,setOpened]=useState(false);
  const [data,setData]=useState<Awaited<ReturnType<typeof research.metrics>>|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!opened)return;
    const ctrl=new AbortController();
    research.metrics(workspace,project,ctrl.signal).then(value=>{
      if(!ctrl.signal.aborted){setData(value);setError("");}
    }).catch(e=>{if(!ctrl.signal.aborted){setData(null);setError(message(e));}});
    return ()=>ctrl.abort();
  },[opened,workspace,project,revision]);
  return <details onToggle={e=>setOpened(e.currentTarget.open)}><summary>项目运行统计</summary>
    {error?<p role="alert">{error}</p>:data?<section aria-label="项目运行统计">
      <p>{project} · 最近 {data.tasks} 个任务{data.more?"（还有更早记录）":""}</p>
      <p>{Object.entries(data.states).map(([key,n])=>statusLabel[key as keyof typeof statusLabel]+" "+n).join(" · ")}</p>
      <p>完成及部分完成任务 p50 {data.p50_seconds??"—"} 秒，p95 {data.p95_seconds??"—"} 秒</p>
      <p>模型调用 {data.model_calls} 次 · 已计量 {data.measured_tokens} tokens{data.tokens_complete?"":"（部分用量缺失）"}</p>
      <p>已知费用估计 {data.known_cost_estimate} · 费用缺失 {data.tasks_missing_cost} 项</p>
    </section>:opened?<p>正在读取项目统计…</p>:null}</details>;
}

function Workspace({owner}:{owner:number}){
  const [params,setParams]=useSearchParams();
  const current=params.get("task")||"";
  const [tasks,setTasks]=useState<TaskItem[]>([]),[error,setError]=useState(""),[refresh,setRefresh]=useState(0);
  const bump=()=>setRefresh(n=>n+1);
  useEffect(()=>{
    const ctrl=new AbortController();
    research.list(ctrl.signal).then(result=>{if(!ctrl.signal.aborted){setTasks(result.tasks);setError("");}})
      .catch(e=>{if(!ctrl.signal.aborted)setError(message(e));});
    return ()=>ctrl.abort();
  },[owner,refresh]);
  function select(id:string){setParams({task:id});bump();}
  return <div className="research-workspace"><div className="research-left">
    <CreateForm owner={owner} onCreated={select}/>
    <section className="research-panel"><h2>我的任务</h2>
      {error&&<p role="alert">{error} <button onClick={bump}>重试</button></p>}
      {!tasks.length&&!error&&<p>暂无研究任务。</p>}
      <ul className="research-tasks">{tasks.map(t=><li key={t.id}>
        <button aria-current={current===t.id?"page":undefined} onClick={()=>select(t.id)}>
          <strong>{t.goal}</strong><span>{statusLabel[t.status]}</span></button></li>)}</ul>
    </section></div>
    {current?<Run key={current} id={current} owner={owner} onUpdate={bump}
      onDeleted={()=>{setTasks(old=>old.filter(task=>task.id!==current));setParams({}, {replace:true});bump();}}/>:<section className="research-panel"><h2>任务详情</h2><p>创建或选择一项任务后可查看计划、证据和报告。</p></section>}
  </div>;
}
export function ResearchPage(){
  const {user,loading}=useAuth();
  const [params]=useSearchParams();
  const next="/research"+(params.toString()?"?"+params.toString():"");
  return <main className="research-page"><h1>深度研究</h1>
    {import.meta.env.VITE_EVOLUTION_LAB==="true"&&user?.role==="admin"&&<Link to="/evolution-lab">进入 Evolution Lab</Link>}
    {loading?<p>正在读取账户…</p>:user?<Workspace owner={user.id} key={user.id}/>:<section className="research-panel"><h2>研究任务随账户保存</h2>
      <Link className="button button-primary" to={"/account?next="+encodeURIComponent(next)}>登录研究账户</Link></section>}
  </main>;
}
