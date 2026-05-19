const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const currencyExact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usdFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const usdFmtExact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

let usdRate = null;
let displayCurrency = localStorage.getItem("displayCurrency") || "EUR";

const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

let dashboardData = null;
let productFilter = "All";
let externalSources = localStorage.getItem("chatExternalSources") === "true";
let chatHistory = JSON.parse(sessionStorage.getItem("chatHistory") || "[]");

async function fetchUsdRate() {
  try {
    const response = await fetch("/api/rates");
    const data = await response.json();
    if (!data.ok || !data.rate) throw new Error("no rate");
    usdRate = data.rate;
    const usdBtn = document.querySelector('.currency-btn[data-currency="USD"]');
    if (usdBtn) {
      usdBtn.disabled = false;
      usdBtn.removeAttribute("title");
      if (displayCurrency === "USD") usdBtn.classList.add("active");
    }
    if (displayCurrency === "USD" && dashboardData) renderCurrentPage();
  } catch {
    // USD unavailable — button stays disabled
  }
}

function injectCurrencyToggle() {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;
  sidebar.querySelectorAll(".currency-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.currency === displayCurrency);
    btn.addEventListener("click", () => {
      displayCurrency = btn.dataset.currency;
      localStorage.setItem("displayCurrency", displayCurrency);
      sidebar.querySelectorAll(".currency-btn").forEach((b) =>
        b.classList.toggle("active", b === btn),
      );
      renderCurrentPage();
    });
  });
}

function setupMobileNav() {
  const sidebar = document.querySelector(".sidebar");
  const topbar = document.querySelector(".topbar");
  if (!sidebar || !topbar) return;

  const hamburger = document.createElement("button");
  hamburger.className = "hamburger";
  hamburger.setAttribute("aria-label", "Toggle navigation");
  hamburger.innerHTML = "<span></span><span></span><span></span>";
  topbar.prepend(hamburger);

  const backdrop = document.createElement("div");
  backdrop.className = "sidebar-backdrop";
  document.body.appendChild(backdrop);

  function close() {
    sidebar.classList.remove("open");
    backdrop.classList.remove("open");
  }

  hamburger.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    backdrop.classList.toggle("open");
  });
  backdrop.addEventListener("click", close);
  sidebar.querySelectorAll(".nav-link").forEach((link) =>
    link.addEventListener("click", close),
  );
}

document.addEventListener("DOMContentLoaded", async () => {
  setActiveNav();
  injectCurrencyToggle();
  setupMobileNav();
  fetchUsdRate();
  try {
    const response = await fetch("/api/dashboard");
    dashboardData = await response.json();
    updateSourcePill(dashboardData);
    renderCurrentPage();
  } catch (error) {
    showPageError(error);
  }
});

function pageName() {
  return document.body.dataset.page || "overview";
}

function setActiveNav() {
  const page = pageName();
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.page === page);
  });
}

function renderCurrentPage() {
  const page = pageName();
  if (page === "overview") renderOverview(dashboardData);
  if (page === "products") renderProducts(dashboardData);
  if (page === "forecast") renderForecast(dashboardData);
  if (page === "price") renderPriceImpact(dashboardData);
  if (page === "chat") renderChat(dashboardData);
  if (page === "data") renderDataPage(dashboardData);
}

