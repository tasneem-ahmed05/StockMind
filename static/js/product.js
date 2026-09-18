// =========================================================
// product.js — logic for templates/product.html ONLY.
//
// Reads ?store=S001&product=P0006 from the URL and renders the full
// analysis from GET /api/product/<store>/<product>.
//
// Every number and every chart below comes straight from that payload,
// which is computed from the real sales history + the SARIMA forecast
// in utils.py. Nothing here is mocked.
// =========================================================

const C = {
    primary: "#2f6fed",
    primarySoft: "rgba(47,111,237,.14)",
    purple: "#7c5cf0",
    purpleSoft: "rgba(124,92,240,.16)",
    green: "#15803d",
    greenSoft: "rgba(21,128,61,.14)",
    red: "#d92d20",
    redSoft: "rgba(217,45,32,.14)",
    amber: "#c2410c",
    grey: "#cbd5e1",
    muted: "#6b7280",
};

const charts = {};
let DATA = null;

const params = new URLSearchParams(window.location.search);
const STORE_ID = params.get("store");
const PRODUCT_ID = params.get("product");

// ---------- small helpers ----------
const n0 = (v) => (v == null || Number.isNaN(v) ? "—" : Math.round(v).toLocaleString());
const n1 = (v) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(1));
const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));
const shortDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function bulletList(el, items) {
    el.innerHTML = items.map((t) => `<li>${t}</li>`).join("");
}

function kvTable(el, rows) {
    el.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

// Shared Chart.js look so every chart on the page matches the design system.
function baseOptions(extra = {}) {
    return Object.assign(
        {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#1a1d29",
                    padding: 11,
                    cornerRadius: 8,
                    titleFont: { size: 12 },
                    bodyFont: { size: 13 },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: "#eef1f6", drawBorder: false },
                    ticks: { color: C.muted, font: { size: 11 } },
                },
                x: {
                    grid: { display: false },
                    ticks: { color: C.muted, font: { size: 11 }, maxRotation: 0, autoSkipPadding: 14 },
                },
            },
        },
        extra
    );
}

function makeChart(id, config) {
    const el = document.getElementById(id);
    if (!el) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(el, config);
}

// Soft vertical gradient used under the line charts.
function fillGradient(ctx, area, color) {
    if (!area) return color;
    const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, color);
    g.addColorStop(1, "rgba(255,255,255,0)");
    return g;
}

// ---------- rendering ----------
function renderHero(d) {
    const info = d.info;
    setText("crumb-name", d.display_name);
    setText("hero-name", d.display_name);
    setText("hero-category", d.category || "—");
    setText("hero-stock", n0(info["Inventory Level"]));

    const img = document.getElementById("hero-image");
    if (d.image) {
        img.src = d.image;
        img.alt = d.display_name;
    } else {
        img.replaceWith(Object.assign(document.createElement("span"), { textContent: d.icon, style: "font-size:52px" }));
    }

    setText("hero-price", d.price.avg != null ? money(d.price.avg) : "—");
    // Price is re-rolled per row in this dataset, so we show the range too
    // rather than pretending there's one fixed price.
    setText("hero-price-range", d.price.min != null ? `range ${money(d.price.min)} – ${money(d.price.max)}` : "");
    setText("hero-demand", n0(info["Average_Daily_Demand"]));
    setText("hero-days", n1(info["Days of Inventory"]));
    setText("hero-leadtime", `lead time ${d.lead_time_days}d`);

    const risk = info["Risk Level"] || "Unknown";
    setText("hero-risk", risk);
    document.getElementById("hero-risk-box").className = `hero-risk risk-${risk}`;
}

