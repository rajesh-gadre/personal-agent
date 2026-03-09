// ── Configuration ──
const API = '/api';

// ── State ──
let currentStagingId = null;  // Upload tab's active staging ID
let categoryChart = null;     // Chart.js instance

// ── Initialization ──
document.addEventListener('DOMContentLoaded', init);

async function init() {
    setupTabs();
    setupUpload();
    setupExpenseFilters();
    setupSummaryDates();
    await refreshPendingCount();
}

// ── API Helper ──
async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, options);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || err.error || 'Request failed');
    }
    return res.json();
}

// ── Tab Management ──
function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => showTab(btn.dataset.tab));
    });
}

function showTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === `tab-${tabName}`));

    // Load data when switching tabs
    if (tabName === 'pending') loadPending();
    if (tabName === 'summary') loadSummary();
}

// ── Upload Tab ──
function setupUpload() {
    const fileInput = document.getElementById('file-input');
    const analyzeBtn = document.getElementById('analyze-btn');

    fileInput.addEventListener('change', () => {
        analyzeBtn.disabled = !fileInput.files.length;
    });

    analyzeBtn.addEventListener('click', async () => {
        if (!fileInput.files.length) return;
        await analyzeReceipt(fileInput.files[0]);
    });
}

async function analyzeReceipt(file) {
    const formData = new FormData();
    formData.append('file', file);
    showSpinner();
    try {
        const result = await api('/receipts/upload', { method: 'POST', body: formData });
        if (result.error) {
            showAlert('upload-review', result.error, 'error');
            return;
        }
        currentStagingId = result.staging_id;

        // Show size info
        const sizeInfo = document.getElementById('upload-size-info');
        if (result.original_size_bytes) {
            const origMB = (result.original_size_bytes / 1_000_000).toFixed(1);
            const sentMB = (result.sent_size_bytes / 1_000_000).toFixed(1);
            sizeInfo.textContent = result.original_size_bytes !== result.sent_size_bytes
                ? `Original: ${origMB} MB → Sent: ${sentMB} MB`
                : `Size: ${origMB} MB (no resize needed)`;
            sizeInfo.classList.remove('hidden');
        }

        await showUploadReview();
        await refreshPendingCount();
    } catch (e) {
        showAlert('upload-review', e.message, 'error');
    } finally {
        hideSpinner();
    }
}

async function showUploadReview() {
    const staged = await api(`/receipts/staged/${currentStagingId}`);
    const container = document.getElementById('upload-review');
    container.innerHTML = '';
    const infoDiv = document.createElement('div');
    infoDiv.className = 'alert alert-info';
    infoDiv.textContent = 'Review the extracted data below. Edit if needed, then approve or reject.';
    container.appendChild(infoDiv);
    await renderReviewForm(staged, container, 'upload');
}

function clearUploadState() {
    currentStagingId = null;
    document.getElementById('upload-review').innerHTML = '';
    document.getElementById('upload-size-info').classList.add('hidden');
    document.getElementById('file-input').value = '';
    document.getElementById('analyze-btn').disabled = true;
}

