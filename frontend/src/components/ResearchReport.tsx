import {useState} from "react";
import {evidenceHref, evidenceLocatorLabel} from "../lib/evidenceLocation";
import {slotLabels, type ResearchClaim, type ResearchReport, type ResearchSource, type ResearchSubtask} from "../services/research";

const profileLabels:Record<string,string>={
  research_objective:"研究目标",research_problem:"研究问题",methods:"方法",proposed_contributions:"作者贡献",
  datasets:"数据集",metrics:"指标",experiment_settings:"实验条件",baselines:"基线",reported_findings:"研究发现",
  limitations:"局限",future_work:"未来工作",author_qualifications:"带有条件的陈述"
};

const supportLabels:Record<string,string>={verified:"已核验",unverified:"待核验",uncertain:"待核验",
  insufficient:"证据不足",contradicted:"存在矛盾",not_comparable:"实验条件不可比"};
const conditions:Record<string,string>={dataset:"数据集",metric_name:"指标",metric_value:"数值",
  unit:"单位",experiment_setup:"实验设置",evaluation_protocol:"评测协议"};
const kinds:Record<string,string>={indexed_fulltext:"索引正文",abstract:"摘要",metadata:"元数据",
  private_upload:"本人上传",external_abstract:"外部摘要"};

function Source({source}:{source:ResearchSource}){
  return <details className="research-source">
    <summary>{source.paper_title || source.paper_id} · {evidenceLocatorLabel(source.locator)}</summary>
    <p>{kinds[source.source_kind]||source.source_kind} · {source.pdf_available===true?"可读 PDF":source.pdf_available===false?"PDF 未提供":"PDF 状态待确认"}
      {source.fulltext_available===false?" · 正文缺失":""}</p>
    <blockquote>{source.quote}</blockquote>
    <a href={evidenceHref(source)} target="_blank" rel="noreferrer">定位到论文原文</a>
  </details>;
}

function Claim({claim,sources,conflicts}:{claim:ResearchClaim;sources:Map<string,ResearchSource>;conflicts:ResearchClaim[]}){
  return <article className="research-claim" data-claim={claim.claim_id} tabIndex={-1}>
    <p><strong>{claim.statement}</strong></p>
    <span className="research-state">{supportLabels[claim.support_status]||claim.support_status}</span>
    {Object.entries(claim.conditions||{}).some(([,value])=>value) &&
      <dl>{Object.entries(claim.conditions||{}).filter(([,v])=>v).map(([key,v])=>
        <div key={key}><dt>{conditions[key]||key}</dt><dd>{v}</dd></div>)}</dl>}
    {claim.semantic_support&&<dl>
      <dt>来源定位</dt><dd>{claim.provenance_valid?"原文已核对":"缺少可核对来源"}</dd>
      <dt>结论支持</dt><dd>{{supported:"证据支持",insufficient:"证据不足",contradicted:"与证据矛盾"}[claim.semantic_support]??"尚未评估"}</dd>
      <dt>比较条件</dt><dd>{claim.comparison_status==="comparable"?"条件已对齐":claim.comparison_status==="not_comparable"?"条件不可比":"不涉及比较"}</dd>
    </dl>}
    {claim.check_notes?.map((note,i)=><p key={i}>{note}</p>)}
    {conflicts.length>0&&<details className="research-conflicts"><summary>冲突结论 · {conflicts.length}</summary>
      <ul>{conflicts.map(peer=><li key={peer.claim_id}>{peer.statement}
        {peer.evidence_ids.map(id=>{const src=sources.get(id);return src?<Source key={id} source={src}/>:null;})}</li>)}</ul></details>}
    {claim.evidence_ids.map(id=>{const src=sources.get(id);return src?<Source key={id} source={src}/>:<p key={id}>该来源未通过报告回验</p>;})}
    {claim.evidence_ids.length===0&&<p>证据缺口 · 此结论尚无可定位的原文。</p>}
  </article>;
}