function text(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function html(id, value) {
  const element = document.getElementById(id);
  if (element) element.innerHTML = value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCurrency(value, exact = false) {
  if (displayCurrency === "USD" && usdRate) {
    return (exact ? usdFmtExact : usdFmt).format((value || 0) * usdRate);
  }
  return (exact ? currencyExact : currency).format(value || 0);
}

function formatSignedCurrency(value) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${formatCurrency(value)}`;
}

function formatNumber(value) {
  return whole.format(value || 0);
}

function formatCompact(value) {
  return compact.format(value || 0);
}

function formatPercent(value) {
  return percent.format(value || 0);
}

function formatSignedPercent(value) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${formatPercent(value)}`;
}

function statusClass(status) {
  if (status === "Healthy") return "healthy";
  if (status === "Growth Opportunity") return "growth";
  if (status === "Matched") return "ok";
  if (status === "Error") return "error";
  return "attention";
}

function statusBadge(status) {
  return `<span class="status ${statusClass(status)}">${escapeHtml(status)}</span>`;
}

function updateSourcePill(data) {
  const pill = document.querySelector("[data-source-pill]");
  if (!pill || !data?.source) return;
  const source = data.source;
  pill.innerHTML = `
    <span class="status-dot"></span>
    <span>${escapeHtml(source.salesFile)} + ${escapeHtml(source.pricesFile)}</span>
  `;
}

function showPageError(error) {
  const main = document.querySelector("main");
  if (!main) return;
  main.insertAdjacentHTML(
    "beforeend",
    `<div class="notice">The dashboard could not load: ${escapeHtml(error.message)}</div>`,
  );
}

function renderOverview(data) {
  text("kpi-revenue", formatCurrency(data.kpis.totalRevenue));
  text("kpi-profit", formatCurrency(data.kpis.totalProfit));
  text("kpi-units", formatNumber(data.kpis.unitsSold));
  text("kpi-asp", formatCurrency(data.kpis.averageSellingPrice, true));
  text("kpi-prediction", formatCurrency(data.kpis.predictedNextMonthSales));
  text("kpi-source", `${data.source.dateRange}`);

  renderLineChart("overview-trend", data.forecast.series, {
    yFormatter: formatCompact,
    actualLabel: "Actual revenue",
    forecastLabel: "Expected revenue",
  });

  renderRecommendedFocus(data.products);
  renderInsights(data.insights);

  const focusProducts = [...data.products]
    .sort((a, b) => {
      const weight = { "Needs Attention": 3, "Growth Opportunity": 2, Healthy: 1 };
      return (weight[b.status] || 0) - (weight[a.status] || 0) || b.revenue - a.revenue;
    })
    .slice(0, 5);

  html(
    "overview-focus",
    focusProducts
      .map(
        (row) => `
          <div class="watch-row">
            <div>
              <strong>${escapeHtml(row.description)}</strong>
              <span>${escapeHtml(row.material)} - ${formatCurrency(row.revenue)}</span>
            </div>
            ${statusBadge(row.status)}
          </div>
        `,
      )
      .join(""),
  );
}

function renderRecommendedFocus(products) {
  const needsAttention = products.filter((row) => row.status === "Needs Attention");
  const growth = products.filter((row) => row.status === "Growth Opportunity");
  const marginRisk = [...needsAttention].sort((a, b) => a.profit - b.profit)[0];
  const investigate = [...needsAttention].sort((a, b) => b.revenue - a.revenue)[0];
  const growthCandidates = [...growth].sort((a, b) => b.trendPct - a.trendPct).slice(0, 2);
  const fallback = [...products].sort((a, b) => b.revenue - a.revenue)[0];

  const cards = [
    {
      label: "Review low-profit product",
      title: marginRisk ? `${marginRisk.description} - ${marginRisk.material}` : `${fallback.description} - ${fallback.material}`,
      body: marginRisk
        ? marginRisk.recommendedAction
        : "Review price and cost before adding more promotion.",
    },
    {
      label: "Investigate",
      title: investigate ? `${investigate.description} - ${investigate.material}` : `${fallback.description} - ${fallback.material}`,
      body: investigate
        ? "This product has meaningful sales, but profit looks weak. Review price and cost."
        : "This product has strong revenue, but a margin too thin to sustain. This is the best starting point for a price and cost review.",
    },
    {
      label: "Growth candidates",
      title: growthCandidates.length
        ? growthCandidates.map((row) => `${row.description} - ${row.material}`).join(" and ")
        : `${fallback.description} - ${fallback.material}`,
      body: growthCandidates.length
        ? "These products have recent momentum and may deserve more sales focus."
        : "Use recent demand and profit together before choosing a promotion.",
    },
    {
      label: "Next action",
      title: "Review price and cost before promotion",
      body: "Start with products marked Needs Attention, then consider Growth Opportunity products for campaigns.",
    },
  ];

  html(
    "recommended-focus",
    cards
      .map(
        (card) => `
          <article class="focus-card">
            <span>${escapeHtml(card.label)}</span>
            <strong>${escapeHtml(card.title)}</strong>
            <p>${escapeHtml(card.body)}</p>
          </article>
        `,
      )
      .join(""),
  );
}

function renderInsights(insights) {
  const markup = insights
    .map(
      (insight) => `
        <article class="insight-card">
          <span class="insight-label">${escapeHtml(insight.label)}</span>
          <h3>${escapeHtml(insight.title)}</h3>
          <p>${escapeHtml(insight.body)}</p>
          <div class="action-line">${escapeHtml(insight.action)}</div>
        </article>
      `,
    )
    .join("");
  html("insight-grid", markup);
}

function renderProducts(data) {
  bindProductControls(data);
  renderProductTable(data.products);
}

function bindProductControls(data) {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      productFilter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderProductTable(data.products);
    });
  });

  const search = document.getElementById("product-search");
  if (search) {
    search.addEventListener("input", () => renderProductTable(data.products));
  }
}

