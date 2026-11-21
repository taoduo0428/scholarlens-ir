import type {ResearchState} from "../services/research";

const statusText:Record<string,string> = {
  supported:"证据支持",partial:"证据部分支持",conflicted:"来源存在分歧",not_comparable:"实验条件不可比",
  insufficient:"证据不足",not_searched:"等待检索",unavailable:"来源不可用"
};
const actionText:Record<string,string> = {
  find_sources:"寻找相关来源",read_passages:"阅读原文片段",align_conditions:"核对实验条件",
  follow_dependency:"先核查依赖问题",finish:"可结束该问题"
};

export function QuestionPlan({state}:{state:ResearchState}) {
  const plan=state.question_plan;
  if(!plan) return null;
  return <section className="research-panel" aria-label="研究问题与证据">
    <div className="research-panel-heading"><h2>研究问题与证据</h2>
      <span>第 {plan.plan_version} 版 · {plan.origin==="personal_model"?"个人模型规划":"离线规划"}</span></div>
    <ol className="research-tree">{plan.graph.nodes.map(node=>{
      const assessment=state.question_assessments?.[node.id];
      return <li key={node.id}><details><summary>{node.id.toUpperCase()} · {node.question}</summary>
        {node.dependencies.length>0&&<p>依赖问题 · {node.dependencies.join("、").toUpperCase()}</p>}
        <p>完成条件 · {node.requirement.acceptance}</p>
        {assessment&&<><p>{statusText[assessment.status]??assessment.status} · {actionText[assessment.next_action]??assessment.next_action}</p>
          {assessment.missing_requirements.map(gap=><p key={gap}>待核查 · {gap}</p>)}
          <p>支持来源 {assessment.supporting_evidence_ids.length} 条 · 相反来源 {assessment.opposing_evidence_ids.length} 条</p></>}
      </details></li>;
    })}</ol>
    {plan.revisions.length>0&&<details><summary>计划调整</summary>{plan.revisions.map((r,i)=><p key={i}>{r}</p>)}</details>}
  </section>;
}
