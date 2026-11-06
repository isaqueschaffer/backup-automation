const root = (typeof htmlNode !== 'undefined') ? htmlNode : document;

// ── 1. Motor de Extração Universal (Com ou Sem Transformações) ─────────────
const rows = context.data?.data || [];
const rawSeries = context.panelData?.series ?? context.data?.series ?? context.__data?.series ?? [];

const metrics = {};
const allFields = []; // Lista unificada de { name, value }

// Helper para ler valores de DataFrames do Grafana (suporta Arrays e Vectors)
const getVal = (field, i) => {
    const vals = field?.values;
    if (!vals) return null;
    if (typeof vals.get === 'function') return vals.get(i);
    if (Array.isArray(vals)) return vals[i];
    if (vals.buffer) return vals.buffer[i];
    return null;
};

// Passo A: Extrai o último valor e o histórico de TODAS as séries brutas
rawSeries.forEach(frame => {
    const valueFields = (frame.fields || []).filter(f => f.type !== 'time' && f.name !== 'Time');
    
    valueFields.forEach(valueField => {
        const len = valueField.values?.length ?? valueField.values?.buffer?.length ?? 0;
        if (len > 0) {
            const history = [];
            let lastVal = null;
            
            for (let j = 0; j < len; j++) {
                const v = getVal(valueField, j);
                if (v !== null && v !== undefined) {
                    if (typeof v === 'number' && !isNaN(v)) {
                        history.push(v);
                        lastVal = v;
                    } else if (typeof v === 'string' && v.trim() !== '') {
                        lastVal = v;
                    }
                }
            }
            if (lastVal === null) lastVal = getVal(valueField, len - 1);
            
            // Descobre o nome real da métrica no Grafana (suporta Merge e Outer Join)
            let metricName = valueField.config?.displayName || 
                             valueField.config?.displayNameFromDS || 
                             valueField.state?.displayName || 
                             frame.name || 
                             valueField.name || '';
                             
            // Se o Grafana nomear a coluna genericamente como "Value", tentamos ler as labels do Zabbix
            if ((metricName.toUpperCase() === 'VALUE' || metricName === '') && valueField.labels) {
                metricName = valueField.labels.item || valueField.labels.name || metricName;
            }
            
            metricName = metricName.replace(/ \{.*\}$/, '').trim(); // Limpa sufixos do Zabbix
            
            if (metricName && metricName.toUpperCase() !== 'VALUE') {
                metrics[metricName.toUpperCase()] = lastVal;
                allFields.push({ name: metricName, value: lastVal, history });
                
                // Se for "Host: Item", guarda só o "Item" também
                if (metricName.includes(': ')) {
                    const shortName = metricName.split(': ').pop().trim();
                    metrics[shortName.toUpperCase()] = lastVal;
                    allFields.push({ name: shortName, value: lastVal, history });
                }
            }
        }
    });
});

// Passo B: Extrai das linhas processadas (Trata transformações como Merge ou Reduce)
rows.forEach(row => {
    // Para Transformações Reduce
    if (row.Field) {
        const v = row['Last *'] ?? row['Last'] ?? row['Value'] ?? row['value'];
        if (v !== undefined && v !== null) {
            metrics[row.Field.trim().toUpperCase()] = v;
        }
    }
    
    // Para Transformações Merge (que criam colunas para cada métrica)
    Object.keys(row).forEach(key => {
        if (key !== 'Time' && key !== 'Time *' && key !== 'Field') {
            const val = row[key];
            // Se o valor não for nulo, salva/atualiza a métrica
            if (val !== null && val !== undefined && val !== '') {
                const cleanKey = key.trim().toUpperCase();
                metrics[cleanKey] = val;
                
                // Atualiza o histórico ou insere
                const existing = allFields.find(f => f.name.toUpperCase() === cleanKey);
                if (existing) {
                    existing.value = val;
                } else {
                    allFields.push({ name: key, value: val, history: [] });
                }
                
                // Se o Grafana mesclar com "Host: Métrica", guarda só a Métrica também!
                if (key.includes(': ')) {
                    const shortName = key.split(': ').pop().trim();
                    const cleanShort = shortName.toUpperCase();
                    metrics[cleanShort] = val;
                    
                    const exShort = allFields.find(f => f.name.toUpperCase() === cleanShort);
                    if (exShort) {
                        exShort.value = val;
                    } else {
                        allFields.push({ name: shortName, value: val, history: [] });
                    }
                }
            }
        }
    });
});

