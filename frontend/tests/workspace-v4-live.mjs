/** Run against a caller-owned loopback fixture demo with the Lab experiment DB. */
import assert from "node:assert/strict";
import {randomBytes,randomUUID} from "node:crypto";
import {existsSync, mkdirSync,writeFileSync} from "node:fs";
import {createRequire} from "node:module";
import path from "node:path";
import {spawnSync} from "node:child_process";
const origin=process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname,"127.0.0.1");
const runtime=path.resolve(process.env.SCHOLARLENS_TEST_RUNTIME);
assert.ok(existsSync(path.join(runtime,".evoresearch-demo")));
const out=process.env.SCHOLARLENS_RESEARCH_OUTPUT;
mkdirSync(out,{recursive:true});
const info=await (await fetch(origin+"/api/research-demo/info")).json();
assert.equal(info.corpus,"fixture");
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const browser=await chromium.launch({headless:true,executablePath:process.env.SCHOLARLENS_CHROME});
const ctx=await browser.newContext({reducedMotion:"reduce"});
const page=await ctx.newPage(), errors=[],checks=[];
page.on("pageerror",e=>errors.push(e.message));
await ctx.route("**/*",r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());

async function identity(){
  const data={username:"v4-"+randomUUID(),password:randomBytes(20).toString("hex")};
  assert.equal((await ctx.request.post(origin+"/api/auth/register",{data})).status(),201);
  const login=await ctx.request.post(origin+"/api/auth/login",{data});
  assert.equal(login.status(),200);
  return {name:data.username,token:(await login.json()).access_token};
}
async function assertLayout(kind,width){
  const box=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(box.scroll<=box.width+1,JSON.stringify({kind,width,...box}));
  await page.screenshot({path:path.join(out,kind+"-"+width+".png")});
  checks.push({kind,width,scroll:box.scroll});
}
try{
  const operator=await identity(),other=await identity();
  const auth=t=>({Authorization:"Bearer "+t});
  const request=(url,t)=>ctx.request.get(origin+url,{headers:auth(t)});
  assert.equal((await request("/api/evolution-lab/index",other.token)).status(),403);
  const operatorSetup=spawnSync(process.env.SCHOLARLENS_PYTHON||"python",["-c",
    "import sys,sqlite3; db=sqlite3.connect(sys.argv[1]); assert db.execute(\"update users set role='admin' where username=? and role='user'\",(sys.argv[2],)).rowcount==1; db.commit()",
    path.join(runtime,"scholarlens.sqlite3"),operator.name]);
  assert.equal(operatorSetup.status,0,"could not provision the new isolated test account");
  const title=(await (await request("/api/papers/"+encodeURIComponent(info.example_paper_ids[0]),operator.token)).json()).title;
  await page.goto(origin+"/research");
  await page.evaluate(token=>sessionStorage.setItem("scholarlens-session",token),operator.token);
  await page.reload();
  await page.getByLabel("研究问题",{exact:true}).fill('Quote the first complete sentence of the abstract of "'+title+'".');
  await page.getByText("本库论文范围",{exact:true}).click();
  await page.getByLabel("限定论文 ID").fill(info.example_paper_ids[0]);
  await page.getByRole("button",{name:"开始研究",exact:true}).click();
  await page.waitForURL("**/research?task=*");
  const work=page.url(), id=new URL(work).searchParams.get("task");
  const report=page.getByRole("region",{name:"研究报告"});
  await report.waitFor({timeout:60000});
  const proof=(await (await request("/api/research/tasks/"+id+"/report",operator.token)).json()).answer_proof;
  assert.ok(proof.sufficient);
  assert.equal((await request("/api/research/tasks/"+id+"/report",other.token)).status(),404);
  for(const [width,height] of [[1440,960],[820,1180],[390,844]]){
    await page.setViewportSize({width,height});
    await page.goto(work);
    const contract=page.getByRole("region",{name:"答案契约"});
    await contract.waitFor();
    await contract.scrollIntoViewIfNeeded();
    await page.getByRole("region",{name:"最终答案与证据"}).waitFor();
    await assertLayout("workspace",width);
    await page.goto(origin+"/evolution-lab");
    const second=page.getByLabel("右侧版本");
    await second.selectOption("adaptive");
    const panels=page.locator(".lab-pair article");
    await panels.nth(1).getByRole("heading",{name:"adaptive",exact:true}).waitFor();
    await panels.first().getByText("执行动作",{exact:true}).click();
    assert.ok(await panels.first().locator("details[open] pre").first().isVisible());
    await page.getByRole("heading",{name:"同任务对照"}).scrollIntoViewIfNeeded();
    await assertLayout("lab",width);
  }
  assert.deepEqual(errors,[]);
  writeFileSync(path.join(out,"result.json"),JSON.stringify({checks,errors,sourceVerified:proof.sufficient,
    otherTaskStatus:404,otherLabStatus:403},null,2));
  console.log(JSON.stringify(checks));
}finally{await browser.close();}
