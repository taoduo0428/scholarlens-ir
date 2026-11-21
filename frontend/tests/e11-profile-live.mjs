import assert from "node:assert/strict";
import {randomBytes, randomUUID} from "node:crypto";
import {createRequire} from "node:module";

const origin = process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const info = await (await fetch(origin + "/api/research-demo/info")).json();
assert.equal(info.corpus, "profile-fixture");
const {chromium} = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({headless:true, executablePath:process.env.SCHOLARLENS_CHROME});
try {
  const context = await browser.newContext();
  await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  async function account() {
    const data = {username:"profile-" + randomUUID(), password:randomBytes(20).toString("hex")};
    assert.equal((await context.request.post(origin + "/api/auth/register", {data})).status(), 201);
    const login = await context.request.post(origin + "/api/auth/login", {data});
    assert.equal(login.status(), 200);
    return (await login.json()).access_token;
  }
  const token = await account();
  const page = await context.newPage();
  let errors = [];
  page.on("pageerror", err => errors.push(err.message));
  await page.goto(origin + "/research");
  await page.evaluate(value => sessionStorage.setItem("scholarlens-session", value), token);
  await page.reload();
  await page.getByLabel("研究问题", {exact:true}).fill("综合这两篇论文各自的方法和主要结果。");
  await page.getByLabel("研究项目（可选）").fill("profile-qa");
  await page.getByText("本库论文范围", {exact:true}).click();
  await page.getByLabel("限定论文 ID").fill(info.example_paper_ids.join(","));
  await page.getByRole("button", {name:"开始研究",exact:true}).click();
  const region = page.getByRole("region", {name:"逐篇研究档案"});
  await region.waitFor({timeout:60000});
  const reportURL = origin + "/api/research/tasks/" + new URL(page.url()).searchParams.get("task") + "/report";
  const headers = {Authorization:"Bearer " + token};
  const reportResponse = await context.request.get(reportURL, {headers});
  assert.equal(reportResponse.status(), 200);
  const report = await reportResponse.json();
  assert.deepEqual(report.research_profiles.map(p => p.paper_id).sort(), [...info.example_paper_ids].sort());
  let verified = 0;
  for (const profile of report.research_profiles) {
    const section = region.locator("details").filter({has:page.getByText(profile.title, {exact:true})});
    await section.locator("summary").click();
    const text = await section.innerText();
    for (const quote of Object.values(profile.fields).flat()) {
      assert.ok(text.includes(quote.quote) && text.includes(quote.locator));
      verified++;
    }
  }
  assert.ok(verified > 0);
  const other = await account();
  assert.equal((await context.request.get(reportURL, {headers:{Authorization:"Bearer " + other}})).status(), 404);
  await page.reload();
  await region.waitFor();
  assert.equal(await region.locator("summary").count(), report.research_profiles.length);
  assert.deepEqual(errors, []);
  console.log("PASS", report.research_profiles.length, "profiles;", verified, "quote/locator pairs; restored; access isolated");
} finally {
  await browser.close();
}
