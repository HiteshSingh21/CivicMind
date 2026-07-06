/**
 * CivicMind Frontend Application
 * ================================
 * Handles SSE streaming, dynamic message rendering, photo uploads,
 * forecast charts, action approval flow, and demo query execution.
 */

// ============================================================
// State
// ============================================================
let currentImage = null;
let isProcessing = false;

// ============================================================
// DOM Elements
// ============================================================
const messagesContainer = document.getElementById('messages-container');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const imageUpload = document.getElementById('image-upload');
const imagePreview = document.getElementById('image-preview');
const previewImg = document.getElementById('preview-img');
const removeImageBtn = document.getElementById('remove-image');
const dropZone = document.getElementById('drop-zone');

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    setupDragDrop();
});

function setupEventListeners() {
    // Send button
    sendBtn.addEventListener('click', handleSend);

    // Enter key
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    // Image upload
    imageUpload.addEventListener('change', handleImageSelect);
    removeImageBtn.addEventListener('click', clearImage);

    // Demo buttons
    document.querySelectorAll('.demo-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.dataset.query;
            if (btn.classList.contains('demo-btn-photo')) {
                // Load the sample pothole image for the photo demo
                loadSampleImage('/data/photos/pothole_01.jpg', query);
            } else {
                queryInput.value = query;
                handleSend();
            }
        });
    });
}

// ============================================================
// Image Handling
// ============================================================
function handleImageSelect(e) {
    const file = e.target.files[0];
    if (file) {
        setImage(file);
    }
}

function setImage(file) {
    currentImage = file;
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        imagePreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
}

function clearImage() {
    currentImage = null;
    imageUpload.value = '';
    previewImg.src = '';
    imagePreview.classList.add('hidden');
}

async function loadSampleImage(url, query) {
    try {
        const response = await fetch(url);
        const blob = await response.blob();
        const file = new File([blob], 'pothole_01.jpg', { type: blob.type || 'image/jpeg' });
        setImage(file);
        queryInput.value = query;
        // Small delay so user sees the image attached
        setTimeout(() => handleSend(), 300);
    } catch (e) {
        // If sample image fails, just send the text query
        queryInput.value = query;
        handleSend();
    }
}

// ============================================================
// Drag and Drop
// ============================================================
function setupDragDrop() {
    let dragCounter = 0;

    document.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (dragCounter === 1) {
            dropZone.classList.remove('hidden');
        }
    });

    document.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            dropZone.classList.add('hidden');
        }
    });

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    document.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
        dropZone.classList.add('hidden');

        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('image/')) {
            setImage(files[0]);
            queryInput.focus();
        }
    });
}

// ============================================================
// Message Handling
// ============================================================
function handleSend() {
    if (isProcessing) return;

    const query = queryInput.value.trim();
    if (!query && !currentImage) return;

    // Hide welcome message
    const welcome = document.getElementById('welcome-message');
    if (welcome) welcome.style.display = 'none';

    // Add user message
    addUserMessage(query, currentImage);

    // Clear input
    queryInput.value = '';

    // Start analysis
    startAnalysis(query, currentImage);

    // Clear image after sending
    clearImage();
}

function addUserMessage(query, image) {
    const msg = document.createElement('div');
    msg.className = 'message user-message';

    let imageHtml = '';
    if (image) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const imgEl = msg.querySelector('.user-image');
            if (imgEl) imgEl.src = e.target.result;
        };
        reader.readAsDataURL(image);
        imageHtml = `<img class="user-image" src="" alt="Uploaded photo" style="max-width:200px;border-radius:8px;margin-bottom:8px;">`;
    }

    msg.innerHTML = `
        <div class="message-icon">
            <span class="material-icons-round">person</span>
        </div>
        <div class="message-content">
            ${imageHtml}
            <p>${escapeHtml(query || 'Analyze this image')}</p>
        </div>
    `;

    messagesContainer.appendChild(msg);
    scrollToBottom();
}