function renderProductTable(products) {
  const query = (document.getElementById("product-search")?.value || "").trim().toLowerCase();
  const filtered = products.filter((product) => {
    const matchesStatus = productFilter === "All" || product.status === productFilter;
    const matchesQuery =
      !query ||
      product.name.toLowerCase().includes(query) ||
      product.material.toLowerCase().includes(query);
    return matchesStatus && matchesQuery;
  });

  text("product-count", `${filtered.length} products`);
  renderRows("products-table", filtered, [
    {
      label: "Product",
      render: (row) =>
        `<span class="product-name">${escapeHtml(row.description)}</span><span class="product-code">${escapeHtml(row.material)}</span>`,
    },
    { label: "Revenue", className: "numeric", render: (row) => formatCurrency(row.revenue) },
    { label: "Quantity", className: "numeric", render: (row) => formatNumber(row.quantity) },
    { label: "Profit", className: "numeric", render: (row) => formatCurrency(row.profit) },
    { label: "Price", className: "numeric", render: (row) => formatCurrency(row.currentPrice, true) },
    { label: "Recent trend", className: "numeric", render: (row) => formatSignedPercent(row.trendPct) },
    { label: "AI status", render: (row) => statusBadge(row.status) },
    { label: "Plain-English reason", render: (row) => escapeHtml(row.explanation) },
    { label: "Recommended action", render: (row) => escapeHtml(row.recommendedAction) },
  ]);
}

function renderForecast(data) {
  text("forecast-revenue", formatCurrency(data.forecast.expectedRevenue));
  text("forecast-units", formatNumber(data.forecast.expectedUnits));
  text("forecast-profit", formatCurrency(data.forecast.expectedProfit));
  text("forecast-summary", data.forecast.summary);
  text(
    "forecast-confidence",
    `Early estimate based on limited sales history (${data.source.dateRange}). Use this as a directional planning signal.`,
  );

  renderLineChart("forecast-chart", data.forecast.series, {
    yFormatter: formatCompact,
    actualLabel: "Historical sales",
    forecastLabel: "Expected sales",
  });

  renderRows("monthly-table", data.forecast.monthly, [
    { label: "Month", render: (row) => escapeHtml(row.month) },
    { label: "Revenue", className: "numeric", render: (row) => formatCurrency(row.revenue) },
    { label: "Profit", className: "numeric", render: (row) => formatCurrency(row.profit) },
    { label: "Units sold", className: "numeric", render: (row) => formatNumber(row.quantity) },
  ]);
}

function renderPriceImpact(data) {
  text("price-summary", data.priceImpact.summary);
  renderScatter("price-scatter", data.priceImpact.scatter);

  const slider = document.getElementById("price-change-slider");
  const updateScenario = () => {
    const selectedPct = slider ? Number(slider.value) / 100 : 0.05;
    renderPriceScenario(data, selectedPct);
  };

  if (slider && slider.dataset.bound !== "true") {
    slider.dataset.bound = "true";
    slider.addEventListener("input", updateScenario);
  }

  updateScenario();
}

