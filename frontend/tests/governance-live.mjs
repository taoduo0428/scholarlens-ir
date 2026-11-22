import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFileSync} from "node:fs";

const origin = process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const [operator, member] = JSON.parse(readFileSync(0, "utf8"));
const {chromium} = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({headless:true, executablePath:process.env.SCHOLARLENS_CHROME});
try {
  const contexts = await Promise.all([browser.newContext(), browser.newContext()]);
  const faults = [];
  async function enter(context, credentials) {
    await context.route("**/*", route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const page = await context.newPage();
    page.on("pageerror", error => faults.push(error.message));
    await page.goto(origin + "/evolution-lab");
    await page.getByRole("link", {name:"登录实验室账户"}).click();
    await page.locator("#account-username").fill(credentials.username);
    await page.locator("#account-password").fill(credentials.password);
    const loggedIn = page.waitForResponse(r => r.url() === origin + "/api/auth/login");
    await page.locator("form button[type=submit]").click();
    const login = await loggedIn;
    assert.equal(login.status(), 200);
    const headers = {Authorization:"Bearer " + (await login.json()).access_token};
    await page.waitForURL(origin + "/evolution-lab");
    return {page, headers};
  }
  const admin = await enter(contexts[0], operator);
  const viewer = await enter(contexts[1], member);
  const url = origin + "/api/evolution-lab/governance";
  const denied = "该账户没有实验室访问权限。";
  const page = admin.page;
  await viewer.page.getByText(denied, {exact:true}).waitFor();
  assert.equal(await viewer.page.getByRole("heading", {name:"研究治理"}).count(), 0);
  assert.equal((await contexts[1].request.get(url, {headers:viewer.headers})).status(), 403);
  assert.equal((await contexts[1].request.get(url)).status(), 401);
  const result = await contexts[0].request.get(url, {headers:admin.headers});
  assert.equal(result.status(), 200);
  const summary = await result.json();
  assert.equal(summary.registry.status, "builtin");
  await page.getByRole("heading", {name:"同任务对照"}).waitFor();
  const runs = await (await contexts[0].request.get(origin + "/api/evolution-lab/index",
    {headers:admin.headers})).json();
  if (runs.runs.length) await page.getByText(/· 新增来源/).waitFor();
  await page.getByText(summary.registry.skill, {exact:true}).waitFor();
  await page.getByText(/^已登记的研究工具/).click();
  await page.getByText("verify_source_quote", {exact:true}).waitFor();
  await page.getByText("最近审批记录", {exact:true}).click();
  await page.getByText("暂无审批记录。", {exact:true}).waitFor();
  assert.equal((await contexts[0].request.post(url, {headers:admin.headers})).status(), 405);
  await page.getByRole("link", {name:"返回研究工作台"}).click();
  await page.getByRole("link", {name:"进入 Evolution Lab"}).click();
  await page.getByRole("heading", {name:"研究治理"}).waitFor();
  async function setRole(context, actor, id, role) {
    const reply = await context.request.patch(origin + "/api/admin/users/" + id, {
      headers:actor.headers, data:{role},
    });
    assert.equal(reply.status(), 200);
  }
  await setRole(contexts[0], admin, member.id, "admin");
  await setRole(contexts[1], viewer, operator.id, "user");
  assert.equal((await contexts[0].request.get(url, {headers:admin.headers})).status(), 403);
  await page.reload();
  await page.getByText(denied, {exact:true}).waitFor();
  assert.equal(await page.getByRole("heading", {name:"研究治理"}).count(), 0);
  await viewer.page.reload();
  await viewer.page.getByRole("heading", {name:"研究治理"}).waitFor();
  assert.deepEqual(faults, []);
  console.log(JSON.stringify({browser:browser.version(), anonymous:401, member:403, admin:200,
    admin_post:405, revoked_session:403, tools:summary.tools.length, replay_runs:runs.runs.length,
    admin_link:true, promoted_member_view:true, page_errors:0}));
} finally {
  await browser.close();
}