function renderOverview(d) {
    const info = d.info;

    // --- Sales trend (monthly, line + area) ---
    makeChart("chart-monthly", {
        type: "line",
        data: {
            labels: d.monthly_sales.labels,
            datasets: [
                {
                    data: d.monthly_sales.values,
                    borderColor: C.primary,
                    borderWidth: 3,
                    pointBackgroundColor: "#fff",
                    pointBorderColor: C.primary,
                    pointBorderWidth: 2.5,
                    pointRadius: 4,
                    tension: 0.35,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.primarySoft),
                },
            ],
        },
        options: baseOptions(),
    });

    // --- Stock vs reorder point donut ---
    const cov = d.coverage;
    const hasShortfall = cov.shortfall > 0;
    const donutData = hasShortfall
        ? [cov.on_hand, cov.shortfall]
        : [cov.reorder_point, cov.surplus];
    const donutColors = hasShortfall ? [C.primary, C.grey] : [C.primary, C.green];
    const donutLabels = hasShortfall
        ? ["Stock on hand", "Shortfall to reorder point"]
        : ["Covers reorder point", "Surplus above reorder point"];

    setText("donut-stock", n0(info["Inventory Level"]));
    makeChart("chart-coverage", {
        type: "doughnut",
        data: { labels: donutLabels, datasets: [{ data: donutData, backgroundColor: donutColors, borderWidth: 0, cutout: "70%" }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#1a1d29",
                    padding: 11,
                    cornerRadius: 8,
                    callbacks: { label: (c) => ` ${c.label}: ${n0(c.parsed)} units` },
                },
            },
        },
    });

    document.getElementById("coverage-legend").innerHTML = donutLabels
        .map(
            (label, i) =>
                `<div class="legend-item"><span class="legend-dot" style="background:${donutColors[i]}"></span>${label}<span class="legend-val">${n0(donutData[i])}</span></div>`
        )
        .join("");

    // --- Predicted demand, weekly bars ---
    makeChart("chart-weekly", {
        type: "bar",
        data: {
            labels: d.forecast_weekly.labels,
            datasets: [
                {
                    data: d.forecast_weekly.values,
                    backgroundColor: C.purple,
                    borderRadius: 7,
                    maxBarThickness: 44,
                },
            ],
        },
        options: baseOptions(),
    });

    // --- KPI cards ---
    const ds = d.demand_summary;
    setText("kpi-demand", `${n0(ds.next_30)} units`);
    if (ds.change_pct != null) {
        const sign = ds.change_pct >= 0 ? "+" : "";
        setText("kpi-demand-change", `${sign}${ds.change_pct}% vs last 30 days (${n0(ds.prev_30)} units)`);
    } else {
        setText("kpi-demand-change", "no comparable history");
    }

    setText("kpi-risk", info["Risk Level"]);
    document.getElementById("kpi-risk").style.color =
        ["Critical", "High"].includes(info["Risk Level"]) ? C.red : info["Risk Level"] === "Medium" ? C.amber : C.green;
    setText("kpi-risk-note", `${n1(info["Days of Inventory"])} days of stock left`);

    setText("kpi-restock", `${n0(info["Recommended Order"])} units`);
    setText("kpi-restock-note", info["Recommendation"] === "REORDER" ? "reorder triggered" : "no reorder needed");

    setText("kpi-timing", d.timing.label);
    setText("kpi-timing-note", d.timing.detail);

    bulletList(document.getElementById("why-list"), d.reasons);
    bulletList(document.getElementById("why-list-2"), d.reasons);
}

function renderHistorical(d) {
    makeChart("chart-history", {
        type: "line",
        data: {
            labels: d.history.dates.map(shortDate),
            datasets: [
                {
                    label: "Units sold",
                    data: d.history.values,
                    borderColor: C.primary,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.25,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.primarySoft),
                },
            ],
        },
        options: baseOptions(),
    });

    makeChart("chart-monthly-bar", {
        type: "bar",
        data: {
            labels: d.monthly_sales.labels,
            datasets: [{ data: d.monthly_sales.values, backgroundColor: C.primary, borderRadius: 7, maxBarThickness: 46 }],
        },
        options: baseOptions(),
    });

    const vals = d.history.values;
    const sum = vals.reduce((a, b) => a + b, 0);
    const peak = Math.max(...vals);
    const low = Math.min(...vals);
    kvTable(document.getElementById("history-table"), [
        ["Days of history shown", vals.length],
        ["Total units sold (90d)", n0(sum)],
        ["Average per day (90d)", n1(sum / vals.length)],
        ["Best day", `${n0(peak)} units`],
        ["Slowest day", `${n0(low)} units`],
        ["All-time units sold", n0(d.info["Total_Demand"])],
    ]);
}

