const params = new URLSearchParams(window.location.search);
const storeId = params.get("store");
const productId = params.get("product");

async function loadProduct() {
    const res = await fetch(`/api/product/${storeId}/${productId}`);
    const data = await res.json();
    const info = data.info;

    const displayName = data.display_name || productId;
    document.getElementById("crumb-product").textContent = displayName;
    document.getElementById("product-title").textContent = displayName;
    document.getElementById("category-badge").textContent = info["Category"];
    document.getElementById("product-image").innerHTML = data.image
        ? `<img src="${data.image}" alt="${displayName}" style="width:100%;height:100%;object-fit:cover;border-radius:12px">`
        : `<span class="product-icon" style="font-size:32px">📦</span>`;
    document.getElementById("risk-badge").outerHTML =
        `<span class="badge badge-${info["Risk Level"]}" id="risk-badge">${info["Risk Level"]}</span>`;

    document.getElementById("m-stock").textContent = `${Math.round(info["Inventory Level"])} units`;
    document.getElementById("m-demand").textContent = info["Average_Daily_Demand"].toFixed(1);
    document.getElementById("m-reorder").textContent = Math.round(info["Reorder Point"]);
    document.getElementById("m-order").textContent = `${Math.round(info["Recommended Order"])} units`;

    new Chart(document.getElementById("history-chart"), {
        type: "line",
        data: {
            labels: data.history.dates,
            datasets: [{ label: "Units Sold", data: data.history.values, borderColor: "#1a1d29", tension: 0.2 }],
        },
        options: { plugins: { legend: { display: false } } },
    });

    new Chart(document.getElementById("forecast-chart"), {
        type: "line",
        data: {
            labels: data.forecast.dates,
            datasets: [{ label: "Forecast", data: data.forecast.values, borderColor: "#2f6fed", borderDash: [6, 4] }],
        },
        options: { plugins: { legend: { display: false } } },
    });

    const why = document.getElementById("why-list");
    const bullets = [];
    if (info["Recommendation"] === "REORDER") {
        bullets.push(
            `Current stock (${Math.round(info["Inventory Level"])} units) is at or below the reorder point (${Math.round(info["Reorder Point"])} units).`
        );
    } else {
        bullets.push(
            `Current stock (${Math.round(info["Inventory Level"])} units) is comfortably above the reorder point.`
        );
    }
    bullets.push(`Average forecasted demand over the next 30 days is about ${Math.round(data.forecast.values.reduce((a,b)=>a+b,0)/data.forecast.values.length)} units/day.`);
    if (data.high_risk_days > 0) {
        bullets.push(`${data.high_risk_days} of the next 30 days are flagged as high stockout-risk days.`);
    }
    why.innerHTML = bullets.map((b) => `<li>${b}</li>`).join("");

    const rec = document.getElementById("recommendation-text");
    rec.innerHTML =
        info["Recommendation"] === "REORDER"
            ? `<b>REORDER</b> — order about <b>${Math.round(info["Recommended Order"])} units</b> soon.`
            : `<b>NO REORDER</b> needed right now — stock is healthy.`;

    document.getElementById("ask-chatbot-btn").href = `/chatbot?store=${storeId}&product=${productId}`;
}

loadProduct();
