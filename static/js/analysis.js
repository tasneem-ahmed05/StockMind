const savedReport = sessionStorage.getItem("stockmindUploadReport");

if (!savedReport) {
    document.getElementById("analysis-empty").hidden = false;
} else {
    const report = JSON.parse(savedReport);
    document.getElementById("results-view").hidden = false;
    renderResults(report.data, report.fileName);
    renderTabData(report.data);
    setupTabs();
    document.getElementById("download-report").addEventListener("click", () => downloadReport(report.data));
    document.getElementById("view-report").addEventListener("click", () => downloadReport(report.data));
}

function setupTabs() {
    document.querySelectorAll(".result-tabs button").forEach((button) => {
        button.addEventListener("click", () => {
            const target = button.dataset.tab;
            document.querySelectorAll(".result-tabs button").forEach((tab) => tab.classList.toggle("active", tab === button));
            document.querySelectorAll(".report-panel").forEach((panel) => {
                panel.hidden = panel.dataset.panel !== target;
            });
        });
    });
}

function renderTabData(data) {
    const salesValues = data.historical_sales.values;
    const largestSale = Math.max(...salesValues, 1);
    document.getElementById("sales-chart").innerHTML = salesValues.map((value) =>
        `<div class="sales-bar" style="height:${Math.max(4, value / largestSale * 100)}%" data-value="${Math.round(value).toLocaleString()} units"></div>`
    ).join("");
    document.getElementById("sales-labels").innerHTML = data.historical_sales.labels.map((label) =>
        `<span title="${escapeHtml(label)}">${escapeHtml(label)}</span>`
    ).join("");

    document.getElementById("inventory-on-hand").textContent = data.inventory.total_on_hand.toLocaleString();
    document.getElementById("inventory-reorder-point").textContent = Math.round(data.inventory.total_reorder_point).toLocaleString();
    document.getElementById("inventory-table").innerHTML = data.inventory.items.map((item) => `
        <tr><td>${escapeHtml(item["Store ID"])}</td><td>${escapeHtml(item["Product ID"])}</td><td>${escapeHtml(item.Category)}</td><td>${Math.round(item["Inventory Level"]).toLocaleString()}</td><td>${Number(item["Days of Inventory"]).toFixed(1)}</td><td>${riskBadge(item["Risk Level"])}</td></tr>
    `).join("");

    document.getElementById("forecast-daily").textContent = `${Math.round(data.forecast.daily_demand).toLocaleString()} units`;
    document.getElementById("forecast-next-30").textContent = `${Math.round(data.forecast.next_30_demand).toLocaleString()} units`;
    const change = data.forecast.change_pct;
    document.getElementById("forecast-change").textContent = `${change >= 0 ? "+" : ""}${change}%`;

    document.getElementById("recommendation-total").textContent = Math.round(data.recommendations.total_order_quantity).toLocaleString();
    document.getElementById("recommendation-table").innerHTML = data.recommendations.items.map((item) => `
        <tr><td>${escapeHtml(item["Store ID"])}</td><td>${escapeHtml(item["Product ID"])}</td><td>${escapeHtml(item.Category)}</td><td>${riskBadge(item["Risk Level"])}</td><td>${Math.round(item["Inventory Level"]).toLocaleString()}</td><td>${Math.round(item["Recommended Order"]).toLocaleString()}</td></tr>
    `).join("");
}

function riskBadge(risk) {
    return `<span class="table-risk ${escapeHtml(risk)}">${escapeHtml(risk)}</span>`;
}

function formatDate(date) {
    return new Intl.DateTimeFormat("en", { month: "short", year: "numeric" }).format(new Date(`${date}T00:00:00`));
}

function renderResults(data, fileName) {
    document.getElementById("dataset-name").textContent = fileName;
    document.getElementById("r-products").textContent = data.total_products.toLocaleString();
    document.getElementById("r-records").textContent = data.total_records.toLocaleString();
    document.getElementById("r-dates").textContent = `${formatDate(data.date_range[0])} – ${formatDate(data.date_range[1])}`;
    document.getElementById("risk-total").textContent = data.total_products.toLocaleString();
    const colours = { Critical: "#f53742", High: "#f53742", Medium: "#ffc400", Low: "#52d146", Unknown: "#9aa7b7" };
    const levels = ["Critical", "High", "Medium", "Low", "Unknown"].filter((level) => data.risk_distribution[level]);
    const total = Object.values(data.risk_distribution).reduce((sum, count) => sum + count, 0) || 1;
    let degrees = 0;
    const gradient = levels.map((level) => {
        const next = degrees + (data.risk_distribution[level] / total) * 360;
        const segment = `${colours[level]} ${degrees}deg ${next}deg`;
        degrees = next;
        return segment;
    }).join(", ");
    document.getElementById("risk-donut").style.setProperty("--segment", `conic-gradient(${gradient})`);
    document.getElementById("r-risk-dist").innerHTML = levels.map((level) => {
        const count = data.risk_distribution[level];
        return `<div class="legend-row"><i class="legend-dot" style="background:${colours[level]}"></i><span>${level} Risk</span><b>${count} (${Math.round(count / total * 100)}%)</b></div>`;
    }).join("");
    document.getElementById("r-top-table").innerHTML = data.top_risk_products.map((product) => `
        <div class="risk-row"><span class="product-risk-name" title="${escapeHtml(product["Product ID"])}">${escapeHtml(product["Product ID"])}</span><span><i class="risk-badge ${product["Risk Level"]}">${product["Risk Level"]}</i></span><strong>${Math.round(product["Stockout Probability"] || 0)}%</strong></div>
    `).join("");
    const insight = data.insights;
    const riskLabel = insight.high_risk_count === 1 ? "product is" : "products are";
    document.getElementById("r-insights").innerHTML = [
        `${insight.high_risk_count} out of ${data.total_products} ${riskLabel} currently at critical or high stockout risk.`,
        insight.highest_risk_category ? `${insight.highest_risk_category} has the greatest concentration of at-risk inventory.` : "Risk distribution is ready for review.",
        `${insight.reorder_count} products are currently at or below their reorder point.`,
        "Review the highest-risk products first to prioritize replenishment."
    ].map((text) => `<li>${text}</li>`).join("");
}

function escapeHtml(value) {
    const element = document.createElement("span");
    element.textContent = value ?? "—";
    return element.innerHTML;
}

function downloadReport(data) {
    const rows = [["Product ID", "Store ID", "Category", "Risk Level", "Stockout Probability", "Recommended Order"]];
    data.top_risk_products.forEach((product) => rows.push([product["Product ID"], product["Store ID"], product.Category, product["Risk Level"], product["Stockout Probability"], Math.round(product["Recommended Order"] || 0)]));
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = "stockmind-risk-report.csv";
    link.click();
    URL.revokeObjectURL(link.href);
}
