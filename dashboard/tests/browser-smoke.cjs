"use strict";

const assert = require("node:assert/strict");
const {chromium} = require("playwright");

async function main() {
  const url = process.env.REPEL_DASHBOARD_URL;
  if (!url) throw new Error("Set REPEL_DASHBOARD_URL to the authenticated URL printed by repel dashboard.");
  const token = new URLSearchParams(new URL(url).hash.slice(1)).get("token");
  assert.ok(token, "The URL must include its session token.");
  const browser = await chromium.launch({headless: true, ...(process.env.REPEL_CHROME ? {executablePath: process.env.REPEL_CHROME} : {})});
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const page = await context.newPage(), errors = [], contentRequests = [], apiMethods = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/")) apiMethods.push(request.method());
      if (/\/api\/.*\/(preview|download)/.test(request.url())) contentRequests.push(request.url());
    });
    await page.goto(url);
    await page.waitForFunction(() => document.getElementById("workspace-repos").textContent !== "—");
    const response = await context.request.get(new URL("/api/summary", url).href, {headers: {Authorization: `Bearer ${token}`}});
    assert.equal(response.status(), 200);
    const summary = await response.json(), latest = new Map();
    assert.match(await page.locator("#data-context-title").innerText(), summary.template ? /Synthetic sample data/ : /journal · read-only/);
    for (const item of summary.deployments) if (!latest.has(item.repository)) latest.set(item.repository, item);
    assert.equal(await page.locator(".project-card").count(), latest.size);
    await page.waitForFunction((count) => document.querySelectorAll(".atlas-repo-row").length === count, latest.size);
    await page.locator('[data-atlas-mode="bytes"]').click();
    const tracks = [...latest.values()].reduce((total, item) => total + Math.min(item.metrics.placed_files, 256), 0);
    assert.equal(await page.locator(".byte-lane").count(), tracks);
    if (tracks) {
      const track = page.locator(".byte-lane").first();
      const path = await track.getAttribute("data-path"); await track.click();
      assert.equal(await page.locator("#atlas-file").innerText(), path);
    }
    await page.locator('[data-atlas-mode="coverage"]').click();
    const placements = [...latest.values()].filter((item) => item.state === "applied").reduce((total, item) => total + item.metrics.placements, 0);
    assert.equal(await page.locator("#workspace-placements").innerText(), new Intl.NumberFormat().format(placements));
    assert.equal(contentRequests.length, 0, "Overview must not fetch stored content.");
    await page.locator("#project-search").fill("__no_matching_repository__");
    assert.equal(await page.locator(".project-card").count(), 0);
    await page.locator("#project-search").fill("");
    const benign = [...latest.values()].find((item) => item.benign && item.metrics.placements);
    if (benign) {
      const card = page.locator(`.project-card[data-deployment="${benign.id}"]`);
      await card.click();
      await page.waitForFunction((id) => document.getElementById("deployment").value === id && !document.getElementById("deployment-content").hidden, benign.id);
      const detailResponse = await context.request.get(new URL(`/api/deployments/${benign.id}`, url).href, {headers: {Authorization: `Bearer ${token}`}});
      const detail = await detailResponse.json();
      const example = ["inspect", "status", "restore"].find((key) => typeof detail.examples?.[key] === "string" && detail.examples[key].trim());
      assert.equal(await page.locator("#command-examples").isVisible(), !!example);
      if (example) {
        await page.locator("#command-examples summary").click();
        await page.locator("#example-select").selectOption(example);
        assert.equal(await page.locator("#example-code").innerText(), detail.examples[example]);
      }
      await page.locator("#load-preview").click();
      await page.locator("#code-preview").waitFor({state: "visible"});
      assert.ok(await page.locator("#snippet-hash").innerText());
      const download = page.waitForEvent("download");
      await page.locator("#download").click();
      assert.ok((await download).suggestedFilename().startsWith("snippet-"));
    }
    await page.locator('.nav-item[data-view="traffic"]').click();
    await page.locator("#traffic-content").waitFor({state: "visible"});
    await page.locator('.nav-item[data-view="workspace"]').click();
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "Mobile page must not overflow horizontally.");
    const unauthorized = await context.request.get(new URL("/api/summary", url).href);
    assert.equal(unauthorized.status(), 401);
    assert.deepEqual(errors, []);
    assert.ok(apiMethods.length && apiMethods.every((method) => method === "GET"), "The viewer must only make read requests.");
    console.log(`PASS: ${latest.size} repositories; overview totals, search, benign preview/download, navigation, mobile layout, and authentication.`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
