"use strict";

const assert = require("node:assert/strict");
const {createHash} = require("node:crypto");
const fs = require("node:fs/promises");
const {chromium} = require("playwright");

async function main() {
  const url = process.env.REPEL_DASHBOARD_URL;
  if (!url) throw new Error("Set REPEL_DASHBOARD_URL to the authenticated URL printed by repel dashboard.");
  const target = new URL(url), fragment = new URLSearchParams(target.hash.slice(1)), token = fragment.get("token");
  assert.ok(token); target.searchParams.set("view", "research");
  const browser = await chromium.launch({headless:true, ...(process.env.REPEL_CHROME ? {executablePath:process.env.REPEL_CHROME} : {})});
  try {
    const context = await browser.newContext({viewport:{width:1512,height:1100}});
    const page = await context.newPage(), errors = [], bodies = [], methods = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith("/api/")) methods.push(request.method());
      if (/\/candidates\/|\/(preview|download)$/.test(path)) bodies.push(path);
    });
    const get = async path => {
      const response = await context.request.get(new URL(path,url).href,{headers:{Authorization:`Bearer ${token}`}});
      assert.equal(response.status(),200); return response.json();
    };
    await page.goto(target.href);
    await page.locator("#study-body").waitFor({state:"visible"});
    assert.equal(new URL(page.url()).hash, "", "Session token must leave the address bar.");
    const catalog = await get("/api/evaluations");
    assert.ok(catalog.studies.length >= 2, "Run against the recorded pilot and authored audit exports.");
    for (const metadata of catalog.studies) {
      await page.locator("#study-select").selectOption(metadata.id);
      await page.waitForFunction(id => window.RepelResearch?.current()?.id === id, metadata.id);
      const report = await get(`/api/evaluations/${metadata.id}`);
      assert.equal(report.benign,true);
      assert.equal(await page.locator("#study-case-count").innerText(),`${report.cases.length} / ${report.cases.length}`);
      assert.match(await page.locator("#study-stats").innerText(),new RegExp(`${report.counts.completed} / ${report.counts.planned}`));
      assert.equal(await page.locator("#study-metrics tr").count(),report.metrics.length);
      assert.equal(bodies.length,0,"Metadata navigation must not fetch source bodies.");
      if (report.stage === "audit") {
        assert.match(await page.locator("#study-chart-title").innerText(),/Faulty candidates/);
        assert.match(await page.locator("#study-chart-note").innerText(),/Lower is better/);
        assert.equal(await page.locator("#study-ablations tbody tr").count(),4);
        await page.locator("#study-group").selectOption("language");
        assert.equal(await page.locator(".study-slice").count(),report.design.formats.length);
      }
      if (report.stage === "pilot") assert.match(await page.locator("#study-chart-note").innerText(),/not overall correctness/);
      await page.locator("#study-search").fill("__no_such_task__");
      assert.equal(await page.locator("#study-cases button").count(),0);
      assert.equal(await page.locator("#study-case-content").isVisible(),false,"Zero matches must clear stale selected evidence.");
      await page.locator("#study-search").fill("");
    }
    await page.locator("#study-select").selectOption("pilot-20261107");
    await page.waitForFunction(() => window.RepelResearch?.current()?.id === "pilot-20261107");
    const pilot = await get("/api/evaluations/pilot-20261107"), candidate = pilot.cases.find(item => item.source_sha256 && item.language === "json");
    await page.locator(`#study-cases button[data-id="${candidate.id}"]`).click();
    await page.locator("#study-load-source").click();
    await page.locator("#study-code").waitFor({state:"visible"});
    const actual = await page.locator("#study-code").textContent();
    assert.equal(createHash("sha256").update(actual).digest("hex"),candidate.source_sha256);
    assert.equal(await page.locator("#study-code script").count(),0);
    assert.equal(await page.locator("#study-copy-source").isEnabled(),true);
    assert.match(await page.locator("#study-code-meta").innerText(),/integrity verified/);
    for (const button of ["study-report","study-protocol","study-observations"]) {
      const pending = page.waitForEvent("download"); await page.locator(`#${button}`).click();
      const download = await pending; assert.equal(await download.failure(),null);
      const data = await fs.readFile(await download.path()); assert.ok(data.length > 50);
    }
    await page.locator("#study-select").selectOption("fault-audit-v1");
    await page.waitForFunction(() => window.RepelResearch?.current()?.id === "fault-audit-v1");
    const pending = page.waitForEvent("download"); await page.locator("#study-reproduction").click();
    const download = await pending; assert.equal(await download.failure(),null);
    const archive = await fs.readFile(await download.path()), audit = await get("/api/evaluations/fault-audit-v1");
    assert.equal(createHash("sha256").update(archive).digest("hex"),audit.provenance.reproduction_sha256);
    const figurePending = page.waitForEvent("download"); await page.locator("#study-figure").click();
    const figureDownload = await figurePending; assert.equal(await figureDownload.failure(),null);
    const figure = await fs.readFile(await figureDownload.path());
    assert.equal(createHash("sha256").update(figure).digest("hex"),audit.provenance.figure_sha256["figure.pdf"]);
    await page.locator("#toast").waitFor({state:"hidden"});
    await page.screenshot({path:process.env.REPEL_RESEARCH_SCREENSHOT || "/tmp/repel-research-desktop.png",fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false,"Mobile page must not overflow.");
    await page.screenshot({path:"/tmp/repel-research-mobile.png",fullPage:true});
    await page.locator('.nav-item[data-view="workspace"]').click();
    assert.equal(await page.locator("#research-content").isVisible(),false);
    await page.locator('.nav-item[data-view="research"]').click();
    assert.equal(await page.locator("#research-content").isVisible(),true);
    const unauthorized = await context.request.get(new URL("/api/evaluations",url).href);
    assert.equal(unauthorized.status(),401);
    assert.deepEqual(errors,[]); assert.ok(methods.length && methods.every(method => method === "GET"));
    console.log(`PASS: ${catalog.studies.length} recorded benign studies; distinct metrics, paired uncertainty, source integrity, downloads, filtering, navigation, mobile layout, and authentication.`);
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error.stack); process.exitCode=1; });