// ── Review Form (shared between Upload and Pending tabs) ──
async function renderReviewForm(staged, container, prefix) {
    const data = staged.extracted_data;
    const imageUrl = staged.image_url;
    const stagingId = staged.staging_id;

    const categories = await api('/categories');
    const currentCat = data.category || 'other';
    // If LLM suggested a new category not in the list, include it
    if (currentCat && !categories.includes(currentCat)) {
        categories.push(currentCat);
    }

    const card = document.createElement('div');
    card.className = 'card';

    const isValid = data.is_valid_receipt !== false;
    const hasValidData = isValid || (data.merchant_name && data.total);

    card.innerHTML = `
        <div class="review-layout">
            <div class="review-image">
                ${imageUrl
                    ? `<img src="${imageUrl}" alt="Receipt" onerror="this.outerHTML='<div class=\\'no-image\\'>Image not available</div>'">`
                    : '<div class="no-image">No image</div>'}
            </div>
            <div class="review-fields">
                <div class="form-row form-row-2">
                    <div class="form-group">
                        <label>Merchant</label>
                        <input type="text" id="${prefix}-merchant" value="${escapeAttr(data.merchant_name || '')}">
                    </div>
                    <div class="form-group">
                        <label>Address</label>
                        <input type="text" id="${prefix}-address" value="${escapeAttr(data.merchant_address || '')}">
                    </div>
                </div>
                <div class="form-row form-row-3">
                    <div class="form-group">
                        <label>Date</label>
                        <input type="date" id="${prefix}-date" value="${data.date || ''}">
                    </div>
                    <div class="form-group">
                        <label>Category</label>
                        <select id="${prefix}-category">
                            ${categories.map(c => `<option value="${c}" ${c === currentCat ? 'selected' : ''}>${c}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Payment</label>
                        <input type="text" id="${prefix}-payment" value="${escapeAttr(data.payment_method || '')}">
                    </div>
                </div>
                <div class="form-row form-row-2" style="max-width:300px;">
                    <div class="form-group">
                        <label>Currency</label>
                        <input type="text" id="${prefix}-currency" value="${escapeAttr(data.currency || 'USD')}">
                    </div>
                </div>
                ${renderItemsTable(data.items)}
                <div class="form-row form-row-4">
                    <div class="form-group">
                        <label>Subtotal</label>
                        <input type="number" step="0.01" id="${prefix}-subtotal" value="${data.subtotal || 0}">
                    </div>
                    <div class="form-group">
                        <label>Tax</label>
                        <input type="number" step="0.01" id="${prefix}-tax" value="${data.tax || 0}">
                    </div>
                    <div class="form-group">
                        <label>Tip</label>
                        <input type="number" step="0.01" id="${prefix}-tip" value="${data.tip || 0}">
                    </div>
                    <div class="form-group">
                        <label>Total</label>
                        <input type="number" step="0.01" id="${prefix}-total" value="${data.total || 0}">
                    </div>
                </div>

                ${!hasValidData ? '<div class="alert alert-error">This does not appear to be a receipt. You can reject it or re-analyze.</div>' : ''}

                <div id="${prefix}-dup-warning"></div>

                <div class="review-actions">
                    <button class="btn btn-sm" onclick="handleCopyJson('${prefix}')">Copy JSON</button>
                    <button class="btn btn-sm" onclick="handleReject('${stagingId}', '${prefix}')">Reject</button>
                    <button class="btn btn-sm" onclick="handleReanalyze('${stagingId}', '${prefix}')">Re-analyze</button>
                    ${hasValidData ? `<button class="btn btn-sm btn-primary" onclick="handleApprove('${stagingId}', '${prefix}')">Approve &amp; Save</button>` : ''}
                </div>
            </div>
        </div>
    `;
    container.appendChild(card);

    // Set up debounced duplicate check
    if (hasValidData) {
        const inputs = card.querySelectorAll('input, select');
        let debounceTimer;
        inputs.forEach(input => {
            input.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => checkAndShowDuplicate(prefix, stagingId), 500);
            });
        });
        // Initial duplicate check
        checkAndShowDuplicate(prefix, stagingId);
    }
}

function renderItemsTable(items) {
    if (!items || !items.length) return '';
    return `
        <div class="mb-1">
            <label style="font-size:0.85rem;font-weight:600;color:#555;">Items</label>
            <table>
                <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead>
                <tbody>
                    ${items.map(i => `<tr>
                        <td>${escapeHtml(i.description)}</td>
                        <td>${i.quantity}</td>
                        <td>${formatCurrency(i.unit_price)}</td>
                        <td>${formatCurrency(i.total)}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function getEditedData(prefix) {
    return {
        merchant_name: document.getElementById(`${prefix}-merchant`).value,
        merchant_address: document.getElementById(`${prefix}-address`).value || null,
        date: document.getElementById(`${prefix}-date`).value || null,
        items: [],  // items are read-only in the form
        subtotal: parseFloat(document.getElementById(`${prefix}-subtotal`).value) || 0,
        tax: parseFloat(document.getElementById(`${prefix}-tax`).value) || 0,
        tip: parseFloat(document.getElementById(`${prefix}-tip`).value) || 0,
        total: parseFloat(document.getElementById(`${prefix}-total`).value) || 0,
        payment_method: document.getElementById(`${prefix}-payment`).value || null,
        category: document.getElementById(`${prefix}-category`).value,
        currency: document.getElementById(`${prefix}-currency`).value || 'USD',
    };
}

// ── Duplicate Detection ──
async function checkAndShowDuplicate(prefix, stagingId) {
    const data = getEditedData(prefix);
    const warningDiv = document.getElementById(`${prefix}-dup-warning`);
    if (!data.merchant_name || !data.total || !data.date) {
        warningDiv.innerHTML = '';
        return;
    }
    try {
        const result = await api('/receipts/check-duplicate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (result.is_duplicate && result.existing_receipt) {
            const dup = result.existing_receipt;
            warningDiv.innerHTML = `
                <div class="alert alert-warning">
                    Possible duplicate: ${escapeHtml(dup.merchant_name)} — ${formatCurrency(dup.total)} — ${formatDate(dup.date)}
                </div>
                <div class="comparison">
                    <div>
                        <h4>New (this receipt)</h4>
                        <table>
                            <tr><td><strong>Merchant</strong></td><td>${escapeHtml(data.merchant_name)}</td></tr>
                            <tr><td><strong>Date</strong></td><td>${formatDate(data.date)}</td></tr>
                            <tr><td><strong>Total</strong></td><td>${formatCurrency(data.total)}</td></tr>
                            <tr><td><strong>Tax</strong></td><td>${formatCurrency(data.tax)}</td></tr>
                            <tr><td><strong>Payment</strong></td><td>${data.payment_method || '—'}</td></tr>
                            <tr><td><strong>Category</strong></td><td>${data.category}</td></tr>
                        </table>
                    </div>
                    <div>
                        <h4>Existing receipt</h4>
                        <table>
                            <tr><td><strong>Merchant</strong></td><td>${escapeHtml(dup.merchant_name)}</td></tr>
                            <tr><td><strong>Date</strong></td><td>${formatDate(dup.date)}</td></tr>
                            <tr><td><strong>Total</strong></td><td>${formatCurrency(dup.total)}</td></tr>
                            <tr><td><strong>Tax</strong></td><td>${formatCurrency(dup.tax)}</td></tr>
                            <tr><td><strong>Payment</strong></td><td>${dup.payment_method || '—'}</td></tr>
                            <tr><td><strong>Category</strong></td><td>${dup.category}</td></tr>
                        </table>
                        ${dup.image_url ? `<img src="${dup.image_url}" alt="Existing receipt" style="max-width:100%;margin-top:0.5rem;border-radius:6px;">` : ''}
                    </div>
                </div>
            `;
            warningDiv.dataset.hasDuplicate = 'true';
        } else {
            warningDiv.innerHTML = '';
            warningDiv.dataset.hasDuplicate = 'false';
        }
    } catch (e) {
        // Silently ignore duplicate check errors
        warningDiv.innerHTML = '';
        warningDiv.dataset.hasDuplicate = 'false';
    }
}

// ── Action Handlers ──
function handleCopyJson(prefix) {
    const data = getEditedData(prefix);
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
        .then(() => showToast('Copied to clipboard'))
        .catch(() => showToast('Failed to copy', 'error'));
}

async function handleReject(stagingId, prefix) {
    try {
        await api(`/receipts/staged/${stagingId}/reject`, { method: 'POST' });
        showToast('Receipt rejected');
        if (prefix === 'upload') {
            clearUploadState();
        } else {
            await loadPending();
        }
        await refreshPendingCount();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function handleReanalyze(stagingId, prefix) {
    showSpinner();
    try {
        const result = await api(`/receipts/staged/${stagingId}/reanalyze`, { method: 'POST' });
        if (result.error) {
            showToast(result.error, 'error');
            return;
        }
        if (prefix === 'upload') {
            currentStagingId = result.staging_id;
            await showUploadReview();
        } else {
            await loadPending();
        }
        showToast('Re-analysis complete');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideSpinner();
    }
}

async function handleApprove(stagingId, prefix) {
    const data = getEditedData(prefix);
    const warningDiv = document.getElementById(`${prefix}-dup-warning`);
    const hasDuplicate = warningDiv && warningDiv.dataset.hasDuplicate === 'true';

    // Preserve items from the staged data
    try {
        const staged = await api(`/receipts/staged/${stagingId}`);
        data.items = staged.extracted_data.items || [];
    } catch (e) {
        // Continue without items
    }

    if (hasDuplicate) {
        showConfirmModal(
            'This receipt appears to be a duplicate. Are you sure you want to save it?',
            async () => {
                await doApprove(stagingId, data, prefix);
            }
        );
    } else {
        await doApprove(stagingId, data, prefix);
    }
}

async function doApprove(stagingId, data, prefix) {
    try {
        const result = await api(`/receipts/staged/${stagingId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        showToast(`Saved as receipt #${result.receipt_id}`);
        if (prefix === 'upload') {
            clearUploadState();
        } else {
            await loadPending();
        }
        await refreshPendingCount();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ── Pending Tab ──
async function loadPending() {
    const container = document.getElementById('pending-list');
    try {
        let pending = await api('/receipts/staged');
        // Exclude receipt shown on Upload tab
        if (currentStagingId) {
            pending = pending.filter(s => s.staging_id !== currentStagingId);
        }

        if (!pending.length) {
            container.innerHTML = '<div class="alert alert-info">No receipts pending review.</div>';
            return;
        }

        container.innerHTML = '';
        for (let i = 0; i < pending.length; i++) {
            const staged = pending[i];
            const data = staged.extracted_data;
            const totalStr = data.total != null ? formatCurrency(data.total) : '$?.??';
            const label = `${data.merchant_name || 'Unknown'} — ${totalStr} — ${formatDate(data.date)}`;

            const card = document.createElement('div');
            card.className = 'card';

            const header = document.createElement('div');
            header.className = `expand-header${i === 0 ? ' expanded' : ''}`;
            header.innerHTML = `<span>${escapeHtml(label)}</span><span class="arrow">&#9654;</span>`;

            const body = document.createElement('div');
            body.className = `expand-body${i === 0 ? ' expanded' : ''}`;

            header.addEventListener('click', () => {
                header.classList.toggle('expanded');
                body.classList.toggle('expanded');
            });

            card.appendChild(header);
            card.appendChild(body);
            container.appendChild(card);

            // Render form only for expanded card (first one), lazy-load others on expand
            if (i === 0) {
                await renderReviewForm(staged, body, `pending_${staged.staging_id}`);
            } else {
                let loaded = false;
                header.addEventListener('click', async () => {
                    if (!loaded && body.classList.contains('expanded')) {
                        loaded = true;
                        await renderReviewForm(staged, body, `pending_${staged.staging_id}`);
                    }
                });
            }
        }
    } catch (e) {
        container.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    }
}

async function refreshPendingCount() {
    try {
        const pending = await api('/receipts/staged');
        const count = currentStagingId
            ? pending.filter(s => s.staging_id !== currentStagingId).length
            : pending.length;
        const badge = document.getElementById('pending-badge');
        if (count > 0) {
            badge.textContent = count;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    } catch (e) {
        // Silently ignore
    }
}

document.getElementById('refresh-pending-btn').addEventListener('click', loadPending);

// ── Expenses Tab ──
function setupExpenseFilters() {
    const today = new Date();
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(today.getDate() - 30);

    document.getElementById('exp-start').value = isoDate(thirtyDaysAgo);
    document.getElementById('exp-end').value = isoDate(today);

    // Populate category dropdown
    populateCategoryDropdown('exp-category');

    document.getElementById('expense-filters').addEventListener('submit', async (e) => {
        e.preventDefault();
        await searchExpenses();
    });
}

async function populateCategoryDropdown(selectId) {
    try {
        const cats = await api('/categories');
        const select = document.getElementById(selectId);
        const current = select.value;
        select.innerHTML = '<option value="">All</option>';
        cats.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            if (c === current) opt.selected = true;
            select.appendChild(opt);
        });
    } catch (e) {
        // Keep default
    }
}

async function searchExpenses() {
    const startDate = document.getElementById('exp-start').value;
    const endDate = document.getElementById('exp-end').value;
    const category = document.getElementById('exp-category').value;
    const merchant = document.getElementById('exp-merchant').value;

    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (category) params.set('category', category);
    if (merchant) params.set('merchant', merchant);

    const resultsDiv = document.getElementById('expenses-results');
    try {
        const receipts = await api(`/expenses?${params}`);
        if (!receipts.length) {
            resultsDiv.innerHTML = '<div class="alert alert-info">No receipts found.</div>';
            return;
        }

        resultsDiv.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Date</th><th>Merchant</th><th>Category</th>
                        <th>Tax</th><th>Total</th><th>Payment</th><th></th>
                    </tr>
                </thead>
                <tbody>
                    ${receipts.map(r => `
                        <tr>
                            <td>${formatDate(r.date)}</td>
                            <td>${escapeHtml(r.merchant_name)}</td>
                            <td>${r.category}</td>
                            <td>${formatCurrency(r.tax)}</td>
                            <td>${formatCurrency(r.total)}</td>
                            <td>${r.payment_method || '—'}</td>
                            <td><button class="btn-link" onclick="showReceiptDetail(${r.id})">View</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {
        resultsDiv.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    }
}

async function showReceiptDetail(receiptId) {
    try {
        const r = await api(`/expenses/${receiptId}`);
        const html = `
            <div class="detail-layout">
                <div class="detail-image">
                    ${r.image_url
                        ? `<img src="${r.image_url}" alt="Receipt" onerror="this.outerHTML='<div class=\\'no-image\\'>Image not available</div>'">`
                        : '<div class="no-image">Image not available</div>'}
                </div>
                <div class="detail-fields">
                    <p><strong>Merchant:</strong> ${escapeHtml(r.merchant_name)}</p>
                    <p><strong>Address:</strong> ${r.merchant_address || '—'}</p>
                    <p><strong>Date:</strong> ${formatDate(r.date)}</p>
                    <p><strong>Category:</strong> ${r.category}</p>
                    <p><strong>Payment:</strong> ${r.payment_method || '—'}</p>
                    <p><strong>Currency:</strong> ${r.currency}</p>
                    ${renderItemsTable(r.items)}
                    <div class="metrics-row" style="grid-template-columns:repeat(4,1fr);">
                        <div class="metric-card"><div class="value">${formatCurrency(r.subtotal)}</div><div class="label">Subtotal</div></div>
                        <div class="metric-card"><div class="value">${formatCurrency(r.tax)}</div><div class="label">Tax</div></div>
                        <div class="metric-card"><div class="value">${formatCurrency(r.tip)}</div><div class="label">Tip</div></div>
                        <div class="metric-card"><div class="value">${formatCurrency(r.total)}</div><div class="label">Total</div></div>
                    </div>
                    <div class="divider"></div>
                    <button class="btn btn-danger btn-sm" onclick="confirmDeleteReceipt(${r.id})">Delete Receipt</button>
                    <span class="text-muted" style="margin-left:0.5rem;">Permanently deletes the receipt and its archived image</span>
                </div>
            </div>
        `;
        showModal(html);
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function confirmDeleteReceipt(receiptId) {
    showConfirmModal(
        'This will permanently delete the receipt record and its archived image.',
        async () => {
            try {
                await api(`/expenses/${receiptId}`, { method: 'DELETE' });
                closeModal();
                showToast('Receipt deleted');
                await searchExpenses();
            } catch (e) {
                showToast(e.message, 'error');
            }
        }
    );
}

// ── Summary Tab ──
function setupSummaryDates() {
    const today = new Date();
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(today.getDate() - 30);

    document.getElementById('sum-start').value = isoDate(thirtyDaysAgo);
    document.getElementById('sum-end').value = isoDate(today);

    document.getElementById('sum-start').addEventListener('change', loadSummary);
    document.getElementById('sum-end').addEventListener('change', loadSummary);
}

async function loadSummary() {
    const startDate = document.getElementById('sum-start').value;
    const endDate = document.getElementById('sum-end').value;

    try {
        const stats = await api(`/expenses/summary?start_date=${startDate}&end_date=${endDate}`);

        // Metrics
        document.getElementById('summary-metrics').innerHTML = `
            <div class="metric-card"><div class="value">${formatCurrency(stats.total_spent)}</div><div class="label">Total Spent</div></div>
            <div class="metric-card"><div class="value">${formatCurrency(stats.total_tax)}</div><div class="label">Total Tax</div></div>
            <div class="metric-card"><div class="value">${stats.receipt_count}</div><div class="label">Receipts</div></div>
        `;

        // Bar chart
        renderCategoryChart(stats.by_category);
    } catch (e) {
        document.getElementById('summary-metrics').innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    }
}

function renderCategoryChart(byCategory) {
    if (categoryChart) categoryChart.destroy();

    const labels = Object.keys(byCategory);
    const values = Object.values(byCategory);

    if (!labels.length) {
        document.getElementById('category-chart').style.display = 'none';
        return;
    }
    document.getElementById('category-chart').style.display = '';

    const ctx = document.getElementById('category-chart').getContext('2d');
    categoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Spending',
                data: values,
                backgroundColor: 'rgba(102, 126, 234, 0.7)',
                borderColor: '#667eea',
                borderWidth: 1,
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => formatCurrency(ctx.raw),
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: v => '$' + v.toFixed(0) },
                },
            },
        },
    });
}

// ── Modal System ──
function showModal(contentHtml) {
    document.getElementById('modal-content').innerHTML = contentHtml;
    document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal-content').innerHTML = '';
}

function showConfirmModal(message, onConfirm) {
    const html = `
        <div style="text-align:center;padding:1rem;">
            <div class="alert alert-warning">${escapeHtml(message)}</div>
            <div style="display:flex;gap:0.5rem;justify-content:center;margin-top:1rem;">
                <button class="btn btn-primary" id="confirm-yes">Confirm</button>
                <button class="btn" onclick="closeModal()">Cancel</button>
            </div>
        </div>
    `;
    showModal(html);
    document.getElementById('confirm-yes').addEventListener('click', async () => {
        closeModal();
        await onConfirm();
    });
}

// ── Spinner ──
function showSpinner() {
    document.getElementById('spinner-overlay').classList.remove('hidden');
}
function hideSpinner() {
    document.getElementById('spinner-overlay').classList.add('hidden');
}

// ── Toast Notifications ──
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:3000;min-width:250px;box-shadow:0 2px 8px rgba(0,0,0,0.15);transition:opacity 0.3s;';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showAlert(containerId, message, type) {
    const container = document.getElementById(containerId);
    container.innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`;
}

// ── Utilities ──
function formatDate(isoDate) {
    if (!isoDate) return '?';
    try {
        const parts = isoDate.split('-');
        if (parts.length === 3) return `${parts[1]}/${parts[2]}/${parts[0]}`;
    } catch (e) {}
    return isoDate;
}

function formatCurrency(amount) {
    return `$${(amount || 0).toFixed(2)}`;
}

function isoDate(d) {
    return d.toISOString().split('T')[0];
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
