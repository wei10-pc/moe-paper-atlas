const state = {
  query: "",
  tier: "all",
  year: "all",
  venue: "all",
  source: "all",
};

const els = {
  total: document.getElementById("statTotal"),
  strict: document.getElementById("statStrict"),
  adjacent: document.getElementById("statAdjacent"),
  showing: document.getElementById("statShowing"),
  generatedAt: document.getElementById("generatedAt"),
  resultTitle: document.getElementById("resultTitle"),
  activeSummary: document.getElementById("activeSummary"),
  search: document.getElementById("searchInput"),
  tier: document.getElementById("tierFilter"),
  year: document.getElementById("yearFilter"),
  venue: document.getElementById("venueFilter"),
  source: document.getElementById("sourceFilter"),
  clear: document.getElementById("clearFilters"),
  yearNav: document.getElementById("yearNav"),
  groups: document.getElementById("paperGroups"),
  template: document.getElementById("paperCardTemplate"),
};

let papers = [];
let summary = {};

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

function normalized(value) {
  return String(value || "").toLowerCase();
}

function yearLabel(year) {
  return year ? String(year) : "Unknown";
}

function tierLabel(tier) {
  return tier === "strict_moe" ? "Strict MoE" : "Expert / routing";
}

function tagLabel(tag) {
  return String(tag || "").replaceAll("\\b", "").replaceAll("\\", "");
}

function safeId(value) {
  return `year-${String(value).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function setOptions(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = allLabel;
  select.appendChild(all);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function initializeFilters() {
  const years = [...new Set(papers.map((paper) => yearLabel(paper.year)))].sort((a, b) => {
    if (a === "Unknown") return 1;
    if (b === "Unknown") return -1;
    return Number(b) - Number(a);
  });
  const venues = [...new Set(papers.map((paper) => paper.venue || "Unknown venue"))]
    .sort((a, b) => a.localeCompare(b));
  const sources = [...new Set(papers.map((paper) => paper.source || "Unknown source"))]
    .sort((a, b) => a.localeCompare(b));

  setOptions(els.year, years, "All years");
  setOptions(els.venue, venues, "All venues");
  setOptions(els.source, sources, "All sources");
}

function passesFilters(paper) {
  const haystack = normalized([
    paper.title,
    paper.title_zh,
    paper.abstract,
    paper.abstract_zh,
    paper.authors,
    paper.venue,
    paper.source,
    ...(paper.tags || []),
  ].join(" "));

  if (state.query && !haystack.includes(state.query)) return false;
  if (state.tier !== "all" && paper.tier !== state.tier) return false;
  if (state.year !== "all" && yearLabel(paper.year) !== state.year) return false;
  if (state.venue !== "all" && (paper.venue || "Unknown venue") !== state.venue) return false;
  if (state.source !== "all" && (paper.source || "Unknown source") !== state.source) return false;
  return true;
}

function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    if (!acc.has(key)) acc.set(key, []);
    acc.get(key).push(item);
    return acc;
  }, new Map());
}

function makeTextElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function summarizeFilters(filteredCount) {
  const active = [];
  if (state.query) active.push(`"${state.query}"`);
  if (state.tier !== "all") active.push(tierLabel(state.tier));
  if (state.year !== "all") active.push(state.year);
  if (state.venue !== "all") active.push(state.venue);
  if (state.source !== "all") active.push(state.source);

  els.resultTitle.textContent = active.length ? "Filtered Papers" : "All Vision MoE Papers";
  els.activeSummary.textContent = active.length
    ? `${formatNumber(filteredCount)} results · ${active.join(" · ")}`
    : `${formatNumber(filteredCount)} papers · all sources`;
}

function renderYearNav(years, byYear) {
  els.yearNav.innerHTML = "";
  years.forEach((year) => {
    const link = document.createElement("a");
    link.href = `#${safeId(year)}`;
    link.textContent = `${year}`;
    link.dataset.count = formatNumber(byYear.get(year).length);
    els.yearNav.appendChild(link);
  });
}

function renderPaper(paper, index) {
  const node = els.template.content.cloneNode(true);
  const article = node.querySelector(".paper-entry");
  const rank = node.querySelector(".rank");
  const tier = node.querySelector(".tier-badge");
  const venue = node.querySelector(".venue-badge");
  const source = node.querySelector(".source-badge");
  const link = node.querySelector(".paper-link");
  const enTitle = node.querySelector(".en-title");
  const zhTitle = node.querySelector(".zh-title");
  const authors = node.querySelector(".authors");
  const original = node.querySelector(".abstract.original");
  const translated = node.querySelector(".abstract.translated");
  const tags = node.querySelector(".tag-row");

  rank.textContent = String(index).padStart(2, "0");
  tier.textContent = tierLabel(paper.tier);
  if (paper.tier !== "strict_moe") tier.classList.add("adjacent");
  venue.textContent = `${paper.venue || "Unknown venue"} · ${yearLabel(paper.year)}`;
  source.textContent = paper.source || "Unknown source";
  link.href = paper.url || "#";

  enTitle.textContent = paper.title || "Untitled";
  zhTitle.textContent = paper.title_zh || "中文标题待生成";
  authors.textContent = paper.authors || "Authors unavailable";
  const isTitleOnly = (paper.tags || []).includes("title_only") || !paper.abstract;
  original.textContent = paper.abstract || "No abstract was available in this source. This paper was collected because its title matches MoE, routing, gating, or expert-system terms.";
  translated.textContent = paper.abstract_zh || (isTitleOnly
    ? "该来源没有摘要；本条因标题命中 MoE、routing、gating 或 expert-system 等关键词被收录。"
    : "中文摘要待生成。");

  (paper.tags || []).forEach((tag) => {
    tags.appendChild(makeTextElement("span", "tag", tagLabel(tag)));
  });

  article.dataset.tier = paper.tier;
  return node;
}

