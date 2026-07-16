const STEP_LABELS = {
  PREPARE_INPUT: "保存不可变输入",
  PARSE_IDEA: "解析技术特征",
  VALIDATE_IDEA_MODEL: "校验 IDEA 模型",
  PLAN_QUERIES: "规划检索式",
  RETRIEVE_CANDIDATES: "双路检索候选",
  NORMALIZE_AND_FETCH: "去重并抓取全文",
  ANALYZE_DOCUMENTS: "逐篇证据映射",
  DETERMINE_NOVELTY: "单篇新颖性裁决",
  ANALYZE_INVENTIVENESS: "多 D1 创造性分析",
  ASSESS_VALUE: "价值预评估",
  AUDIT_AND_REPORT: "证据审计与报告",
};

const MODE_DEFAULTS = {
  quick: { candidate_max: 30, deep_review_min: 10, deep_review_max: 10 },
  standard: { candidate_max: 80, deep_review_min: 10, deep_review_max: 20 },
  deep: { candidate_max: 150, deep_review_min: 20, deep_review_max: 40 },
};

const state = {
  cases: [],
  selectedCase: null,
  selectedRun: null,
  report: null,
  eventSource: null,
  activeTab: "overview",
};

const $ = (id) => document.getElementById(id);

function clearRuntimeApiKey() {
  const input = $("apiToken");
  if (input) input.value = "";
}

window.addEventListener("pageshow", clearRuntimeApiKey);
window.addEventListener("pagehide", clearRuntimeApiKey);

document.addEventListener("DOMContentLoaded", async () => {
  clearRuntimeApiKey();
  $("evaluationDate").value = new Date().toISOString().slice(0, 10);
  $("ideaText").addEventListener("input", () => {
    $("ideaCount").textContent = `${$("ideaText").value.length} 字符`;
  });
  $("searchMode").addEventListener("change", applyModeDefaults);
  $("runForm").addEventListener("submit", createRun);
  $("newCaseBtn").addEventListener("click", clearCaseSelection);
  $("cancelRun").addEventListener("click", cancelSelectedRun);
  $("rerunBtn").addEventListener("click", rerunSelected);
  $("deleteRunBtn").addEventListener("click", deleteSelectedRun);
  await Promise.all([loadHealth(), loadCases()]);
  renderEmptyProgress();
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = body?.detail || body?.error || (typeof body === "string" ? body : response.statusText);
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("；") : detail);
  }
  return body;
}

async function loadHealth() {
  try {
    const [health, cache] = await Promise.all([api("/api/system/health"), api("/api/system/cache")]);
    $("healthDot").className = `health-dot ${health.ok ? "ok" : "bad"}`;
    const modelNeedsToken = health.components?.model?.status === "runtime_required";
    $("healthText").textContent = health.ok
      ? (modelNeedsToken ? "核心服务就绪 · 等待本页 API Token" : "核心服务就绪")
      : "服务降级";
    $("cacheText").textContent = `缓存 ${formatBytes(cache.total_bytes || 0)} / ${formatBytes(cache.max_bytes)}`;
  } catch (error) {
    $("healthDot").className = "health-dot bad";
    $("healthText").textContent = "健康检查失败";
  }
}

async function loadCases(selectCaseId = state.selectedCase?.case_id) {
  const data = await api("/api/idea/cases");
  state.cases = data.cases;
  renderCases();
  if (selectCaseId && state.cases.some((item) => item.case_id === selectCaseId)) {
    await selectCase(selectCaseId, false);
  }
}

function renderCases() {
  const list = $("caseList");
  list.replaceChildren();
  if (!state.cases.length) {
    list.append(el("p", "small", "暂无历史。填写 Case 名称和 IDEA 后即可开始。"));
    return;
  }
  for (const item of state.cases) {
    const fragment = $("caseTemplate").content.cloneNode(true);
    const card = fragment.querySelector(".case-card");
    card.dataset.caseId = item.case_id;
    if (state.selectedCase?.case_id === item.case_id) card.classList.add("active");
    fragment.querySelector(".case-name").textContent = item.title;
    fragment.querySelector(".case-meta").textContent = `${item.run_count} 个 Run · ${formatTime(item.latest_run_at || item.created_at)}`;
    fragment.querySelector(".case-main").addEventListener("click", () => selectCase(item.case_id));
    fragment.querySelector(".case-delete").addEventListener("click", (event) => {
      event.stopPropagation();
      deleteCase(item.case_id, item.title);
    });
    list.append(fragment);
  }
}