function exportMarkdown(id:string, markdown:string){
  const url=URL.createObjectURL(new Blob([markdown],{type:"text/markdown;charset=utf-8"}));
  const a=document.createElement("a");
  a.href=url; a.download="ScholarLens-"+id+".md"; a.click();
  window.setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

export function ReportPanel({report,taskId,subtasks}:{report:ResearchReport;taskId:string;subtasks:ResearchSubtask[]}){
  const [showFull,setShowFull]=useState(false);
  const claims=new Map(report.claims.map(c=>[c.claim_id,c]));
  const sources=new Map(report.sources.map(s=>[s.evidence_id,s]));
  const plan=report.graph?.subtasks??subtasks;
  const edges=new Map((report.graph?.subtask_claim??[]).map(edge=>[edge.claim_id,edge.subtask_id]));
  const owner=(claim:ResearchClaim)=>edges.get(claim.claim_id)??claim.subtask_id;
  const rows=plan.map(sub=>({id:sub.id,goal:sub.goal,missing:sub.missing_slots,
    claims:report.claims.filter(claim=>owner(claim)===sub.id)}));
  const planIds=new Set(plan.map(sub=>sub.id));
  const other=report.claims.filter(claim=>!planIds.has(owner(claim)??""));
  if(other.length) rows.push({id:"unassigned",goal:"其他结论",missing:[],claims:other});
  const peers=(id:string)=>{
    const peerIds=new Set((report.graph?.conflicts??[]).filter(edge=>edge.claim_ids.includes(id)).flatMap(edge=>edge.claim_ids));
    peerIds.delete(id);
    return [...peerIds].map(peer=>claims.get(peer)).filter((claim):claim is ResearchClaim=>Boolean(claim));
  };
  const experiments=report.claims.filter(claim=>["method","metric","comparison"].includes(claim.claim_type));
  return <section className="research-panel" aria-label="研究报告">
    <div className="research-panel-heading"><h2>研究报告</h2>
      <button className="button button-secondary" onClick={()=>exportMarkdown(taskId,report.markdown)}>导出 Markdown</button></div>
    <p>{report.summary}</p>
    {report.spending&&<p>工具调用 {report.spending.tools} 次 · 模型调用 {report.spending.model_calls} 次 ·
      输入 {report.spending.input_tokens??"未报告"} tokens · 输出 {report.spending.output_tokens??"未报告"} tokens ·
      费用 {report.spending.cost==null?"未报告":report.spending.cost}</p>}
    {report.pdf_cell_evidence&&<section aria-label="指定 PDF 单元格"><h3>指定 PDF 单元格</h3>
      {report.pdf_cell_evidence.status==="source_verified"
        ? <blockquote>{report.pdf_cell_evidence.cell.quote}<footer>{report.pdf_cell_evidence.cell.paper_id} ·
          第 {report.pdf_cell_evidence.cell.page} 页 · 表 {report.pdf_cell_evidence.cell.table_id} ·
          第 {report.pdf_cell_evidence.cell.row} 行第 {report.pdf_cell_evidence.cell.column} 列
          <br/>{report.pdf_cell_evidence.cell.locator}</footer></blockquote>
        : <p>无法核验此单元格（{report.pdf_cell_evidence.reason}）</p>}
    </section>}
    {report.research_profiles&&<section aria-label="逐篇研究档案"><h3>逐篇研究档案</h3>
      {report.research_profiles.map(p=><details key={p.paper_id}><summary>{p.title}</summary>
        {Object.entries(p.fields).map(([field,quotes])=><div key={field}>
          <h4>{profileLabels[field]??field}</h4>
          {quotes.length===0?<p>尚无已核验的原文</p>:quotes.map(q=><blockquote key={q.locator}>
            {q.quote}<footer>{q.locator} · {q.origin} · {q.extraction_method}</footer></blockquote>)}
        </div>)}</details>)}</section>}
    {report.answerability&&<section aria-label="字段核验"><h3>字段核验</h3>
      {report.field_requirements?.flatMap(q=>q.fields).map(f=>{
        const d=report.answerability!.fields[f.field_id];
        if(!d)return null;
        const labels:Record<string,string>={answerable:"已核验",partially_answerable:"部分可答",insufficient_evidence:"证据不足",
          source_capability_mismatch:"来源不能提供所需信息",unavailable_in_scope:"许可范围内无此信息",conflicted:"证据冲突",
          not_comparable:"不可直接比较",blocked_by_permission:"权限受限"};
        return <details key={f.field_id}><summary>{f.request} · {labels[d.status]||d.status}</summary>
          <p>{f.datatype} · {d.reason} · {d.next_action}</p>
          {d.bindings.map(b=><p key={JSON.stringify([b.claim_id,b.evidence_id,b.locator.raw])}>{b.locator.paper_id} · {b.locator.raw}</p>)}</details>;
      })}</section>}
    {report.overview&&<section aria-label="综合研究"><h3>综合研究</h3>
      {report.overview.findings.map((f,i)=><details key={i}><summary>{f.statement}</summary>
        <p>{{derived_synthesis:"根据多篇论文推导",supported_claim:"有原文支持",hypothesis:"作者假说",speculation:"作者推测"}[f.level]||f.level}</p>
        {f.premise_claim_ids.map(id=>{const c=claims.get(id);return c&&<Claim key={id} claim={c} sources={sources} conflicts={peers(id)}/>;})}
      </details>)}
      {report.overview.incomplete_papers.map(p=><p key={p}>{p} · 仍缺研究方法或结果的原文证据</p>)}
    </section>}
    {report.answer_groups&&<section aria-label="最终答案与证据">
      <h3>{report.answerability?.status==="partially_answerable"?"已核验的部分回答":report.answer_groups.unanswerable?"最终问题仍无法回答":"可发布的直接结论"}</h3>
      {([["direct","直接回答"],["background","背景与推理前提"],["incomparable","条件不可比"],["conflicting","相互矛盾的观察"]] as const).map(([key,label])=>{
        const ids=report.answer_groups![key];
        return ids.length>0&&<details key={key} open={key==="direct"}><summary>{label} · {ids.length}</summary>
          {ids.map(id=>{const c=claims.get(id);return c&&<Claim key={id} claim={c} sources={sources} conflicts={peers(c.claim_id)}/>;})}</details>;
      })}
      {report.answer_groups.unresolved.map(id=><p key={id}>缺口 · {report.answer_proof?.obligations[id]?.required||id}</p>)}
    </section>}
    {experiments.length>0&&<details className="research-comparison"><summary>方法与实验对照 · {experiments.length} 条</summary>
      <div className="research-table-scroll" tabIndex={0} role="region" aria-label="方法与实验对照表"><table>
        <thead><tr><th>方法或结果</th><th>数据集</th><th>指标及数值</th><th>协议或设置</th><th>核验结果</th></tr></thead>
        <tbody>{experiments.map(c=><tr key={c.claim_id}><th scope="row">{c.statement}</th><td>{c.conditions?.dataset||"未报告"}</td>
          <td>{[c.conditions?.metric_name,c.conditions?.metric_value,c.conditions?.unit].filter(Boolean).join(" ")||"未报告"}</td>
          <td>{c.conditions?.evaluation_protocol||c.conditions?.experiment_setup||"未报告"}</td>
          <td>{supportLabels[c.support_status]||c.support_status}</td></tr>)}</tbody></table></div></details>}
    <section aria-label="结论与证据矩阵"><h3>结论与证据矩阵</h3>
      {rows.map(row=><details key={row.id} open className="research-matrix-row" data-matrix-subtask={row.id}>
        <summary>{row.goal} · {row.claims.length} 条结论</summary>
        {row.missing.length>0&&<p>子任务缺口 · {row.missing.map(slot=>slotLabels[slot]||slot).join("、")}</p>}
        {row.claims.length===0&&<p>此子任务尚无已发布的结论。</p>}
        {row.claims.map(claim=><Claim key={claim.claim_id} claim={claim} sources={sources} conflicts={peers(claim.claim_id)}/>)}
      </details>)}</section>
    {report.unresolved.length>0&&<section><h3>待解决问题</h3><ul>{report.unresolved.map((v,i)=><li key={i}>{v}</li>)}</ul></section>}
    {report.sources.length>0&&<section><h3>全部来源</h3>{report.sources.map(s=><Source key={s.evidence_id} source={s}/>)}</section>}
    <button className="button button-secondary" aria-expanded={showFull} onClick={()=>setShowFull(v=>!v)}>
      {showFull?"收起 Markdown 原稿":"查看 Markdown 原稿"}</button>
    {showFull&&<pre className="research-markdown">{report.markdown}</pre>}
  </section>;
}
export {Source as ResearchSourceDetail};