function renderInventory(d) {
    const p = d.projection;
    const reorderPoint = d.coverage.reorder_point;

    makeChart("chart-projection", {
        type: "line",
        data: {
            labels: p.days.map((x) => `Day ${x}`),
            datasets: [
                {
                    label: "Projected stock",
                    data: p.values,
                    borderColor: C.primary,
                    borderWidth: 3,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.25,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.primarySoft),
                },
                {
                    label: "Reorder point",
                    data: p.days.map(() => reorderPoint),
                    borderColor: C.red,
                    borderWidth: 2,
                    borderDash: [7, 5],
                    pointRadius: 0,
                    fill: false,
                },
            ],
        },
        options: baseOptions({
            plugins: {
                legend: { display: true, position: "top", align: "end", labels: { boxWidth: 12, font: { size: 12 }, color: C.muted } },
                tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8 },
            },
        }),
    });

    const notes = [];
    if (p.stockout_day) notes.push(`Stock is projected to hit zero around <b>day ${p.stockout_day}</b> if no order is placed.`);
    else notes.push("Stock is not projected to run out within the next 30 days.");
    if (p.reorder_day === 1) notes.push("It is <b>already below</b> the reorder point today.");
    else if (p.reorder_day) notes.push(`It crosses the reorder point on <b>day ${p.reorder_day}</b>.`);
    document.getElementById("projection-note").innerHTML = notes.join(" ");

    // Reorder point = lead time demand + safety stock
    makeChart("chart-reorder", {
        type: "bar",
        data: {
            labels: ["Current stock", "Lead time demand", "Safety stock", "Reorder point"],
            datasets: [
                {
                    data: [
                        d.info["Inventory Level"],
                        d.coverage.lead_time_demand,
                        d.coverage.safety_stock,
                        reorderPoint,
                    ],
                    backgroundColor: [C.primary, C.purple, C.amber, C.red],
                    borderRadius: 7,
                    maxBarThickness: 52,
                },
            ],
        },
        options: baseOptions(),
    });

    document.getElementById("reorder-note").innerHTML =
        `Reorder point = lead time demand (${d.lead_time_days} days of average demand) + a 20% safety buffer. ` +
        `An order is triggered whenever current stock falls below it.`;

    kvTable(document.getElementById("inventory-table"), [
        ["Current stock", `${n0(d.info["Inventory Level"])} units`],
        ["Average daily demand", `${n1(d.info["Average_Daily_Demand"])} units`],
        ["Days of inventory", n1(d.info["Days of Inventory"])],
        ["Supplier lead time", `${d.lead_time_days} days`],
        ["Lead time demand", `${n0(d.coverage.lead_time_demand)} units`],
        ["Safety stock", `${n0(d.coverage.safety_stock)} units`],
        ["Reorder point", `${n0(reorderPoint)} units`],
        ["Recommended order", `${n0(d.info["Recommended Order"])} units`],
    ]);
}

function renderForecast(d) {
    // Actual history then forecast, joined on one continuous axis.
    const histLen = d.history.values.length;
    const labels = [...d.history.dates.map(shortDate), ...d.forecast.dates.map(shortDate)];

    makeChart("chart-forecast", {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Actual sales",
                    data: [...d.history.values, ...Array(d.forecast.values.length).fill(null)],
                    borderColor: C.primary,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.25,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.primarySoft),
                },
                {
                    label: "SARIMA forecast",
                    // repeat the last actual point so the two lines connect
                    data: [
                        ...Array(histLen - 1).fill(null),
                        d.history.values[histLen - 1],
                        ...d.forecast.values,
                    ],
                    borderColor: C.purple,
                    borderWidth: 2.5,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.25,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.purpleSoft),
                },
            ],
        },
        options: baseOptions({
            plugins: {
                legend: { display: true, position: "top", align: "end", labels: { boxWidth: 12, font: { size: 12 }, color: C.muted } },
                tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8 },
            },
            spanGaps: false,
        }),
    });

    // Risk label distribution across the 30 forecast days
    const rb = d.risk_breakdown;
    const riskLabels = ["High Demand / Stockout Risk", "Normal Risk", "Low Demand / Overstock Risk"];
    const present = riskLabels.filter((l) => rb[l]);
    makeChart("chart-riskdays", {
        type: "bar",
        data: {
            labels: present.map((l) => l.split(" / ")[0]),
            datasets: [
                {
                    data: present.map((l) => rb[l]),
                    backgroundColor: present.map((l) =>
                        l.startsWith("High") ? C.red : l.startsWith("Low") ? C.amber : C.green
                    ),
                    borderRadius: 7,
                    maxBarThickness: 52,
                },
            ],
        },
        options: baseOptions({
            indexAxis: "y",
            scales: {
                x: { beginAtZero: true, grid: { color: "#eef1f6" }, ticks: { color: C.muted, font: { size: 11 }, precision: 0 } },
                y: { grid: { display: false }, ticks: { color: C.muted, font: { size: 11 } } },
            },
        }),
    });

    const f = d.forecast.values;
    const avg = f.reduce((a, b) => a + b, 0) / f.length;
    kvTable(document.getElementById("forecast-table"), [
        ["Forecast horizon", `${f.length} days`],
        ["Total forecast demand", `${n0(d.demand_summary.next_30)} units`],
        ["Average per day", `${n1(avg)} units`],
        ["Peak forecast day", `${n1(Math.max(...f))} units`],
        ["Lowest forecast day", `${n1(Math.min(...f))} units`],
        ["High-risk days", `${d.high_risk_days} of ${f.length}`],
        ["vs last 30 days actual", d.demand_summary.change_pct != null ? `${d.demand_summary.change_pct >= 0 ? "+" : ""}${d.demand_summary.change_pct}%` : "—"],
    ]);
}