function renderPriceScenario(data, priceChangePct) {
  const whatIf = data.priceImpact.whatIf;
  const scenario = calculatePriceScenario(whatIf, priceChangePct);
  const moveText = priceMoveText(priceChangePct);
  const selectedText = formatScenarioPercent(priceChangePct);

  text("price-summary", data.priceImpact.summary);
  text("price-change-value", selectedText);
  text("whatif-revenue-label", priceChangePct === 0 ? "No price change" : `If prices ${moveText}`);
  text("whatif-revenue", formatSignedCurrency(scenario.revenueChange));
  text("whatif-profit", formatSignedCurrency(scenario.profitChange));
  text("whatif-units", formatSignedPercent(scenario.expectedUnitChangePct));
  text("whatif-revenue-detail", formatSignedCurrency(scenario.revenueChange));
  text("whatif-profit-detail", formatSignedCurrency(scenario.profitChange));
  text("whatif-action", scenario.action);

  const typicalRec = Math.max(...data.priceImpact.byProduct.map((r) => recommendProductPriceChange(r).change));
  const discrepancyNote =
    priceChangePct > 0 && typicalRec > 0 && priceChangePct > typicalRec
      ? ` The table below recommends testing a smaller ${formatScenarioPercent(typicalRec)} move first — the model projects higher revenue at ${formatScenarioPercent(priceChangePct)}, but that estimate assumes demand reacts predictably. A smaller test validates the assumption before committing.`
      : "";
  text("price-note", scenario.explanation + discrepancyNote);
  text(
    "whatif-copy",
    priceChangePct === 0
      ? `At no price change, expected revenue remains ${formatCurrency(
          scenario.expectedRevenue,
        )} and expected units remain ${formatNumber(scenario.expectedUnits)}.`
      : `If prices ${moveText}, expected revenue becomes ${formatCurrency(
          scenario.expectedRevenue,
        )} and expected units become ${formatNumber(
          scenario.expectedUnits,
        )}. ${scenario.explanation}`,
  );

  const productRows = data.priceImpact.byProduct
    .map((row) => ({
      ...row,
      scenario: calculateProductPriceScenario(row, priceChangePct),
      recommendation: recommendProductPriceChange(row),
    }))
    .sort((a, b) => Math.abs(b.scenario.revenueChange) - Math.abs(a.scenario.revenueChange));

  renderRows("price-table", productRows, [
    {
      label: "Product",
      render: (row) =>
        `<span class="product-name">${escapeHtml(row.description)}</span><span class="product-code">${escapeHtml(row.material)}</span>`,
    },
    { label: "Avg price", className: "numeric", render: (row) => formatCurrency(row.avgPrice, true) },
    { label: "Observed price change", className: "numeric", render: (row) => formatSignedPercent(row.priceChangePct) },
    { label: "Observed volume change", className: "numeric", render: (row) => formatSignedPercent(row.volumeChangePct) },
    { label: `${selectedText} revenue result`, className: "numeric", render: (row) => formatSignedCurrency(row.scenario.revenueChange) },
    { label: "Unit change", className: "numeric", render: (row) => formatSignedPercent(row.scenario.unitChangePct) },
    { label: "Signal", render: (row) => `<span class="badge">${escapeHtml(row.scenario.signal)}</span>` },
    { label: "Recommended test", render: (row) => `<span class="badge">${escapeHtml(row.recommendation.label)}</span>` },
  ]);
}

function calculatePriceScenario(whatIf, priceChangePct) {
  const currentRevenue = whatIf.currentRevenue || 0;
  const currentProfit = whatIf.currentProfit || 0;
  const currentUnits = whatIf.currentUnits || 0;
  const sensitivity = whatIf.priceChangePct
    ? whatIf.expectedUnitChangePct / whatIf.priceChangePct
    : -0.45;
  const expectedUnitChangePct = sensitivity * priceChangePct;
  const unitFactor = Math.max(0, 1 + expectedUnitChangePct);
  const priceFactor = Math.max(0, 1 + priceChangePct);
  const avgPrice = currentUnits ? currentRevenue / currentUnits : 0;
  const avgCost = currentUnits ? (currentRevenue - currentProfit) / currentUnits : 0;
  const expectedUnits = currentUnits * unitFactor;
  const expectedRevenue = expectedUnits * avgPrice * priceFactor;
  const expectedProfit = expectedRevenue - expectedUnits * avgCost;
  const revenueChange = expectedRevenue - currentRevenue;
  const profitChange = expectedProfit - currentProfit;

  let action = "Test carefully";
  let explanation = "Revenue can fall while profit improves because fewer units may sell, but each unit can earn more.";
  if (priceChangePct < 0) {
    action = profitChange < 0 ? "Protect profit" : "Test discount";
    explanation = "A lower price may increase units sold, but profit per unit may shrink.";
  } else if (priceChangePct === 0) {
    action = "No price change";
    explanation = "This keeps the current price assumption unchanged.";
  } else if (profitChange > 0) {
    action = "Test carefully";
  } else {
    action = "Review before changing";
  }

  return {
    expectedUnits,
    expectedRevenue,
    expectedProfit,
    revenueChange,
    profitChange,
    expectedUnitChangePct,
    action,
    explanation,
  };
}

