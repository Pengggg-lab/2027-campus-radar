const state = {
  data: null,
  region: "全部",
  status: null,
  query: "",
};

const statusOrder = { today: 0, released: 1, possible: 2, not_found: 3, error: 4, not_checked: 5 };
const statusNames = {
  today: "今日更新",
  released: "已发现 2027 校招",
  possible: "有校招入口，年份待核实",
  not_found: "暂未发现 2027 校招",
  error: "访问异常，待核实",
  not_checked: "待扫描",
};

const elements = {
  updated: document.querySelector("#updated-time"),
  resultCount: document.querySelector("#result-count"),
  list: document.querySelector("#company-list"),
  empty: document.querySelector("#empty-state"),
  search: document.querySelector("#search"),
  clearSearch: document.querySelector("#clear-search"),
  activeFilter: document.querySelector("#active-filter"),
  activeFilterText: document.querySelector("#active-filter-text"),
  resetFilter: document.querySelector("#reset-filter"),
  emptyReset: document.querySelector("#empty-reset"),
};

function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function formatUpdate(value) {
  if (!value) return "尚未扫描";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatDate(value) {
  if (!value) return null;
  const parts = String(value).split("-");
  if (parts.length === 3) return `${Number(parts[1])}月${Number(parts[2])}日`;
  return String(value);
}

function allCompanies() {
  return state.data?.companies || [];
}

function filteredCompanies() {
  const query = state.query.trim().toLowerCase();
  return allCompanies()
    .filter((item) => state.region === "全部" || item.region === state.region)
    .filter((item) => {
      if (!state.status) return true;
      if (state.status === "released") return ["released", "today"].includes(item.status);
      return item.status === state.status;
    })
    .filter((item) => {
      if (!query) return true;
      return [item.name, item.region, item.evidence, item.pageTitle, item.statusLabel]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .sort((a, b) => {
      const order = (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99);
      if (order) return order;
      const time = String(b.lastChecked || "").localeCompare(String(a.lastChecked || ""));
      if (time) return time;
      return a.name.localeCompare(b.name, "zh-CN");
    });
}

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function createLink(label, url, className = "") {
  const link = createElement("a", className, label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function renderCard(item) {
  const card = createElement("article", "company-card");
  card.dataset.status = item.status;

  const head = createElement("div", "card-head");
  const titleWrap = createElement("div");
  const meta = createElement("div", "company-meta");
  meta.append(
    createElement("span", "region-tag", item.region === "全国" ? "央企" : item.region),
    createElement("span", "row-tag", `${item.group} · ${item.checkSource || "官网入口"}`),
  );
  titleWrap.append(meta, createElement("h3", "", item.name));
  head.append(titleWrap, createElement("span", `status-badge ${item.status}`, item.statusLabel || statusNames[item.status]));

  const evidence = createElement("p", "evidence");
  evidence.textContent = item.checkError && item.status === "error"
    ? `本次检查：${item.checkError}`
    : item.evidence || "本次扫描未提取到可读的招聘宣传文案，请点击官网进一步确认。";

  const checkMeta = createElement("div", "check-meta");
  if (item.evidenceDate) checkMeta.append(createElement("span", "", `页面日期 ${formatDate(item.evidenceDate)}`));
  checkMeta.append(createElement("span", "", `检查于 ${formatUpdate(item.lastChecked)}`));
  if (item.stale) checkMeta.append(createElement("span", "", "今日未验证，保留上次结果"));
  if (item.subsidiaryHint) checkMeta.append(createElement("span", "", "页面含总部/子公司招聘信息"));
  if (item.previousStatus && item.previousStatus !== item.status) {
    checkMeta.append(createElement("span", "", `上次状态：${statusNames[item.previousStatus] || item.previousStatus}`));
  }

  const cardBody = [head, evidence, checkMeta];

  const related = (item.relatedLinks || [])
    .filter((link) => {
      const url = safeUrl(link.url);
      return url && url !== safeUrl(item.campusUrl) && url !== safeUrl(item.officialUrl);
    })
    .slice(0, 4);
  if (related.length) {
    const relatedWrap = createElement("div", "related-links");
    for (const itemLink of related) {
      const url = safeUrl(itemLink.url);
      if (url) relatedWrap.append(createLink(itemLink.label || "相关招聘信息", url));
    }
    if (relatedWrap.childElementCount) cardBody.push(relatedWrap);
  }

  const actions = createElement("div", "card-actions");
  const campusUrl = safeUrl(item.campusUrl);
  if (campusUrl) {
    actions.append(createLink(item.status === "today" ? "查看今日更新" : "立即网申", campusUrl, "primary"));
  } else {
    actions.append(createElement("span", "primary disabled", "暂无网申链接"));
  }
  const officialUrl = safeUrl(item.officialUrl);
  if (officialUrl) actions.append(createLink("企业官网", officialUrl));
  cardBody.push(actions);

  card.append(...cardBody);
  return card;
}

function updateCounts() {
  const companies = allCompanies();
  const counts = {
    released: companies.filter((item) => ["released", "today"].includes(item.status)).length,
    today: companies.filter((item) => item.status === "today").length,
    possible: companies.filter((item) => item.status === "possible").length,
    not_found: companies.filter((item) => item.status === "not_found").length,
    error: companies.filter((item) => item.status === "error").length,
  };
  for (const [key, value] of Object.entries(counts)) {
    const target = document.querySelector(`#count-${key.replace("_", "-")}`);
    if (target) target.textContent = String(value);
  }
}

function updateActiveFilter() {
  const labels = [];
  if (state.region !== "全部") labels.push(state.region === "全国" ? "央企" : state.region);
  if (state.status) labels.push(statusNames[state.status] || state.status);
  if (state.query) labels.push(`“${state.query}”`);
  elements.activeFilter.hidden = labels.length === 0;
  elements.activeFilterText.textContent = `当前筛选：${labels.join(" · ")}`;
}

function render() {
  const companies = filteredCompanies();
  const fragment = document.createDocumentFragment();
  for (const item of companies) fragment.append(renderCard(item));
  elements.list.replaceChildren(fragment);
  elements.resultCount.textContent = String(companies.length);
  elements.empty.hidden = companies.length > 0;
  updateActiveFilter();
}

function resetAll() {
  state.region = "全部";
  state.status = null;
  state.query = "";
  elements.search.value = "";
  document.querySelectorAll(".filter-chip").forEach((chip) => chip.classList.toggle("is-active", chip.dataset.region === "全部"));
  render();
}

function bindEvents() {
  elements.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });
  elements.clearSearch.addEventListener("click", () => {
    state.query = "";
    elements.search.value = "";
    elements.search.focus();
    render();
  });
  document.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.region = chip.dataset.region;
      document.querySelectorAll(".filter-chip").forEach((other) => other.classList.toggle("is-active", other === chip));
      render();
    });
  });
  document.querySelectorAll(".stat-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.status = state.status === card.dataset.statusFilter ? null : card.dataset.statusFilter;
      render();
      document.querySelector(".results").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  elements.resetFilter.addEventListener("click", resetAll);
  elements.emptyReset.addEventListener("click", resetAll);
}

async function init() {
  bindEvents();
  try {
    const response = await fetch("data/companies.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    elements.updated.textContent = formatUpdate(state.data.meta?.scannedAt || state.data.meta?.generatedAt);
    updateCounts();
    render();
  } catch (error) {
    elements.updated.textContent = "读取失败";
    elements.list.replaceChildren(createElement("p", "empty-state", `数据加载失败：${error.message}`));
  }
}

init();
