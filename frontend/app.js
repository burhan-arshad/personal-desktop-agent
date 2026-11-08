
// =============================================
// AETHRIX — CHARCOAL UI + REAL BACKEND
// =============================================

const API_BASE = "http://127.0.0.1:8000";

const STORAGE_KEY = "aethrix_conversation_id";
const PENDING_THREAD_KEY = "aethrix_pending_thread_id";

// Migrate old shared storage into this tab's session.
function migrateSessionValue(key) {
    const sessionValue = sessionStorage.getItem(key);

    if (sessionValue !== null) {
        return sessionValue;
    }

    const legacyValue = localStorage.getItem(key);

    if (legacyValue !== null) {
        sessionStorage.setItem(key, legacyValue);
        localStorage.removeItem(key);
    }

    return legacyValue;
}

let conversationId = migrateSessionValue(STORAGE_KEY);
let activeThreadId = migrateSessionValue(PENDING_THREAD_KEY);

let isSending = false;
let isApproving = false;


// =============================================
// DOM ELEMENTS
// =============================================

const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const voiceBtn = document.getElementById("voiceBtn");

const welcomeScreen = document.getElementById("welcomeScreen");
const messagesContainer = document.getElementById("messagesContainer");
const composerArea = document.querySelector(".composer-area");

const newChatBtn = document.getElementById("newChatBtn");

const systemStatusElements = document.querySelectorAll("#systemStatus");
const connectionText = document.getElementById("connectionText");
const connectionDot = document.getElementById("connectionDot");

const agentState = document.getElementById("agentState");

const activityList = document.getElementById("activityList");
const emptyActivity = document.getElementById("emptyActivity");

const approvalCount = document.getElementById("approvalCount");

const pageTitle = document.getElementById("pageTitle");

const chatView = document.getElementById("chatView");
const placeholderView = document.getElementById("placeholderView");

const placeholderTitle = document.getElementById("placeholderTitle");
const placeholderDescription = document.getElementById(
    "placeholderDescription"
);


// =============================================
// UI HELPERS
// =============================================

function setSystemStatus(text) {
    systemStatusElements.forEach((element) => {
        element.textContent = text;
    });
}


function setConnectionStatus(online) {

    if (connectionDot) {
        connectionDot.style.background = online
            ? "#c3e68a"
            : "#d77e78";
    }

    if (connectionText) {
        connectionText.textContent = online
            ? "Backend Online"
            : "Backend Offline";
    }
}


function refreshIcons() {

    if (window.lucide) {
        lucide.createIcons();
    }
}


function ensureComposerVisible() {
    if (composerArea) {
        composerArea.style.display = "block";
        composerArea.style.visibility = "visible";
        composerArea.style.opacity = "1";
    }
}

function hideWelcomeScreen() {
    if (welcomeScreen) {
        welcomeScreen.style.display = "none";
    }

    ensureComposerVisible();
}

function showWelcomeScreen() {
    if (welcomeScreen) {
        welcomeScreen.style.display = "block";
    }

    ensureComposerVisible();
}


function scrollToBottom(element) {

    if (!element) return;

    element.scrollIntoView({
        behavior: "smooth",
        block: "end"
    });
}


// =============================================
// API HELPER
// =============================================

async function apiRequest(endpoint, options = {}) {

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            ...(options.headers || {})
        }
    });

    let data = {};

    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (!response.ok) {

        const detail = data.detail;

        const errorMessage =
            typeof detail === "string"
                ? detail
                : detail
                    ? JSON.stringify(detail)
                    : `API request failed: ${response.status}`;

        throw new Error(errorMessage);
    }

    return data;
}


// =============================================
// BACKEND HEALTH
// =============================================

async function checkBackend() {

    try {

        const data = await apiRequest("/api/health");

        setSystemStatus("Connected");
        setConnectionStatus(true);

        if (!activeThreadId) {
            agentState.textContent = "Standby";
        }

        console.log("[AETHRIX] Backend online:", data);

    } catch (error) {

        setSystemStatus("Offline");
        setConnectionStatus(false);

        if (!activeThreadId) {
            agentState.textContent = "Backend unavailable";
        }

        console.error(
            "[AETHRIX] Health check failed:",
            error.message
        );
    }
}


