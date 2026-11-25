/**
 * Comprehensive Stage 7 real-backend browser E2E acceptance suite.
 * Covers auth, workspace/library/reload persistence, PDF upload, research project/task/DAG/
 * profiles/comparison/report/export, trace viewer, cost stats, cross-user isolation & permissions,
 * admin upload review + Evolution Lab, error/empty states, and mobile (390x844) responsiveness.
 */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const origin = new URL(process.env.SCHOLARLENS_URL).origin;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const output = path.resolve(process.env.SCHOLARLENS_E2E_OUTPUT || "output/release-v1/browser-e2e");
await mkdir(output, { recursive: true });
const samplePdfPath = process.env.SCHOLARLENS_SAMPLE_PDF;
const adminCredentials = process.env.SCHOLARLENS_ADMIN_USER
  ? { username: process.env.SCHOLARLENS_ADMIN_USER, password: process.env.SCHOLARLENS_ADMIN_PASSWORD }
  : null;

const { chromium } = createRequire(import.meta.url)(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.SCHOLARLENS_CHROME || undefined,
});

const PAPER_A_TITLE =
  "Factors responsible for high arsenic concentrations in two groundwater catchments in Taiwan";
const PAPER_B_TITLE =
  "Arsenic speciation in groundwater";

const receipt = {
  browser: browser.version(),
  origin,
  checks: {},
  screenshots: [],
  page_errors: [],
  console_errors: [],
};

