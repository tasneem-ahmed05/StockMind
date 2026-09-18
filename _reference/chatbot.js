const params = new URLSearchParams(window.location.search);
const storeId = params.get("store");
const productId = params.get("product");

if (productId) {
    document.getElementById("chat-context-label").textContent = `Context-aware for: ${productId} (${storeId})`;
}

const messagesEl = document.getElementById("chat-messages");

function addMessage(text, who) {
    const div = document.createElement("div");
    div.className = `msg ${who}`;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage() {
    const input = document.getElementById("chat-input");
    const question = input.value.trim();
    if (!question) return;
    addMessage(question, "user");
    input.value = "";

    addMessage("Thinking...", "bot");
    const thinkingEl = messagesEl.lastChild;

    const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, product_id: productId, store_id: storeId }),
    });
    const data = await res.json();
    thinkingEl.textContent = data.answer;
}

document.getElementById("chat-send").addEventListener("click", sendMessage);
document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
});