// Helper de busca final
const get = (fieldName, def = '-') => {
    const upperName = fieldName.toUpperCase();
    
    // 1. Busca nas linhas processadas
    const row = rows.find(r => r.Field && r.Field.trim().toUpperCase() === upperName);
    if (row) {
        const v = row['Last *'] ?? row['Last'] ?? row['Value'] ?? row['value'];
        if (v !== undefined && v !== null) return v;
    }
    
    // 2. Busca nas séries brutas
    if (metrics[upperName] !== undefined && metrics[upperName] !== null) {
        return metrics[upperName];
    }
    
    return def;
};

// ── Injeta texto em elemento por ID ────────────────────────────────────────
const set = (id, val) => {
    const el = root.querySelector('#' + id);
    if (el) el.innerText = val;
};

// ── KPI Cards ──────────────────────────────────────────────────────────────
set('kpi-total-onu',        get('TOTAL DE ONU'));
set('kpi-onus-online',      get('ONUs ONLINE'));
set('kpi-onus-offline',     get('ONUs OFFLINE'));
set('kpi-onus-sem-energia', get('ONUs SEM ENERGIA'));
set('kpi-onus-falha',       get('ONUs COM FALHA'));

// Busca o Uptime (procura qualquer métrica que contenha 'UPTIME' no nome)
const uptimeRow = allFields.find(r => r.name && r.name.toUpperCase().includes('UPTIME'));
let uptimeVal = uptimeRow ? uptimeRow.value : get('System uptime', '-');

// Se o Zabbix mandar o uptime em segundos puros, formata bonitinho
if (!isNaN(uptimeVal) && uptimeVal > 0) {
    const upSecs = parseFloat(uptimeVal);
    const d = Math.floor(upSecs / 86400);
    const h = Math.floor((upSecs % 86400) / 3600);
    const m = Math.floor((upSecs % 3600) / 60);
    uptimeVal = `${d}d ${h}h ${m}m`;
}
set('kpi-uptime', uptimeVal);

const tempVal = get('Temperatura da OLT');
const elTemp  = root.querySelector('#kpi-temp');
if (elTemp) {
    elTemp.innerText   = tempVal + '°C';
    elTemp.style.color = parseFloat(tempVal) > 48 ? '#fb7185' : '#34d399';
}

// ── Helper: formata bps em Kbps/Mbps/Gbps ────────────────────────────────
const fmtBps = (bps) => {
    const v = parseFloat(bps || 0);
    if (v >= 1e9) return (v / 1e9).toFixed(2) + ' Gbps';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + ' Mbps';
    if (v >= 1e3) return (v / 1e3).toFixed(2) + ' Kbps';
    return v.toFixed(0) + ' bps';
};

// ── Coleta dados de Hardware e Tráfego ─────────────────────────────────────
// Para OLTs com múltiplas placas (ex: Slot 1 zerado e Slot 2 com uso), pegamos o maior valor encontrado
const cpuRows = allFields.filter(r => r.name && r.name.toUpperCase().includes('CPU'));
let cpuVal = 0;
if (cpuRows.length > 0) {
    const cpuVals = cpuRows.map(r => parseFloat(r.value || 0)).filter(v => !isNaN(v));
    if (cpuVals.length > 0) cpuVal = Math.max(...cpuVals);
} else {
    cpuVal = parseFloat(get('cardCpuUtil [2]', 0));
}
const cpuW   = Math.min(cpuVal, 100);
const cpuColor = cpuVal > 80 ? '#fb7185' : cpuVal > 60 ? '#fbbf24' : '#38bdf8';

const memRows = allFields.filter(r => r.name && (
    r.name.toUpperCase().includes('MEM') || 
    r.name.toUpperCase().includes('MENUTIL') // Suporta o typo 'cardMenUtil' do template
));
let memVal = 0;
if (memRows.length > 0) {
    const memVals = memRows.map(r => parseFloat(r.value || 0)).filter(v => !isNaN(v));
    if (memVals.length > 0) memVal = Math.max(...memVals);
} else {
    memVal = parseFloat(get('cardMenUtil [2]', 0) || get('cardMemUtil [2]', 0) || get('mgrCardMemUtil', 0));
}
const memW   = Math.min(memVal, 100);
const memColor = memVal > 80 ? '#fb7185' : memVal > 60 ? '#fbbf24' : '#c084fc';

