import assert from "node:assert/strict";
import {randomBytes, randomUUID} from "node:crypto";
import {mkdirSync} from "node:fs";
import {createRequire} from "node:module";
import path from "node:path";

const origin=process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname,"127.0.0.1");
const info=await (await fetch(origin+"/api/research-demo/info")).json();
assert.equal(info.corpus,"fixture");
const {chromium}=createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const browser=await chromium.launch({headless:true,executablePath:process.env.SCHOLARLENS_CHROME});
const output=process.env.SCHOLARLENS_RESEARCH_OUTPUT;
try{
  const ctx=await browser.newContext();
  const errors=[];
  await ctx.route("**/*",r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
  const credentials={username:"e9-"+randomUUID(),password:randomBytes(18).toString("hex")};
  assert.equal((await ctx.request.post(origin+"/api/auth/register",{data:credentials})).status(),201);
  const {access_token}=await (await ctx.request.post(origin+"/api/auth/login",{data:credentials})).json();
  const page=await ctx.newPage();
  page.on("pageerror",e=>errors.push(e.message));
  await page.goto(origin+"/research");
  await page.evaluate(t=>sessionStorage.setItem("scholarlens-session",t),access_token);
  await page.reload();
  await page.getByLabel("研究问题",{exact:true}).fill('Quote the first sentence of the abstract of "Cedar ranking trial" and give its PDF page number.');
  await page.getByText("本库论文范围",{exact:true}).click();
  await page.getByLabel("限定论文 ID").fill("fixture:cedar");
  await page.getByRole("button",{name:"开始研究",exact:true}).click();
  const region=page.getByRole("region",{name:"字段核验"});
  await region.waitFor({timeout:60000});
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:900});
    await region.scrollIntoViewIfNeeded();
    assert.equal(await region.locator("summary").count(),2);
    const limited=region.locator("details").filter({hasText:"来源不能提供所需信息"});
    await limited.locator("summary").click();
    assert.match(await limited.innerText(),/source_capability_mismatch/);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    if(output){mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,"field-"+width+".png")});}
    await limited.locator("summary").click();
  }
  const id=new URL(page.url()).searchParams.get("task");
  const report=await(await ctx.request.get(origin+"/api/research/tasks/"+id+"/report",{headers:{Authorization:"Bearer "+access_token}})).json();
  assert.equal(report.answerability.status,"partially_answerable");
  assert.equal(report.answerability.bindings.length,1);
  assert.deepEqual(errors,[]);
  console.log("PASS: actual authenticated task, two fields, original-source binding, desktop and phone");
}finally{await browser.close();}
