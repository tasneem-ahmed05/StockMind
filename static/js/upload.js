const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const message = document.getElementById("upload-message");
let currentReport = null;

document.getElementById("choose-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    fileInput.click();
});
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") fileInput.click();
});
fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
}));
["dragleave", "drop"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
}));
dropzone.addEventListener("drop", (event) => handleFile(event.dataTransfer.files[0]));

function setStep(stepNumber) {
    document.querySelectorAll(".step").forEach((step, index) => step.classList.toggle("active", index < stepNumber));
}

async function handleFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
        message.textContent = "Please choose a file in CSV format.";
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        message.textContent = "The file must be smaller than 10MB.";
        return;
    }
    message.style.color = "var(--primary)";
    message.textContent = `Uploading ${file.name}…`;
    setStep(3);
    const formData = new FormData();
    formData.append("file", file);
    try {
        const response = await fetch("/api/upload", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to analyze this file.");
        setStep(4);
        currentReport = data;
        sessionStorage.setItem("stockmindUploadReport", JSON.stringify({ data, fileName: file.name }));
        window.location.assign("/analysis");
    } catch (error) {
        setStep(1);
        message.style.color = "var(--red-text)";
        message.textContent = error.message;
    }
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

function downloadReport() {
    if (!currentReport) return;
    const rows = [["Product ID", "Store ID", "Category", "Risk Level", "Stockout Probability", "Recommended Order"]];
    currentReport.top_risk_products.forEach((product) => rows.push([product["Product ID"], product["Store ID"], product.Category, product["Risk Level"], product["Stockout Probability"], Math.round(product["Recommended Order"] || 0)]));
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = "stockmind-risk-report.csv";
    link.click();
    URL.revokeObjectURL(link.href);
}

document.getElementById("download-report").addEventListener("click", downloadReport);
document.getElementById("view-report").addEventListener("click", downloadReport);
document.getElementById("upload-another").addEventListener("click", () => {
    fileInput.value = "";
    message.textContent = "";
    setStep(1);
    document.getElementById("results-view").hidden = true;
    document.getElementById("upload-view").hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
});
