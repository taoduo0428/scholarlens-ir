import assert from "node:assert/strict";
import {randomBytes, randomUUID} from "node:crypto";
import {readFile} from "node:fs/promises";
import {createRequire} from "node:module";

const origin = process.env.SCHOLARLENS_URL;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const records = JSON.parse(await readFile(new URL("../../docs/agent-v7/figure-legend-semantics-results.json", import.meta.url)));
const {chromium} = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({headless: true, executablePath: process.env.SCHOLARLENS_CHROME});
try {
  const context = await browser.newContext();
  await context.route("**/*", route =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const data = {username: "legend-" + randomUUID(), password: randomBytes(20).toString("hex")};
  assert.equal((await context.request.post(origin + "/api/auth/register", {data})).status(), 201);
  const login = await context.request.post(origin + "/api/auth/login", {data});
  assert.equal(login.status(), 200);
  const page = await context.newPage();
  const errors = [];
  const serverErrors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", r => { if (r.status() >= 500) serverErrors.push(new URL(r.url()).pathname); });
  await page.goto(origin + "/research");
  await page.evaluate(value => sessionStorage.setItem("scholarlens-session", value), (await login.json()).access_token);
  await page.reload();
  await page.getByText("本库论文范围", {exact:true}).click();
  await page.getByLabel("限定论文 ID").fill("figure-eval-paper");
  await page.getByText("引用 PDF 表格单元格（可选）", {exact:true}).click();
  const summary = page.getByText(/图 [56] · 图例文字（OCR）/);
  const tested = [];
  async function readPage(n) {
    await page.getByLabel("PDF 页码").fill(String(n));
    const pending = page.waitForResponse(r => new URL(r.url()).pathname === "/api/papers/figure-eval-paper/pdf/layout/" + n);
    await page.getByRole("button", {name:"读取本页表格"}).click();
    return await pending;
  }
  for (const n of [9, 10]) {
    const expected = records.figures.find(row => row.page === n);
    const reply = await readPage(n);
    assert.equal(reply.status(), 200);
    const layout = await reply.json();
    assert.equal(layout.source_version, records.pdf_sha256);
    assert.equal(layout.paper_id, "figure-eval-paper");
    assert.equal(layout.figure_legends[0].rgb_sha256, expected.rgb_sha256);
    assert.equal(layout.figure_legends[0].caption_quote_sha256, expected.caption_sha256);
    await summary.click();
    const details = summary.locator("..");
    assert.ok((await details.innerText()).includes(expected.rgb_sha256));
    const rows = details.getByRole("listitem");
    assert.equal(await rows.count(), expected.entries.length);
    for (const [index, entry] of expected.entries.entries()) {
      const row = await rows.nth(index).innerText();
      for (const text of [entry.text, entry.color, entry.label_pdf_bbox.join(", ")]) assert.ok(row.includes(text));
    }
    tested.push({page:n, figure:expected.number, status:reply.status(), displayed_rows:expected.entries.length});
  }
  const unsupported = await readPage(6);
  assert.deepEqual((await unsupported.json()).figure_legends, []);
  await page.getByText("本页未识别出可核对的彩色图例。", {exact:true}).waitFor();
  assert.equal(await summary.count(), 0);
  const missing = await readPage(499);
  assert.equal(missing.status(), 422);
  const issue = (await missing.json()).error;
  assert.equal(issue.code, "layout_unavailable");
  await page.getByText(issue.message, {exact:true}).waitFor();
  assert.equal(await summary.count(), 0);
  assert.deepEqual(errors, []);
  assert.deepEqual(serverErrors, []);
  console.log(JSON.stringify({browser:browser.version(), fixture:"one paper metadata row; production layout route",
    pdf_sha256:records.pdf_sha256, supported:tested, line_key:{page:6,status:unsupported.status(),rows:0},
    missing_page:{page:499,status:422,code:issue.code,visible_message:issue.message},
    stale_legend_rows:0,page_errors:errors.length,http_5xx:serverErrors.length}));
} finally {
  await browser.close();
}
