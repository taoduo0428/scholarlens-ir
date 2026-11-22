import assert from "node:assert/strict";
import {randomUUID} from "node:crypto";
import {createRequire} from "node:module";

const mode = process.argv[2];
const origin = process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const {chromium} = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({headless:true, executablePath:process.env.SCHOLARLENS_CHROME});
try {
  const context = await browser.newContext({permissions:["clipboard-read","clipboard-write"]});
  const attempts = [];
  let deny = false;
  await context.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname.startsWith("/jaeger/trace/") && request.isNavigationRequest()) {
      const h = await request.allHeaders();
      attempts.push({path:url.pathname, search:url.search, auth:!!h.authorization, referrer:!!h.referer});
      if (deny) return route.fulfill({status:403, contentType:"text/plain", body:"Viewer gateway denied access"});
    }
    return route.continue();
  });
  async function account() {
    const user = {username:"trace-" + randomUUID(), password:randomUUID()};
    assert.equal((await context.request.post(origin+"/api/auth/register", {data:user})).status(),201);
    const resp = await context.request.post(origin+"/api/auth/login", {data:user});
    return {...user, token:(await resp.json()).access_token};
  }
  const owner = await account(), other = await account();
  const auth = {Authorization:"Bearer "+owner.token};
  const info = await (await context.request.get(origin+"/api/research-demo/info")).json();
  assert.equal(info.corpus, "seed");
  const task = await context.request.post(origin+"/api/research/tasks", {
    headers:{...auth, "Idempotency-Key":randomUUID()},
    data:{goal:"综合这两篇论文各自的方法和主要结果。", scope:{paper_ids:info.example_paper_ids}},
  });
  assert.equal(task.status(),202);
  const taskId = (await task.json()).task_id;
  const detail = origin+"/api/research/tasks/"+taskId;
  const page = await context.newPage();
  async function login(user) {
    if (page.url() !== origin+"/account") await page.goto(origin+"/account");
    await page.locator("#account-username").fill(user.username);
    await page.locator("#account-password").fill(user.password);
    await page.locator("form button[type=submit]").click();
    await page.getByRole("button",{name:"退出登录"}).waitFor();
  }
  const taskUrl = origin+"/research?task="+taskId+"&viewer=https%3A%2F%2Fwrong.invalid";
  await login(owner);
  await page.goto(taskUrl);
  await page.getByText("任务追踪",{exact:true}).click();
  const copy = page.getByRole("button",{name:"复制追踪 ID"});
  await copy.waitFor();
  const ids = (await (await context.request.get(detail,{headers:auth})).json()).trace_ids;
  assert.equal(ids.length,1);
  await copy.click();
  await page.getByText("已复制追踪 ID",{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),ids[0]);
  const link = page.getByRole("link",{name:"在 Jaeger 查看"});
  let renderedSpans = 0;
  if (mode === "configured") {
    const target = "/jaeger/trace/"+ids[0];
    const api = "/jaeger/api/v3/traces/"+ids[0];
    assert.equal(await link.getAttribute("href"),target);
    // The first batch may still be buffered when the report becomes visible.
    await page.getByRole("region",{name:"研究报告"}).waitFor({timeout:60000});
    const deadline = Date.now()+15000;
    while (Date.now() < deadline) {
      const ready = await context.request.get(origin+api);
      if (ready.ok() && (await ready.text()).includes("research.workflow")) break;
      await new Promise(resolve=>setTimeout(resolve,150));
    }
    const opened = context.waitForEvent("page");
    await link.click();
    const viewer = await opened;
    await viewer.waitForURL(origin+target);
    await viewer.getByText("research.api",{exact:true}).first().waitFor({timeout:20000});
    assert.equal(await viewer.evaluate(()=>window.opener),null);
    const query = await context.request.get(origin+api);
    const batch = await query.json();
    const spans = batch.result.resourceSpans.flatMap(r=>r.scopeSpans.flatMap(s=>s.spans));
    assert.ok(spans.length>0 && spans.every(s=>s.traceId===ids[0]));
    renderedSpans = spans.length;
    await viewer.close();
    deny = true;
    const denied = context.waitForEvent("page");
    await link.click();
    const rejected = await denied;
    await rejected.getByText("Viewer gateway denied access",{exact:true}).waitFor();
    await rejected.close();
    await copy.click();
    assert.deepEqual(attempts, Array(2).fill({path:target, search:"", auth:false, referrer:false}));
  } else {
    assert.equal(mode,"default");
    assert.equal(await link.count(),0);
    await page.getByText("当前环境未配置 Jaeger 查看地址。",{exact:true}).waitFor();
    assert.deepEqual(attempts,[]);
  }
  await page.evaluate(()=>Object.defineProperty(navigator,"clipboard",{value:undefined,configurable:true}));
  await copy.click();
  await page.getByText("请选中上方追踪 ID，手动复制。",{exact:true}).waitFor();
  await page.getByRole("region",{name:"研究报告"}).waitFor({timeout:60000});
  const downloadStarted = page.waitForEvent("download");
  await page.getByRole("button",{name:"导出任务 ZIP"}).click();
  const download = await downloadStarted;
  assert.equal(download.suggestedFilename(),"research-"+taskId+".zip");
  await download.saveAs(process.env.SCHOLARLENS_QA_ZIP);
  const erase = page.getByRole("button",{name:"删除任务",exact:true});
  await erase.click();
  await page.getByRole("button",{name:"保留任务"}).click();
  assert.ok((await context.request.get(detail,{headers:auth})).ok());
  await erase.click();
  await page.route(detail+"?*", async route=>{
    assert.equal(route.request().method(),"DELETE");
    const request = await route.fetch({url:detail+"?revision=0"});
    assert.equal(request.status(),409);
    await route.fulfill({response:request});
  }, {times:1});
  await page.getByRole("button",{name:"确认永久删除"}).click();
  await page.getByRole("alert").filter({hasText:"修订号"}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get("task"),taskId);
  await page.goto(origin+"/account");
  await page.getByRole("button",{name:"退出登录"}).click();
  await page.getByLabel("用户名",{exact:true}).waitFor();
  await login(other);
  const deniedDetail = page.waitForResponse(r=>r.url()===detail);
  await page.goto(taskUrl);
  assert.equal((await deniedDetail).status(),404);
  await page.getByText("任务不存在或当前账户无权查看。",{exact:true}).waitFor();
  assert.equal(await page.getByText(ids[0],{exact:true}).count(),0);
  assert.equal(await link.count(),0);
  assert.equal(await page.getByRole("button",{name:"导出任务 ZIP"}).count(),0);
  assert.equal(await erase.count(),0);
  const otherHeaders = {Authorization:"Bearer "+other.token};
  assert.equal((await context.request.get(detail+"/export",{headers:otherHeaders})).status(),404);
  const separate = await context.request.post(origin+"/api/research/tasks", {
    headers:{...otherHeaders, "Idempotency-Key":randomUUID()},
    data:{goal:"描述这项研究的方法。",scope:{paper_ids:info.example_paper_ids.slice(0,1)}}});
  assert.equal(separate.status(),202);
  const separateId = (await separate.json()).task_id;
  await page.goto(origin+"/research?task="+separateId);
  await page.getByRole("button",{name:"导出任务 ZIP"}).waitFor();
  await page.goto(origin+"/account");
  await page.getByRole("button",{name:"退出登录"}).click();
  await page.locator("#account-username").waitFor();
  await login(owner);
  await page.goto(taskUrl);
  await erase.click();
  const deleteReply = page.waitForResponse(r=>r.request().method()==="DELETE" && r.url().startsWith(detail+"?revision="));
  await page.getByRole("button",{name:"确认永久删除"}).click();
  assert.equal((await deleteReply).status(),204);
  await page.getByText("创建或选择一项任务后可查看计划、证据和报告。",{exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get("task"),null);
  assert.equal((await context.request.get(detail,{headers:auth})).status(),404);
  assert.equal((await context.request.get(detail+"/export",{headers:auth})).status(),404);
  assert.equal((await context.request.get(origin+"/api/research/tasks/"+separateId,{headers:otherHeaders})).status(),200);
  console.log(JSON.stringify({mode,browser:browser.version(),queried_spans:renderedSpans,
    gateway_navigations:attempts.length,copy:"passed",manual_copy:"passed",other_account_status:404,
    saved_task:taskId,retained_after_cancel:true,stale_revision:409,confirmed_delete:204,other_task:200}));
} finally {
  await browser.close();
}