function renderRecommendations(d) {
    const info = d.info;
    const reorder = info["Recommendation"] === "REORDER";
    const qty = info["Recommended Order"];

    const badge = document.getElementById("verdict-badge");
    badge.textContent = reorder ? "ACTION NEEDED" : "NO ACTION NEEDED";
    badge.className = `verdict-badge ${reorder ? "verdict-reorder" : "verdict-ok"}`;

    setText("verdict-title", reorder ? `Restock ${n0(qty)} units` : "Stock levels are healthy");
    setText(
        "verdict-text",
        reorder
            ? `Current stock of ${n0(info["Inventory Level"])} units is below the reorder point of ${n0(d.coverage.reorder_point)} units. Ordering ${n0(qty)} units brings inventory back up to the reorder point, covering the ${d.lead_time_days}-day supplier lead time plus a 20% safety buffer.`
            : `Current stock of ${n0(info["Inventory Level"])} units sits above the reorder point of ${n0(d.coverage.reorder_point)} units, so there is enough cover for the ${d.lead_time_days}-day lead time without ordering now.`
    );

    setText("reco-qty", reorder ? n0(qty) : "0");
    setText("reco-qty-note", reorder ? "units to bring stock back to the reorder point" : "no order required at this stock level");

    setText("reco-timing", d.timing.label);
    setText("reco-timing-note", d.timing.detail);

    const value = d.price.avg != null && qty ? qty * d.price.avg : null;
    setText("reco-value", reorder && value ? money(value) : "—");
    setText(
        "reco-value-note",
        value != null && reorder
            ? `estimated at the average unit price of ${money(d.price.avg)}`
            : "no order value to estimate"
    );

    bulletList(document.getElementById("method-list"), [
        `<b>Average daily demand</b> = mean of all recorded Units Sold for this store + product → <code>${n1(info["Average_Daily_Demand"])}</code> units/day.`,
        `<b>Days of inventory</b> = current stock ÷ average daily demand → <code>${n1(info["Days of Inventory"])}</code> days.`,
        `<b>Risk level</b> comes from days of inventory: under 3 days is Critical, under 7 is High, under 14 is Medium, otherwise Low → <code>${info["Risk Level"]}</code>.`,
        `<b>Reorder point</b> = (average daily demand × ${d.lead_time_days}-day lead time) + 20% safety stock → <code>${n0(d.coverage.reorder_point)}</code> units.`,
        `<b>Recommended order</b> = reorder point − current stock, floored at zero → <code>${n0(qty)}</code> units.`,
        `<b>Forecast</b> is a SARIMA model fitted on this product's daily demand, projected 30 days ahead.`,
    ]);
}

// Charts must be drawn while their panel is visible, otherwise Chart.js
// measures a zero-size canvas. We render each tab the first time it opens.
const rendered = {};
function showTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));

    if (!DATA || rendered[name]) return;
    rendered[name] = true;
    if (name === "historical") renderHistorical(DATA);
    if (name === "inventory") renderInventory(DATA);
    if (name === "forecast") renderForecast(DATA);
    if (name === "reco") renderRecommendations(DATA);
}

document.getElementById("tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (tab) showTab(tab.dataset.tab);
});

async function init() {
    const loading = document.getElementById("loading");
    const errorBox = document.getElementById("error");

    if (!STORE_ID || !PRODUCT_ID) {
        loading.hidden = true;
        errorBox.hidden = false;
        errorBox.innerHTML = `No product selected. <a href="/products" style="color:var(--primary)">Back to Products</a>`;
        return;
    }

    try {
        const res = await fetch(`/api/product/${STORE_ID}/${PRODUCT_ID}`);
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        DATA = await res.json();

        loading.hidden = true;
        document.getElementById("analysis").hidden = false;

        renderHero(DATA);
        renderHero(DATA);
        document.getElementById("ask-chatbot-btn").href = `/chatbot?store=${STORE_ID}&product=${PRODUCT_ID}`;
        renderOverview(DATA);
        renderOverview(DATA);
        rendered.overview = true;
    } catch (err) {
        console.error(err);
        loading.hidden = true;
        errorBox.hidden = false;
        errorBox.innerHTML = `Couldn't load the analysis for this product. <a href="/products" style="color:var(--primary)">Back to Products</a>`;
    }
}

init();