// =============================================
// MESSAGE RENDERING
// =============================================

function addMessage(text, sender = "user") {

    hideWelcomeScreen();

    const row = document.createElement("div");

    row.className =
        `message ${sender === "user" ? "user-message" : "assistant-message"}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    avatar.textContent = sender === "user" ? "U" : "A";

    const body = document.createElement("div");
    body.className = "message-body";

    const content = document.createElement("div");
    content.className = "message-text";

    // textContent prevents HTML/script injection.
    content.textContent = String(text);

    const time = document.createElement("div");
    time.className = "message-time";
    time.textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    });

    body.appendChild(content);
    body.appendChild(time);

    row.appendChild(avatar);
    row.appendChild(body);

    messagesContainer.appendChild(row);

    refreshIcons();
    scrollToBottom(row);

    return row;
}

// =============================================
// RESTORE CONVERSATION HISTORY
// =============================================

async function loadConversationHistory() {

    if (!conversationId) {
        console.log("[AETHRIX] No previous conversation to restore.");
        return;
    }

    try {

        console.log(
            "[AETHRIX] Loading conversation history:",
            conversationId
        );

        const data = await apiRequest(
            `/api/conversation/${encodeURIComponent(conversationId)}/history`
        );

        const history = Array.isArray(data.messages)
            ? data.messages
            : [];

        messagesContainer.innerHTML = "";

        // No previous messages.
        if (history.length === 0) {

            showWelcomeScreen();

            console.log(
                "[AETHRIX] Conversation is empty."
            );

            return;
        }

        hideWelcomeScreen();

        // Restore messages in their original order.
        history.forEach((message) => {

            if (
                !message ||
                !["user", "assistant"].includes(message.role)
            ) {
                return;
            }

            addMessage(
                message.content,
                message.role
            );

        });

        console.log(
            `[AETHRIX] Restored ${history.length} messages.`
        );

    } catch (error) {

        console.error(
            "[AETHRIX] History restoration failed:",
            error.message
        );

        // Preserve the existing conversation ID.
        // The user can still continue using the backend.
    }
}

// =============================================
// LOADING INDICATOR
// =============================================

function showLoading() {

    const row = addMessage("Processing your instruction...", "assistant");

    row.classList.add("loading-message");

    return row;
}


// =============================================
// ACTIVITY PANEL
// =============================================

function addActivity(text) {

    if (!activityList) return;

    if (emptyActivity) {
        emptyActivity.style.display = "none";
    }

    const item = document.createElement("div");
    item.className = "activity-item";

    const indicator = document.createElement("span");
    indicator.className = "activity-indicator";

    const content = document.createElement("div");
    content.className = "activity-content";

    const title = document.createElement("strong");
    title.textContent = text;

    const time = document.createElement("span");

    time.textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    });

    content.appendChild(title);
    content.appendChild(time);

    item.appendChild(indicator);
    item.appendChild(content);

    activityList.prepend(item);
}


// =============================================
// AGENT STATUS
// =============================================

function updateAgentStatus(status) {

    const labels = {

        standby: "Standby",
        running: "Executing your command",
        approval_required: "Waiting for your approval",
        completed: "Task completed",
        denied: "Action denied",
        blocked: "Action blocked",
        error: "Task failed",
        verification_failed: "Verification failed",
        max_steps_reached: "Action limit reached",
        api_rate_limited: "AI provider rate limited"

    };

    agentState.textContent = labels[status] || status || "Unknown";

    if (approvalCount) {
        approvalCount.textContent =
            status === "approval_required" ? "1" : "0";
    }
}


// =============================================
// PENDING APPROVAL STORAGE
// =============================================

function savePendingThread(threadId) {
    activeThreadId = threadId;

    if (threadId) {
        sessionStorage.setItem(PENDING_THREAD_KEY, threadId);
    } else {
        sessionStorage.removeItem(PENDING_THREAD_KEY);
    }
}


// =============================================
// APPROVAL CARD
// =============================================

function showApprovalCard(agent) {

    if (!agent.thread_id) {

        addMessage(
            "Approval information is missing a thread ID.",
            "assistant"
        );

        return;
    }

    savePendingThread(agent.thread_id);

    updateAgentStatus("approval_required");

    // Avoid duplicate cards for the same thread.
    const existingCard = document.querySelector(
        `[data-thread-id="${agent.thread_id}"]`
    );

    if (existingCard) {
        return;
    }

    hideWelcomeScreen();

    const card = document.createElement("div");

    card.className = "approval-card";
    card.dataset.threadId = agent.thread_id;

    const heading = document.createElement("h3");
    heading.textContent = "Approval Required";

    const description = document.createElement("p");

    description.textContent =
        "AETHRIX has prepared an action. Review the details before allowing execution.";

    const details = document.createElement("pre");
    details.className = "approval-details";

    details.textContent = JSON.stringify(
        agent.approval || {},
        null,
        2
    );

    const actions = document.createElement("div");
    actions.className = "approval-actions";

    const approveBtn = document.createElement("button");
    approveBtn.className = "approve-btn";
    approveBtn.textContent = "Approve";

    const denyBtn = document.createElement("button");
    denyBtn.className = "deny-btn";
    denyBtn.textContent = "Deny";

    approveBtn.addEventListener("click", () => {

        submitApproval(
            true,
            card,
            approveBtn,
            denyBtn
        );

    });

    denyBtn.addEventListener("click", () => {

        submitApproval(
            false,
            card,
            approveBtn,
            denyBtn
        );

    });

    actions.appendChild(approveBtn);
    actions.appendChild(denyBtn);

    card.appendChild(heading);
    card.appendChild(description);
    card.appendChild(details);
    card.appendChild(actions);

    messagesContainer.appendChild(card);

    scrollToBottom(card);
}


// =============================================
// APPROVAL API
// =============================================

async function submitApproval(
    approved,
    card,
    approveBtn,
    denyBtn
) {
    const threadId = card?.dataset.threadId;

    if (!threadId || isApproving) {
        console.error(
            "[AETHRIX] Approval rejected: missing thread ID or request already processing."
        );
        return;
    }

    isApproving = true;

    approveBtn.disabled = true;
    denyBtn.disabled = true;

    approveBtn.textContent = "Processing...";

    try {
        const result = await apiRequest(
            `/api/agent/${encodeURIComponent(threadId)}/approval`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    approved: approved
                })
            }
        );

        card.remove();

        updateAgentStatus(result.status);

        addActivity(
            approved
                ? `Approval response: ${result.status}`
                : "Action denied by user"
        );

        if (result.status === "approval_required") {
            showApprovalCard(result);

        } else {
            // Clear only the thread that this card belongs to.
            if (activeThreadId === threadId) {
                savePendingThread(null);
            }

            const messages = {
                completed:
                    "The desktop task was completed successfully.",

                denied:
                    "The action was denied. No further execution was performed after your rejection.",

                blocked:
                    "The requested action was blocked by the safety system.",

                verification_failed:
                    "The action could not be verified successfully.",

                max_steps_reached:
                    "The task reached its maximum action limit.",

                api_rate_limited:
                    "The AI provider rate limit was reached.",

                error:
                    "The task could not be completed."
            };

            addMessage(
                messages[result.status] ||
                `Task finished with status: ${result.status || "Unknown"}`,
                "assistant"
            );
        }

    } catch (error) {
        approveBtn.disabled = false;
        denyBtn.disabled = false;

        approveBtn.textContent = "Approve";

        addMessage(
            `Approval request failed: ${error.message}`,
            "assistant"
        );

        console.error(
            "[AETHRIX] Approval error:",
            error
        );

    } finally {
        isApproving = false;
    }
}


// =============================================
// PROCESS CONVERSATION RESPONSE
// =============================================

function processResponse(data) {

    if (data.conversation_id) {

        conversationId = data.conversation_id;

        sessionStorage.setItem(
            STORAGE_KEY,
            conversationId
        );
    }


    // NORMAL CONVERSATION / CLARIFICATION

    if (
        data.type === "conversation" ||
        data.type === "clarification"
    ) {

        addMessage(
            data.response || "No response received.",
            "assistant"
        );

        updateAgentStatus("standby");

        return;
    }


    // DESKTOP ACTION

    if (data.type === "action") {

        const agent = data.agent || {};

        updateAgentStatus(agent.status);

        addActivity(
            `Desktop task: ${data.instruction || "New task"}`
        );

        if (agent.status === "approval_required") {

            showApprovalCard(agent);

        } else {

            savePendingThread(null);

            const messages = {

                completed:
                    "Your desktop task was completed successfully.",

                denied:
                    "The action was denied.",

                blocked:
                    "The requested action was blocked by the safety system.",

                verification_failed:
                    "The action could not be verified.",

                max_steps_reached:
                    "The task reached its maximum action limit.",

                api_rate_limited:
                    "The AI provider rate limit was reached.",

                error:
                    "The desktop task failed."

            };

            addMessage(
                messages[agent.status] ||
                `Task status: ${agent.status || "Unknown"}`,
                "assistant"
            );
        }

        return;
    }


    addMessage(
        "Received an unexpected response from the backend.",
        "assistant"
    );
}


// =============================================
// SEND MESSAGE TO BACKEND
// =============================================

async function sendMessage() {

    const message = messageInput.value.trim();

    if (!message || isSending || isApproving) {
        return;
    }

    if (activeThreadId) {

        addMessage(
            "Please resolve the pending approval before sending another instruction.",
            "assistant"
        );

        return;
    }

    isSending = true;

    sendBtn.disabled = true;

    addMessage(message, "user");

    addActivity("Processing message");

    messageInput.value = "";
    messageInput.style.height = "43px";

    const loadingMessage = showLoading();

    updateAgentStatus("running");

    try {

        const payload = {
            message: message
        };

        if (conversationId) {
            payload.conversation_id = conversationId;
        }

        const data = await apiRequest(
            "/api/conversation",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            }
        );

        loadingMessage.remove();

        processResponse(data);

    } catch (error) {

        loadingMessage.remove();

        updateAgentStatus("error");

        addMessage(
            `Something went wrong: ${error.message}`,
            "assistant"
        );

        console.error("[AETHRIX] Chat error:", error);

    } finally {

        isSending = false;
        sendBtn.disabled = false;

        messageInput.focus();
    }
}


// =============================================
// SEND BUTTON
// =============================================

sendBtn.addEventListener("click", sendMessage);


// =============================================
// ENTER TO SEND
// =============================================

messageInput.addEventListener("keydown", (event) => {

    if (event.key === "Enter" && !event.shiftKey) {

        event.preventDefault();

        sendMessage();
    }

});


// =============================================
// TEXTAREA AUTO RESIZE
// =============================================

messageInput.addEventListener("input", () => {

    messageInput.style.height = "43px";

    messageInput.style.height =
        `${Math.min(messageInput.scrollHeight, 120)}px`;

});


// =============================================
// QUICK PROMPTS
// =============================================

document.querySelectorAll(".quick-prompt").forEach((button) => {

    button.addEventListener("click", () => {

        messageInput.value = button.dataset.prompt || "";

        messageInput.focus();

        messageInput.dispatchEvent(
            new Event("input")
        );

    });

});


// =============================================
// NEW CONVERSATION
// =============================================

async function createNewConversation() {

    if (isSending || isApproving) {
        return;
    }

    if (activeThreadId) {

        addMessage(
            "Please resolve the pending approval before starting a new conversation.",
            "assistant"
        );

        return;
    }

    newChatBtn.disabled = true;

    try {

        const data = await apiRequest(
            "/api/conversation/new",
            {
                method: "POST"
            }
        );

        conversationId = data.conversation_id;

        sessionStorage.setItem(
            STORAGE_KEY,
            conversationId
        );

        savePendingThread(null);

        messagesContainer.innerHTML = "";

        showWelcomeScreen();

        messageInput.value = "";
        messageInput.style.height = "43px";

        activityList.innerHTML = "";

        if (emptyActivity) {

            activityList.appendChild(emptyActivity);

            emptyActivity.style.display = "block";
        }

        updateAgentStatus("standby");

        addActivity("New conversation created");

        console.log(
            "[AETHRIX] New conversation:",
            conversationId
        );

    } catch (error) {

        addMessage(
            `Could not create a new conversation: ${error.message}`,
            "assistant"
        );

        console.error(
            "[AETHRIX] New conversation error:",
            error
        );

    } finally {

        newChatBtn.disabled = false;
    }
}


newChatBtn.addEventListener(
    "click",
    createNewConversation
);


// =============================================
// RECOVER PENDING APPROVAL AFTER REFRESH
// =============================================

async function recoverPendingApproval() {

    if (!activeThreadId) {
        return;
    }

    try {

        console.log(
            "[AETHRIX] Recovering pending thread:",
            activeThreadId
        );

        const result = await apiRequest(
            `/api/agent/${activeThreadId}`
        );

        updateAgentStatus(result.status);

        if (result.status === "approval_required") {

            showApprovalCard(result);

            addMessage(
                "A pending approval was recovered. Review the action below.",
                "assistant"
            );

            return;
        }

        // The thread is no longer waiting for approval.
        savePendingThread(null);

        addMessage(
            `Previous task status: ${result.status || "Unknown"}`,
            "assistant"
        );

    } catch (error) {

        console.error(
            "[AETHRIX] Could not recover pending approval:",
            error.message
        );

        // Keep the stored ID. The backend may become available again.
        addMessage(
            "A previous approval could not be recovered. Please check the backend before starting another task.",
            "assistant"
        );
    }
}


// =============================================
// VOICE BUTTON — PHASE 3
// =============================================

voiceBtn.addEventListener("click", () => {

    addMessage(
        "Voice integration is not connected yet. It will be implemented in Phase 3.",
        "assistant"
    );

});


// =============================================
// SIDEBAR NAVIGATION
// =============================================

const sections = {

    chat: {
        title: "Assistant",
        description: "Your intelligent desktop companion."
    },

    activity: {
        title: "Activity",
        description: "Monitor your desktop agent's activities."
    },

    scheduler: {
        title: "Scheduler",
        description: "Manage your scheduled tasks."
    },

    approvals: {
        title: "Approvals",
        description: "Review sensitive actions before execution."
    },

    settings: {
        title: "Settings",
        description: "Configure your AETHRIX preferences."
    }

};


document.querySelectorAll(".nav-item[data-page]").forEach((button) => {

    button.addEventListener("click", () => {

        const section = button.dataset.page;

        const selected = sections[section];

        if (!selected) return;

        document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
            item.classList.remove("active");
        });

        button.classList.add("active");

        pageTitle.textContent = selected.title;

        if (section === "chat") {

            chatView.style.display = "flex";
            placeholderView.style.display = "none";

            ensureComposerVisible();

        } else {

            chatView.style.display = "none";
            placeholderView.style.display = "flex";

            placeholderTitle.textContent = selected.title;

            placeholderDescription.textContent =
                `${selected.description} This module will be connected in an upcoming phase.`;
        }
    });

});


// =============================================
// KEYBOARD SHORTCUT — CTRL + K
// =============================================

document.addEventListener("keydown", (event) => {

    if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "k"
    ) {

        event.preventDefault();

        createNewConversation();
    }

});


// =============================================
// STARTUP
// =============================================

// =============================================
// STARTUP
// =============================================

async function initializeAethrix() {

    console.log("================================");
    console.log("       AETHRIX AI SYSTEM        ");
    console.log("================================");

    // 1. Check backend availability.
    await checkBackend();

    // 2. Restore previous conversation.
    await loadConversationHistory();

    // 3. Recover pending approval.
    await recoverPendingApproval();

    // 4. Monitor backend health.
    setInterval(checkBackend, 15000);

    if (conversationId) {

        console.log(
            "[AETHRIX] Active conversation:",
            conversationId
        );
    }
}

initializeAethrix();