function calculateProductPriceScenario(row, priceChangePct) {
  const sensitivity = row.priceSensitivity ?? (row.expectedUnitChangePct ? row.expectedUnitChangePct / 0.05 : -0.45);
  const unitChangePct = sensitivity * priceChangePct;
  const unitFactor = Math.max(0, 1 + unitChangePct);
  const priceFactor = Math.max(0, 1 + priceChangePct);
  const currentUnits = row.totalUnits || 0;
  const currentRevenue = row.totalRevenue || 0;
  const currentProfit = row.totalProfit || 0;
  const avgPrice = currentUnits ? currentRevenue / currentUnits : row.avgPrice || 0;
  const avgCost = currentUnits ? (currentRevenue - currentProfit) / currentUnits : 0;
  const expectedUnits = currentUnits * unitFactor;
  const expectedRevenue = expectedUnits * avgPrice * priceFactor;
  const expectedProfit = expectedRevenue - expectedUnits * avgCost;
  const revenueChange = expectedRevenue - currentRevenue;
  const profitChange = expectedProfit - currentProfit;
  let signal = "Test carefully";
  if (priceChangePct === 0) signal = "No change";
  else if (priceChangePct < 0 && profitChange < 0) signal = "Profit may shrink";
  else if (priceChangePct < 0 && expectedUnits > currentUnits) signal = "Volume may grow";
  else if (priceChangePct > 0 && unitChangePct < -0.08) signal = "Demand may soften";
  else if (priceChangePct > 0 && profitChange > 0) signal = "Profit may improve";

  return { expectedProfit, revenueChange, profitChange, unitChangePct, signal };
}

function recommendProductPriceChange(row) {
  const margin = row.totalRevenue ? row.totalProfit / row.totalRevenue : 0;
  const sensitivity = row.priceSensitivity ?? -0.8;

  if ((row.totalProfit || 0) < 0) {
    return { change: 0, label: "Review cost first" };
  }
  if (margin < 0.05) {
    return { change: 0.05, label: "Test +5%" };
  }
  if (sensitivity <= -1.5) {
    return { change: 0, label: "Hold price" };
  }
  if (margin < 0.08) {
    return { change: 0.03, label: "Test +3%" };
  }
  if (sensitivity > -0.5 && margin > 0.12) {
    return { change: 0.03, label: "Test +3%" };
  }
  if (sensitivity > -0.8) {
    return { change: 0.02, label: "Test +2%" };
  }
  return { change: 0, label: "Hold price" };
}

function formatScenarioPercent(value) {
  const rounded = Math.round(value * 100);
  if (rounded > 0) return `+${rounded}%`;
  return `${rounded}%`;
}

function priceMoveText(value) {
  const amount = Math.abs(Math.round(value * 100));
  if (value > 0) return `increase by ${amount}%`;
  if (value < 0) return `decrease by ${amount}%`;
  return "stay the same";
}

function renderChat(data) {
  const initialSuggestions = [
    "Which products should we prioritize?",
    "Which products need attention?",
    "Which products are good promotion candidates?",
    "What happens if prices decrease by 5%?",
    "Were the files matched correctly?",
  ];

  const messagesEl = document.getElementById("chat-messages");
  if (messagesEl && messagesEl.children.length === 0) {
    renderChatSuggestions(initialSuggestions);
    if (chatHistory.length > 0) {
      rebuildMessages();
    } else {
      addChatMessage(
        "assistant",
        `Hi, I can answer questions about ${data.source.salesFile} and ${data.source.pricesFile}. Try one of the suggested questions or ask your own.`,
      );
    }
  }

  const toggle = document.getElementById("external-sources-toggle");
  if (toggle && !toggle.dataset.bound) {
    toggle.dataset.bound = "true";
    toggle.checked = externalSources;
    const warning = document.getElementById("external-warning");
    if (warning) warning.hidden = !externalSources;
    toggle.addEventListener("change", () => {
      externalSources = toggle.checked;
      localStorage.setItem("chatExternalSources", externalSources);
      if (warning) warning.hidden = !externalSources;
    });
  }

  const form = document.getElementById("chat-form");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-question");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    await askSalesAi(question);
  });
}

