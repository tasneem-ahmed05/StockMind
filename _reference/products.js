let currentRisk = "All";
let currentSearch = "";

function riskBadge(risk) {
    return `<span class="badge badge-${risk}">${risk}</span>`;
}

async function loadProducts() {
    const params = new URLSearchParams({ risk: currentRisk, search: currentSearch });
    const res = await fetch(`/api/products?${params}`);
    const rows = await res.json();

    const grid = document.getElementById("products-grid");
    if (!rows.length) {
        grid.innerHTML = `<p style="color:var(--text-muted)">No products match this filter.</p>`;
        return;
    }

    grid.innerHTML = rows
        .map(
            (r) => `
        <div class="product-card">
            <div class="product-image">
                ${r["image"] ? `<img src="${r["image"]}" alt="${r["display_name"]}">` : `<span class="product-icon">${r["icon"]}</span>`}
            </div>
            <div class="product-card-body">
                <span class="badge" style="background:#eef2ff;color:var(--primary)">${r["Category"]}</span>
                <h3>${r["display_name"]}</h3>
                <div class="product-card-row">
                    <span style="color:var(--text-muted);font-size:13px">Current stock</span>
                    <b>${Math.round(r["Inventory Level"])} units</b>
                </div>
                <div class="product-card-row">
                    <span style="color:var(--text-muted);font-size:13px">Risk level</span>
                    ${riskBadge(r["Risk Level"])}
                </div>
                <button class="btn btn-primary" style="width:100%;margin-top:10px" onclick="openProduct('${r["Store ID"]}','${r["Product ID"]}')">Analyze</button>
            </div>
        </div>`
        )
        .join("");
}

function openProduct(storeId, productId) {
    window.location.href = `/product?store=${storeId}&product=${productId}`;
}

document.getElementById("filters").addEventListener("click", (e) => {
    if (!e.target.classList.contains("filter-chip")) return;
    document.querySelectorAll(".filter-chip").forEach((c) => c.classList.remove("active"));
    e.target.classList.add("active");
    currentRisk = e.target.dataset.risk;
    loadProducts();
});

document.getElementById("search").addEventListener("input", (e) => {
    currentSearch = e.target.value;
    loadProducts();
});

loadProducts();