try {
  // Verify unauthenticated access boundary before creating browser sessions
  const probeCtx = await browser.newContext();
  assert.equal((await probeCtx.request.get(origin + "/api/research/tasks")).status(), 401);
  assert.equal((await probeCtx.request.get(origin + "/api/me/workspace")).status(), 401);
  assert.equal((await probeCtx.request.get(origin + "/api/admin/uploads")).status(), 401);
  assert.equal((await probeCtx.request.get(origin + "/api/evolution-lab/governance")).status(), 401);
  receipt.checks.unauthenticated_401 = true;
  await probeCtx.close();

  // --- Session A: User Registration, Workspace, Search, Upload, Two-Paper Research ---
  const ctxA = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: "reduce" });
  await ctxA.route("**/*", (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort()
  );
  const pageA = await ctxA.newPage();
  pageA.on("pageerror", (err) => receipt.page_errors.push(String(err)));
  pageA.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("404") && !msg.text().includes("401") && !msg.text().includes("403")) {
      receipt.console_errors.push(msg.text());
    }
  });

  const userA = "e2ea-" + randomUUID().slice(0, 8);
  const passA = "PassA-" + randomUUID();
  await pageA.goto(origin + "/account");
  await pageA.getByRole("button", { name: "创建账户", exact: true }).click();
  await pageA.locator("#account-username").fill(userA);
  await pageA.locator("#account-password").fill(passA);
  const regResp = pageA.waitForResponse((r) => new URL(r.url()).pathname === "/api/auth/register");
  const loginResp = pageA.waitForResponse((r) => new URL(r.url()).pathname === "/api/auth/login");
  await pageA.locator("form button[type=submit]").click();
  assert.equal((await regResp).status(), 201);
  assert.equal((await loginResp).status(), 200);
  await pageA.getByRole("button", { name: "退出登录" }).waitFor();

  // Reload persistence check for Session A
  await pageA.reload();
  await pageA.getByRole("button", { name: "退出登录" }).waitFor();
  receipt.checks.register_login_and_reload = true;

  // Empty states check on Library & Research before adding items
  await pageA.goto(origin + "/library");
  await pageA.getByRole("heading", { name: "我的文献" }).waitFor();
  await pageA.goto(origin + "/research");
  await pageA.getByText("暂无研究任务。").waitFor();
  receipt.checks.empty_states_rendered = true;

  // Search paper A & paper B, test error/missing paper state, save paper A to library
  await pageA.goto(origin + "/paper/nonexistent-paper-e2e-check");
  await pageA.getByText(/没有找到|未找到|不存在|无法读取|不可用/).first().waitFor({ timeout: 15000 });
  receipt.checks.missing_paper_error_state = true;

  await pageA.goto(origin + "/");
  const searchInput = pageA.getByLabel("论文关键词", { exact: true });
  await searchInput.fill(PAPER_A_TITLE);
  await searchInput.press("Enter");
  const hitA = pageA.locator(".paper-title-link").filter({ hasText: PAPER_A_TITLE }).first();
  await hitA.waitFor({ timeout: 30000 });
  const paperAId = decodeURIComponent((await hitA.getAttribute("href")).substring("/paper/".length));

  // Also grab a second paper ID via API search to exercise cross-paper comparison
  const searchB = await ctxA.request.get(origin + "/api/search", { params: { q: "arsenic", page_size: 5 } });
  assert.equal(searchB.status(), 200);
  const hitsB = (await searchB.json()).results;
  const paperBId = (hitsB.find((h) => h.paper_id !== paperAId) || hitsB[0]).paper_id;
  assert.notEqual(paperAId, paperBId);

  // Visit paper A detail and favorite it, verify Library persistence across reload
  await hitA.click();
  await pageA.getByRole("heading", { name: PAPER_A_TITLE, exact: true }).waitFor();
  const favBtn = pageA.getByRole("button", { name: /加入收藏|收藏/ }).first();
  await favBtn.click();
  await pageA.waitForTimeout(900); // Allow workspace debounce sync
  await pageA.goto(origin + "/library");
  await pageA.getByText(PAPER_A_TITLE).first().waitFor({ timeout: 15000 });
  await pageA.reload();
  await pageA.getByText(PAPER_A_TITLE).first().waitFor({ timeout: 15000 });
  await pageA.screenshot({ path: path.join(output, "01-library-persisted.png") });
  receipt.screenshots.push("01-library-persisted.png");
  receipt.checks.workspace_and_library_persisted = true;

  // PDF Upload flow (when sample PDF fixture provided)
  if (samplePdfPath) {
    await pageA.goto(origin + "/upload");
    const fileInput = pageA.locator("input[type=file]").first();
    await fileInput.setInputFiles(samplePdfPath);
    const submitBtn = pageA.getByRole("button", { name: /提交审核/ });
    await submitBtn.waitFor({ timeout: 10000 });
    const upResp = pageA.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/uploads");
    await submitBtn.click();
    assert.equal((await upResp).status(), 201);
    await pageA.getByText("文件已提交，等待管理员审核。").waitFor({ timeout: 15000 });
    await pageA.screenshot({ path: path.join(output, "02-upload-pending.png") });
    receipt.screenshots.push("02-upload-pending.png");
    receipt.checks.pdf_upload_workflow = true;
  }

  // Create two-paper Research Task with Research Project -> check DAG, Profiles, Evidence, Report, Export, Trace, Cost
  await pageA.goto(origin + "/research");
  await pageA.getByLabel("研究问题", { exact: true }).fill(
    "Compare the research methods and reported findings of both papers on arsenic in groundwater with exact evidence."
  );
  await pageA.getByLabel(/研究项目/).fill("e2e-closure");
  await pageA.getByText("本库论文范围", { exact: true }).click();
  await pageA.getByLabel("限定论文 ID").fill(`${paperAId}, ${paperBId}`);
  const taskCreated = pageA.waitForResponse(
    (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/research/tasks"
  );
  const reportReady = pageA.waitForResponse(
    (r) => r.ok() && /\/api\/research\/tasks\/[a-f0-9-]+\/report$/.test(new URL(r.url()).pathname),
    { timeout: 180000 }
  );
  await pageA.getByRole("button", { name: "开始研究", exact: true }).click();
  const createdRes = await taskCreated;
  assert.equal(createdRes.status(), 202);
  const taskId = (await createdRes.json()).task_id;
  await pageA.waitForURL(origin + "/research?task=" + taskId);
  const reportJson = await (await reportReady).json();

  // Verify Report region, Question DAG, Profiles, Evidence, Trace Viewer, Project Metrics/Cost
  const reportRegion = pageA.getByRole("region", { name: "研究报告", exact: true });
  await reportRegion.waitFor({ timeout: 20000 });
  await pageA.getByRole("region", { name: "研究问题与证据" }).waitFor();
  await pageA.getByText(/工具调用 \d+ 次 · 模型调用 \d+ 次/).waitFor();
  await pageA.locator("details", { hasText: "项目运行统计" }).locator("summary").click();
  await pageA.getByRole("region", { name: "项目运行统计" }).waitFor({ timeout: 15000 });
  await pageA.locator("details", { hasText: "任务追踪" }).locator("summary").click();
  await pageA.getByText("任务 ID " + taskId).waitFor();

  // Open Research Profiles if rendered
  if (reportJson.research_profiles?.length) {
    const profileSec = pageA.getByRole("region", { name: "逐篇研究档案" });
    await profileSec.waitFor();
    await profileSec.locator("details summary").first().click();
  }
  // Open Read Evidence artifact
  const evButtons = pageA.getByRole("button", { name: /^读取证据 / });
  if ((await evButtons.count()) > 0) {
    await evButtons.first().click();
    await pageA.waitForTimeout(300);
  }
  await pageA.screenshot({ path: path.join(output, "03-research-report-dag.png"), fullPage: true });
  receipt.screenshots.push("03-research-report-dag.png");

  // Reload task page -> state persists
  await pageA.reload();
  await pageA.getByRole("region", { name: "研究报告", exact: true }).waitFor({ timeout: 20000 });
  receipt.checks.research_reload_persisted = true;

  // Export Markdown + ZIP
  const mdDlPromise = pageA.waitForEvent("download");
  await reportRegion.getByRole("button", { name: "导出 Markdown" }).click();
  const mdDl = await mdDlPromise;
  const mdPath = path.join(output, mdDl.suggestedFilename());
  await mdDl.saveAs(mdPath);
  assert.equal(await readFile(mdPath, "utf8"), reportJson.markdown);

  const zipDlPromise = pageA.waitForEvent("download");
  await pageA.getByRole("button", { name: "导出任务 ZIP" }).click();
  const zipDl = await zipDlPromise;
  const zipPath = path.join(output, zipDl.suggestedFilename());
  await zipDl.saveAs(zipPath);
  const zipBytes = await readFile(zipPath);
  assert.equal(zipBytes.subarray(0, 2).toString("ascii"), "PK");
  receipt.checks.research_dag_profiles_report_export_trace_cost = true;
  receipt.research_task_id = taskId;

  // Non-admin user A should be denied admin & evolution-lab APIs (403)
  const tokenA = await pageA.evaluate(() => sessionStorage.getItem("scholarlens-session"));
  assert.ok(tokenA);
  assert.equal(
    (await ctxA.request.get(origin + "/api/admin/uploads", { headers: { Authorization: "Bearer " + tokenA } })).status(),
    403
  );
  assert.equal(
    (await ctxA.request.get(origin + "/api/evolution-lab/governance", { headers: { Authorization: "Bearer " + tokenA } })).status(),
    403
  );
  receipt.checks.non_admin_forbidden_403 = true;

  // Mobile viewport responsiveness check (390x844)
  await pageA.setViewportSize({ width: 390, height: 844 });
  for (const route of ["/", "/library", "/research?task=" + taskId]) {
    await pageA.goto(origin + route);
    await pageA.waitForTimeout(400);
    const metrics = await pageA.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    assert.ok(
      metrics.scrollWidth <= metrics.clientWidth + 4,
      `Horizontal overflow on mobile ${route}: ${JSON.stringify(metrics)}`
    );
  }
  await pageA.screenshot({ path: path.join(output, "04-mobile-research.png") });
  receipt.screenshots.push("04-mobile-research.png");
  receipt.checks.mobile_responsive_layout = true;
  await ctxA.close();

  // --- Session B: Cross-user isolation check ---
  const ctxB = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
  const pageB = await ctxB.newPage();
  const userB = "e2eb-" + randomUUID().slice(0, 8);
  const passB = "PassB-" + randomUUID();
  await pageB.goto(origin + "/account");
  await pageB.getByRole("button", { name: "创建账户", exact: true }).click();
  await pageB.locator("#account-username").fill(userB);
  await pageB.locator("#account-password").fill(passB);
  await pageB.locator("form button[type=submit]").click();
  await pageB.getByRole("button", { name: "退出登录" }).waitFor();
  const tokenB = await pageB.evaluate(() => sessionStorage.getItem("scholarlens-session"));
  assert.equal(
    (await ctxB.request.get(origin + "/api/research/tasks/" + taskId, { headers: { Authorization: "Bearer " + tokenB } })).status(),
    404
  );
  assert.equal(
    (await ctxB.request.get(origin + "/api/research/tasks/" + taskId + "/report", { headers: { Authorization: "Bearer " + tokenB } })).status(),
    404
  );
  await pageB.goto(origin + "/research?task=" + taskId);
  await pageB.getByText("任务不存在或当前账户无权查看。").waitFor({ timeout: 15000 });
  receipt.checks.cross_user_isolation_404 = true;
  await ctxB.close();

  // --- Admin Session (when provisioned in isolated E2E test DB) ---
  if (adminCredentials) {
    const ctxAdmin = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: "reduce" });
    const pageAdmin = await ctxAdmin.newPage();
    await pageAdmin.goto(origin + "/account");
    await pageAdmin.locator("#account-username").fill(adminCredentials.username);
    await pageAdmin.locator("#account-password").fill(adminCredentials.password);
    await pageAdmin.locator("form button[type=submit]").click();
    await pageAdmin.getByRole("button", { name: "退出登录" }).waitFor();

    await pageAdmin.goto(origin + "/admin");
    await pageAdmin.getByRole("heading", { name: /审核|管理/ }).first().waitFor({ timeout: 15000 });
    await pageAdmin.screenshot({ path: path.join(output, "05-admin-console.png") });
    receipt.screenshots.push("05-admin-console.png");

    await pageAdmin.goto(origin + "/evolution-lab");
    await pageAdmin.getByRole("heading", { name: "Evolution Lab" }).waitFor({ timeout: 15000 });
    await pageAdmin.screenshot({ path: path.join(output, "06-evolution-lab.png") });
    receipt.screenshots.push("06-evolution-lab.png");
    receipt.checks.admin_and_evolution_lab_views = true;
    await ctxAdmin.close();
  }

  assert.deepEqual(receipt.page_errors, []);
  receipt.status = "PASS";
  await writeFile(path.join(output, "stage7-e2e-receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify(receipt));
} finally {
  await browser.close();
}
