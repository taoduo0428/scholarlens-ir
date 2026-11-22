/** Follow the real indexed-paper journey on a running loopback ScholarLens product. */
import assert from "node:assert/strict";
import {createHash, randomUUID} from "node:crypto";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import path from "node:path";

const origin = new URL(process.env.SCHOLARLENS_URL).origin;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const output = path.resolve(process.env.SCHOLARLENS_RESEARCH_OUTPUT || "output/v7/real-workbench");
await mkdir(output, {recursive:true});
const title = "Factors responsible for high arsenic concentrations in two groundwater catchments in Taiwan";
const goal = process.env.SCHOLARLENS_JOURNEY_GOAL
  || "What does the abstract report about groundwater arsenic in the two catchments in Taiwan? Cite the source.";
const sha = text => createHash("sha256").update(text).digest("hex");
const personal = process.env.SCHOLARLENS_JOURNEY_MODE === "personal_model";
const config = personal ? {url:process.env.AI_BASE_URL,model:process.env.AI_MODEL,key:process.env.AI_API_KEY} : null;
if (personal) {
  assert.ok(config.url && config.model && config.key, "personal_model requires AI_BASE_URL, AI_MODEL and AI_API_KEY");
  const provider = new URL(config.url);
  assert.ok(provider.protocol === "https:" && !provider.username && !provider.password
    && !provider.search && !provider.hash, "expected a credential-free HTTPS base URL");
  delete process.env.DEBUG;
  delete process.env.PWDEBUG;
  delete process.env.AI_API_KEY;
}
const {chromium} = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({headless:true, executablePath:process.env.SCHOLARLENS_CHROME});
let stage = "setup", activePage, catalogSize = null;
try {
  const ctx = await browser.newContext({viewport:{width:1440,height:960}, reducedMotion:"reduce"});
  await ctx.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const stats = await ctx.request.get(origin + "/api/stats");
  assert.equal(stats.status(), 200);
  const corpus = await stats.json();
  assert.equal(corpus.status, "real");
  assert.equal(corpus.indexed, 859);
  const page = await ctx.newPage();
  activePage = page;
  const faults = [];
  page.on("pageerror", error => faults.push(error.name));
  const username = "journey-" + randomUUID();
  const password = randomUUID();
  await page.goto(origin + "/account");
  await page.getByRole("button", {name:"创建账户",exact:true}).click();
  await page.locator("#account-username").fill(username);
  await page.locator("#account-password").fill(password);
  const registration = page.waitForResponse(r => new URL(r.url()).pathname === "/api/auth/register");
  const login = page.waitForResponse(r => new URL(r.url()).pathname === "/api/auth/login");
  await page.locator("form button[type=submit]").click();
  assert.equal((await registration).status(), 201);
  assert.equal((await login).status(), 200);
  await page.getByRole("button", {name:"退出登录"}).waitFor();

  if (personal) {
    stage = "personal_settings";
    await page.goto(origin + "/assistant");
    await page.getByRole("button", {name:"API 设置",exact:true}).click();
    await page.getByLabel("个人API地址", {exact:true}).fill(config.url);
    await page.getByLabel("个人API密钥", {exact:true}).fill(config.key);
    stage = "fetch_catalog";
    const nextCatalog = page.waitForResponse(r => new URL(r.url()).pathname === "/api/ai/models");
    await page.getByRole("button", {name:"获取模型",exact:true}).click();
    const catalog = await nextCatalog;
    stage = "catalog_http_" + catalog.status();
    assert.ok(catalog.ok());
    const {models} = await catalog.json();
    stage = "model_selection";
    assert.ok(Array.isArray(models) && models.includes(config.model));
    catalogSize = models.length;
    await page.getByLabel("筛选服务商模型", {exact:true}).fill(config.model);
    await page.getByRole("checkbox", {name:"添加 " + config.model,exact:true}).check();
    await page.getByRole("button", {name:"加入可选模型（1）",exact:true}).click();
    await page.getByLabel("个人API模型", {exact:true}).selectOption(config.model);
    await page.getByRole("button", {name:"保存个人配置",exact:true}).click();
    await page.getByRole("status").filter({hasText:"配置已保存"}).waitFor();
  }
  stage = "paper_search";
  await page.goto(origin + "/");
  const search = page.getByLabel("论文关键词", {exact:true});
  await search.fill(title);
  await search.press("Enter");
  const hit = page.locator(".paper-title-link").filter({hasText:title}).first();
  await hit.waitFor({timeout:30000});
  const href = await hit.getAttribute("href");
  const paperId = decodeURIComponent(href.substring("/paper/".length));
  assert.match(paperId, /^source-sha256:[0-9a-f]{64}$/);
  await page.screenshot({path:path.join(output, "01-search.png")});
  await hit.click();
  await page.getByRole("heading", {name:title,exact:true}).waitFor();
  const paper = await ctx.request.get(origin + "/api/papers/" + encodeURIComponent(paperId));
  assert.equal(paper.status(), 200);
  assert.equal(paper.headers()["x-scholarlens-data-status"], "real");
  const article = await paper.json();
  assert.equal(article.paper_id, paperId);

  await page.goto(origin + "/research");
  stage = "choose_research_mode";
  if (personal) {
    const picker = page.getByRole("combobox", {name:"研究模式",exact:true});
    await picker.selectOption("personal_model");
    assert.equal(await picker.inputValue(), "personal_model");
    stage = "research_configuration_loaded";
    await page.getByText("已配置模型 " + config.model, {exact:false}).first().waitFor();
  }
  stage = "fill_research_question";
  await page.getByLabel("研究问题", {exact:true}).fill(goal);
  await page.getByText("本库论文范围", {exact:true}).click();
  await page.getByLabel("限定论文 ID").fill(paperId);
  stage = "research_submit_enabled";
  const start = page.getByRole("button", {name:"开始研究",exact:true});
  assert.ok(await start.isEnabled());
  const created = page.waitForResponse(r => r.request().method() === "POST"
    && new URL(r.url()).pathname === "/api/research/tasks");
  created.catch(() => {});
  const reportResponse = page.waitForResponse(r => r.ok()
    && /\/api\/research\/tasks\/[a-f0-9-]+\/report$/.test(new URL(r.url()).pathname), {timeout:240000});
  // Keep rejection handled if the create request fails before the report is requested.
  reportResponse.catch(() => {});
  stage = "submit_task_http";
  await start.click();
  const createdResponse = await created;
  stage = "task_http_" + createdResponse.status();
  assert.equal(createdResponse.status(), 202);
  const id = (await createdResponse.json()).task_id;
  await page.waitForURL(origin + "/research?task=" + id);
  stage = "waiting_for_report";
  const report = await (await reportResponse).json();
  const region = page.getByRole("region", {name:"研究报告",exact:true});
  await region.waitFor();
  await region.getByRole("button", {name:"查看 Markdown 原稿"}).click();
  assert.equal(await region.locator(".research-markdown").textContent(), report.markdown);
  stage = "validating_sources";
  const selected = report.sources ?? [];
  const locators = [];
  for (const source of selected) {
    assert.equal(source.paper_id, paperId);
    const match = /^(title|abstract|fulltext):chars:(\d+)-(\d+)$/.exec(source.locator);
    assert.ok(match, "unrecognized source locator");
    const text = [...article[match[1]]];
    assert.ok(source.quote && +match[3] <= text.length && +match[2] < +match[3]);
    assert.ok(text.slice(+match[2],+match[3]).join("").includes(source.quote));
    locators.push(source.locator);
  }
  let readerOpened = false;
  if (selected.length) {
    const detail = region.locator("details.research-source").first();
    await detail.locator("summary").click();
    const opened = ctx.waitForEvent("page");
    await detail.getByRole("link", {name:"定位到论文原文"}).click();
    const reader = await opened;
    await reader.getByText(/已核对并定位原文/).waitFor();
    await reader.screenshot({path:path.join(output, "03-source.png")});
    await reader.close();
    readerOpened = true;
  } else {
    assert.match(await region.innerText(), /缺少|证据不足|不足以|尚无|不支持/);
  }
  await region.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output, "02-report.png")});
  const downloading = page.waitForEvent("download");
  await region.getByRole("button", {name:"导出 Markdown"}).click();
  const download = await downloading;
  stage = "verifying_download";
  assert.equal(download.suggestedFilename(), "ScholarLens-" + id + ".md");
  const outputFile = path.join(output, download.suggestedFilename());
  await download.saveAs(outputFile);
  const markdown = await readFile(outputFile, "utf8");
  assert.equal(markdown, report.markdown);
  assert.equal((await ctx.request.get(origin + "/api/research/tasks/" + id + "/report")).status(), 401);
  assert.deepEqual(faults, []);
  let providerReceipts = null;
  if (personal) {
    providerReceipts = await page.evaluate(async id => {
      const response = await fetch("/api/research/tasks/" + id, {headers:{
        Authorization:"Bearer " + sessionStorage.getItem("scholarlens-session"),
      }});
      if (!response.ok) return null;
      const {provider_usage} = await response.json();
      return Array.isArray(provider_usage) ? provider_usage.length : null;
    }, id);
  }
  const summary = {browser:browser.version(), origin, indexed:corpus.indexed, dataset:corpus.status,
    account_register:201, login:200, paper_id:paperId, title, question:goal, task_id:id,
    report_status:report.status, answerability:report.answerability?.status ?? null,
    verified_source_locations:locators, reader_opened:readerOpened, report_filename:download.suggestedFilename(),
    report_bytes:Buffer.byteLength(markdown), report_sha256:sha(markdown), model_calls:report.spending?.model_calls,
    mode:personal ? "personal_model" : "evidence_only", selected_model:personal ? config.model : null,
    catalog_size:catalogSize, provider_receipts:providerReceipts,
    input_tokens:report.spending?.input_tokens ?? null, output_tokens:report.spending?.output_tokens ?? null,
    page_errors:faults.length, anonymous_report:401};
  await writeFile(path.join(output, "journey.json"), JSON.stringify(summary,null,2) + "\n");
  console.log(JSON.stringify(summary));
  if (personal) {
    stage = "provider_evidence";
    assert.ok(report.spending?.model_calls > 0 && providerReceipts > 0);
  }
} catch (error) {
  if (!personal) throw error;
  // Playwright errors can include field input values. Emit only the fixed stage.
  console.error("Personal-model browser acceptance stopped at " + stage);
  process.exitCode = 1;
} finally {
  if (personal && activePage && !activePage.isClosed()) {
    await activePage.evaluate(() => {sessionStorage.clear(); localStorage.clear();}).catch(() => {});
    config.key = "";
  }
  await browser.close();
}