// ============================================================
// SSE Analysis Stream
// ============================================================
async function startAnalysis(query, image) {
    isProcessing = true;
    sendBtn.disabled = true;

    // Create a container for this analysis response
    const responseContainer = document.createElement('div');
    responseContainer.className = 'message system-message';
    responseContainer.innerHTML = `
        <div class="message-icon">
            <span class="material-icons-round">auto_awesome</span>
        </div>
        <div class="message-content" id="response-content-${Date.now()}">
        </div>
    `;
    messagesContainer.appendChild(responseContainer);
    const contentEl = responseContainer.querySelector('.message-content');

    try {
        let body;
        let headers = {};

        if (image) {
            body = new FormData();
            body.append('query', query || 'Analyze this civic issue and create a work order');
            body.append('image', image);
        } else {
            body = JSON.stringify({ query });
            headers['Content-Type'] = 'application/json';
        }

        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: image ? {} : headers,
            body: body,
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        // Persistent state across chunks - event/data may arrive in separate reads
        let pendingEvent = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE spec: events are separated by blank lines (\n\n or \r\n\r\n)
            // Split on double-newline to get complete event blocks
            const blocks = buffer.split(/\r?\n\r?\n/);
            // Last element may be incomplete - keep in buffer
            buffer = blocks.pop() || '';

            for (const block of blocks) {
                if (!block.trim()) continue;

                let eventType = null;
                let eventData = null;

                const lines = block.split(/\r?\n/);
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        eventType = line.substring(6).trim();
                    } else if (line.startsWith('data:')) {
                        eventData = line.substring(5).trim();
                    }
                }

                if (eventType && eventData) {
                    try {
                        const parsed = JSON.parse(eventData);
                        handleSSEEvent(eventType, parsed, contentEl);
                    } catch (e) {
                        console.warn('SSE parse error:', e, eventData);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Stream error:', error);
        contentEl.innerHTML += renderError('Connection error. Please check the server is running and try again.');
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        scrollToBottom();
        clearActiveAgents();
    }
}

// ============================================================
// SSE Event Handlers
// ============================================================
function handleSSEEvent(event, data, contentEl) {
    switch (event) {
        case 'routing':
            handleRouting(data, contentEl);
            break;
        case 'thinking':
            handleThinking(data, contentEl);
            break;
        case 'data':
            handleData(data, contentEl);
            break;
        case 'action':
            handleAction(data, contentEl);
            break;
        case 'error':
            handleError(data, contentEl);
            break;
        case 'complete':
            handleComplete(data, contentEl);
            break;
    }
    scrollToBottom();
}

function handleRouting(data, contentEl) {
    // Remove any existing thinking indicator
    const existing = contentEl.querySelector('.thinking-indicator');
    if (existing) existing.remove();

    // Highlight active agent in sidebar
    setActiveAgent(data.intent);

    contentEl.innerHTML += `
        <div class="routing-indicator">
            <div class="routing-dot" style="background: ${data.color}"></div>
            <span class="routing-text">Routing to <span class="routing-agent">${data.agent}</span></span>
        </div>
    `;
}

function handleThinking(data, contentEl) {
    // Remove previous thinking indicator
    const existing = contentEl.querySelector('.thinking-indicator');
    if (existing) existing.remove();

    if (data.agent) setActiveAgent(data.agent);

    contentEl.innerHTML += `
        <div class="thinking-indicator">
            <div class="thinking-dots">
                <span></span><span></span><span></span>
            </div>
            <span class="thinking-text">${escapeHtml(data.message)}</span>
        </div>
    `;
}

function handleData(data, contentEl) {
    // Remove thinking indicator
    const thinking = contentEl.querySelector('.thinking-indicator');
    if (thinking) thinking.remove();

    const agent = data.agent || '';

    if (data.fallback) {
        contentEl.innerHTML += renderError(data.message || 'Fallback result provided.');
        return;
    }

    switch (agent) {
        case 'data_agent':
            contentEl.innerHTML += renderDataAgentResult(data);
            break;
        case 'rag_agent':
            contentEl.innerHTML += renderRAGAgentResult(data);
            break;
        case 'forecasting_agent':
            contentEl.innerHTML += renderForecastResult(data);
            break;
        case 'multimodal_agent':
            contentEl.innerHTML += renderMultimodalResult(data);
            break;
        default:
            contentEl.innerHTML += `<div class="summary-text">${escapeHtml(JSON.stringify(data, null, 2))}</div>`;
    }
}

function handleAction(data, contentEl) {
    if (data.agent === 'action') {
        setActiveAgent('action');
    }
    contentEl.innerHTML += renderActionCard(data);

    // Wire up approval buttons after rendering
    setTimeout(() => {
        const approveBtn = contentEl.querySelector('.btn-approve');
        const rejectBtn = contentEl.querySelector('.btn-reject');
        if (approveBtn) {
            approveBtn.addEventListener('click', () => handleApproval(data.action_id, contentEl));
        }
        if (rejectBtn) {
            rejectBtn.addEventListener('click', () => handleRejection(data.action_id, contentEl));
        }
    }, 100);
}

function handleError(data, contentEl) {
    if (data.recoverable) {
        contentEl.innerHTML += `
            <div class="error-card">
                <span class="material-icons-round">refresh</span>
                <span class="error-card-text">${escapeHtml(data.message)}</span>
            </div>
        `;
    } else {
        contentEl.innerHTML += renderError(data.message);
    }
}

function handleComplete(data, contentEl) {
    // Remove any remaining thinking indicator
    const thinking = contentEl.querySelector('.thinking-indicator');
    if (thinking) thinking.remove();
}

// ============================================================
// Render Functions
// ============================================================
function renderDataAgentResult(data) {
    let html = `
        <div class="result-card">
            <div class="result-header">
                <div class="result-header-icon" style="background: rgba(79, 195, 247, 0.1);">
                    <span class="material-icons-round" style="color: var(--color-data)">storage</span>
                </div>
                <span class="result-header-title">Data Agent Result</span>
                <span class="result-header-badge">Structured Query</span>
            </div>
            <div class="result-body">
    `;

    // Summary
    if (data.summary) {
        html += `<div class="summary-text">${escapeHtml(data.summary)}</div>`;
    }

    // Table
    if (data.results && data.results.length > 0) {
        const keys = Object.keys(data.results[0]);
        html += `<div class="data-table-wrapper"><table class="data-table"><thead><tr>`;
        keys.forEach(k => html += `<th>${escapeHtml(formatColumnName(k))}</th>`);
        html += `</tr></thead><tbody>`;
        data.results.slice(0, 10).forEach(row => {
            html += `<tr>`;
            keys.forEach(k => html += `<td>${escapeHtml(String(row[k] ?? ''))}</td>`);
            html += `</tr>`;
        });
        html += `</tbody></table></div>`;
    }

    // SQL
    if (data.sql) {
        html += `<div class="sql-display">${escapeHtml(data.sql)}</div>`;
    }

    // Source
    if (data.source) {
        html += `<span class="source-tag"><span class="material-icons-round">verified</span>${escapeHtml(data.source)}</span>`;
    }

    html += `</div></div>`;
    return html;
}

function renderRAGAgentResult(data) {
    let html = `
        <div class="result-card">
            <div class="result-header">
                <div class="result-header-icon" style="background: rgba(129, 199, 132, 0.1);">
                    <span class="material-icons-round" style="color: var(--color-rag)">search</span>
                </div>
                <span class="result-header-title">Document Search Result</span>
                <span class="result-header-badge">${data.source_count || 0} sources</span>
                ${data.pii_redacted ? `<span class="pii-badge"><span class="material-icons-round">shield</span>PII Redacted</span>` : ''}
            </div>
            <div class="result-body">
    `;

    // Answer
    if (data.answer) {
        html += `<div class="summary-text">${formatAnswer(data.answer)}</div>`;
    }

    // Citations
    if (data.citations && data.citations.length > 0) {
        html += `<div class="citations-list">`;
        data.citations.forEach((c, i) => {
            html += `
                <div class="citation-item">
                    <div class="citation-number">${i + 1}</div>
                    <div class="citation-content">
                        <div class="citation-source">${escapeHtml(c.source)}</div>
                        <div class="citation-category">${escapeHtml(c.category)}</div>
                        <div class="citation-excerpt">${escapeHtml(c.excerpt)}</div>
                    </div>
                    <div class="citation-score">${(c.relevance_score * 100).toFixed(0)}% match</div>
                </div>
            `;
        });
        html += `</div>`;
    }

    html += `</div></div>`;
    return html;
}

function renderForecastResult(data) {
    const chartId = `forecast-chart-${Date.now()}`;

    let html = `
        <div class="result-card">
            <div class="result-header">
                <div class="result-header-icon" style="background: rgba(255, 183, 77, 0.1);">
                    <span class="material-icons-round" style="color: var(--color-forecast)">trending_up</span>
                </div>
                <span class="result-header-title">${escapeHtml(data.metric || 'Forecast')}</span>
                <span class="result-header-badge">${data.method || 'Statistical'}</span>
            </div>
            <div class="result-body">
    `;

    // Summary
    if (data.summary) {
        html += `<div class="summary-text">${escapeHtml(data.summary)}</div>`;
    }

    // Chart
    if (data.historical && data.forecast) {
        html += `
            <div class="forecast-chart-container">
                <canvas id="${chartId}"></canvas>
            </div>
            <div class="forecast-legend">
                <div class="forecast-legend-item">
                    <div class="forecast-legend-dot" style="background: #4FC3F7"></div>
                    Historical
                </div>
                <div class="forecast-legend-item">
                    <div class="forecast-legend-dot" style="background: #FFB74D"></div>
                    Forecast
                </div>
                <div class="forecast-legend-item">
                    <div class="forecast-legend-dot" style="background: rgba(255,183,77,0.2)"></div>
                    95% Confidence Band
                </div>
            </div>
        `;
    }

    // Confidence info
    if (data.confidence_level) {
        html += `
            <div class="confidence-info">
                <span class="material-icons-round">ssid_chart</span>
                <span>Model confidence: ${(data.confidence_level * 100).toFixed(0)}% | Method: ${escapeHtml(data.method || 'N/A')} | Google Cloud equivalent: ${escapeHtml(data.google_cloud_equivalent || 'BigQuery ML')}</span>
            </div>
        `;
    }

    // Source
    if (data.source) {
        html += `<span class="source-tag"><span class="material-icons-round">verified</span>${escapeHtml(data.source)}</span>`;
    }

    html += `</div></div>`;

    // Render chart after DOM update
    if (data.historical && data.forecast) {
        setTimeout(() => drawForecastChart(chartId, data.historical, data.forecast), 200);
    }

    return html;
}

function renderMultimodalResult(data) {
    const cls = data.classification || {};
    const geo = data.geolocation || {};
    const severity = cls.severity || 0;

    let severityDots = '';
    for (let i = 1; i <= 5; i++) {
        const filled = i <= severity;
        const level = severity <= 2 ? 'low' : severity <= 3 ? 'med' : 'high';
        severityDots += `<div class="severity-dot ${filled ? 'filled ' + level : ''}"></div>`;
    }

    let html = `
        <div class="result-card">
            <div class="result-header">
                <div class="result-header-icon" style="background: rgba(206, 147, 216, 0.1);">
                    <span class="material-icons-round" style="color: var(--color-multimodal)">photo_camera</span>
                </div>
                <span class="result-header-title">Photo Analysis Result</span>
                <span class="result-header-badge">${escapeHtml(data.complaint_id || '')}</span>
            </div>
            <div class="result-body">
                <div class="classification-grid">
                    <div class="classification-item">
                        <div class="classification-label">Issue Type</div>
                        <div class="classification-value">${escapeHtml((cls.issue_type || 'unknown').replace(/_/g, ' '))}</div>
                    </div>
                    <div class="classification-item">
                        <div class="classification-label">Severity</div>
                        <div class="classification-value">${severity}/5</div>
                        <div class="severity-meter">${severityDots}</div>
                    </div>
                    <div class="classification-item">
                        <div class="classification-label">Location</div>
                        <div class="classification-value">${geo.latitude?.toFixed(4) || 'N/A'}, ${geo.longitude?.toFixed(4) || 'N/A'}</div>
                    </div>
                    <div class="classification-item">
                        <div class="classification-label">Est. Repair Time</div>
                        <div class="classification-value">${escapeHtml(cls.estimated_repair_time || 'TBD')}</div>
                    </div>
                </div>
                <div class="summary-text">${escapeHtml(cls.description || '')}</div>
                <div class="summary-text" style="color: var(--text-secondary); font-size: 0.85rem;">
                    <strong>Recommended Action:</strong> ${escapeHtml(cls.recommended_action || '')}
                </div>
    `;

    if (data.stored) {
        html += `
            <span class="source-tag"><span class="material-icons-round">check_circle</span>${escapeHtml(data.stored_message || 'Stored in knowledge base')}</span>
        `;
    }

    html += `</div></div>`;
    return html;
}

function renderActionCard(data) {
    const action = data.action || {};
    const actionId = data.action_id || '';

    return `
        <div class="action-card" id="action-card-${actionId}">
            <div class="action-header">
                <span class="material-icons-round">gavel</span>
                <div class="action-header-text">
                    <div class="action-header-title">${escapeHtml(action.title || 'Proposed Action')}</div>
                    <div class="action-header-subtitle">Requires Human Approval</div>
                </div>
            </div>
            <div class="action-body">
                <div class="action-details">
                    <span class="action-detail-label">Type:</span>
                    <span class="action-detail-value">${escapeHtml((action.action_type || '').replace(/_/g, ' '))}</span>

                    <span class="action-detail-label">Priority:</span>
                    <span class="action-detail-value">${escapeHtml(action.priority || 'N/A')}</span>

                    <span class="action-detail-label">Department:</span>
                    <span class="action-detail-value">${escapeHtml(action.department || 'N/A')}</span>

                    ${action.location ? `
                        <span class="action-detail-label">Location:</span>
                        <span class="action-detail-value">${escapeHtml(action.location)}</span>
                    ` : ''}

                    ${action.estimated_repair_time ? `
                        <span class="action-detail-label">Est. Time:</span>
                        <span class="action-detail-value">${escapeHtml(action.estimated_repair_time)}</span>
                    ` : ''}
                </div>

                ${action.enhanced_description ? `
                    <div class="summary-text" style="font-size: 0.85rem;">${escapeHtml(action.enhanced_description)}</div>
                ` : `
                    <div class="summary-text" style="font-size: 0.85rem;">${escapeHtml(action.recommended_action || action.description || '')}</div>
                `}

                <div class="action-rai-notice">
                    <span class="material-icons-round">shield</span>
                    <span>${escapeHtml(data.approval_message || 'This action requires human approval before dispatch.')}</span>
                </div>

                <div class="action-buttons" id="action-buttons-${actionId}">
                    <button class="btn-approve" data-action-id="${actionId}">
                        <span class="material-icons-round">check_circle</span>
                        Approve & Dispatch
                    </button>
                    <button class="btn-reject" data-action-id="${actionId}">
                        <span class="material-icons-round">cancel</span>
                        Reject
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderError(message) {
    return `
        <div class="error-card">
            <span class="material-icons-round">error_outline</span>
            <span class="error-card-text">${escapeHtml(message)}</span>
        </div>
    `;
}

// ============================================================
// Action Approval
// ============================================================
async function handleApproval(actionId, contentEl) {
    const buttonsEl = document.getElementById(`action-buttons-${actionId}`);
    if (!buttonsEl) return;

    // Disable buttons
    buttonsEl.querySelectorAll('button').forEach(b => b.disabled = true);

    try {
        const response = await fetch('/api/approve-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action_id: actionId }),
        });

        const result = await response.json();

        if (result.success) {
            buttonsEl.innerHTML = `
                <div class="dispatched-banner">
                    <span class="material-icons-round">check_circle</span>
                    <span class="dispatched-banner-text">${escapeHtml(result.message)}</span>
                </div>
            `;
        } else {
            buttonsEl.innerHTML = renderError(result.error || 'Failed to approve action.');
        }
    } catch (e) {
        buttonsEl.innerHTML = renderError('Network error. Could not approve action.');
    }

    scrollToBottom();
}

async function handleRejection(actionId, contentEl) {
    const buttonsEl = document.getElementById(`action-buttons-${actionId}`);
    if (!buttonsEl) return;

    buttonsEl.querySelectorAll('button').forEach(b => b.disabled = true);

    try {
        const response = await fetch('/api/reject-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action_id: actionId, reason: 'Rejected by operator' }),
        });

        const result = await response.json();
        buttonsEl.innerHTML = `
            <div class="error-card" style="border-color: rgba(239,68,68,0.2);">
                <span class="material-icons-round">cancel</span>
                <span class="error-card-text">Action rejected.</span>
            </div>
        `;
    } catch (e) {
        buttonsEl.innerHTML = renderError('Network error.');
    }

    scrollToBottom();
}

// ============================================================
// Forecast Chart (Canvas-based)
// ============================================================
function drawForecastChart(canvasId, historical, forecast) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const container = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = container.clientWidth * dpr;
    canvas.height = container.clientHeight * dpr;
    canvas.style.width = container.clientWidth + 'px';
    canvas.style.height = container.clientHeight + 'px';
    ctx.scale(dpr, dpr);

    const W = container.clientWidth;
    const H = container.clientHeight;
    const padding = { top: 20, right: 30, bottom: 40, left: 50 };

    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    // Combine data
    const allValues = [
        ...historical.map(d => d.value),
        ...forecast.map(d => d.predicted),
        ...forecast.map(d => d.upper_bound),
        ...forecast.map(d => d.lower_bound),
    ];
    const minVal = Math.max(0, Math.min(...allValues) - 2);
    const maxVal = Math.max(...allValues) + 2;
    const totalPoints = historical.length + forecast.length;

    function xPos(i) { return padding.left + (i / (totalPoints - 1)) * chartW; }
    function yPos(v) { return padding.top + chartH - ((v - minVal) / (maxVal - minVal)) * chartH; }

    // Background
    ctx.fillStyle = 'rgba(0,0,0,0)';
    ctx.fillRect(0, 0, W, H);

    // Grid lines
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.08)';
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
        const y = padding.top + (i / gridLines) * chartH;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(W - padding.right, y);
        ctx.stroke();

        // Y-axis labels
        const val = maxVal - (i / gridLines) * (maxVal - minVal);
        ctx.fillStyle = '#64748b';
        ctx.font = '11px Inter, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(0), padding.left - 8, y + 4);
    }

    // Vertical divider (forecast start)
    const dividerX = xPos(historical.length - 1);
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.15)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(dividerX, padding.top);
    ctx.lineTo(dividerX, H - padding.bottom);
    ctx.stroke();
    ctx.setLineDash([]);

    // Labels
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Historical', padding.left + (dividerX - padding.left) / 2, H - 8);
    ctx.fillText('Forecast', dividerX + (W - padding.right - dividerX) / 2, H - 8);

    // X-axis dates (sparse)
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter, sans-serif';
    const allDates = [...historical.map(d => d.date), ...forecast.map(d => d.date)];
    const step = Math.max(1, Math.floor(totalPoints / 8));
    for (let i = 0; i < totalPoints; i += step) {
        const x = xPos(i);
        const dateStr = allDates[i];
        if (dateStr) {
            const parts = dateStr.split('-');
            ctx.fillText(`${parts[1]}/${parts[2]}`, x, H - padding.bottom + 16);
        }
    }

    // Confidence band (forecast region)
    if (forecast.length > 1) {
        ctx.fillStyle = 'rgba(255, 183, 77, 0.1)';
        ctx.beginPath();
        for (let i = 0; i < forecast.length; i++) {
            const x = xPos(historical.length + i);
            const y = yPos(forecast[i].upper_bound);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        for (let i = forecast.length - 1; i >= 0; i--) {
            const x = xPos(historical.length + i);
            const y = yPos(forecast[i].lower_bound);
            ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fill();

        // Upper bound line
        ctx.strokeStyle = 'rgba(255, 183, 77, 0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        forecast.forEach((d, i) => {
            const x = xPos(historical.length + i);
            const y = yPos(d.upper_bound);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Lower bound line
        ctx.beginPath();
        forecast.forEach((d, i) => {
            const x = xPos(historical.length + i);
            const y = yPos(d.lower_bound);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    // Historical line
    ctx.strokeStyle = '#4FC3F7';
    ctx.lineWidth = 2;
    ctx.beginPath();
    historical.forEach((d, i) => {
        const x = xPos(i);
        const y = yPos(d.value);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Forecast line
    ctx.strokeStyle = '#FFB74D';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.beginPath();
    // Connect from last historical point
    if (historical.length > 0) {
        const lastH = historical[historical.length - 1];
        ctx.moveTo(xPos(historical.length - 1), yPos(lastH.value));
    }
    forecast.forEach((d, i) => {
        const x = xPos(historical.length + i);
        const y = yPos(d.predicted);
        ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
}

// ============================================================
// Sidebar Agent Highlighting
// ============================================================
function setActiveAgent(intent) {
    clearActiveAgents();

    // Always activate supervisor first
    const supervisorCard = document.getElementById('agent-card-supervisor');
    if (supervisorCard) supervisorCard.classList.add('active');

    // Map intent to card ID
    const mapping = {
        'structured': 'agent-card-data',
        'unstructured': 'agent-card-rag',
        'predictive': 'agent-card-forecast',
        'multimodal': 'agent-card-multimodal',
        'action': 'agent-card-action',
    };

    const cardId = mapping[intent];
    if (cardId) {
        const card = document.getElementById(cardId);
        if (card) card.classList.add('active');
    }
}

function clearActiveAgents() {
    document.querySelectorAll('.agent-card').forEach(c => c.classList.remove('active'));
}

// ============================================================
// Utilities
// ============================================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatColumnName(name) {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatAnswer(text) {
    // Bold source references
    return escapeHtml(text).replace(
        /\[(Source \d+:[^\]]*)\]/g,
        '<span class="source-tag" style="display:inline; margin:0 2px;"><span class="material-icons-round" style="font-size:10px">verified</span>$1</span>'
    );
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    });
}
