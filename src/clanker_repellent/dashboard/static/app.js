"use strict";

const $ = (id) => document.getElementById(id);
const state = {summary: null, detail: null, view: "overview", file: null, version: "insertion", step: 0,
  preview: null, response: null, responses: [], request: 0, previewRequest: 0, refreshing: false};
const fragment = new URLSearchParams(location.hash.slice(1));
const suppliedToken = fragment.get("token");
if (suppliedToken) { sessionStorage.setItem("repel-token", suppliedToken); history.replaceState(null, "", location.pathname); }
const token = sessionStorage.getItem("repel-token") || "";
const titles = {overview: ["Deployment overview", "A clear view of where your snippets live."],
  snippets: ["Snippet explorer", "Find the exact insertion. Take the original example with you."],
  traffic: ["HTTP archive", "Every recorded response, with its original bytes intact."]};
const kindLabels = {javascript_global_data: "JavaScript", native_retained_string: "C / C++", html_data_block: "HTML",
  wasm_custom_section: "WASM", document_data: "Document", artifact: "Artifact"};
const capital = (s) => s ? s[0].toUpperCase() + s.slice(1) : "—";
const short = (s, n = 10) => s ? s.slice(0, n) : "—";
const fmt = (n) => new Intl.NumberFormat().format(n || 0);
const percent = (n) => n === null || n === undefined ? "—" : `${n.toFixed(n % 1 ? 1 : 0)}%`;
function bytes(n) { if (n < 1024) return `${fmt(n)} B`; if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`; return `${(n / 1024 / 1024).toFixed(1)} MB`; }
function node(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
function setText(id, text) { $(id).textContent = text; }
function showError(message) { setText("error-banner", message); $("error-banner").hidden = !message; }
let toastTimer;
function toast(message) { setText("toast", message); $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2800); }
async function api(path, raw = false) {
  const response = await fetch(path, {headers: {Authorization: `Bearer ${token}`}, cache: "no-store"});
  if (!response.ok) { let error; try { error = await response.json(); } catch { error = {}; } throw new Error(error.error || `Request failed (${response.status}).`); }
  return raw ? response : response.json();
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
  catch { toast("Clipboard unavailable. Select and copy the text instead."); }
}
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob); const anchor = node("a"); anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function options(select, entries, value) {
  select.replaceChildren(...entries.map(([key, label]) => { const option = node("option", "", label); option.value = key; return option; }));
  if (entries.some(([key]) => key === value)) select.value = value;
}
function connected(ok) {
  $("connection-state").replaceChildren(node("span", "status-dot"), document.createTextNode(ok ? "Journal connected" : "Connection unavailable"));
  $("connection-state").firstChild.style.background = ok ? "#79aa7a" : "#d39c73";
}
async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true; $("refresh").disabled = true;
  try {
    const previous = state.summary;
    const summary = await api("/api/summary"); state.summary = summary; connected(true);
    if (summary.demo) $("connection-state").replaceChildren(node("span", "status-dot"), document.createTextNode("Benign demo journal"));
    setText("store-path", summary.store); $("store-path").title = summary.store;
    setText("response-count", fmt(summary.response_count));
    setText("last-updated", `Updated ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"})} · refreshes every 10s`);
    const repos = [...new Map(summary.deployments.map((d) => [d.repository, d.repository_name])).entries()];
    options($("repository"), [["", "All repositories"], ...repos], $("repository").value);
    updateDeploymentOptions();
    if (summary.errors.length) showError(`${summary.errors.length} journal record(s) failed validation and were withheld.`); else showError("");
    if (state.view === "traffic") await loadTraffic();
    else {
      const current = summary.deployments.find((d) => d.id === $("deployment").value);
      const old = previous?.deployments.find((d) => d.id === current?.id);
      if (!state.detail || state.detail.id !== current?.id || old?.updated_at !== current?.updated_at || old?.state !== current?.state) await loadDeployment();
    }
  } catch (error) { connected(false); showError(error.message); }
  finally { state.refreshing = false; $("refresh").disabled = false; }
}
function updateDeploymentOptions() {
  const repository = $("repository").value, phase = $("state-filter").value;
  const selected = $("deployment").value;
  const entries = (state.summary?.deployments || []).filter((d) => (!repository || d.repository === repository) && (!phase || d.state === phase));
  options($("deployment"), entries.map((d) => [d.id, `${d.repository_name} · ${short(d.id, 7)} · ${d.state}`]), selected);
  if (!entries.length) options($("deployment"), [["", "No matching deployments"]], "");
  setText("record-caption", `${entries.length} recent record${entries.length === 1 ? "" : "s"}${state.summary?.total_deployments > 200 ? " · latest 200 shown" : ""}`);
}
async function loadDeployment() {
  const id = $("deployment").value, request = ++state.request;
  if (!id) { state.detail = null; state.file = null; renderVisibility(); return; }
  try {
    const detail = await api(`/api/deployments/${id}`);
    if (request !== state.request || id !== $("deployment").value) return;
    const previousPath = state.detail?.id === id ? state.file?.path : null;
    state.detail = detail; state.file = detail.files.find((r) => r.path === previousPath) || detail.files.find((r) => r.role === "placement") || detail.files[0] || null;
    state.step = 0; state.version = state.file?.placements ? "insertion" : "before";
    clearPreview(); renderDetail(); renderVisibility();
  } catch (error) { if (request === state.request) { state.detail = null; renderVisibility(); showError(error.message); } }
}
function renderVisibility() {
  const traffic = state.view === "traffic";
  $("deployment-controls").hidden = traffic; $("traffic-content").hidden = !traffic;
  $("deployment-content").hidden = traffic || !state.detail;
  $("empty-state").hidden = traffic || !!state.detail;
  $("metrics").hidden = state.view !== "overview"; $("visuals").hidden = state.view !== "overview";
  document.body.classList.toggle("mode-snippets", state.view === "snippets");
  $("export").disabled = traffic ? !state.responses.length : !state.detail;
}
function renderDetail() {
  const detail = state.detail, m = detail.metrics;
  setText("coverage-value", percent(m.coverage_percent));
  setText("coverage-foot", m.eligible_files === null ? "Eligible-file count not recorded" : `${fmt(m.placed_files)} of ${fmt(m.eligible_files)} compatible files`);
  $("coverage-track").style.width = `${m.coverage_percent || 0}%`;
  setText("placements-value", fmt(m.placements)); setText("placements-foot", `Across ${fmt(m.placed_files)} files · ${detail.mode} data`);
  setText("inserted-value", bytes(m.inserted_bytes));
  setText("inserted-foot", `${percent(m.density_percent)} of final placed-file bytes`);
  setText("journal-state", capital(detail.state));
  $("journal-state").style.color = detail.state === "applied" ? "#4b7d54" : "#8c91a1";
  setText("journal-foot", detail.state === "restored" ? "Historical placement · original files restored" : `${fmt(m.artifacts)} captured artifacts · originals stored`);
  setText("scope-label", m.scope);
  setText("donut-value", percent(m.coverage_percent));
  $("donut-fill").style.strokeDashoffset = String(364.43 * (1 - (m.coverage_percent || 0) / 100));
  $("donut-fill").parentElement.setAttribute("aria-label", m.coverage_percent === null ? "Coverage denominator was not recorded" : `${percent(m.coverage_percent)} recorded file coverage`);
  renderMap();
  const groups = [0, 0, 0];
  for (const file of detail.files.filter((f) => f.role === "placement")) for (const edit of file.edits) {
    if (edit.inserted_bytes) groups[edit.location_percent < 33.333 ? 0 : edit.location_percent < 66.667 ? 1 : 2]++;
  }
  const total = groups.reduce((a, b) => a + b, 0);
  $("distribution").replaceChildren(...["Head", "Middle", "Tail"].map((label, i) => {
    const row = node("div", "distribution-row"), bar = node("div", "bar"), fill = node("div", "fill");
    fill.style.width = `${total ? groups[i] * 100 / total : 0}%`; bar.append(fill);
    row.append(node("span", "", label), bar, node("span", "", total ? `${Math.round(groups[i] * 100 / total)}%` : "—"));
    row.title = `${groups[i]} recorded insertion${groups[i] === 1 ? "" : "s"}`; return row;
  }));
  setText("selection-description", detail.selection.random ? `Seeded selection · seed ${detail.selection.seed}` : "Deterministic selection · safe placement locations");
  renderFiles(); renderInspector(); renderExample();
}
function allFiles() {
  if (!state.detail) return [];
  const result = [...state.detail.files];
  if ($("show-unselected").checked) {
    const placed = new Set(result.map((row) => row.path));
    for (const path of state.detail.eligible_paths) if (!placed.has(path)) result.push({path, kind: "unselected", role: "unselected", placements: 0, spans: [], inserted_bytes: 0});
  }
  const filter = $("file-search").value.toLowerCase();
  return result.filter((row) => `${row.path} ${row.kind} ${kindLabels[row.kind] || ""}`.toLowerCase().includes(filter));
}
function renderMap() {
  const detail = state.detail;
  const paths = detail.eligible_paths.length ? detail.eligible_paths : detail.files.filter((f) => f.role === "placement").map((f) => f.path);
  const byPath = new Map(detail.files.map((file) => [file.path, file]));
  const tiles = paths.slice(0, 200).map((path) => {
    const file = byPath.get(path), tile = node("button", `map-tile${file?.placements ? " placed" : ""}${state.file?.path === path ? " selected" : ""}`);
    tile.title = `${path} · ${file ? "placed" : "unselected"}`; tile.setAttribute("aria-label", tile.title);
    tile.addEventListener("click", () => chooseFile(file || {path, role: "unselected", kind: "unselected", placements: 0, edits: [], spans: []}));
    return tile;
  });
  $("file-map").replaceChildren(...tiles);
  setText("map-caption", detail.metrics.eligible_files === null ? "Eligible set was not recorded. Showing placed files only."
    : `${fmt(detail.metrics.placed_files)} placed · ${fmt(detail.metrics.eligible_files - detail.metrics.placed_files)} unselected${paths.length > 200 ? " · first 200 tiles shown" : ""}`);
}
function renderFiles() {
  const rows = allFiles();
  setText("file-count", fmt(rows.length));
  $("files-body").replaceChildren(...rows.slice(0, 400).map((row) => {
    const tr = node("tr", state.file?.path === row.path ? "selected" : ""); tr.tabIndex = 0;
    tr.setAttribute("aria-label", `Inspect ${row.path}`);
    tr.addEventListener("click", () => chooseFile(row));
    tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); chooseFile(row); } });
    const pathCell = node("td"), name = node("div", "file-cell"); name.append(node("span", "file-icon", "◇"), node("span", "file-name", row.path)); name.title = row.path; pathCell.append(name);
    const type = node("td"); type.append(node("span", "type-tag", kindLabels[row.kind] || capital(row.kind)));
    const map = node("td");
    if (!row.placements) map.append(node("span", "unselected-label", row.role === "artifact" ? (row.pending ? "Awaiting seal" : "Snapshot") : "Not selected"));
    else { const rail = node("div", "placement-rail"); for (const span of row.spans) { const segment = node("span", "placement-segment"); segment.style.left = `${Math.min(span.start_percent, 99)}%`; segment.style.width = `${Math.min(span.width_percent, 100 - span.start_percent)}%`; segment.title = `Bytes ${span.start}–${span.end} in final image`; rail.append(segment); } map.append(rail); }
    tr.append(pathCell, type, map, node("td", "align-right", row.inserted_bytes ? bytes(row.inserted_bytes) : "—")); return tr;
  }));
  if (!rows.length) { const tr = node("tr", "no-results"), td = node("td", "", "No files match this filter."); td.colSpan = 4; tr.append(td); $("files-body").append(tr); }
  setText("table-caption", `${fmt(Math.min(rows.length, 400))} of ${fmt(rows.length)} matching files · recorded postimage ranges`);
}
function chooseFile(file) {
  state.file = file; state.step = 0; state.version = file.placements ? "insertion" : "before";
  clearPreview(); renderMap(); renderFiles(); renderInspector();
}
function clearPreview() {
  state.preview = null; state.previewRequest++;
  $("code-preview").hidden = true; setText("code-preview", ""); $("preview-placeholder").hidden = false;
  $("copy-snippet").disabled = true; $("download").disabled = true; setText("preview-status", ""); setText("snippet-hash", "—");
}
function renderInspector() {
  const file = state.file, unselected = !file || file.role === "unselected";
  setText("inspector-path", file?.path || "Choose a file");
  setText("inspector-subtitle", unselected ? "No stored placement for this file." : "Exact bytes from the journal.");
  for (const button of document.querySelectorAll("[data-version]")) {
    button.classList.toggle("active", button.dataset.version === state.version);
    button.disabled = unselected || (button.dataset.version === "insertion" && !file.edits?.length) || (button.dataset.version === "before" && !file.before_sha256);
  }
  $("step-control").hidden = unselected || state.version !== "insertion";
  options($("step"), (file?.edits || []).map((edit) => [String(edit.step), `#${edit.step + 1} · byte ${fmt(edit.offset)}`]), String(state.step));
  const edit = file?.edits?.[state.step];
  setText("snippet-meta", unselected ? "Compatible file; no bytes were stored for it."
    : state.version === "insertion" && edit ? `${bytes(edit.inserted_bytes)} inserted at byte ${fmt(edit.offset)} · before step ${edit.step + 1}`
    : state.version === "before" ? `${bytes(file.before_bytes)} · original file before deployment` : `${bytes(file.after_bytes)} · planned final file`);
  $("load-preview").disabled = unselected || (state.version === "before" && !file.before_sha256);
  $("load-preview").replaceChildren(document.createTextNode(state.version === "insertion" ? "Load snippet " : "Load example "), node("span", "", "↗"));
}
function previewPath(action = "preview") {
  return `/api/deployments/${state.detail.id}/${action}?${new URLSearchParams({file: state.file.number, step: state.step, version: state.version})}`;
}
async function loadPreview() {
  if (!state.file || state.file.role === "unselected") return;
  const request = ++state.previewRequest, path = previewPath(); $("load-preview").disabled = true;
  setText("preview-status", "Verifying stored bytes…");
  try {
    const result = await api(path);
    if (request !== state.previewRequest) return;
    state.preview = result; $("preview-placeholder").hidden = true; $("code-preview").hidden = false;
    setText("code-preview", result.text || "(Empty byte sequence)"); setText("snippet-hash", result.sha256);
    setText("preview-status", `${result.encoding === "base64" ? "Binary preview · base64" : "UTF-8 · checksum verified"}${result.truncated ? ` · preview limited to ${bytes(result.preview_bytes)}; download for all ${bytes(result.bytes)}` : ` · ${bytes(result.bytes)}`}`);
    $("copy-snippet").disabled = !result.text; setText("copy-snippet", result.truncated ? "Copy preview" : result.encoding === "base64" ? "Copy base64" : "Copy snippet");
    $("download").disabled = false;
  } catch (error) { if (request === state.previewRequest) { state.preview = null; setText("preview-status", error.message); } }
  finally { if (request === state.previewRequest) $("load-preview").disabled = false; }
}
function renderExample() { setText("example-code", state.detail?.examples[$("example-select").value] || ""); }
async function download(path, filename) {
  try { const response = await api(path, true); saveBlob(await response.blob(), filename); toast("Download ready"); }
  catch (error) { toast(error.message); }
}
async function loadTraffic() {
  const result = await api("/api/responses"); state.responses = result.responses;
  $("traffic-body").replaceChildren(...result.responses.map((row) => {
    const tr = node("tr"); tr.append(node("td", "file-name", `${row.request.method || "GET"} ${row.request.path || "/"}`), node("td", "", row.status), node("td", "", row.content_type), node("td", "file-name", short(row.id)));
    const action = node("td"), button = node("button", "button secondary traffic-action", "View original ↗");
    button.addEventListener("click", async () => {
      state.response = row; $("response-preview").hidden = false; setText("response-title", `${row.request.path || "/"} · Original body`); setText("response-code", "Verifying stored bytes…");
      try { const preview = await api(`/api/responses/${row.id}/preview?version=before`); if (state.response?.id === row.id) setText("response-code", `${preview.encoding === "base64" ? "[Binary data · base64]\n\n" : ""}${preview.text}${preview.truncated ? "\n\n[Preview truncated; download for all bytes.]" : ""}`); }
      catch (error) { if (state.response?.id === row.id) setText("response-code", error.message); }
    }); action.append(button); tr.append(action); return tr;
  }));
  if (!result.responses.length) { const tr = node("tr", "no-results"), td = node("td", "", "This journal has no archived HTTP responses."); td.colSpan = 5; tr.append(td); $("traffic-body").append(tr); }
  renderVisibility();
}
function changeView(view) {
  state.view = view;
  for (const button of document.querySelectorAll("[data-view]")) { button.classList.toggle("active", button.dataset.view === view); button.setAttribute("aria-current", button.dataset.view === view ? "page" : "false"); }
  $("page-title").replaceChildren(document.createTextNode(titles[view][0]), node("span", "heading-dot", "."));
  setText("page-description", titles[view][1]); setText("breadcrumb-current", view === "traffic" ? "HTTP archive" : view === "snippets" ? "Snippet explorer" : "Overview");
  renderVisibility();
  if (view === "traffic") loadTraffic().catch((error) => showError(error.message));
  else if (!state.detail || state.detail.id !== $("deployment").value) loadDeployment();
}
document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => changeView(button.dataset.view)));
$("refresh").addEventListener("click", refresh);
$("repository").addEventListener("change", () => { updateDeploymentOptions(); loadDeployment(); });
$("state-filter").addEventListener("change", () => { updateDeploymentOptions(); loadDeployment(); });
$("deployment").addEventListener("change", loadDeployment);
$("file-search").addEventListener("input", renderFiles);
$("show-unselected").addEventListener("change", renderFiles);
document.querySelectorAll("[data-version]").forEach((button) => button.addEventListener("click", () => { state.version = button.dataset.version; clearPreview(); renderInspector(); }));
$("step").addEventListener("change", () => { state.step = Number($("step").value); clearPreview(); renderInspector(); });
$("load-preview").addEventListener("click", loadPreview);
$("copy-snippet").addEventListener("click", () => { if (state.preview) copy(state.preview.text); });
$("download").addEventListener("click", () => { if (state.preview) download(previewPath("download"), state.preview.filename); });
$("example-select").addEventListener("change", renderExample);
$("copy-example").addEventListener("click", () => copy($("example-code").textContent));
$("response-download").addEventListener("click", () => { if (state.response) download(`/api/responses/${state.response.id}/download?version=before`, `${state.response.id}-original.bin`); });
$("export").addEventListener("click", () => { const data = state.view === "traffic" ? {responses: state.responses} : state.detail; if (data) saveBlob(new Blob([JSON.stringify(data, null, 2) + "\n"], {type: "application/json"}), `repel-${state.view === "traffic" ? "responses" : short(state.detail.id)}.json`); });
renderVisibility(); refresh(); setInterval(() => { if (!document.hidden) refresh(); }, 10000);
