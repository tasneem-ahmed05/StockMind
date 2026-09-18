// =========================================================
// products.js — logic for templates/products.html ONLY.
//
// Data source: GET /api/products  (the 6 curated FEATURED_PRODUCTS,
// see utils.py). We fetch it once and filter/search on the client
// since the featured catalog is small - no need to round-trip to
// the server for every click.
// =========================================================

let fullCatalog = [];
let currentRisk = "All";
let currentSearch = "";

// Keeps a sensible severity order regardless of which Risk Levels
// happen to be present in the current catalog.
const RISK_ORDER = ["Critical", "High", "Medium", "Low", "Unknown"];

function riskBadge(risk) {
    return `<span class="badge badge-${risk}">${risk}</span>`;
}

function trendMarkup(trend) {
    if (trend === "up") return `<span class="trend trend-up">▲ Up</span>`;
    if (trend === "down") return `<span class="trend trend-down">▼ Down</span>`;
    return `<span class="trend trend-flat">→ Flat</span>`;
}

// Builds the filter pills from whatever Risk Levels actually exist in the
// loaded catalog. If a level (e.g. "Low") has zero products right now, no
// pill is shown for it - nothing to click that would just say "no results".
function renderFilters() {
    const counts = {};
    fullCatalog.forEach((r) => {
        const risk = r["Risk Level"];
        counts[risk] = (counts[risk] || 0) + 1;
    });

    const risksPresent = Object.keys(counts).sort(
        (a, b) => RISK_ORDER.indexOf(a) - RISK_ORDER.indexOf(b)
    );

    const pills = [
        `<button type="button" class="filter-pill ${currentRisk === "All" ? "active" : ""}" data-risk="All">All <span class="count">${fullCatalog.length}</span></button>`,
    ];
    risksPresent.forEach((risk) => {
        pills.push(
            `<button type="button" class="filter-pill ${currentRisk === risk ? "active" : ""}" data-risk="${risk}">${risk} <span class="count">${counts[risk]}</span></button>`
        );
    });

    document.getElementById("filters").innerHTML = pills.join("");
}

function renderRows(rows) {
    const body = document.getElementById("products-body");

    if (!rows.length) {
        body.innerHTML = `<div class="table-state">No products match this filter.</div>`;
        return;
    }

    body.innerHTML = rows
        .map(
            (r) => `
        <div class="table-row table-body-row">
            <div class="product-cell">
                <div class="product-thumb">
                    ${r.image ? `<img src="${r.image}" alt="${r.display_name}">` : `<span class="icon-fallback">${r.icon}</span>`}
                </div>
                <span class="product-name">${r.display_name}</span>
            </div>
            <div>${r["Category"] ?? "—"}</div>
            <div>${Number.isFinite(r["Inventory Level"]) ? Math.round(r["Inventory Level"]) : "—"}</div>
            <div>${riskBadge(r["Risk Level"])}</div>
            <div>${trendMarkup(r["Trend"])}</div>
            <div><button type="button" class="btn btn-primary analyze-btn" onclick="openProduct('${r["Store ID"]}','${r["Product ID"]}')">Analyze →</button></div>
        </div>`
        )
        .join("");
}

function applyFilters() {
    let rows = fullCatalog;

    if (currentRisk !== "All") {
        rows = rows.filter((r) => r["Risk Level"] === currentRisk);
    }
    if (currentSearch) {
        const q = currentSearch.toLowerCase();
        rows = rows.filter(
            (r) =>
                r["Product ID"].toLowerCase().includes(q) ||
                r.display_name.toLowerCase().includes(q)
        );
    }
    renderRows(rows);
}

function openProduct(storeId, productId) {
    window.location.href = `/product?store=${storeId}&product=${productId}`;
}

async function loadCatalog() {
    const body = document.getElementById("products-body");
    try {
        const res = await fetch("/api/products");
        if (!res.ok) throw new Error(`API error ${res.status}`);
        fullCatalog = await res.json();
        renderFilters();
        applyFilters();
    } catch (err) {
        body.innerHTML = `<div class="table-state">Couldn't load products right now. Is the Flask server running?</div>`;
        console.error(err);
    }
}

document.getElementById("filters").addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-pill");
    if (!btn) return;
    currentRisk = btn.dataset.risk;
    renderFilters();
    applyFilters();
});

document.getElementById("search").addEventListener("input", (e) => {
    currentSearch = e.target.value;
    applyFilters();
});

document.getElementById("random-btn").addEventListener("click", () => {
    if (!fullCatalog.length) return;
    const pick = fullCatalog[Math.floor(Math.random() * fullCatalog.length)];
    openProduct(pick["Store ID"], pick["Product ID"]);
});

loadCatalog();
