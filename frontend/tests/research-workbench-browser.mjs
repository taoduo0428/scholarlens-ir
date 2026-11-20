/** Research workbench UI acceptance. Only the local preview and explicit Mock routes may be reached. */
import assert from "node:assert/strict";
import {mkdirSync,readFileSync} from "node:fs";
import {createRequire} from "node:module";
import path from "node:path";

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:19468";
assert.equal(new URL(origin).hostname,"127.0.0.1");
const output=path.resolve(process.env.SCHOLARLENS_RESEARCH_OUTPUT||"../output/research-workbench");
mkdirSync(output,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.SCHOLARLENS_CHROME||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
await ctx.addInitScript(()=>sessionStorage.setItem("scholarlens-session","mock-research-session"));
const quote="Unicode β · Dataset Alpha scored 0.82.";
const evidence={evidence_id:"e1",paper_id:"fixture-paper",paper_title:"Mock evaluation paper",chunk_id:"chunk:1",
  locator:"fulltext:chars:0-"+[...quote].length,quote,source_kind:"indexed_fulltext",rights:"public_corpus",
  corpus_generation:"test-gen",quote_hash:"a".repeat(64),pdf_available:false,fulltext_available:true};
const claim={claim_id:"c1",subtask_id:"s1",statement:"Dataset Alpha scored 0.82.",claim_type:"metric",evidence_ids:["e1"],
  support_status:"verified",conditions:{dataset:"Dataset Alpha",metric_value:"0.82"}};
const otherQuote="The claimed Alpha score of 0.82 was ruled out by the replication.";
const opposite={...evidence,evidence_id:"e2",paper_id:"fixture-replication",paper_title:"Mock replication",
  quote:otherQuote,locator:"fulltext:chars:0-"+otherQuote.length};
const otherClaim={...claim,claim_id:"c2",statement:otherQuote,evidence_ids:["e2"],support_status:"contradicted"};
const report={summary:"Mock study of Alpha.",claims:[claim,otherClaim],sources:[evidence,opposite],
  graph:{conflicts:[{claim_ids:["c1","c2"],relation:"contradicts"}]},
  sections:{verified:["c1"],uncertain:[],not_comparable:[],contradicted:["c2"]},unresolved:["第二种模型缺少独立评测。"],
  markdown:"# Alpha\n\nDataset Alpha scored 0.82.\n"};
const records=[],events=new Map(),states=new Map(),keys=[],controls=[],cursors=[],errors=[],outbound=[];
let failEvents=false, cancelAcknowledged=false, created=0, user=71;
function append(id,kind,status){
  const list=events.get(id);list.push({seq:list.length+1,kind,status,created_at:new Date().toISOString()});
  states.get(id).status=status;
}
function add(body){
  const id="task-"+(++created);
  const state={run_id:id,user_id:user,task:body,status:"running",corpus_generation:"test-gen",model_id:"none",
    subtasks:[{id:"s1",goal:"提取指标及协议",required_slots:["metric","protocol"],missing_slots:["protocol"],status:"active"},
      {id:"s2",goal:"复核局限",required_slots:["limitation"],missing_slots:["limitation"],status:"blocked"}],
    actions:[{seq:1,tool:"search_passages",elapsed_ms:22,status:"done",error_code:null}],
    evidence_refs:[evidence],artifact_refs:["evidence-a"],claims:[claim],warnings:[],
    budget:{rounds_used:1,max_rounds:4,tool_calls_used:2,max_tool_calls:30},stop_reason:null};
  states.set(id,state);events.set(id,[]);append(id,"created","queued");append(id,"started","running");records.push(id);
  return id;
}
await ctx.route("**/*",async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){outbound.push(url.origin);return route.abort();}
  const p=url.pathname;
  if(!p.startsWith("/api/"))return route.continue();
  let data={};let status=200;
  if(p==="/api/auth/me")data={id:user,username:"mock-user",role:"user"};
  if(p==="/api/stats")data={papers:2,indexed:2,status:"real"};
  if(p==="/api/me/workspace")data={version:0,history:[],favorites:[],collections:[]};
  if(p==="/api/papers/fixture-paper")data={paper_id:evidence.paper_id,title:evidence.paper_title,
    authors:[],abstract:"Mock abstract.",fulltext:quote,year:2024};
  if(p==="/api/research/tasks"){
    if(request.method()==="POST"){
      keys.push(request.headers()["idempotency-key"]);
      const task_id=add(request.postDataJSON());data={task_id,status:"queued",revision:0};status=202;
    } else data={tasks:records.filter(id=>states.get(id).user_id===user).map(id=>({id,goal:states.get(id).task.goal,status:states.get(id).status,revision:events.get(id).length-1}))};
  } else if(p.startsWith("/api/research/tasks/")){
    const [,id,suffix]=p.match(/^\/api\/research\/tasks\/([^/]+)(?:\/(.*))?$/);
    const s=states.get(id);
    if(!s||s.user_id!==user){status=404;data={error:{code:"not_found",message:"not found"}};}
    else if(!suffix)data={state:s,revision:events.get(id).length-1};
    else if(suffix==="events"){
      const cursor=Number(url.searchParams.get("after_seq"));cursors.push(cursor);
      if(failEvents){failEvents=false;return route.abort("failed");}
      data={events:events.get(id).filter(e=>e.seq>cursor)};
    } else if(suffix==="report")data=report;
    else if(suffix==="artifacts/evidence-a")data=evidence;
    else if(["cancel","resume","pause"].includes(suffix)){
      controls.push(suffix);
      if(suffix==="cancel"){append(id,"cancel_requested",s.status);cancelAcknowledged=true;}
      else append(id,suffix==="pause"?"paused":"resumed",suffix==="pause"?"paused":"running");
      data={task_id:id,status:s.status,revision:events.get(id).length-1};
    } else throw Error("unexpected research route "+p);
  }
  await route.fulfill({status,json:data});
});
const page=await ctx.newPage();page.setDefaultTimeout(10000);
page.on("pageerror",e=>errors.push(e.message));
const one=(name)=>page.getByRole("button",{name,exact:true});
const assertNoOverflow=async()=>assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
const pass=(message)=>console.log("PASS "+message);
try{
  await page.goto(origin+"/research");
  await page.getByLabel("研究问题",{exact:true}).fill("比较 Alpha 的指标和实验协议");
  await page.getByText("本库论文范围",{exact:true}).click();
  await page.getByLabel("限定论文 ID").fill("fixture-paper");
  await one("开始研究").click();
  await page.waitForURL("**/research?task=task-1");
  assert.match(keys[0],/^[a-z0-9-]{36}$/);
  await page.locator('[data-event-seq="2"]').waitFor();
  const plan=page.getByRole("region",{name:"研究计划"});
  await plan.locator(".research-tree > summary").click();
  assert.ok(!await plan.locator("[data-plan-subtask=s1] > summary").isVisible());
  await plan.locator(".research-tree > summary").click();
  await plan.locator("[data-plan-subtask=s1] > summary").click();
  await plan.getByText("完成条件 · 指标、实验协议").waitFor();
  await one("读取证据 1").click();
  await page.locator(".research-source summary").first().click();
  assert.equal(await page.locator(".research-source blockquote").first().innerText(),quote);
  pass("create posts scoped input; running evidence is readable");
  await one("暂停任务").click();
  await one("恢复任务").waitFor();
  await one("恢复任务").click();
  await one("暂停任务").waitFor();
  failEvents=true;
  await page.getByText(/连接中断，保留已接收的进度/).waitFor();
  append("task-1","round","running");
  await one("立即重连").click();
  await page.locator('[data-event-seq="5"]').waitFor();
  await page.reload();await page.locator('[data-event-seq="5"]').waitFor();
  assert.deepEqual((await page.locator("[data-event-seq]").allTextContents()).length,5);
  assert.ok(cursors.some(n=>n>0));assert.deepEqual(controls,["pause","resume"]);
  pass("pause, resume, reconnect and reload replay server events without gaps");
  append("task-1","completed","completed");
  await page.getByRole("region",{name:"研究报告"}).waitFor();
  const matrix=page.getByRole("region",{name:"结论与证据矩阵"});
  await matrix.locator("[data-matrix-subtask=s2]").getByText("此子任务尚无已发布的结论。").waitFor();
  await matrix.locator("[data-matrix-subtask=s1]").getByText("子任务缺口 · 实验协议").waitFor();
  const claimNode=matrix.locator("[data-claim=c1]");
  await claimNode.locator(".research-conflicts > summary").click();
  await claimNode.locator(".research-conflicts .research-source > summary").click();
  assert.equal(await claimNode.locator(".research-conflicts blockquote").innerText(),otherQuote);
  await page.locator(".research-comparison > summary").click();
  assert.equal(await page.getByRole("region",{name:"方法与实验对照表"}).getByRole("row").count(),3);
  await claimNode.locator(":scope > .research-source > summary").click();
  const open=ctx.waitForEvent("page");await claimNode.locator(":scope > .research-source a").click();
  const article=await open;await article.locator("#paper-evidence-match").waitFor();
  assert.equal(await article.locator("#paper-evidence-match").innerText(),quote);await article.close();
  const save=page.waitForEvent("download");await one("导出 Markdown").click();
  assert.equal(readFileSync(await (await save).path(),"utf8"), report.markdown);
  await assertNoOverflow();await page.screenshot({path:path.join(output,"desktop-report.png"),fullPage:true});
  await page.setViewportSize({width:390,height:844});await assertNoOverflow();
  await page.getByRole("region",{name:"研究报告"}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,"mobile-report.png")});
  pass("task tree and matrix cover plan status, missing and conflicting evidence, both exact source quotes and comparison rows; Markdown matches; desktop and 390px fit");
  await page.getByLabel("研究问题",{exact:true}).fill("检索一个可取消的任务");
  await one("开始研究").click();await page.waitForURL("**/research?task=task-2");await one("取消任务").click();
  await page.getByText("已提交取消请求，等待执行器确认。").waitFor();
  assert.ok(cancelAcknowledged);assert.notEqual(states.get("task-2").status,"cancelled");
  append("task-2","cancelled","cancelled");
  await page.locator(".research-run .research-state").getByText("已取消").waitFor();
  assert.equal(await one("取消任务").count(),0);
  user=72;await page.reload();await page.getByText("任务不存在或当前账户无权查看。").waitFor();
  assert.equal(await page.locator(".research-source").count(),0);
  assert.deepEqual(outbound,[]);assert.deepEqual(errors,[]);
  pass("cancel waits for worker acknowledgement; other account sees no task or private source");
}finally{await browser.close();}