// Busca todos os campos de tráfego de entrada/saída (SFP/XFP) na lista unificada
const trafficRows = allFields.filter(r => r.name && (
    r.name.toUpperCase().includes('TRAFEGO DE ENTRADA') ||
    r.name.toUpperCase().includes('TRAFEGO DE SAIDA')
));

let trafficHTML = '';
const interfaces = {};
trafficRows.forEach(r => {
    const isIn  = r.name.toUpperCase().includes('ENTRADA');
    const iface = r.name.replace(/Trafego de (Entrada|Saida) na Interface /i, '').trim();
    if (!interfaces[iface]) interfaces[iface] = {};
    if (isIn) {
        interfaces[iface].in = r.value;
        interfaces[iface].inHist = r.history || [];
    } else {
        interfaces[iface].out = r.value;
        interfaces[iface].outHist = r.history || [];
    }
});

// Gerador de mini-gráficos SVG (Sparklines responsivos)
function createSparkline(dataArray, color) {
    if (!dataArray || dataArray.length < 2) return '<div style="width:100%;height:25px;border-bottom:1px dashed rgba(255,255,255,.1);"></div>';
    
    const max = Math.max(...dataArray);
    const min = 0;
    const range = max - min || 1;
    
    // ViewBox virtual dimensions (serão esticadas pelo CSS width:100%)
    const vW = 150;
    const vH = 25;
    
    const step = Math.ceil(dataArray.length / 40); 
    const sampled = dataArray.filter((_, i) => i % step === 0);
    if (sampled[sampled.length - 1] !== dataArray[dataArray.length - 1]) {
        sampled.push(dataArray[dataArray.length - 1]);
    }
    
    const sStepX = vW / (sampled.length - 1 || 1);
    
    const points = sampled.map((v, i) => {
        const x = i * sStepX;
        const y = vH - ((v - min) / range) * vH;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    
    const polyPoints = `${points} ${vW},${vH} 0,${vH}`;
    const lastY = vH - ((sampled[sampled.length - 1] - min) / range) * vH;

    const gradId = `grad-${Math.random().toString(36).substr(2,5)}`;
    const stop1 = color === '#34d399' ? 'rgba(52, 211, 153, 0.4)' : 'rgba(56, 189, 248, 0.4)';
    const stop2 = color === '#34d399' ? 'rgba(52, 211, 153, 0.0)' : 'rgba(56, 189, 248, 0.0)';

    return `
        <svg viewBox="0 -5 ${vW} ${vH+10}" preserveAspectRatio="none" style="width:100%; height:100%; overflow:visible;">
            <defs>
                <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${stop1}"/>
                    <stop offset="100%" stop-color="${stop2}"/>
                </linearGradient>
            </defs>
            <polygon points="${polyPoints}" fill="url(#${gradId})" stroke="none"/>
            <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 2px 4px ${color}80);"/>
            <circle cx="${vW}" cy="${lastY}" r="3" fill="#0f172a" stroke="${color}" stroke-width="2" style="filter:drop-shadow(0 0 5px ${color});" />
        </svg>
    `;
}

Object.entries(interfaces).forEach(([iface, vals]) => {
    const inVal  = fmtBps(vals.in  || 0);
    const outVal = fmtBps(vals.out || 0);
    
    const inMax = vals.inHist && vals.inHist.length > 0 ? Math.max(...vals.inHist) : (vals.in || 0);
    const inAvg = vals.inHist && vals.inHist.length > 0 ? vals.inHist.reduce((a,b)=>a+b,0)/vals.inHist.length : (vals.in || 0);
    
    const outMax = vals.outHist && vals.outHist.length > 0 ? Math.max(...vals.outHist) : (vals.out || 0);
    const outAvg = vals.outHist && vals.outHist.length > 0 ? vals.outHist.reduce((a,b)=>a+b,0)/vals.outHist.length : (vals.out || 0);
    
    const inSpark = createSparkline(vals.inHist, '#34d399');
    const outSpark = createSparkline(vals.outHist, '#38bdf8');

    trafficHTML += `
        <div style="background:rgba(30,41,59,0.4); border:1px solid rgba(255,255,255,.05); border-radius:10px; padding:0.8rem; margin-bottom:0.7rem; box-shadow:0 3px 10px rgba(0,0,0,.15);">
            <div style="display:flex; align-items:center; gap:6px; margin-bottom:0.6rem;">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round"><path d="M4 11V9a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2M4 15v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M10 11v4M14 11v4"/></svg>
                <div style="font-weight:700; font-size:0.9rem; color:#f8fafc; letter-spacing:0.3px;">${iface}</div>
            </div>
            
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.7rem;">
                <!-- IN Column -->
                <div style="background:rgba(0,0,0,.2); border-radius:6px; padding:0.6rem; border:1px solid rgba(52,211,153,.1);">
                    <div style="display:flex; align-items:center; gap:5px; margin-bottom:.4rem;">
                        <div style="width:18px;height:18px;border-radius:4px;background:rgba(52,211,153,.15);display:flex;align-items:center;justify-content:center;">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="3" stroke-linecap="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
                        </div>
                        <span style="font-size:.65rem; color:#94a3b8; font-weight:700; text-transform:uppercase; letter-spacing:0.5px;">RX (IN)</span>
                    </div>
                    <div style="font-size:0.95rem; font-weight:800; color:#f8fafc; margin-bottom:.1rem; font-variant-numeric: tabular-nums;">${inVal}</div>
                    <div style="font-size:.6rem; color:#64748b; margin-bottom:.5rem; display:flex; justify-content:space-between;">
                        <span>Méd: ${fmtBps(inAvg)}</span>
                        <span>Máx: ${fmtBps(inMax)}</span>
                    </div>
                    <div style="width:100%; height:25px;">${inSpark}</div>
                </div>
                
                <!-- OUT Column -->
                <div style="background:rgba(0,0,0,.2); border-radius:6px; padding:0.6rem; border:1px solid rgba(56,189,248,.1);">
                    <div style="display:flex; align-items:center; gap:5px; margin-bottom:.4rem;">
                        <div style="width:18px;height:18px;border-radius:4px;background:rgba(56,189,248,.15);display:flex;align-items:center;justify-content:center;">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="3" stroke-linecap="round"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>
                        </div>
                        <span style="font-size:.65rem; color:#94a3b8; font-weight:700; text-transform:uppercase; letter-spacing:0.5px;">TX (OUT)</span>
                    </div>
                    <div style="font-size:0.95rem; font-weight:800; color:#f8fafc; margin-bottom:.1rem; font-variant-numeric: tabular-nums;">${outVal}</div>
                    <div style="font-size:.6rem; color:#64748b; margin-bottom:.5rem; display:flex; justify-content:space-between;">
                        <span>Méd: ${fmtBps(outAvg)}</span>
                        <span>Máx: ${fmtBps(outMax)}</span>
                    </div>
                    <div style="width:100%; height:25px;">${outSpark}</div>
                </div>
            </div>
        </div>`;
});

// ── Monta as linhas da tabela PON TX ───────────────────────────────────────
const ponRowsList = allFields
    .filter(r => r.name && r.name.toUpperCase().includes('POTENCIA'))
    .filter(r => r.name.toUpperCase() !== 'POTENCIA DE SAIDA DA PORTA') // Remove o item duplicado genérico
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));

