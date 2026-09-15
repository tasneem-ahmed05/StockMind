// =========================================================
// upload.js — logic for templates/upload.html ONLY.
//
// Flow:
//   1. User picks/drops a CSV -> POST /api/upload (validates, saves it
//      server-side under an upload_id, returns the Overview data).
//   2. Switch to the results view, render Overview immediately.
//   3. Each other tab (Historical/Inventory/Forecast/Recommendations) is
//      fetched lazily from GET /api/uploaded/<upload_id>/<tab> the first
//      time it's opened.
//
// Every number rendered here comes from the API - this file has no mock
// data and no client-side "fake" computation.
// =========================================================

const C = {
    primary: "#2f6fed",
    primarySoft: "rgba(47,111,237,.14)",
    purple: "#7c5cf0",
    green: "#15803d",
    red: "#d92d20",
    amber: "#c2410c",
    grey: "#cbd5e1",
    muted: "#6b7280",
};

const RISK_COLORS = { "High Risk": C.red, "Medium Risk": "#eab308", "Low Risk": C.green };
const RISK_FULL_COLORS = { Critical: "#b91c1c", High: C.red, Medium: "#eab308", Low: C.green, Unknown: C.grey };

let uploadId = null;
let overviewData = null;
const charts = {};
const rendered = {};

// ---------- small helpers ----------
const n0 = (v) => (v == null || Number.isNaN(v) ? "—" : Math.round(v).toLocaleString());
const n1 = (v) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(1));
const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));
const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
function kvTable(el, rows) {
    el.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}
function riskBadge(risk) {
    return `<span class="badge badge-${risk}">${risk}</span>`;
}

function baseOptions(extra = {}) {
    return Object.assign(
        {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8, titleFont: { size: 12 }, bodyFont: { size: 13 } },
            },
            scales: {
                y: { beginAtZero: true, grid: { color: "#eef1f6", drawBorder: false }, ticks: { color: C.muted, font: { size: 11 } } },
                x: { grid: { display: false }, ticks: { color: C.muted, font: { size: 11 }, maxRotation: 0, autoSkipPadding: 14 } },
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
function fillGradient(ctx, area, color) {
    if (!area) return color;
    const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, color);
    g.addColorStop(1, "rgba(255,255,255,0)");
    return g;
}

// =========================================================
// Step tracker
// =========================================================
function setStep(name, state) {
    const step = document.querySelector(`.step[data-step="${name}"]`);
    if (!step) return;
    step.classList.remove("active", "done", "error");
    if (state) step.classList.add(state);
    const order = ["upload", "validate", "process", "analyze"];
    const idx = order.indexOf(name);
    const line = step.previousElementSibling;
    if (line && line.classList.contains("step-line") && state === "done") line.classList.add("done");
}
function resetSteps() {
    document.querySelectorAll(".step").forEach((s) => s.classList.remove("active", "done", "error"));
    document.querySelectorAll(".step-line").forEach((l) => l.classList.remove("done"));
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// =========================================================
// Upload flow
// =========================================================
async function handleFile(file) {
    if (!file) return;
    resetSteps();
    document.getElementById("upload-error").hidden = true;
    setStep("upload", "active");

    if (!file.name.toLowerCase().endsWith(".csv")) {
        return showUploadError("Only .csv files are supported.");
    }
    if (file.size > 10 * 1024 * 1024) {
        return showUploadError("File is larger than the 10MB limit.");
    }

    await wait(250);
    setStep("upload", "done");
    setStep("validate", "active");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/upload", { method: "POST", body: formData });
        const data = await res.json();

        if (!res.ok) {
            setStep("validate", "error");
            return showUploadError(data.error || "Something went wrong reading that file.");
        }

        await wait(300);
        setStep("validate", "done");
        setStep("process", "active");
        await wait(350);
        setStep("process", "done");
        setStep("analyze", "active");
        await wait(300);
        setStep("analyze", "done");

        overviewData = data;
        uploadId = data.upload_id;
        history.replaceState(null, "", `/upload?id=${uploadId}`);

        await wait(200);
        showResults(data);
    } catch (err) {
        console.error(err);
        setStep("validate", "error");
        showUploadError("Couldn't reach the server. Is the Flask app running?");
    }
}

function showUploadError(msg) {
    const box = document.getElementById("upload-error");
    box.textContent = msg;
    box.hidden = false;
}

function showResults(data) {
    document.getElementById("upload-view").hidden = true;
    const results = document.getElementById("results-view");
    results.hidden = false;

    setText("results-filename", data.filename || "your file");
    document.getElementById("download-btn").href = `/api/uploaded/${uploadId}/download`;

    const warnBox = document.getElementById("warnings-box");
    if (data.warnings && data.warnings.length) {
        warnBox.hidden = false;
        warnBox.innerHTML = data.warnings.map((w) => `⚠️ ${w}`).join("<br>");
    } else {
        warnBox.hidden = true;
    }

    renderOverview(data);
    rendered.overview = true;
}

// =========================================================
// Overview tab
// =========================================================
function renderOverview(d) {
    setText("sum-products", n0(d.total_products));
    setText("sum-records", n0(d.total_records));
    setText("sum-daterange", `${d.date_range[0]} → ${d.date_range[1]}`);

    const risk = d.risk_distribution; // { "High Risk": n, "Medium Risk": n, "Low Risk": n }
    const total = Object.values(risk).reduce((a, b) => a + b, 0);
    const labels = Object.keys(risk).filter((k) => risk[k] > 0);
    setText("donut-total", n0(total));

    makeChart("chart-risk-donut", {
        type: "doughnut",
        data: {
            labels,
            datasets: [{ data: labels.map((l) => risk[l]), backgroundColor: labels.map((l) => RISK_COLORS[l]), borderWidth: 0, cutout: "68%" }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8 } },
        },
    });

    document.getElementById("risk-legend").innerHTML = Object.keys(risk)
        .map((label) => {
            const pct = total ? Math.round((risk[label] / total) * 100) : 0;
            return `<div class="legend-item"><span class="legend-dot" style="background:${RISK_COLORS[label]}"></span>${label}<span class="legend-val">${risk[label]} (${pct}%)</span></div>`;
        })
        .join("");

    const tbody = document.querySelector("#top-risk-table tbody");
    if (!d.top_risk_products.length) {
        tbody.innerHTML = `<tr><td colspan="3" class="empty-note">No products found.</td></tr>`;
    } else {
        tbody.innerHTML = d.top_risk_products
            .map(
                (p) => `
            <tr>
                <td><div class="product-name">${p["Product ID"]}</div><div class="product-sub">${p["Store ID"]} · ${p["Category"]}</div></td>
                <td>${riskBadge(p["Risk Level"])}</td>
                <td>${p["Stockout_Probability_Pct"]}%</td>
            </tr>`
            )
            .join("");
    }

    const insights = document.getElementById("insights-list");
    insights.innerHTML = d.key_insights.length
        ? d.key_insights.map((i) => `<li>${i}</li>`).join("")
        : `<li>Not enough data yet to generate insights.</li>`;
}