async function selectCase(caseId, render = true) {
  state.selectedCase = await api(`/api/idea/cases/${caseId}`);
  $("caseTitle").value = state.selectedCase.title;
  $("activeCaseBadge").textContent = state.selectedCase.title;
  if (render) renderCases();
  const card = document.querySelector(`[data-case-id="${cssEscape(caseId)}"]`);
  if (!card) return;
  document.querySelectorAll(".case-card").forEach((item) => item.classList.remove("active"));
  card.classList.add("active");
  const runList = card.querySelector(".run-list");
  runList.replaceChildren();
  for (const run of state.selectedCase.runs) {
    const button = el("button", "run-item");
    button.type = "button";
    if (state.selectedRun?.run_id === run.run_id) button.classList.add("active");
    const dot = el("span", `run-dot ${statusClass(run.status)}`);
    const copy = el("span", "run-copy");
    copy.append(
      el("strong", "", `${run.status} · ${run.run_id.slice(0, 8)}`),
      el("span", "", `${run.evaluation_date} · ${formatTime(run.created_at)}`),
    );
    button.append(dot, copy);
    button.addEventListener("click", () => selectRun(run.run_id));
    runList.append(button);
  }
}

function clearCaseSelection() {
  state.selectedCase = null;
  $("caseTitle").value = "";
  $("activeCaseBadge").textContent = "将新建 Case";
  document.querySelectorAll(".case-card").forEach((item) => item.classList.remove("active"));
  $("caseTitle").focus();
}