function render() {
  const filtered = papers.filter(passesFilters);
  els.showing.textContent = formatNumber(filtered.length);
  els.groups.innerHTML = "";
  summarizeFilters(filtered.length);

  if (!filtered.length) {
    els.yearNav.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No papers match the current filters.";
    els.groups.appendChild(empty);
    return;
  }

  const byYear = groupBy(filtered, (paper) => yearLabel(paper.year));
  const years = [...byYear.keys()].sort((a, b) => {
    if (a === "Unknown") return 1;
    if (b === "Unknown") return -1;
    return Number(b) - Number(a);
  });

  renderYearNav(years, byYear);

  let globalIndex = 1;
  years.forEach((year) => {
    const yearItems = byYear.get(year);
    const yearSection = document.createElement("section");
    yearSection.className = "year-section";
    yearSection.id = safeId(year);

    const yearHeading = document.createElement("div");
    yearHeading.className = "year-heading";
    yearHeading.appendChild(makeTextElement("h2", "", year));
    yearHeading.appendChild(makeTextElement("span", "", `${formatNumber(yearItems.length)} papers`));
    yearSection.appendChild(yearHeading);

    const byVenue = groupBy(yearItems, (paper) => paper.venue || "Unknown venue");
    const venues = [...byVenue.keys()].sort((a, b) => {
      const diff = byVenue.get(b).length - byVenue.get(a).length;
      return diff || a.localeCompare(b);
    });

    venues.forEach((venueName) => {
      const venueItems = byVenue.get(venueName).sort((a, b) => {
        if (a.tier !== b.tier) return a.tier === "strict_moe" ? -1 : 1;
        return normalized(a.title).localeCompare(normalized(b.title));
      });

      const venueSection = document.createElement("section");
      venueSection.className = "venue-section";
      const venueHeading = document.createElement("div");
      venueHeading.className = "venue-heading";
      venueHeading.appendChild(makeTextElement("h3", "", venueName));
      venueHeading.appendChild(makeTextElement("span", "", formatNumber(venueItems.length)));
      venueSection.appendChild(venueHeading);

      const list = document.createElement("div");
      list.className = "paper-list";
      venueItems.forEach((paper) => {
        list.appendChild(renderPaper(paper, globalIndex));
        globalIndex += 1;
      });
      venueSection.appendChild(list);
      yearSection.appendChild(venueSection);
    });

    els.groups.appendChild(yearSection);
  });
}

function updateStats() {
  const strict = papers.filter((paper) => paper.tier === "strict_moe").length;
  const adjacent = papers.length - strict;
  els.total.textContent = formatNumber(papers.length);
  els.strict.textContent = formatNumber(strict);
  els.adjacent.textContent = formatNumber(adjacent);
  if (summary.generated_at) {
    const date = new Date(summary.generated_at);
    els.generatedAt.textContent = `Generated ${date.toLocaleString()}.`;
  }
}

function syncControls() {
  els.search.value = state.query;
  els.tier.value = state.tier;
  els.year.value = state.year;
  els.venue.value = state.venue;
  els.source.value = state.source;
}

function resetFilters() {
  state.query = "";
  state.tier = "all";
  state.year = "all";
  state.venue = "all";
  state.source = "all";
  syncControls();
  render();
}

function bindEvents() {
  els.search.addEventListener("input", (event) => {
    state.query = normalized(event.target.value.trim());
    render();
  });
  els.tier.addEventListener("change", (event) => {
    state.tier = event.target.value;
    render();
  });
  els.year.addEventListener("change", (event) => {
    state.year = event.target.value;
    render();
  });
  els.venue.addEventListener("change", (event) => {
    state.venue = event.target.value;
    render();
  });
  els.source.addEventListener("change", (event) => {
    state.source = event.target.value;
    render();
  });
  els.clear.addEventListener("click", resetFilters);
  document.querySelectorAll("[data-query]").forEach((button) => {
    button.addEventListener("click", () => {
      state.query = normalized(button.dataset.query || "");
      els.search.value = button.dataset.query || "";
      render();
    });
  });
}

async function boot() {
  const response = await fetch("data/papers.json");
  const data = await response.json();
  summary = data.summary || {};
  papers = (data.papers || []).filter((paper) => paper.title);
  initializeFilters();
  updateStats();
  bindEvents();
  render();
}

boot().catch((error) => {
  els.groups.innerHTML = `<div class="empty">Failed to load data: ${error.message}</div>`;
});
