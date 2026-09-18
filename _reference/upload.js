const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");

document.getElementById("choose-btn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

["dragover", "dragenter"].forEach((evt) =>
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

async function handleFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    dropzone.querySelector("p").textContent = "Processing " + file.name + "...";

    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();

    document.getElementById("results").style.display = "block";
    document.getElementById("r-products").textContent = data.total_products;
    document.getElementById("r-records").textContent = data.total_records;
    document.getElementById("r-dates").textContent = data.date_range.join(" → ");

    const riskDist = document.getElementById("r-risk-dist");
    riskDist.innerHTML = Object.entries(data.risk_distribution)
        .map(([risk, count]) => `<span class="badge badge-${risk}" style="margin-right:8px">${risk}: ${count}</span>`)
        .join("");

    const table = document.getElementById("r-top-table");
    table.innerHTML = data.top_risk_products
        .map(
            (r) => `<tr>
                <td>${r["Store ID"]}</td><td>${r["Product ID"]}</td><td>${r["Category"]}</td>
                <td><span class="badge badge-${r["Risk Level"]}">${r["Risk Level"]}</span></td>
                <td>${Math.round(r["Recommended Order"])}</td>
            </tr>`
        )
        .join("");
}
