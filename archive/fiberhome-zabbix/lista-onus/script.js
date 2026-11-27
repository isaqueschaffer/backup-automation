// ─── Padrão idêntico ao Lista de Ramais ───────────────────────────────────────
let currentData = typeof context !== 'undefined' && context.data ? context.data : data;
let domRoot = typeof context !== 'undefined' && context.panel ? context.panel.elements.root : (typeof htmlNode !== 'undefined' ? htmlNode : document);

// ─── Referências ao DOM ────────────────────────────────────────────────────────
const summaryBar   = domRoot.querySelector('#onu-summary-bar')   || document.getElementById('onu-summary-bar');
const onuGrid      = domRoot.querySelector('#onu-grid')          || document.getElementById('onu-grid');
const pagControls  = domRoot.querySelector('#onu-pagination-controls') || document.getElementById('onu-pagination-controls');
const searchInput  = domRoot.querySelector('#onu-search-input')  || document.getElementById('onu-search-input');

if (!onuGrid) return;

// ─── Extrai a String JSON de qualquer estrutura que o Grafana entregar ─────────
let rawJsonString = null;

function deepSearch(obj) {
    if (typeof obj === 'string' && obj.includes('{#SNMPINDEX}')) {
        rawJsonString = obj;
        return;
    }
    if (Array.isArray(obj)) {
        for (let i of obj) { deepSearch(i); if (rawJsonString) return; }
    } else if (obj !== null && typeof obj === 'object') {
        for (let key in obj) { deepSearch(obj[key]); if (rawJsonString) return; }
    }
}

deepSearch(currentData);

// ─── Parse do JSON ─────────────────────────────────────────────────────────────
let allOnus = [];

if (rawJsonString) {
    try {
        const parsed = JSON.parse(rawJsonString);
        if (parsed && parsed.data) {
            allOnus = parsed.data.map(item => {
                const sigStr = item['{#SIGNAL}'] || '0.00 dBm';
                const sigValue = parseFloat(sigStr);
                const status = item['{#STATUS}'] || 'Offline';

                let sigClass = 'signal-good';
                if (status === 'Offline' || sigValue === 0 || isNaN(sigValue)) {
                    sigClass = 'signal-off';
                } else if (sigValue <= -27) {
                    sigClass = 'signal-critical';
                } else if (sigValue <= -25) {
                    sigClass = 'signal-warning';
                }

                return {
                    nome:       item['{#ONUNAME}']  || 'Desconhecido',
                    serial:     item['{#IFSERIAL}'] || '-',
                    slot:       item['{#SLOT}']     || '-',
                    pon:        item['{#PON}']      || '-',
                    onu:        item['{#ONU}']      || '-',
                    status:     status,
                    signal:     sigStr,
                    sigClass:   sigClass
                };
            });
        }
    } catch (e) { }
}

if (allOnus.length === 0) {
    onuGrid.innerHTML = '<div style="text-align:center;color:#888;padding:20px;width:100%;">Nenhuma ONU encontrada.</div>';
    return;
}

// ─── KPIs do Summary Bar ───────────────────────────────────────────────────────
if (summaryBar) {
    const total    = allOnus.length;
    const online   = allOnus.filter(o => o.status === 'Online').length;
    const offline  = allOnus.filter(o => o.status === 'Offline').length;
    const critical = allOnus.filter(o => o.sigClass === 'signal-critical').length;
    const warning  = allOnus.filter(o => o.sigClass === 'signal-warning').length;

    summaryBar.innerHTML = `
        <div class="kpi-card kpi-total">
            <span class="kpi-value">${total}</span>
            <span class="kpi-label">Total</span>
        </div>
        <div class="kpi-card kpi-online">
            <span class="kpi-value">${online}</span>
            <span class="kpi-label">Online</span>
        </div>
        <div class="kpi-card kpi-offline">
            <span class="kpi-value">${offline}</span>
            <span class="kpi-label">Offline</span>
        </div>
        <div class="kpi-card kpi-warning">
            <span class="kpi-value">${warning}</span>
            <span class="kpi-label">Sinal Fraco</span>
        </div>
        <div class="kpi-card kpi-critical">
            <span class="kpi-value">${critical}</span>
            <span class="kpi-label">Sinal Crítico</span>
        </div>
    `;
}

// ─── Paginação e Busca ─────────────────────────────────────────────────────────
const pageSize = 120; // Multiplo de 2,3,4,5,6,8,10,12 (perfeito para preencher grids)
let currentPage = 1;
let filteredOnus = [...allOnus];

function renderGrid(page) {
    onuGrid.innerHTML = '';
    const start = (page - 1) * pageSize;
    const end   = start + pageSize;
    const items = filteredOnus.slice(start, end);

    if (items.length === 0) {
        onuGrid.innerHTML = '<div style="text-align:center;color:#888;padding:20px;width:100%;">Nenhum resultado encontrado.</div>';
        return;
    }

    items.forEach(onu => {
        const card = document.createElement('div');
        card.className = `onu-card ${onu.status === 'Offline' ? 'is-offline' : ''}`;
        
        card.innerHTML = `
            <div class="onu-card-info">
                <span class="onu-name" title="${onu.nome}">${onu.nome}</span>
                <span class="onu-serial">${onu.serial}</span>
                <span class="onu-port">PON ${onu.pon} &bull; ONU ${onu.onu}</span>
            </div>
            <div class="onu-card-status">
                <span class="status-badge status-${onu.status.toLowerCase()}">${onu.status}</span>
                <span class="status-badge ${onu.sigClass}">${onu.signal}</span>
            </div>
        `;
        onuGrid.appendChild(card);
    });

    renderPagination();
}

function renderPagination() {
    if (!pagControls) return;
    const totalPages = Math.ceil(filteredOnus.length / pageSize);
    if (totalPages <= 1) { pagControls.innerHTML = ''; return; }

    let html = `<button class="page-btn" id="btn-onu-prev" ${currentPage === 1 ? 'disabled' : ''}>&laquo;</button>`;
    for (let i = 1; i <= totalPages; i++) {
        html += `<button class="page-btn num-btn ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    html += `<button class="page-btn" id="btn-onu-next" ${currentPage === totalPages ? 'disabled' : ''}>&raquo;</button>`;
    pagControls.innerHTML = html;

    const btnPrev = domRoot.querySelector('#btn-onu-prev');
    const btnNext = domRoot.querySelector('#btn-onu-next');

    if (btnPrev) btnPrev.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderGrid(currentPage); } });
    if (btnNext) btnNext.addEventListener('click', () => { const tp = Math.ceil(filteredOnus.length / pageSize); if (currentPage < tp) { currentPage++; renderGrid(currentPage); } });

    domRoot.querySelectorAll('.num-btn').forEach(btn => {
        btn.addEventListener('click', e => {
            const pg = parseInt(e.target.getAttribute('data-page'));
            if (pg !== currentPage) { currentPage = pg; renderGrid(currentPage); }
        });
    });
}

// ─── Busca em tempo real ───────────────────────────────────────────────────────
if (searchInput) {
    searchInput.addEventListener('input', () => {
        const term = searchInput.value.toLowerCase().trim();
        filteredOnus = term
            ? allOnus.filter(o =>
                o.nome.toLowerCase().includes(term) ||
                o.serial.toLowerCase().includes(term) ||
                `${o.slot}/${o.pon}/${o.onu}`.includes(term)
              )
            : [...allOnus];
        currentPage = 1;
        renderGrid(currentPage);
    });
}

// ─── Inicia ────────────────────────────────────────────────────────────────────
renderGrid(1);