// Filtra duplicatas (caso a série bruta e o Reduce tragam os mesmos dados)
const uniquePonRows = [];
const ponSet = new Set();
ponRowsList.forEach(r => {
    const portName = r.name.split(':')[0];
    if (!ponSet.has(portName)) {
        ponSet.add(portName);
        uniquePonRows.push(r);
    }
});

let ponRowsHTML = '';
uniquePonRows.forEach(r => {
    const portName = r.name.split(':')[0];
    const tx = parseFloat(r.value || 0);
    const color = (tx <= 0 || tx > 7) ? '#fb7185' : (tx < 2 ? '#fbbf24' : '#34d399');
    ponRowsHTML += `
        <div style="display:flex;justify-content:space-between;padding:.45rem 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.9rem;">
            <span style="font-weight:600;">${portName}</span>
            <span>TX: <strong style="color:${color};">${tx.toFixed(2)} dBm</strong></span>
        </div>`;
});

// ── Parse do Inventário Geral de ONUs ─────────────────────────────────────
let onuList = [];

function processOnuData(invData) {
    return invData.sort((a, b) => {
        const sigA = parseFloat(a['{#SIGNAL}']);
        const sigB = parseFloat(b['{#SIGNAL}']);
        
        // Trata 0, nulo ou inválido como Offline
        const isOffA = isNaN(sigA) || sigA === 0;
        const isOffB = isNaN(sigB) || sigB === 0;
        
        // Se um é offline e outro não, joga o offline para o final da lista
        if (isOffA && !isOffB) return 1;
        if (!isOffA && isOffB) return -1;
        if (isOffA && isOffB) return 0;
        
        // Ordena do pior sinal (mais negativo, ex: -30) para o melhor (ex: -15)
        return sigA - sigB;
    });
}

