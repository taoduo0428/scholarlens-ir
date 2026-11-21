/** Exercise the local demo's real HTTP API and worker, passing no provider credentials. */
import assert from "node:assert/strict";
import {mkdirSync, readFileSync} from "node:fs";
import {randomBytes,randomUUID} from "node:crypto";
import {createRequire} from "node:module";
import path from "node:path";

const origin=process.env.SCHOLARLENS_URL;
if(!origin || new URL(origin).hostname!=="127.0.0.1") throw Error("Set SCHOLARLENS_URL to a running local research demo");
const info=await (await fetch(origin+"/api/research-demo/info",{redirect:"error"})).json();
assert.equal(info.demo,"evoresearch-local");assert.equal(info.corpus,"fixture");
const out=path.resolve(process.env.SCHOLARLENS_RESEARCH_OUTPUT||"../output/live-workbench");
mkdirSync(out,{recursive:true});
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const browser=await chromium.launch({headless:true,executablePath:process.env.SCHOLARLENS_CHROME||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
const errors=[],outbound=[];
await ctx.route("**/*",route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin){outbound.push(url.origin);return route.abort();}
  return route.continue();
});
const page=await ctx.newPage();
page.on("pageerror",err=>errors.push(err.message));
async function newIdentity(){
  const api=ctx.request;
  const credentials={username:"demo-"+randomUUID(),password:randomBytes(18).toString("hex")};
  const created=await api.post(origin+"/api/auth/register",{data:credentials});assert.equal(created.status(),201);
  const login=await api.post(origin+"/api/auth/login",{data:credentials});assert.equal(login.status(),200);
  return (await login.json()).access_token;
}
try{
  const token=await newIdentity();
  await page.goto(origin+"/research");
  await page.evaluate(value=>sessionStorage.setItem("scholarlens-session",value), token);await page.reload();
  await page.getByLabel("研究问题",{exact:true}).fill("Compare Cedar and Birch ranking trial method, dataset, metric and protocol");
  await page.getByText("本库论文范围",{exact:true}).click();
  await page.getByLabel("限定论文 ID").fill(info.example_paper_ids.join(","));
  await page.getByRole("button",{name:"开始研究",exact:true}).click();
  await page.waitForURL("**/research?task=*");
  const id=new URL(page.url()).searchParams.get("task");
  const reportNode=page.getByRole("region",{name:"研究报告"});
  await reportNode.waitFor({timeout:60000});
  const headers={Authorization:"Bearer "+token};
  const detail=await (await ctx.request.get(origin+"/api/research/tasks/"+id,{headers})).json();
  const records=await (await ctx.request.get(origin+"/api/research/tasks/"+id+"/events",{headers})).json();
  const report=await (await ctx.request.get(origin+"/api/research/tasks/"+id+"/report",{headers})).json();
  assert.ok(["completed","partial"].includes(detail.state.status));
  assert.ok(report.sources.length>0&&report.claims.length>0);
  assert.ok(report.sections.not_comparable.length>0, "Cedar and Birch use incompatible evaluation conditions");
  assert.ok(report.sources.every(source => source.pdf_available === false && typeof source.fulltext_available === "boolean"),
    "Each fixture source must report its known PDF and full-text availability");
  assert.ok(records.events.length>3);
  assert.deepEqual(records.events.map(e=>e.seq),Array.from({length:records.events.length},(_,i)=>i+1));
  const taskPlan=page.getByRole("region",{name:"研究计划"});
  assert.equal(await taskPlan.locator("[data-plan-subtask]").count(),detail.state.subtasks.length);
  await taskPlan.locator("[data-plan-subtask] > summary").first().click();
  assert.ok((await taskPlan.innerText()).includes("完成条件"));
  const matrix=reportNode.getByRole("region",{name:"结论与证据矩阵"});
  for(const sub of detail.state.subtasks){
    const matching=await matrix.locator("[data-matrix-subtask]").evaluateAll((nodes,id)=>nodes.filter(n=>n.dataset.matrixSubtask===id).length,sub.id);
    assert.equal(matching,1);
    for(const claim of report.claims.filter(c=>c.subtask_id===sub.id)){
      const assigned=await matrix.locator("[data-claim]").evaluateAll((nodes,id)=>nodes.find(n=>n.dataset.claim===id)?.closest("[data-matrix-subtask]")?.dataset.matrixSubtask,claim.claim_id);
      assert.equal(assigned,sub.id);
    }
  }
  await reportNode.locator(".research-comparison > summary").click();
  const comparison=reportNode.getByRole("region",{name:"方法与实验对照表"});
  assert.ok((await comparison.innerText()).includes("实验条件不可比"));
  const source=matrix.locator(".research-claim > .research-source").first();
  await source.locator("summary").click();
  assert.ok((await source.innerText()).includes("PDF 未提供"));
  if (report.sources[0].fulltext_available === false) assert.ok((await source.innerText()).includes("正文缺失"));
  const quote=await source.locator("blockquote").innerText();
  const target=ctx.waitForEvent("page");await source.getByRole("link",{name:"定位到论文原文"}).click();
  const article=await target;await article.locator("#paper-evidence-match").waitFor();
  assert.equal(await article.locator("#paper-evidence-match").innerText(),quote);await article.close();
  const download=page.waitForEvent("download");
  await reportNode.getByRole("button",{name:"导出 Markdown"}).click();
  assert.equal(readFileSync(await(await download).path(),"utf8"),report.markdown);
  await reportNode.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,"live-desktop-report.png")});
  await page.setViewportSize({width:390,height:844});await page.reload();await reportNode.waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await reportNode.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,"live-mobile-report.png")});
  const secondToken=await newIdentity();const forbidden=await ctx.request.get(origin+"/api/research/tasks/"+id,{headers:{Authorization:"Bearer "+secondToken}});
  assert.equal(forbidden.status(),404);
  assert.deepEqual(errors,[]);assert.deepEqual(outbound,[]);
  console.log(JSON.stringify({corpus:info.corpus,worker_status:detail.state.status,
    stop_reason:detail.state.stop_reason,events:records.events.length,verified_sources:report.sources.length,
    claims:report.claims.length,sections:Object.fromEntries(Object.entries(report.sections).map(([k,v])=>[k,v.length])),
    matrix_subtasks:detail.state.subtasks.length,all_claims_linked:true,comparison_table:true,pdf_status_visible:true,source_highlight:true,markdown_exact:true,other_owner_http:forbidden.status(),viewport:390,page_errors:errors.length}));
}finally{await browser.close();}