// =========================================================
// Historical Sales tab
// =========================================================
async function renderHistorical() {
    const d = await fetch(`/api/uploaded/${uploadId}/historical`).then((r) => r.json());

    makeChart("chart-daily", {
        type: "line",
        data: {
            labels: d.daily.dates.map(shortDate),
            datasets: [
                {
                    data: d.daily.values,
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

    makeChart("chart-monthly", {
        type: "bar",
        data: { labels: d.monthly.labels, datasets: [{ data: d.monthly.values, backgroundColor: C.primary, borderRadius: 7, maxBarThickness: 46 }] },
        options: baseOptions(),
    });

    makeChart("chart-by-category", {
        type: "bar",
        data: { labels: d.by_category.labels, datasets: [{ data: d.by_category.values, backgroundColor: C.purple, borderRadius: 7, maxBarThickness: 46 }] },
        options: baseOptions({ indexAxis: "y" }),
    });

    kvTable(document.getElementById("historical-table"), [
        ["Records analyzed", n0(d.summary.records)],
        ["Products", n0(d.summary.num_products)],
        ["Stores", n0(d.summary.num_stores)],
        ["Categories", n0(d.summary.num_categories)],
        ["Total units sold (all time)", n0(d.summary.total_units_sold)],
        ["Average units sold / day", n1(d.summary.avg_daily_units)],
    ]);
}

// =========================================================
// Inventory tab
// =========================================================
async function renderInventory() {
    const d = await fetch(`/api/uploaded/${uploadId}/inventory`).then((r) => r.json());
    const h = d.health;
    const totalHealth = h.needs_restock + h.healthy;

    setText("health-total", n0(totalHealth));
    makeChart("chart-health", {
        type: "doughnut",
        data: {
            labels: ["Needs Restock", "Healthy"],
            datasets: [{ data: [h.needs_restock, h.healthy], backgroundColor: [C.red, C.green], borderWidth: 0, cutout: "68%" }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8 } } },
    });
    document.getElementById("health-legend").innerHTML = [
        ["Needs Restock", h.needs_restock, C.red],
        ["Healthy", h.healthy, C.green],
    ]
        .map(([label, val, color]) => `<div class="legend-item"><span class="legend-dot" style="background:${color}"></span>${label}<span class="legend-val">${val}</span></div>`)
        .join("");

    makeChart("chart-restock-category", {
        type: "bar",
        data: { labels: d.restock_by_category.labels, datasets: [{ data: d.restock_by_category.values, backgroundColor: C.purple, borderRadius: 7, maxBarThickness: 46 }] },
        options: baseOptions(),
    });

    const riskLabels = Object.keys(d.risk_breakdown);
    makeChart("chart-risk-full", {
        type: "bar",
        data: {
            labels: riskLabels,
            datasets: [{ data: riskLabels.map((k) => d.risk_breakdown[k]), backgroundColor: riskLabels.map((k) => RISK_FULL_COLORS[k] || C.grey), borderRadius: 7, maxBarThickness: 50 }],
        },
        options: baseOptions({ indexAxis: "y" }),
    });

    kvTable(document.getElementById("inventory-table"), [
        ["Total current stock", `${n0(d.summary.total_current_stock)} units`],
        ["Total reorder point", `${n0(d.summary.total_reorder_point)} units`],
        ["Total recommended order", `${n0(d.summary.total_recommended_order)} units`],
        ["Average days of inventory", n1(d.summary.avg_days_of_inventory)],
        ["Products needing restock", n0(d.summary.products_needing_restock)],
        ["Healthy products", n0(d.summary.products_healthy)],
    ]);
}

// =========================================================
// Forecast tab
// =========================================================
async function renderForecast() {
    const res = await fetch(`/api/uploaded/${uploadId}/forecast`);
    const d = await res.json();
    if (!res.ok) {
        document.getElementById("panel-forecast").innerHTML = `<div class="card empty-note">${d.error}</div>`;
        return;
    }

    const histLen = d.history.values.length;
    const labels = [...d.history.dates.map(shortDate), ...d.forecast.dates.map(shortDate)];

    makeChart("chart-forecast", {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Actual",
                    data: [...d.history.values, ...Array(d.forecast.values.length).fill(null)],
                    borderColor: C.primary,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.25,
                    fill: true,
                    backgroundColor: (ctx) => fillGradient(ctx.chart.ctx, ctx.chart.chartArea, C.primarySoft),
                },
                {
                    label: "Forecast",
                    data: [...Array(histLen - 1).fill(null), d.history.values[histLen - 1], ...d.forecast.values],
                    borderColor: C.purple,
                    borderWidth: 2.5,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    tension: 0.25,
                    fill: false,
                },
            ],
        },
        options: baseOptions({
            plugins: { legend: { display: true, position: "top", align: "end", labels: { boxWidth: 12, font: { size: 12 }, color: C.muted } }, tooltip: { backgroundColor: "#1a1d29", padding: 11, cornerRadius: 8 } },
        }),
    });

    const rb = d.risk_breakdown;
    const riskLabels = Object.keys(rb);
    makeChart("chart-forecast-risk", {
        type: "bar",
        data: {
            labels: riskLabels.map((l) => l.split(" / ")[0]),
            datasets: [{ data: riskLabels.map((l) => rb[l]), backgroundColor: riskLabels.map((l) => (l.startsWith("High") ? C.red : l.startsWith("Low") ? C.amber : C.green)), borderRadius: 7, maxBarThickness: 52 }],
        },
        options: baseOptions({ indexAxis: "y" }),
    });

    kvTable(document.getElementById("forecast-table"), [
        ["Forecast horizon", "30 days"],
        ["Total forecast demand", `${n0(d.summary.next_30)} units`],
        ["Average per day", `${n1(d.summary.avg_per_day)} units`],
        ["Peak forecast day", `${n1(d.summary.peak_day)} units`],
        ["Lowest forecast day", `${n1(d.summary.low_day)} units`],
        ["High-risk days", `${d.summary.high_risk_days} of 30`],
        ["vs last 30 days actual", d.summary.change_pct != null ? `${d.summary.change_pct >= 0 ? "+" : ""}${d.summary.change_pct}%` : "—"],
    ]);
}

// =========================================================
// Recommendations tab
// =========================================================
async function renderRecommendations() {
    const d = await fetch(`/api/uploaded/${uploadId}/recommendations`).then((r) => r.json());
    const needsAction = d.needs_restock_count > 0;

    const badge = document.getElementById("verdict-badge");
    badge.textContent = needsAction ? "ACTION NEEDED" : "NO ACTION NEEDED";
    badge.className = `verdict-badge ${needsAction ? "verdict-reorder" : "verdict-ok"}`;
    setText("verdict-title", needsAction ? `${d.needs_restock_count} of ${d.total_products} products need restocking` : "All products are within safe stock levels");
    setText(
        "verdict-text",
        needsAction
            ? `Together they need ${n0(d.total_units_to_reorder)} units reordered${d.estimated_order_value != null ? `, an estimated ${money(d.estimated_order_value)}` : ""}.${d.worst_category ? ` "${d.worst_category}" has the most products needing restock.` : ""}`
            : `No product in this file is currently below its reorder point (average demand × ${d.lead_time_days}-day lead time + a 20% safety buffer).`
    );

    setText("reco-count", n0(d.needs_restock_count));
    setText("reco-units", n0(d.total_units_to_reorder));
    setText("reco-value", d.estimated_order_value != null ? money(d.estimated_order_value) : "—");
    setText("reco-value-note", d.estimated_order_value != null ? "at each product's average price in the file" : "no Price column in this file");

    const tbody = document.querySelector("#reco-table tbody");
    if (!d.top_products.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-note">Nothing needs restocking.</td></tr>`;
    } else {
        tbody.innerHTML = d.top_products
            .map(
                (p) => `
            <tr>
                <td><div class="product-name">${p["Product ID"]}</div><div class="product-sub">${p["Store ID"]}</div></td>
                <td>${p["Category"]}</td>
                <td>${riskBadge(p["Risk Level"])}</td>
                <td>${n0(p["Inventory Level"])}</td>
                <td>${n0(p["Recommended Order"])}</td>
            </tr>`
            )
            .join("");
    }

    document.getElementById("method-list").innerHTML = [
        `Every product uses the identical formulas as the Product Analysis page: <code>Reorder Point = (avg daily demand × ${d.lead_time_days}d lead time) + 20% safety stock</code>.`,
        `<code>Recommended Order = Reorder Point − current stock</code>, floored at zero.`,
        `Risk Level and Stockout Probability use the same days-of-inventory thresholds and normal-approximation formula as the single-product page — just computed for every row in your file instead of one product at a time.`,
    ]
        .map((t) => `<li>${t}</li>`)
        .join("");
}

// =========================================================
// Tabs
// =========================================================
function showTab(name) {
    document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
    if (rendered[name]) return;
    rendered[name] = true;
    if (name === "historical") renderHistorical();
    if (name === "inventory") renderInventory();
    if (name === "forecast") renderForecast();
    if (name === "reco") renderRecommendations();
}

document.getElementById("tabs")?.addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (tab) showTab(tab.dataset.tab);
});