try {
    const invRaw = get('Inventário Geral ONUs', null) || get('INVENTÁRIO GERAL ONUS', null);
    if (invRaw && typeof invRaw === 'string' && invRaw.length > 10) {
        const invJson = JSON.parse(invRaw);
        onuList = processOnuData(invJson.data || invJson);
    }
} catch(e) {}

// Fallback Bruto: procura o JSON em TODAS as strings de TODAS as queries
if (onuList.length === 0) {
    try {
        outer: for (const frame of rawSeries) {
            for (const field of (frame.fields || [])) {
                const len = field.values?.length ?? field.values?.buffer?.length ?? 0;
                for (let i = 0; i < len; i++) {
                    const v = getVal(field, i);
                    if (v && typeof v === 'string' && v.includes('{#SIGNAL}')) {
                        const invJson = JSON.parse(v);
                        onuList = processOnuData(invJson.data || invJson);
                        if (onuList.length > 0) break outer;
                    }
                }
            }
        }
    } catch(e) {}
}

// ── Paginação da tabela de ONUs ───────────────────────────────────────────
const PAGE_SIZE = 14;
let currentPage = 0;

function getSignalBadge(signalStr) {
    const v = parseFloat(signalStr);
    if (isNaN(v) || v === 0) return { cls: 'badge-warning', label: 'Offline', color: '#64748b' };
    if (v < -28)  return { cls: 'badge-critical', label: 'Crítico',  color: '#fb7185' };
    if (v < -25)  return { cls: 'badge-warning',  label: 'Aviso',    color: '#fbbf24' };
    return              { cls: 'badge-good',    label: 'Normal',   color: '#34d399' };
}

function renderOnuPage(tbodyEl, paginationEl, page) {
    const start  = page * PAGE_SIZE;
    const slice  = onuList.slice(start, start + PAGE_SIZE);
    const total  = Math.ceil(onuList.length / PAGE_SIZE);

    tbodyEl.innerHTML = '';
    slice.forEach(o => {
        const sig   = o['{#SIGNAL}'] || '-';
        const badge = getSignalBadge(sig);
        const pon   = `PON ${o['{#SLOT}']}/${o['{#PON}']}`;
        const tr    = document.createElement('tr');
        tr.innerHTML = `
            <td>${o['{#ONUNAME}'] || '-'}</td>
            <td>${pon}</td>
            <td style="font-size:.8rem;color:#94a3b8;">${o['{#IFSERIAL}'] || '-'}</td>
            <td style="color:${badge.color};font-weight:700;">${(badge.label === 'Offline') ? '-' : sig}</td>
            <td><span class="badge ${badge.cls}">${badge.label}</span></td>`;
        tbodyEl.appendChild(tr);
    });

    // Paginação
    paginationEl.innerHTML = '';
    if (total > 1) {
        const prevBtn = document.createElement('button');
        prevBtn.className = 'page-btn';
        prevBtn.innerText = '← Ant.';
        prevBtn.disabled  = page === 0;
        prevBtn.onclick   = () => { currentPage--; renderOnuPage(tbodyEl, paginationEl, currentPage); };
        paginationEl.appendChild(prevBtn);

        const info = document.createElement('span');
        info.style = 'color:#94a3b8;font-size:.82rem;padding:0 .5rem;';
        info.innerText = `${page + 1} / ${total}`;
        paginationEl.appendChild(info);

        const nextBtn = document.createElement('button');
        nextBtn.className = 'page-btn';
        nextBtn.innerText = 'Próx. →';
        nextBtn.disabled  = page >= total - 1;
        nextBtn.onclick   = () => { currentPage++; renderOnuPage(tbodyEl, paginationEl, currentPage); };
        paginationEl.appendChild(nextBtn);
    }
}