async function createRun(event) {
  event.preventDefault();
  setMessage("");
  const submit = $("submitRun");
  submit.disabled = true;
  try {
    const apiKey = $("apiToken").value.trim();
    if (!apiKey) throw new Error("请输入本页使用的 API Token");
    let caseId = state.selectedCase?.case_id;
    const caseTitle = $("caseTitle").value.trim();
    if (!caseId) {
      if (!caseTitle) throw new Error("请填写 Case 名称");
      const created = await api("/api/idea/cases", {
        method: "POST",
        body: JSON.stringify({ title: caseTitle }),
      });
      caseId = created.case_id;
      state.selectedCase = created;
    }
    const payload = {
      api_key: apiKey,
      input_text: $("ideaText").value.trim(),
      evaluation_date: $("evaluationDate").value,
      date_basis: $("dateBasis").value.trim() || "用户指定或提交日",
      analysis_scope: "full",
      settings: {
        search_mode: $("searchMode").value,
        candidate_max: numberValue("candidateMax"),
        deep_review_min: numberValue("deepMin"),
        deep_review_max: numberValue("deepMax"),
      },
    };
    if (payload.input_text.length < 10) throw new Error("IDEA 至少需要 10 个字符");
    const run = await api(`/api/idea/cases/${caseId}/runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadCases(caseId);
    await activateRun(run);
    subscribeToRun(run.run_id);
  } catch (error) {
    setMessage(error.message);
  } finally {
    submit.disabled = false;
  }
}

async function selectRun(runId) {
  closeEvents();
  const run = await api(`/api/idea/runs/${runId}`);
  state.report = null;
  $("reportView").classList.add("hidden");
  $("emptyResult").classList.remove("hidden");
  await activateRun(run);
  if (isTerminal(run.status)) await loadReport(runId);
  else subscribeToRun(runId);
  if (state.selectedCase) await selectCase(state.selectedCase.case_id);
}

async function activateRun(run) {
  state.selectedRun = run;
  renderProgress(run);
  renderRunActions(run);
  if (!isTerminal(run.status)) {
    state.report = null;
    $("reportView").classList.add("hidden");
    $("emptyResult").classList.remove("hidden");
    $("emptyResult").querySelector("h3").textContent = "评估正在执行";
    $("emptyResult").querySelector("p").textContent = "进度由持久 Harness 状态驱动；关闭页面不会丢失任务。";
  }
}

function subscribeToRun(runId) {
  closeEvents();
  const source = new EventSource(`/api/idea/runs/${runId}/events`);
  state.eventSource = source;
  source.onmessage = async (event) => {
    const message = JSON.parse(event.data);
    if (!message.data) return;
    state.selectedRun = message.data;
    renderProgress(message.data);
    renderRunActions(message.data);
    if (message.type === "terminal") {
      closeEvents();
      await loadCases(message.data.case_id);
      await loadReport(runId);
    }
  };
  source.onerror = () => {
    if (!isTerminal(state.selectedRun?.status)) setMessage("进度连接中断，可重新选择该 Run 恢复查看");
    closeEvents();
  };
}

function closeEvents() {
  state.eventSource?.close();
  state.eventSource = null;
}

function renderProgress(run) {
  const progress = run.progress;
  $("progressTitle").textContent = progress.current_step ? STEP_LABELS[progress.current_step] : "Workflow 已结束";
  $("runStatus").textContent = run.status;
  $("runStatus").className = `status-pill ${statusClass(run.status)}`;
  $("progressBar").style.width = `${Math.round(progress.completed_steps / progress.total_steps * 100)}%`;
  const list = $("stepList");
  list.replaceChildren();
  for (const step of progress.steps) {
    const item = el("li", step.status.toLowerCase(), STEP_LABELS[step.name] || step.name);
    if (step.attempt > 1) item.title = `第 ${step.attempt} 次尝试`;
    list.append(item);
  }
  if (run.error_message) setMessage(`${run.error_code || "ERROR"}：${run.error_message}`);
}

function renderEmptyProgress() {
  $("stepList").replaceChildren(...Object.values(STEP_LABELS).map((label) => el("li", "", label)));
}

function renderRunActions(run) {
  const terminal = isTerminal(run.status);
  $("cancelRun").classList.toggle("hidden", terminal);
  $("rerunBtn").classList.toggle("hidden", !terminal);
  $("deleteRunBtn").classList.toggle("hidden", !terminal);
  $("markdownLink").classList.toggle("hidden", !terminal || !state.report);
  $("markdownLink").href = `/api/idea/runs/${run.run_id}/report.md`;
}

async function loadReport(runId) {
  try {
    state.report = await api(`/api/idea/runs/${runId}/report`);
    state.activeTab = "overview";
    renderReport();
    renderRunActions(state.selectedRun);
  } catch (error) {
    state.report = null;
    $("reportView").classList.add("hidden");
    $("emptyResult").classList.remove("hidden");
    $("emptyResult").querySelector("h3").textContent = state.selectedRun?.status === "FAILED" ? "Run 未生成最终报告" : "报告暂不可用";
    $("emptyResult").querySelector("p").textContent = state.selectedRun?.error_message || error.message;
  }
}

function renderReport() {
  const report = state.report;
  $("emptyResult").classList.add("hidden");
  $("reportView").classList.remove("hidden");
  const overview = report.conclusion_overview;
  const card = $("conclusionCard");
  card.replaceChildren();
  card.className = `conclusion-card ${overview.novelty_code === "NOT_NOVEL" ? "not-novel" : overview.novelty_code === "UNCERTAIN" ? "uncertain" : ""}`;
  card.append(
    el("div", "conclusion-label", overview.novelty_label),
    el("div", "conclusion-meta", `置信度 ${formatNumber(overview.novelty_confidence)} · 申请建议 ${overview.filing_recommendation}`),
    el("p", "conclusion-summary", overview.executive_summary),
  );
  const tabs = [
    ["overview", "总览"], ["features", "技术特征"], ["search", "检索与文献"],
    ["novelty", "新颖性"], ["inventive", "创造性"], ["value", "价值"],
    ["audit", "审计与限制"],
  ];
  $("resultTabs").replaceChildren(...tabs.map(([key, label]) => {
    const button = el("button", `tab-button ${state.activeTab === key ? "active" : ""}`, label);
    button.type = "button";
    button.addEventListener("click", () => { state.activeTab = key; renderReport(); });
    return button;
  }));
  renderActiveTab();
}

function renderActiveTab() {
  const report = state.report;
  const root = $("tabContent");
  root.replaceChildren();
  if (state.activeTab === "overview") renderOverview(root, report);
  if (state.activeTab === "features") renderFeatures(root, report);
  if (state.activeTab === "search") renderSearch(root, report);
  if (state.activeTab === "novelty") renderNovelty(root, report);
  if (state.activeTab === "inventive") renderInventive(root, report);
  if (state.activeTab === "value") renderValue(root, report);
  if (state.activeTab === "audit") renderAudit(root, report);
}

function renderOverview(root, report) {
  const facts = el("div", "fact-grid");
  const search = report.search_execution;
  facts.append(
    fact("评估日", report.evaluation.date), fact("候选文献", search.unique_candidate_count),
    fact("深度核验", search.deep_review_count), fact("原始命中", search.raw_hit_count),
    fact("模型", report.provenance.model), fact("Workflow", report.provenance.workflow_version),
  );
  root.append(section("执行摘要", report.conclusion_overview.executive_summary), facts);
  root.append(section("模拟审查意见", report.simulated_office_action));
}

function renderFeatures(root, report) {
  const table = makeTable(["ID", "必要", "来源", "技术特征"]);
  for (const feature of report.idea_features) {
    addRow(table, [feature.feature_id, feature.required ? "是" : "否", feature.source_type, feature.feature_text]);
  }
  root.append(table);
}

function renderSearch(root, report) {
  const execution = report.search_execution;
  root.append(section("检索执行", `共 ${execution.queries.length} 条检索式、${execution.provider_call_count} 次 Provider 调用；${execution.raw_hit_count} 条原始命中合并为 ${execution.unique_candidate_count} 个候选。`));
  const providerGrid = el("div", "fact-grid");
  for (const [name, status] of Object.entries(report.provider_status)) {
    providerGrid.append(fact(name, `${status.successes}/${status.calls} 成功 · ${status.result_count} 结果`));
  }
  root.append(providerGrid, el("div", "section-block"));
  const docs = el("div", "section-block");
  docs.append(el("h3", "", `深度核验文献（${report.deep_review_documents.length}）`));
  for (const doc of report.deep_review_documents) {
    const card = el("article", "doc-card");
    const header = el("header");
    header.append(el("strong", "", doc.publication_number), tag(doc.relevance || "ANALYZED"));
    card.append(header, el("p", "", doc.title || "无标题"), el("span", "small", `${doc.publication_date || "日期未知"} · ${doc.assignee || "申请人未知"}`));
    const mappings = el("div");
    for (const mapping of doc.feature_mappings) mappings.append(tag(`${mapping.feature_id} ${mapping.status}`, mapping.status));
    card.append(mappings);
    docs.append(card);
  }
  root.append(docs);
}

function renderNovelty(root, report) {
  const novelty = report.novelty;
  root.append(section("裁决理由", novelty.rationale));
  const facts = el("div", "fact-grid");
  facts.append(
    fact("最接近文献", novelty.closest_publication_number),
    fact("破坏性文献", novelty.destroying_publication_number || "无"),
    fact("缺失特征", novelty.missing_features.join(", ") || "无"),
  );
  root.append(facts, el("div", "section-block"));
  const table = makeTable(["单篇文献", "逐特征覆盖", "破坏新颖性"]);
  for (const matrix of novelty.matrices) {
    const mappings = matrix.mappings.map((item) => `${item.feature_id}:${item.status}`).join(" · ");
    addRow(table, [matrix.publication_number, mappings, matrix.destroys_novelty ? "是" : "否"]);
  }
  root.append(table);
}

function renderInventive(root, report) {
  if (!report.inventiveness.length) {
    root.append(section("创造性分析不适用", "已有单篇文献破坏新颖性，因此没有继续消耗模型调用构造 D1/D2 路线。"));
    return;
  }
  for (const route of report.inventiveness) {
    const card = el("article", "route-card");
    const header = el("header");
    header.append(el("strong", "", `${route.route_id} · D1 ${route.d1_publication_number}`), tag(route.status, route.status));
    card.append(header, el("p", "", route.objective_technical_problem), el("p", "small", route.overall_rationale));
    for (const item of route.distinguishing_features) {
      card.append(el("p", "", `${item.feature_id}：D2 ${item.d2_publication_numbers.join(", ") || "无"} · 组合动机 ${item.motivation_to_combine}`));
    }
    root.append(card);
  }
}

function renderValue(root, report) {
  const value = report.value_assessment;
  const grid = el("div", "fact-grid");
  grid.append(
    valueFact("可取证性", value.detectability), valueFact("规避难度", value.workaround_difficulty),
    valueFact("技术/市场价值", value.technical_market_value),
  );
  root.append(grid, section("申请建议", `${value.recommendation}：${value.rationale}`));
  const paths = el("ul", "limitation-list");
  for (const path of value.alternative_paths) paths.append(el("li", "", path));
  const block = el("div", "section-block");
  block.append(el("h3", "", "替代路径"), paths);
  root.append(block);
}

function renderAudit(root, report) {
  const counts = report.audit.counts;
  const facts = el("div", "fact-grid");
  facts.append(fact("Critical", counts.critical), fact("Warning", counts.warning), fact("Info", counts.info));
  root.append(facts, el("div", "section-block"));
  for (const finding of report.audit.findings) {
    const item = el("article", "finding");
    item.append(tag(finding.severity, finding.severity), el("strong", "", ` ${finding.code}`), el("p", "", finding.message));
    root.append(item);
  }
  const limitations = el("ul", "limitation-list");
  for (const item of report.limitations) limitations.append(el("li", "", `${item.code || "LIMITATION"}：${item.message || JSON.stringify(item)}`));
  const block = el("div", "section-block");
  block.append(el("h3", "", "检索与分析局限"), limitations);
  root.append(block);
}

async function cancelSelectedRun() {
  if (!state.selectedRun || isTerminal(state.selectedRun.status)) return;
  if (!confirm("确定取消当前 Run？已完成步骤和审计记录会保留。")) return;
  await api(`/api/idea/runs/${state.selectedRun.run_id}/cancel`, { method: "POST", body: "{}" });
}

async function rerunSelected() {
  if (!state.selectedRun) return;
  const apiKey = $("apiToken").value.trim();
  if (!apiKey) {
    setMessage("重新运行前，请输入本页使用的 API Token");
    $("apiToken").focus();
    return;
  }
  try {
    const run = await api(`/api/idea/runs/${state.selectedRun.run_id}/rerun`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    });
    await loadCases(run.case_id);
    await activateRun(run);
    subscribeToRun(run.run_id);
  } catch (error) {
    setMessage(error.message);
  }
}

async function deleteSelectedRun() {
  if (!state.selectedRun || !confirm("永久删除这个 Run 的输入、结果和报告？此操作不可恢复。")) return;
  const caseId = state.selectedRun.case_id;
  await api(`/api/idea/runs/${state.selectedRun.run_id}`, { method: "DELETE", body: "{}" });
  closeEvents();
  state.selectedRun = null;
  state.report = null;
  $("reportView").classList.add("hidden");
  $("emptyResult").classList.remove("hidden");
  renderEmptyProgress();
  await loadCases(caseId);
}

async function deleteCase(caseId, title) {
  if (!confirm(`永久删除 Case「${title}」及其全部 Run？`)) return;
  await api(`/api/idea/cases/${caseId}`, { method: "DELETE", body: "{}" });
  if (state.selectedCase?.case_id === caseId) {
    closeEvents();
    state.selectedCase = null;
    state.selectedRun = null;
    state.report = null;
    $("activeCaseBadge").textContent = "未选择 Case";
    $("reportView").classList.add("hidden");
    $("emptyResult").classList.remove("hidden");
    renderEmptyProgress();
  }
  await loadCases();
}

function applyModeDefaults() {
  const values = MODE_DEFAULTS[$("searchMode").value];
  $("candidateMax").value = values.candidate_max;
  $("deepMin").value = values.deep_review_min;
  $("deepMax").value = values.deep_review_max;
}

function section(title, text) {
  const block = el("section", "section-block");
  block.append(el("h3", "", title), el("p", "", text || "—"));
  return block;
}

function fact(label, value) {
  const item = el("div", "fact");
  item.append(el("span", "", label), el("strong", "", String(value ?? "—")));
  return item;
}

function valueFact(label, dimension) {
  const item = fact(label, dimension.rating);
  item.append(el("p", "small", dimension.rationale));
  return item;
}

function makeTable(headers) {
  const table = el("table", "data-table");
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  headers.forEach((header) => row.append(el("th", "", header)));
  head.append(row);
  table.append(head, document.createElement("tbody"));
  return table;
}

function addRow(table, values) {
  const row = document.createElement("tr");
  values.forEach((value) => row.append(el("td", "", String(value ?? "—"))));
  table.querySelector("tbody").append(row);
}

function tag(text, kind = text) {
  return el("span", `tag ${String(kind).toLowerCase().replaceAll("_", "-")}`, text);
}

function el(tagName, className = "", text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function numberValue(id) {
  const value = Number($(id).value);
  return Number.isFinite(value) ? value : null;
}

function statusClass(status = "") {
  const value = status.toLowerCase();
  if (value === "queued") return "neutral";
  if (value === "completed_with_limitations") return "completed";
  return value;
}

function isTerminal(status) {
  return ["COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"].includes(status);
}

function formatTime(milliseconds) {
  if (!milliseconds) return "—";
  return new Date(milliseconds).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatNumber(value) {
  return typeof value === "number" ? value.toFixed(2) : "—";
}

function setMessage(message) { $("formMessage").textContent = message || ""; }
function cssEscape(value) { return window.CSS?.escape ? CSS.escape(value) : value.replaceAll('"', '\\"'); }