function renderChatSuggestions(suggestions) {
  const target = document.getElementById("chat-suggestions");
  if (!target) return;
  target.innerHTML = suggestions
    .map(
      (suggestion) =>
        `<button class="quiet-button suggestion-button" type="button">${escapeHtml(suggestion)}</button>`,
    )
    .join("");
  target.querySelectorAll(".suggestion-button").forEach((button) => {
    button.addEventListener("click", () => askSalesAi(button.textContent.trim()));
  });
}

async function askSalesAi(question) {
  addChatMessage("user", question);
  const loadingId = addChatMessage("assistant", "Checking the sales and price data...");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, external: externalSources, currency: displayCurrency, usdRate: usdRate }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Ask Sales AI could not answer right now.");
    }
    replaceChatMessage(loadingId, payload.answer, payload);
    if (payload.suggestions) renderChatSuggestions(payload.suggestions);
  } catch (error) {
    replaceChatMessage(loadingId, error.message, { cards: [], products: [] });
  }
}

function addChatMessage(role, body) {
  const target = document.getElementById("chat-messages");
  if (!target) return "";
  const id = `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  target.insertAdjacentHTML(
    "beforeend",
    `
      <div class="chat-message ${role}" id="${id}">
        <div class="chat-role">${role === "user" ? "You" : "Ask Sales AI"}</div>
        <p>${escapeHtml(body)}</p>
      </div>
    `,
  );
  target.scrollTop = target.scrollHeight;
  chatHistory.push({ id, role, body, cards: [], products: [] });
  sessionStorage.setItem("chatHistory", JSON.stringify(chatHistory));
  return id;
}

function buildChatCardsHtml(cards) {
  if (!cards?.length) return "";
  return `<div class="chat-card-grid">${cards
    .map(
      (card) =>
        `<div class="chat-card">
          <span>${escapeHtml(card.label)}</span>
          <strong>${card.valueRaw != null ? escapeHtml(formatCurrency(card.valueRaw)) : escapeHtml(card.value)}</strong>
          <p>${escapeHtml(card.note || "")}</p>
        </div>`,
    )
    .join("")}</div>`;
}

function buildChatProductsHtml(products) {
  if (!products?.length) return "";
  return `<div class="chat-products">${products
    .slice(0, 4)
    .map(
      (p) =>
        `<div class="chat-product">
          <div>
            <strong>${escapeHtml(p.description || p.name)}</strong>
            <span>${escapeHtml(p.material || "")} - ${formatCurrency(p.revenue || p.expectedRevenueChange || 0)}</span>
          </div>
          ${p.status ? statusBadge(p.status) : `<span class="badge">${escapeHtml(p.signal || "Price signal")}</span>`}
        </div>`,
    )
    .join("")}</div>`;
}

function replaceChatMessage(id, body, payload) {
  const message = document.getElementById(id);
  if (!message) return;
  message.innerHTML = `
    <div class="chat-role">Ask Sales AI</div>
    <p>${escapeHtml(body)}</p>
    ${buildChatCardsHtml(payload.cards)}
    ${buildChatProductsHtml(payload.products)}
  `;
  message.scrollIntoView({ block: "nearest" });
  const entry = chatHistory.find((m) => m.id === id);
  if (entry) {
    entry.body = body;
    entry.cards = payload.cards || [];
    entry.products = payload.products || [];
    sessionStorage.setItem("chatHistory", JSON.stringify(chatHistory));
  }
}

function rebuildMessages() {
  const target = document.getElementById("chat-messages");
  if (!target) return;
  chatHistory.forEach((msg) => {
    if (msg.role === "user") {
      target.insertAdjacentHTML(
        "beforeend",
        `<div class="chat-message user" id="${msg.id}">
          <div class="chat-role">You</div>
          <p>${escapeHtml(msg.body)}</p>
        </div>`,
      );
    } else {
      target.insertAdjacentHTML(
        "beforeend",
        `<div class="chat-message assistant" id="${msg.id}">
          <div class="chat-role">Ask Sales AI</div>
          <p>${escapeHtml(msg.body)}</p>
          ${buildChatCardsHtml(msg.cards)}
          ${buildChatProductsHtml(msg.products)}
        </div>`,
      );
    }
  });
  target.scrollTop = target.scrollHeight;
}

function renderDataPage(data) {
  bindUploadForm();
  renderMatchStats(data);
  renderPreviewTables(data);
  renderDefaultDownloads(data);
}

function renderDefaultDownloads(data) {
  const el = document.getElementById("default-downloads");
  if (!el) return;
  const isDefault =
    data.source.salesFile === "Sales.xlsx" && data.source.pricesFile === "Prices.xlsx";
  el.hidden = !isDefault;
}

function bindUploadForm() {
  const form = document.getElementById("upload-form");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sales = document.getElementById("sales-file").files[0];
    const prices = document.getElementById("prices-file").files[0];
    const message = document.getElementById("upload-message");
    if (!sales || !prices) {
      message.innerHTML = '<span class="status error">Error</span> Please choose both files.';
      return;
    }

    const formData = new FormData();
    formData.append("sales", sales);
    formData.append("prices", prices);

    message.innerHTML = '<span class="status attention">Checking</span> Matching the files now.';
    try {
      const response = await fetch("/api/upload", { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Upload failed.");
      }
      dashboardData = payload.data;
      updateSourcePill(dashboardData);
      renderMatchStats(dashboardData);
      renderPreviewTables(dashboardData);
      message.innerHTML = '<span class="status ok">Matched</span> Files were matched successfully.';
    } catch (error) {
      message.innerHTML = `<span class="status error">Error</span> ${escapeHtml(error.message)}`;
    }
  });

  const reset = document.getElementById("reset-data");
  if (reset) {
    reset.addEventListener("click", async () => {
      await fetch("/api/reset", { method: "POST" });
      const response = await fetch("/api/dashboard");
      dashboardData = await response.json();
      updateSourcePill(dashboardData);
      renderMatchStats(dashboardData);
      renderPreviewTables(dashboardData);
      renderDefaultDownloads(dashboardData);
      document.getElementById("upload-message").innerHTML =
        '<span class="status ok">Matched</span> Default files restored.';
    });
  }
}

function renderMatchStats(data) {
  const source = data.source;
  html(
    "match-stats",
    `
      <div class="match-stat"><span>Sales rows</span><strong>${formatNumber(source.salesRows)}</strong></div>
      <div class="match-stat"><span>Price rows</span><strong>${formatNumber(source.priceRows)}</strong></div>
      <div class="match-stat"><span>Matched rows</span><strong>${formatNumber(source.matchedRows)}</strong></div>
      <div class="match-stat"><span>Match rate</span><strong>${formatPercent(source.matchRate)}</strong></div>
    `,
  );
  const status = source.matchedSuccessfully ? "Matched" : "Needs Attention";
  html(
    "match-status",
    `${statusBadge(status)} <span class="muted">Sales and Prices are matched by product, channel, and date.</span>`,
  );
}

function renderPreviewTables(data) {
  renderPlainPreview("sales-preview", data.preview.sales);
  renderPlainPreview("prices-preview", data.preview.prices);
  renderPlainPreview("matched-preview", data.preview.matched);
}

function renderRows(targetId, rows, columns) {
  if (!rows.length) {
    html(targetId, '<div class="empty-state">No products match this view.</div>');
    return;
  }
  const header = columns
    .map((column) => `<th class="${column.className || ""}">${escapeHtml(column.label)}</th>`)
    .join("");
  const body = rows
    .map(
      (row) => `
        <tr>
          ${columns
            .map(
              (column) =>
                `<td class="${column.className || ""}">${column.render(row)}</td>`,
            )
            .join("")}
        </tr>
      `,
    )
    .join("");
  html(targetId, `<div class="table-wrap"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`);
}

function renderPlainPreview(targetId, rows) {
  if (!rows.length) {
    html(targetId, '<div class="empty-state">No preview rows available.</div>');
    return;
  }
  const columns = Object.keys(rows[0]).map((key) => ({
    label: key.replaceAll("_", " "),
    render: (row) => escapeHtml(row[key]),
  }));
  renderRows(targetId, rows, columns);
}

function renderLineChart(targetId, series, options = {}) {
  const container = document.getElementById(targetId);
  if (!container) return;

  const width = 920;
  const height = 320;
  const pad = { top: 22, right: 28, bottom: 42, left: 70 };
  const values = series
    .flatMap((point) => [point.actual, point.forecast])
    .filter((value) => value !== null && value !== undefined);
  const maxValue = Math.max(...values, 1);
  const minValue = 0;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (index / Math.max(series.length - 1, 1)) * plotW;
  const y = (value) => pad.top + (1 - (value - minValue) / (maxValue - minValue || 1)) * plotH;

  const actualPoints = [];
  const forecastPoints = [];
  series.forEach((point, index) => {
    if (point.actual !== null && point.actual !== undefined) {
      actualPoints.push([x(index), y(point.actual)]);
    }
    if (point.forecast !== null && point.forecast !== undefined) {
      forecastPoints.push([x(index), y(point.forecast)]);
    }
  });
  if (actualPoints.length && forecastPoints.length) {
    forecastPoints.unshift(actualPoints[actualPoints.length - 1]);
  }

  const path = (points) =>
    points.map((point, index) => `${index ? "L" : "M"} ${point[0].toFixed(1)} ${point[1].toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((tick) => {
      const yy = pad.top + tick * plotH;
      const value = maxValue * (1 - tick);
      return `
        <line class="chart-grid" x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}"></line>
        <text class="axis-label" x="${pad.left - 12}" y="${yy + 4}" text-anchor="end">${escapeHtml(
          options.yFormatter ? options.yFormatter(value) : formatCompact(value),
        )}</text>
      `;
    })
    .join("");
  const labels = [
    [0, series[0]?.label],
    [Math.floor(series.length / 2), series[Math.floor(series.length / 2)]?.label],
    [series.length - 1, series[series.length - 1]?.label],
  ]
    .map(
      ([index, label]) =>
        `<text class="axis-label" x="${x(index)}" y="${height - 12}" text-anchor="middle">${escapeHtml(label || "")}</text>`,
    )
    .join("");

  container.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sales trend chart">
      ${grid}
      <path class="chart-line" d="${path(actualPoints)}"></path>
      <path class="chart-line forecast" d="${path(forecastPoints)}"></path>
      ${labels}
    </svg>
    <div class="legend">
      <span class="legend-item"><span class="legend-swatch"></span>${escapeHtml(options.actualLabel || "Actual")}</span>
      <span class="legend-item"><span class="legend-swatch forecast"></span>${escapeHtml(options.forecastLabel || "Expected")}</span>
    </div>
  `;
}

function renderScatter(targetId, points) {
  const container = document.getElementById(targetId);
  if (!container) return;
  if (!points.length) {
    container.innerHTML = '<div class="empty-state">No price points available.</div>';
    return;
  }

  const width = 900;
  const height = 320;
  const pad = { top: 22, right: 28, bottom: 46, left: 70 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const minPrice = Math.min(...points.map((point) => point.price));
  const maxPrice = Math.max(...points.map((point) => point.price));
  const maxQty = Math.max(...points.map((point) => point.quantity), 1);
  const x = (value) => pad.left + ((value - minPrice) / (maxPrice - minPrice || 1)) * plotW;
  const y = (value) => pad.top + (1 - value / maxQty) * plotH;

  const circles = points
    .map(
      (point, index) => `
        <circle cx="${x(point.price).toFixed(1)}" cy="${y(point.quantity).toFixed(1)}" r="5"
          fill="${index % 3 === 0 ? "#22a88f" : index % 3 === 1 ? "#3b82f6" : "#f59e0b"}" opacity="0.72">
          <title>${escapeHtml(point.product)}: ${formatCurrency(point.price, true)}, ${formatNumber(point.quantity)} units</title>
        </circle>
      `,
    )
    .join("");

  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((tick) => {
      const yy = pad.top + tick * plotH;
      const value = maxQty * (1 - tick);
      return `
        <line class="chart-grid" x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}"></line>
        <text class="axis-label" x="${pad.left - 12}" y="${yy + 4}" text-anchor="end">${formatNumber(value)}</text>
      `;
    })
    .join("");

  container.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Price and volume chart">
      ${grid}
      ${circles}
      <text class="axis-label" x="${pad.left}" y="${height - 14}">${formatCurrency(minPrice, true)}</text>
      <text class="axis-label" x="${width - pad.right}" y="${height - 14}" text-anchor="end">${formatCurrency(maxPrice, true)}</text>
      <text class="chart-label" x="${width / 2}" y="${height - 14}" text-anchor="middle">Price</text>
      <text class="chart-label" x="18" y="${height / 2}" transform="rotate(-90 18 ${height / 2})" text-anchor="middle">Units sold</text>
    </svg>
  `;
}