// ── Badge de sinal para o cabeçalho ────────────────────────────────────────
const badgeCount  = onuList.filter(o => parseFloat(o['{#SIGNAL}']) < -28 && parseFloat(o['{#SIGNAL}']) !== 0).length;
const headerBadge = badgeCount > 0
    ? `<span class="badge badge-critical">${badgeCount} Crítico${badgeCount > 1 ? 's' : ''}</span>`
    : `<span class="badge badge-good">Sinal OK</span>`;

// ── Constrói o painel inferior via JS ─────────────────────────────────────
const container = root.querySelector('#main-grid-container');
if (container) {
    container.innerHTML = `
        <div class="main-grid">
            <div class="panel">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">
                    <h2 style="margin:0;font-size:1rem;color:#f8fafc;">Monitoramento Óptico</h2>
                    ${onuList.length > 0 ? headerBadge : '<span class="badge badge-warning">Aguardando Coleta RX</span>'}
                </div>
                ${onuList.length === 0 ? `<p class="muted-text">Aguardando Inventário... Para corrigir, <b>exclua a transformação "Reduce"</b> na aba Transformations do Grafana.</p>` : ''}
                <table>
                    <thead>
                        <tr>
                            <th>Cliente (UNM2000)</th>
                            <th>Porta PON</th>
                            <th>Serial ONU</th>
                            <th>Sinal RX</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="onu-tbody"></tbody>
                </table>
                <div id="onu-pagination" style="display:flex;justify-content:center;align-items:center;gap:.5rem;margin-top:1rem;"></div>
            </div>

            <div class="panel">
                <h2 style="margin-bottom:1rem;font-size:1rem;color:#f8fafc;">Portas PON — TX</h2>
                <div>${ponRowsHTML || '<p class="muted-text">Sem dados de TX disponíveis.</p>'}</div>

                <div style="margin-top:1.5rem;">
                    <p style="color:#94a3b8;font-size:.82rem;margin-bottom:.8rem;text-transform:uppercase;letter-spacing:.5px;">Recursos de Hardware</p>
                    <div class="hw-item">
                        <div class="hw-header">
                            <span>CPU</span>
                            <span style="color:${cpuColor};font-weight:700;">${cpuVal}%</span>
                        </div>
                        <div class="progress-bg">
                            <div class="progress-fill" style="width:${cpuW}%;background:${cpuColor};"></div>
                        </div>
                    </div>
                    <div class="hw-item" style="margin-bottom: 1.5rem;">
                        <div class="hw-header">
                            <span>Memória</span>
                            <span style="color:${memColor};font-weight:700;">${memVal}%</span>
                        </div>
                        <div class="progress-bg">
                            <div class="progress-fill" style="width:${memW}%;background:${memColor};"></div>
                        </div>
                    </div>
                    <p style="color:#94a3b8;font-size:.82rem;margin:1rem 0 .6rem;text-transform:uppercase;letter-spacing:.5px;">Tráfego SFP / XFP</p>
                    ${trafficHTML || '<p class="muted-text">Sem dados de tráfego.</p>'}
                </div>
            </div>
        </div>`;

    // Renderiza a primeira página da tabela de ONUs após montar o HTML
    if (onuList.length > 0) {
        const tbody      = container.querySelector('#onu-tbody');
        const pagination = container.querySelector('#onu-pagination');
        if (tbody && pagination) renderOnuPage(tbody, pagination, 0);
    }
}

// ── Limpador da Barra Inferior (Frame Selector do Grafana) ──────────────────
// Este script caça a barra de paginação do plugin (TOTAL DE ONU) e a oculta via DOM
setTimeout(() => {
    try {
        const panel = htmlNode ? htmlNode.getRootNode() : document;
        const pluginTabs = panel.querySelectorAll('.MuiTabs-root, [role="tablist"], [class*="TabGroup"], [class*="dynamic-text"]');
        pluginTabs.forEach(tab => {
            // Só esconde se o texto for parecido com nossas métricas (ex: TOTAL DE ONU)
            if (tab.innerText && (tab.innerText.includes('TOTAL') || tab.innerText.includes('ONLINE'))) {
                tab.style.display = 'none';
            }
        });
        
        // Em versões antigas do Volkov Labs, o seletor fica assim:
        if (root && root.parentNode) {
            const extraSelect = root.parentNode.querySelector('select');
            if (extraSelect && extraSelect.innerHTML.includes('TOTAL')) {
                extraSelect.style.display = 'none';
            }
        }
    } catch (e) {
        console.log(e);
    }
}, 500);
