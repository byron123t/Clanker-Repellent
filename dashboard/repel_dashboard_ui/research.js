"use strict";

(() => {
  let study = null, selected = null, source = null, epoch = 0, loading = false;
  const modelName = (value) => ({glm: "GLM", deepseek: "DeepSeek", authored: "Authored corpus"}[value] || value);
  const armName = (value) => ({baseline: "Baseline", contract: "Task contracts", "structure-fix":"Structure fix only", "filter-only": "Filter only", original: "Original CLI"}[value] || value);
  const rate = (value) => typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
  const color = (row) => row.arm === "contract" || row.arm === "original" && row.model === "deepseek" ? "#c4ed8b" : "#94aac8";
  const count = (value) => typeof value === "number" ? new Intl.NumberFormat().format(value) : "—";
  const label = (row) => row.model==="authored" ? armName(row.arm) : `${modelName(row.model)} · ${armName(row.arm)}`;
  const failure = (item) => study?.stage === "audit" ? item.accepted === item.known_fault : !item.accepted || item.strict_pass === false || !!item.diagnostic;
  function error(message) { $("study-error").hidden = !message; $("study-error").textContent = message; }
  function svg(tag, attrs = {}, text) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function drawChart() {
    const pilot = study.stage === "pilot", audit = study.stage === "audit";
    const rows = study.metrics.filter((row) => row.arm !== "filter-only");
    $("study-chart-title").textContent = pilot ? "Validation acceptance" : audit ? "Faulty candidates accepted" : "Verified success, with uncertainty";
    $("study-chart-note").textContent = pilot ? "Exploratory pilot. This chart measures validation acceptance, not overall correctness."
      : audit ? "Lower is better. 48 fixed faults per system; 95% intervals resample 12 task clusters."
      : "Accepted and correct on every independent check. Whiskers show 95% task-bootstrap intervals.";
    if (!study.counts.completed) $("study-chart-note").textContent="No completed model outputs yet. Planned observations are not results; missing data are not failures.";
    const legend = pilot ? [{model:"glm", arm:"original", name:"GLM"}, {model:"deepseek",arm:"original",name:"DeepSeek"}]
      : [{arm:"baseline",name:"Baseline"},{arm:"contract",name:"Task contracts"}];
    $("study-legend").replaceChildren(...legend.map((entry) => { const item = node("span", "", entry.name); const mark = node("i"); mark.style.background = color(entry); item.prepend(mark); return item; }));
    const width = 810, left = 220, right = 725, height = 82 + rows.length * 52;
    const chart = svg("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":pilot ? "Static acceptance by model" : audit ? "False acceptance by validator; lower is better" : "Verified success by model and system"});
    for (const tick of [0, .25, .5, .75, 1]) {
      const x = left + tick * (right - left);
      chart.append(svg("line", {x1:x,x2:x,y1:24,y2:height-42,class:"study-gridline"}), svg("text", {x,y:height-17,"text-anchor":"middle",class:"study-axis-label"},`${tick*100}%`));
    }
    rows.forEach((row, index) => {
      const y = 40 + index * 52, value = pilot ? row.acceptance_rate : audit ? row.false_acceptance_rate : row.verified_rate;
      chart.append(svg("text", {x:4,y:y+4,class:"study-row-label"},label(row)));
      if (typeof value !== "number") return;
      const x = left + Math.max(0,Math.min(1,value)) * (right-left);
      if (!pilot && row.ci95) {
        const a = left + row.ci95[0]*(right-left), b = left + row.ci95[1]*(right-left);
        chart.append(svg("line",{x1:a,x2:b,y1:y,y2:y,stroke:color(row),"stroke-width":2}),
          svg("line",{x1:a,x2:a,y1:y-4,y2:y+4,stroke:color(row)}), svg("line",{x1:b,x2:b,y1:y-4,y2:y+4,stroke:color(row)}));
      }
      const dot = svg("circle", {cx:x,cy:y,r:5.5,fill:color(row),stroke:"#131c2b","stroke-width":2,tabindex:0,role:"button","aria-label":`${label(row)}: ${rate(value)}. Filter these candidates.`});
      dot.append(svg("title",{},`${label(row)}: ${rate(value)} (${pilot ? row.accepted : audit ? row.false_acceptance : row.verified}/${audit ? row.faults : row.n})${row.ci95 ? `; 95% CI ${rate(row.ci95[0])}–${rate(row.ci95[1])}` : ""}`));
      const filter = () => { $("study-model").value=row.model; $("study-arm").value=row.arm; renderCases(); };
      dot.addEventListener("click",filter); dot.addEventListener("keydown",(event)=>{ if (["Enter"," "].includes(event.key)) { event.preventDefault(); filter(); } });
      chart.append(dot,svg("text",{x:right+22,y:y+4,class:"study-value-label"},rate(value)));
    });
    $("study-chart").replaceChildren(chart);
  }
  function renderStats() {
    const audit=study.stage==="audit";
    const entries = [[audit ? "Validator evaluations" : "Completed candidates",`${count(study.counts.completed)} / ${count(study.counts.planned)}`,audit ? "84 identical sources, paired across systems" : "Planned denominator retained"],
      [study.stage==="pilot" ? "Task / format units" : "Task clusters",count(study.design.tasks),audit ? "7 fixed variants per development task" : `${study.design.replicates} replicate${study.design.replicates===1 ? "" : "s"} per task / system`],
      [audit ? "Authored faulty sources" : "Validation accepted",count(audit ? study.counts.faults : study.counts.accepted),audit ? `${study.counts.controls} correct controls scored separately` : "Acceptance and correctness are separate"],
      [study.stage==="pilot" ? "Behavior checks" : "Private behavior checks",count(study.counts.hidden_checks),"Checks are not independent task samples"]];
    $("study-stats").replaceChildren(...entries.map(([title,value,note]) => { const block=node("div","study-stat"); block.append(node("span","",title),node("strong","",value),node("p","",note)); return block; }));
  }
  function renderMetrics() {
    const audit=study.stage==="audit";
    $("study-metrics").closest("table").querySelectorAll("th").forEach((heading,index)=>{ heading.textContent=(audit ? ["System","Accepted","Correct accepted","False accepts","False rejects"] : ["Model / system","Accepted","Verified","False accepts","Attempts"])[index]; });
    $("study-metrics").replaceChildren(...study.metrics.map((row)=>{
      const tr=node("tr"); tr.append(node("td","",label(row)),node("td","study-numeric",row.n ? `${row.accepted}/${row.n}` : "Not run"),
        node("td","study-numeric",!row.n ? "Not run" : row.verified===null || row.verified===undefined ? "Not scored" : `${row.verified}/${audit ? row.controls : row.n}`),
        node("td","study-numeric",audit ? `${row.false_acceptance}/${row.faults}` : count(row.false_acceptance)),node("td","study-numeric",audit ? `${row.false_rejection}/${row.controls}` : count(row.attempts))); return tr;
    }));
    $("study-effects").replaceChildren(...(study.effects||[]).map((effect)=>{
      const entry=node("div","study-effect");
      entry.append(node("span","",audit ? "Paired reduction in false acceptance" : `${modelName(effect.model)} · paired change`),node("strong","",`${effect.difference>=0 ? "+" : ""}${(100*effect.difference).toFixed(1)} pp`),
        node("p","",`95% CI ${(100*effect.ci95[0]).toFixed(1)} to ${(100*effect.ci95[1]).toFixed(1)} pp · ${effect.paired_tasks} task clusters`));
      if (effect.ci95[0]<=0 && effect.ci95[1]>=0) entry.append(node("p","study-quiet","The interval includes no improvement."));
      if (effect.family_ci95) entry.append(node("p","study-quiet",`Related-family sensitivity: ${(100*effect.family_ci95[0]).toFixed(1)} to ${(100*effect.family_ci95[1]).toFixed(1)} pp · ${effect.family_clusters} families.`));
      return entry;
    }));
    const findings = study.findings || [study.state==="complete" ? "All planned observations are recorded. Inspect differences by task and format below." : "This study is incomplete. Missing observations are not model failures.",
      "Filter-only rows describe rejection of existing baseline outputs. They do not measure repair or additional generation."];
    $("study-findings").replaceChildren(...findings.map((finding)=>node("p","study-finding",finding)));
    const ablations=$("study-ablations"); ablations.hidden=!study.ablations?.length; ablations.replaceChildren();
    if (study.ablations?.length) {
      const table=node("table","study-metrics-table"), head=node("thead"), header=node("tr"), body=node("tbody");
      header.append(...["System","Faults accepted","Controls rejected"].map((text)=>node("th","",text))); head.append(header);
      for (const row of study.ablations) { const entry=node("tr"); entry.append(node("td","",armName(row.arm)),node("td","study-numeric",`${row.false_acceptance}/${row.faults}`),node("td","study-numeric",`${row.false_rejection}/${row.controls}`)); body.append(entry); }
      table.append(head,body); ablations.append(node("h4","","Mechanism check · post hoc"),node("p","study-quiet","Same sources. No additional tasks or model generation. Both error columns: lower is better."),table);
    }
    const costs=$("study-costs"), costRows=study.metrics.filter((row)=>row.arm!=="filter-only" && typeof row.inference_seconds==="number");
    costs.hidden=!costRows.length; costs.replaceChildren();
    if (costRows.length) {
      const table=node("table","study-metrics-table"), head=node("thead"), header=node("tr"), body=node("tbody");
      header.append(...["Model / system","Input tokens","Output tokens","Minutes","Limit stops"].map((text)=>node("th","",text))); head.append(header);
      for (const row of costRows) { const entry=node("tr"); entry.append(node("td","",label(row)),node("td","study-numeric",count(row.prompt_tokens)),node("td","study-numeric",count(row.completion_tokens)),node("td","study-numeric",(row.inference_seconds/60).toFixed(1)),node("td","study-numeric",count(row.length_stops))); body.append(entry); }
      table.append(head,body); costs.append(node("h4","","Observed inference cost"),node("p","study-quiet","All attempts included. Server-reported tokens and elapsed inference time; hardware and load are uncontrolled. Filter-only reuses baseline inference."),table);
    }
  }
  function renderBreakdown() {
    const groups=(study.groups||[]).filter((group)=>group.dimension===$("study-group").value);
    document.querySelector(".study-slices").hidden=!study.groups?.length;
    $("study-breakdown").replaceChildren(...groups.map((group)=>{
      const row=node("div","study-slice"); row.style.setProperty("--study-series",group.metrics.length); row.append(node("h4","",group.dimension==="level" ? `Level ${group.value}` : group.value));
      for (const metric of group.metrics) {
        const item=node("div","study-slice-metric"), track=node("div","study-mini-track"), mark=node("span");
        const audit=study.stage==="audit", value=audit ? metric.false_acceptance_rate : metric.verified_rate;
        mark.style.width=`${100*(value||0)}%`; mark.style.background=color(metric); track.append(mark);
        item.append(node("span","",label(metric)),node("strong","",audit ? `${rate(value)} · ${metric.false_acceptance}/${metric.faults} faults accepted` : `${rate(value)} · ${metric.verified}/${metric.n}`),track); row.append(item);
      }
      return row;
    }));
  }
  function selectCase(item) {
    selected=item; source=null; epoch++;
    $("study-selection-note").hidden=true; $("study-case-content").hidden=false;
    $("study-case-title").textContent=item.task;
    $("study-case-tags").replaceChildren(node("span","study-tag",modelName(item.model)),node("span","study-tag",armName(item.arm)),node("span","study-tag",item.language),node("span","study-tag",study.stage==="audit" ? item.known_fault ? "Authored fault" : "Correct control" : `${item.attempts} attempt${item.attempts===1 ? "" : "s"}`));
    $("study-case-diagnostic").textContent=item.diagnostic || (item.strict_pass===true ? "The candidate passed all registered independent checks." : item.accepted ? "Validation passed. Review the independent checks and documentation notes." : `Generation ended with ${item.status}. No accepted source was saved.`);
    $("study-task-text").textContent=item.prompt || "See the frozen protocol for this task.";
    $("study-contract").textContent=item.public_contract ? JSON.stringify(item.public_contract,null,2) : "The pilot did not use explicit task contracts.";
    $("study-checks").textContent=JSON.stringify({independent_grade:item.grade||{},...(item.validation ? {validation:item.validation} : {}),...(item.attempt_checks ? {attempt_checks:item.attempt_checks,resources:item.resources} : {})},null,2);
    $("study-code").hidden=true; $("study-code").textContent=""; $("study-code-meta").textContent="";
    $("study-load-source").disabled=!item.source_sha256; $("study-copy-source").disabled=true;
    for (const button of $("study-cases").querySelectorAll("button")) { button.classList.toggle("selected",button.dataset.id===item.id); button.setAttribute("aria-pressed",String(button.dataset.id===item.id)); }
  }
  function renderCases() {
    const search=$("study-search").value.trim().toLowerCase(), model=$("study-model").value, arm=$("study-arm").value, verdict=$("study-verdict").value;
    const matches=study.cases.filter((item)=>(!model||item.model===model)&&(!arm||item.arm===arm)&&(!search||`${item.task} ${item.language}`.toLowerCase().includes(search))
      &&(!verdict || verdict==="verified"&&item.strict_pass===true || verdict==="issue"&&failure(item) || verdict==="accepted"&&item.accepted));
    $("study-case-count").textContent=`${matches.length} / ${study.cases.length}`;
    $("study-cases").replaceChildren(...matches.map((item)=>{
      const button=node("button",`study-case${item.id===selected?.id ? " selected" : ""}`); button.dataset.id=item.id; button.setAttribute("aria-pressed",String(item.id===selected?.id));
      const verdictLabel=study.stage==="audit" ? failure(item) ? item.known_fault ? "Fault accepted" : "False rejection" : item.known_fault ? "Fault rejected" : "Control passed" : item.strict_pass===true ? "Verified" : !item.accepted ? "Rejected" : failure(item) ? "Review issue" : "Accepted";
      const title=node("span","study-case-name",item.task); const verdictNode=node("span",`study-case-verdict ${item.strict_pass===true ? "pass" : failure(item) ? "issue" : ""}`,verdictLabel);
      button.append(title,node("span","study-case-meta",`${modelName(item.model)} · ${armName(item.arm)}${study.stage==="audit" ? "" : ` · run ${item.trial+1}`}`),verdictNode);
      button.addEventListener("click",()=>selectCase(item)); return button;
    }));
    if (!matches.length) {
      $("study-cases").append(node("p","study-quiet","No candidates match these filters."));
      selected=null; source=null; epoch++; $("study-case-content").hidden=true; $("study-selection-note").hidden=false;
    }
    if (matches.length && !matches.some((item)=>item.id===selected?.id)) selectCase(matches[0]);
  }
  function renderMethod() {
    $("study-methodology").replaceChildren(...(study.methodology||[]).map((item)=>{ const section=node("section"); section.append(node("h4","",item.title),node("p","",item.body)); return section; }));
    $("study-limitations").replaceChildren(...(study.limitations||[]).map((item)=>node("li","",item)));
    const facts=[["Protocol SHA-256",study.provenance.protocol_sha256],["Baseline commit",study.provenance.baseline_commit],["Frozen snapshot files",study.provenance.snapshot_files],["Study",study.id]];
    $("study-provenance").replaceChildren(...facts.filter(([,value])=>value!==undefined&&value!==null).map(([key,value])=>{ const entry=node("div"); entry.append(node("dt","",key),node("dd","",String(value))); return entry; }));
    $("study-references").replaceChildren(...(study.references||[]).flatMap((reference)=>{
      let url; try { url=new URL(reference.url); } catch { return []; } if (url.protocol!=="https:") return [];
      const link=node("a","",`${reference.title} ↗`); link.href=url.href; link.target="_blank"; link.rel="noopener noreferrer"; return [link];
    }));
  }
  async function load(identity) {
    const request=++epoch;
    try {
      const report=await api(`/api/evaluations/${encodeURIComponent(identity)}`);
      if (request!==epoch) return;
      if (report.benign!==true) throw new Error("This view accepts explicitly benign experiment reports only.");
      study=report; selected=null; source=null; error(""); $("study-body").hidden=false; $("study-empty").hidden=true;
      $("study-title").textContent=study.title; $("study-badge").textContent=`${study.stage} · ${study.state}`;
      $("study-subtitle").textContent=`${study.design.formats.length} formats · ${study.design.tasks} task units · recorded ${new Date(study.created_at).toLocaleDateString([], {month:"long",day:"numeric",year:"numeric"})}`;
      $("study-source").textContent=!study.counts.completed ? "Awaiting inference · no generated outputs" : study.stage==="audit" ? "Authored fault study · no model generation" : "Measured benign outputs · unchanged source";
      const sliceTitle=document.querySelector(".study-slices h3"), sliceNote=document.querySelector(".study-slices .study-panel-heading p");
      sliceTitle.textContent=study.stage==="audit" ? "Where faults remain undetected" : "Where the system succeeds";
      sliceNote.textContent=study.stage==="audit" ? "False acceptance by authored complexity and format. Lower is better; slices are descriptive." : "Descriptive breakdowns; the registered overall result remains primary.";
      $("study-reproduction").hidden=!study.provenance.reproduction_sha256;
      $("study-figure").hidden=!study.provenance.figure_sha256?.["figure.pdf"];
      options($("study-model"),[["","All models"],...study.design.models.map((model)=>[model,modelName(model)])],"");
      options($("study-arm"),[["","All systems"],...study.design.arms.filter((arm)=>arm!=="filter-only").map((arm)=>[arm,armName(arm)])],"");
      $("study-search").value=""; $("study-verdict").value="";
      $("study-case-content").hidden=true; $("study-selection-note").hidden=false;
      renderStats(); drawChart(); renderMetrics(); renderBreakdown(); renderCases(); renderMethod(); renderVisibility();
    } catch (problem) { if (request===epoch) error(problem.message); }
  }
  async function refresh() {
    if (loading) return; loading=true;
    try {
      const catalog=await api("/api/evaluations");
      const previous=$("study-select").value;
      options($("study-select"),catalog.studies.map((item)=>[item.id,item.title]),previous);
      if (!catalog.studies.length) { $("study-empty").hidden=false; $("study-body").hidden=true; study=null; renderVisibility(); return; }
      if (catalog.errors) error(`${catalog.errors} invalid report(s) were omitted.`);
      const identity=$("study-select").value; const meta=catalog.studies.find((item)=>item.id===identity);
      if (!study||study.id!==identity||study.updated_at!==meta.updated_at) await load(identity);
    } catch (problem) { error(problem.message); }
    finally { loading=false; }
  }
  $("study-select").addEventListener("change",()=>load($("study-select").value));
  $("study-group").addEventListener("change",renderBreakdown);
  for (const id of ["study-search","study-model","study-arm","study-verdict"]) $(id).addEventListener(id==="study-search" ? "input" : "change",()=>{if(study)renderCases();});
  $("study-load-source").addEventListener("click",async()=>{
    if (!study||!selected) return;
    const request=++epoch, identity=selected.id; $("study-load-source").disabled=true;
    try {
      const preview=await api(`/api/evaluations/${study.id}/candidates/${identity}`);
      if (request!==epoch||selected?.id!==identity) return;
      source=preview.text; $("study-code").textContent=preview.text; $("study-code").hidden=false;
      $("study-copy-source").disabled=preview.truncated; $("study-code-meta").textContent=`${count(preview.bytes)} bytes · SHA-256 ${preview.sha256}${preview.truncated ? " · truncated preview" : " · integrity verified"}`;
    } catch(problem) { if(request===epoch) $("study-code-meta").textContent=problem.message; }
    finally { if(request===epoch) $("study-load-source").disabled=false; }
  });
  $("study-copy-source").addEventListener("click",()=>{if(source!==null)copy(source);});
  $("study-protocol").addEventListener("click",()=>{if(study)download(`/api/evaluations/${study.id}/download?file=protocol.json`,`${study.id}-protocol.json`);});
  $("study-observations").addEventListener("click",()=>{if(study)download(`/api/evaluations/${study.id}/download?file=scores.json`,`${study.id}-observations.json`);});
  $("study-reproduction").addEventListener("click",()=>{if(study)download(`/api/evaluations/${study.id}/download?file=reproduction.zip`,`${study.id}-reproduction.zip`);});
  $("study-report").addEventListener("click",()=>{if(study)download(`/api/evaluations/${study.id}/download?file=REPORT.md`,`${study.id}-report.md`);});
  $("study-figure").addEventListener("click",()=>{if(study)download(`/api/evaluations/${study.id}/download?file=figure.pdf`,`${study.id}-figure.pdf`);});
  window.RepelResearch={refresh,current:()=>study,export:()=>{if(study)saveBlob(new Blob([JSON.stringify(study,null,2)+"\n"],{type:"application/json"}),`${study.id}-report.json`);}};
  if (fragment.get("view")==="research" || new URLSearchParams(location.search).get("view")==="research") changeView("research");
})();
