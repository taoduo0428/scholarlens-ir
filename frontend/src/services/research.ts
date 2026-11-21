import {backend} from "./backend";
import {personalAiHeaders, type PersonalAi} from "./personalAi";

export const RESEARCH_ENABLED = import.meta.env.VITE_RESEARCH_ENABLED === "true";
export type TaskStatus = "queued"|"running"|"paused"|"awaiting_credentials"|"awaiting_input"|"completed"|"partial"|"cancelled"|"failed";
export type Command = "pause"|"resume"|"cancel";
export interface TaskInput {
  goal:string;
  scope:{paper_ids:string[];include_own_uploads:boolean;library_only:true};
  depth:"standard"|"deep";
  mode:"evidence_only"|"personal_model";
}
export interface TaskItem {id:string;goal:string;status:TaskStatus;revision:number}
export interface ResearchEvent {seq:number;kind:string;status:TaskStatus;created_at:string}
export interface ResearchSource {
  evidence_id:string;paper_id:string;paper_title?:string;chunk_id:string;quote:string;locator:string;
  source_kind:string;rights:string;corpus_generation:string;quote_hash:string;
  pdf_available?:boolean|null;fulltext_available?:boolean|null;
}
export interface ResearchClaim {
  provenance_valid?:boolean;semantic_support?:string;comparison_status?:string;
  claim_id:string;subtask_id?:string;statement:string;claim_type:string;support_status:string;
  evidence_ids:string[];conditions?:Record<string,string|null>;check_notes?:string[];
}
export interface ResearchSubtask {id:string;goal:string;required_slots:string[];missing_slots:string[];status:string}
export const slotLabels:Record<string,string>={method:"方法",dataset:"数据集",metric:"指标",protocol:"实验协议",limitation:"局限",comparison:"比较",fact:"事实"};
export const subtaskLabels:Record<string,string>={pending:"待执行",active:"执行中",satisfied:"已满足",blocked:"有缺口"};
export interface PlanQuestion {
  id:string; question:string; dependencies:string[];
  requirement:{kind:string;acceptance:string;failure:string;min_papers:number};
}
export interface ResearchState {
  answer_contract?:{goal:string;answer_type:string;deliverables:string[];constraints:string[];
    obligations:{id:string;requirement:string;prerequisites:string[];evidence:string[]}[];stop_conditions:string[]}|null;
  retrieval_policy?:string;
  question_plan?:{origin:string;plan_version:number;graph:{nodes:PlanQuestion[]};revisions:string[]} | null;
  question_assessments?:Record<string,{status:string;next_action:string;missing_requirements:string[];supporting_evidence_ids:string[];opposing_evidence_ids:string[]}>;
  run_id:string;user_id:number;status:TaskStatus;task:TaskInput;corpus_generation:string;model_id:string;
  subtasks:ResearchSubtask[];
  actions:{seq:number;tool:string;status:string;elapsed_ms:number;error_code:string|null}[];
  evidence_refs:{evidence_id:string;paper_id:string;chunk_id:string;locator:string;source_kind:string}[];
  artifact_refs:string[]; claims:ResearchClaim[];warnings:string[];
  budget:{rounds_used:number;max_rounds:number;tool_calls_used:number;max_tool_calls:number};
  stop_reason:string|null;
}
export interface ResearchReport {
  overview?:{findings:{kind:string;level:string;statement:string;premise_claim_ids:string[];evidence_ids:string[];paper_ids:string[]}[];incomplete_papers:string[]};
  summary:string;claims:ResearchClaim[];sources:ResearchSource[];unresolved:string[];markdown:string;
  sections:{verified:string[];uncertain:string[];not_comparable:string[];contradicted:string[]};
  field_requirements?:{question_id:string;fields:{field_id:string;request:string;datatype:string}[]}[];
  answerability?:{status:string;fields:Record<string,{status:string;reason:string;next_action:string;bindings:{claim_id:string;evidence_id:string;locator:{paper_id:string;raw:string}}[]}>};
  answer_groups?:{direct:string[];background:string[];incomparable:string[];conflicting:string[];unresolved:string[];unanswerable:boolean};
  answer_proof?:{obligations:Record<string,{status:string;required:string;claims:string[]}>};
  graph?:{subtasks?:ResearchSubtask[];subtask_claim?:{subtask_id:string;claim_id:string}[];
    conflicts?:{claim_ids:string[];relation:string;basis?:string}[]};
}
type Receipt = {task_id:string;status:TaskStatus;revision:number};
const base="/research/tasks";
const item=(id:string)=>base+"/"+encodeURIComponent(id);
export const research={
  list:(signal?:AbortSignal)=>backend<{tasks:TaskItem[]}>(base,{signal}),
  create:(body:TaskInput,key:string,personal:PersonalAi|null)=>backend<Receipt>(base,{
    method:"POST",headers:{"Idempotency-Key":key,...personalAiHeaders(personal)},body
  }),
  detail:(id:string,signal?:AbortSignal)=>backend<{state:ResearchState;revision:number}>(item(id),{signal}),
  events:(id:string,cursor:number,signal?:AbortSignal)=>backend<{events:ResearchEvent[]}>(item(id)+"/events?after_seq="+cursor,{signal}),
  control:(id:string,cmd:Command,personal:PersonalAi|null=null)=>backend<Receipt>(item(id)+"/"+cmd,{
    method:"POST",headers:personalAiHeaders(personal)
  }),
  report:(id:string,signal?:AbortSignal)=>backend<ResearchReport>(item(id)+"/report",{signal}),
  artifact:(id:string,aid:string,signal?:AbortSignal)=>backend<ResearchSource>(item(id)+"/artifacts/"+encodeURIComponent(aid),{signal})
};
