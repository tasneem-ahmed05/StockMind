// =========================================================
// chatbot.js — logic for templates/chatbot.html ONLY.
// Sends each question to POST /api/chat with:
//     { question, product_id, store_id }
// product_id/store_id are read from the URL query string, e.g.
//     /chatbot?store=S001&product=P0006
// so a user arriving from a product page gets an answer about
// that specific product. Expects back: { answer }
// =========================================================

(function () {
    const params = new URLSearchParams(window.location.search);
    const productId = params.get("product");
    const storeId = params.get("store");

    const messagesEl = document.getElementById("chat-messages");
    const inputEl = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send");

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    function addMessage(text, sender) {
        const row = document.createElement("div");
        row.className = "msg-row " + sender;

        if (sender === "bot") {
            const avatar = document.createElement("div");
            avatar.className = "msg-bot-avatar";
            avatar.textContent = "\u{1F916}"; // robot emoji
            row.appendChild(avatar);
        }

        const wrap = document.createElement("div");
        wrap.className = "msg-bubble-wrap";

        const bubble = document.createElement("div");
        bubble.className = "msg " + sender;
        bubble.textContent = text;

        const time = document.createElement("div");
        time.className = "msg-time";
        time.textContent = formatTime(new Date());

        wrap.appendChild(bubble);
        wrap.appendChild(time);
        row.appendChild(wrap);

        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return row;
    }

    function showTyping() {
        const row = document.createElement("div");
        row.className = "msg-row bot";
        row.id = "typing-row";

        const avatar = document.createElement("div");
        avatar.className = "msg-bot-avatar";
        avatar.textContent = "\u{1F916}";

        const indicator = document.createElement("div");
        indicator.className = "typing-indicator";
        indicator.innerHTML = "<span></span><span></span><span></span>";

        row.appendChild(avatar);
        row.appendChild(indicator);
        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function hideTyping() {
        const row = document.getElementById("typing-row");
        if (row) row.remove();
    }

    async function sendMessage() {
        const question = inputEl.value.trim();
        if (!question) return;

        addMessage(question, "user");
        inputEl.value = "";
        inputEl.disabled = true;
        sendBtn.disabled = true;
        showTyping();

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: question,
                    product_id: productId,
                    store_id: storeId,
                }),
            });
            const data = await res.json();
            hideTyping();
            addMessage(data.answer || "Sorry, I couldn't process that.", "bot");
        } catch (err) {
            hideTyping();
            addMessage("Connection error: " + err.message, "bot");
        } finally {
            inputEl.disabled = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keypress", function (e) {
        if (e.key === "Enter") sendMessage();
    });

    // Initial greeting
    addMessage(
        productId
            ? "Hi! Ask me anything about this product — its risk, forecast, or recommendation."
            : "Hi! Ask me about the project, forecasts, risk levels, or anything else.",
        "bot"
    );
})();