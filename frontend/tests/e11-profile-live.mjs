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
  await page.getByText("引用 PDF 表格单元格（可选）", {exact:true}).click();
  await page.getByLabel("表格所属论文").selectOption("ui:wave");
  const layoutResponse = page.waitForResponse(r=>r.url().includes("/pdf/layout/"));
  await page.getByRole("button", {name:"读取本页表格"}).click();
  const layout = await layoutResponse;
  assert.equal(layout.status(), 200);
  const pageLayout = await layout.json();
  assert.ok(pageLayout.items.some(item=>item.kind==="cell" && item.quote==="87"));
  assert.equal(pageLayout.figure_caption_links.length, 1);
  const figure = page.locator("details").filter({has:page.locator(":scope > summary", {hasText:"图 1 · 第 1 页题注"})}).last();
  await figure.locator(":scope > summary").click();
  assert.ok((await figure.innerText()).includes("Figure 1. Synthetic image"));
  assert.ok((await figure.innerText()).includes(pageLayout.figure_caption_links[0].caption_locator));
  assert.ok((await figure.innerText()).includes(pageLayout.figure_caption_links[0].figure_locator));
  await page.getByLabel("PDF 页码").fill("2");
  const nextPage = page.waitForResponse(r=>r.url().includes("/pdf/layout/2"));
  await page.getByRole("button", {name:"读取本页表格"}).click();
  const nextLayout = await (await nextPage).json();
  assert.equal(nextLayout.table_continuations.length, 1);
  const continued = page.locator("details").filter({has:page.locator(":scope > summary", {hasText:"表 1 续表 · 第 1–2 页"})}).last();
  await continued.locator(":scope > summary").click();
  const link = nextLayout.table_continuations[0];
  for (const value of [...link.headers, link.previous.table_locator, link.current.table_locator])
    assert.ok((await continued.innerText()).includes(value));
  const picker = page.getByRole("combobox", {name:/^引用单元格/});
  await picker.waitFor();
  const target = picker.locator("option").filter({hasText:/行 2 · 列 2 · 64/});
  await picker.selectOption(await target.getAttribute("value"));
  await page.getByRole("button", {name:"开始研究",exact:true}).click();
  const region = page.getByRole("region", {name:"逐篇研究档案"});
  await region.waitFor({timeout:60000});
  const reportURL = origin + "/api/research/tasks/" + new URL(page.url()).searchParams.get("task") + "/report";
  const headers = {Authorization:"Bearer " + token};
  const reportResponse = await context.request.get(reportURL, {headers});
  assert.equal(reportResponse.status(), 200);
  const report = await reportResponse.json();
  assert.deepEqual(report.research_profiles.map(p => p.paper_id).sort(), [...info.example_paper_ids].sort());
  const selected = report.pdf_cell_evidence;
  assert.equal(selected.status, "source_verified");
  assert.equal(selected.cell.quote, "64");
  assert.equal(selected.cell.page, 2);
  assert.equal(selected.cell.row, 2);
  assert.equal(selected.cell.column, 2);
  const published = page.getByRole("region", {name:"指定 PDF 单元格"});
  assert.ok((await published.innerText()).includes(selected.cell.locator));
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name:"导出 Markdown"}).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const buffers = [];
  for await (const chunk of stream) buffers.push(chunk);
  const markdown = Buffer.concat(buffers).toString("utf8");
  assert.equal(markdown, report.markdown);
  assert.ok(markdown.includes("64") && markdown.includes("指定 PDF 单元格"));
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
  await page.getByText("项目运行统计", {exact:true}).click();
  const dashboard = page.getByRole("region", {name:"项目运行统计"});
  await dashboard.waitFor();
  assert.match(await dashboard.innerText(), /profile-qa · 最近 1 个任务/);
  assert.match(await dashboard.innerText(), /模型调用 0 次/);
  await page.getByText("任务追踪", {exact:true}).click();
  assert.match(await page.locator("details[open]").allTextContents().then(x=>x.join(" ")), /任务 ID /);
  const other = await account();
  const otherMetrics = await context.request.get(origin + "/api/research/workspaces/personal/projects/profile-qa/metrics",
    {headers:{Authorization:"Bearer " + other}});
  assert.equal(otherMetrics.status(), 200);
  assert.equal((await otherMetrics.json()).tasks, 0);
  assert.equal((await context.request.get(reportURL, {headers:{Authorization:"Bearer " + other}})).status(), 404);
  await page.reload();
  await region.waitFor();
  assert.equal(await region.locator("summary").count(), report.research_profiles.length);
  assert.deepEqual(errors, []);
  console.log("PASS", report.research_profiles.length, "profiles;", verified, "quote/locator pairs; selected cell; report downloaded; restored; access isolated");
} finally {
  await browser.close();
}