// =========================================================
// Dropzone wiring
// =========================================================
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");

document.getElementById("choose-file-btn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => handleFile(e.target.files[0]));

["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    })
);
["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
    })
);
dropzone.addEventListener("drop", (e) => handleFile(e.dataTransfer.files[0]));

document.getElementById("new-upload-btn").addEventListener("click", () => {
    uploadId = null;
    overviewData = null;
    Object.keys(rendered).forEach((k) => delete rendered[k]);
    Object.values(charts).forEach((c) => c.destroy());
    fileInput.value = "";
    resetSteps();
    document.getElementById("results-view").hidden = true;
    document.getElementById("upload-view").hidden = false;
    history.replaceState(null, "", "/upload");
});

// =========================================================
// Restore from ?id=... on page load (e.g. after a refresh)
// =========================================================
(async function init() {
    const params = new URLSearchParams(window.location.search);
    const existingId = params.get("id");
    if (!existingId) return;

    uploadId = existingId;
    try {
        const res = await fetch(`/api/uploaded/${uploadId}/overview`);
        if (!res.ok) throw new Error("upload not found");
        const data = await res.json();
        showResults(data);
    } catch {
        // upload_id no longer exists server-side (e.g. app restarted) - fall
        // back to the empty dropzone instead of a broken results view.
        uploadId = null;
        history.replaceState(null, "", "/upload");
    }
})();
