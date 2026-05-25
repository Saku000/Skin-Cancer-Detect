const API = 'http://127.0.0.1:8000';

const uploadZone     = document.getElementById('uploadZone');
const fileInput      = document.getElementById('fileInput');
const emptyState     = document.getElementById('emptyState');
const filesState     = document.getElementById('filesState');
const previewGrid    = document.getElementById('previewGrid');
const addMoreBtn     = document.getElementById('addMoreBtn');
const clearBtn       = document.getElementById('clearBtn');
const analyseWrap    = document.getElementById('analyseWrap');
const analyseBtn     = document.getElementById('analyseBtn');
const resultsSection = document.getElementById('resultsSection');
const resultsContainer = document.getElementById('resultsContainer');

const CLASS_LABEL = {
  // Malignant
  MEL:       'Melanoma (MEL)',
  BCC:       'Basal Cell Carcinoma (BCC)',
  AKIEC:     'Actinic Keratosis / SCC (AKIEC)',
  // Benign — dermoscopic
  NV:        'Melanocytic Nevi (NV)',
  BKL:       'Benign Keratosis (BKL)',
  DF:        'Dermatofibroma (DF)',
  VASC:      'Vascular Lesion (VASC)',
  // Common skin conditions
  WART:      'Wart / Verruca',
  ECZEMA:    'Eczema / Dermatitis',
  PSORIASIS: 'Psoriasis',
  ACNE:      'Acne',
  SEBDERM:   'Seborrheic Dermatitis',
  ROSACEA:   'Rosacea',
  TINEA:     'Tinea / Fungal Infection',
  VITILIGO:  'Vitiligo',
  OTHER:     'Other Condition',
};

let selectedFiles = [];
let nRuns = 3;
let chatHistory = [];
let currentResults = null;
let isAnalysing = false;
let abortController = null;

/* ── Chat ── */
const chatMessages    = document.getElementById('chatMessages');
const chatInput       = document.getElementById('chatInput');
const chatSendBtn     = document.getElementById('chatSendBtn');
const chatClearBtn    = document.getElementById('chatClearBtn');

function getChatPlaceholder() { return document.getElementById('chatPlaceholder'); }

function appendMessage(role, content) {
  const ph = getChatPlaceholder();
  if (ph) ph.remove();
  const msg = document.createElement('div');
  msg.className = `msg ${role}`;
  msg.textContent = content;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendTyping() {
  const ph = getChatPlaceholder();
  if (ph) ph.remove();
  const msg = document.createElement('div');
  msg.className = 'msg assistant typing-indicator';
  msg.innerHTML = '<span></span><span></span><span></span>';
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

async function generateSummary(results) {
  const typing = appendTyping();
  try {
    const res = await fetch(`${API}/chat/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    typing.remove();
    if (data.reply) {
      appendMessage('assistant', data.reply);
    }
    // Not stored in chatHistory — history must start with a user message
  } catch (e) {
    typing.remove();
    console.error('[chat summary]', e);
  }
}

async function sendMessage(text) {
  if (!text.trim()) return;
  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });
  const typing = appendTyping();
  chatSendBtn.disabled = true;
  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(0, -1),
        results: currentResults,
      }),
    });
    const data = await res.json();
    typing.remove();
    appendMessage('assistant', data.reply);
    chatHistory.push({ role: 'assistant', content: data.reply });
  } catch {
    typing.remove();
    appendMessage('assistant', 'Sorry, something went wrong. Please try again.');
  } finally {
    chatSendBtn.disabled = false;
    chatInput.style.height = 'auto';
  }
}

chatSendBtn.addEventListener('click', () => {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  sendMessage(text);
});

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    chatSendBtn.click();
  }
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 110) + 'px';
});

chatClearBtn.addEventListener('click', () => {
  chatHistory = [];
  chatMessages.innerHTML = '';
  const ph = document.createElement('div');
  ph.className = 'chat-placeholder';
  ph.id = 'chatPlaceholder';
  ph.innerHTML = '<div class="chat-placeholder-icon">💬</div><p>Run an analysis to get<br>AI insights and recommendations</p>';
  chatMessages.appendChild(ph);
});

/* ── Settings ── */
const settingsBtn  = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const stepperMinus = document.getElementById('stepperMinus');
const stepperPlus  = document.getElementById('stepperPlus');
const stepperVal   = document.getElementById('stepperVal');
const applyBtn     = document.getElementById('applyBtn');

let pendingRuns = nRuns;
let settingsOpen = false;

function openSettings() {
  pendingRuns = nRuns;
  stepperVal.textContent = pendingRuns;
  settingsPanel.classList.add('open');
  settingsBtn.classList.add('open');
  settingsOpen = true;
}

function closeSettings() {
  settingsPanel.classList.remove('open');
  settingsBtn.classList.remove('open');
  settingsOpen = false;
}

function bumpVal() {
  stepperVal.classList.remove('bump');
  void stepperVal.offsetWidth;
  stepperVal.classList.add('bump');
  setTimeout(() => stepperVal.classList.remove('bump'), 120);
}

settingsBtn.addEventListener('click', e => {
  e.stopPropagation();
  settingsOpen ? closeSettings() : openSettings();
});

document.addEventListener('click', e => {
  if (settingsOpen && !settingsPanel.contains(e.target)) closeSettings();
});

stepperMinus.addEventListener('click', () => {
  if (pendingRuns > 1) { pendingRuns--; stepperVal.textContent = pendingRuns; bumpVal(); }
});
stepperPlus.addEventListener('click', () => {
  if (pendingRuns < 5) { pendingRuns++; stepperVal.textContent = pendingRuns; bumpVal(); }
});

applyBtn.addEventListener('click', () => {
  nRuns = pendingRuns;
  applyBtn.textContent = '✓ Applied';
  setTimeout(() => { applyBtn.textContent = 'Apply'; closeSettings(); }, 700);
});

/* ── Drag & Drop ── */
uploadZone.addEventListener('click', e => {
  if (e.target.closest('button, label')) return;
  if (!selectedFiles.length) fileInput.click();
});

document.getElementById('browseBtn').addEventListener('click', e => {
  e.stopPropagation();
  fileInput.click();
});

addMoreBtn.addEventListener('click', e => {
  e.stopPropagation();
  fileInput.click();
});

clearBtn.addEventListener('click', async e => {
  e.stopPropagation();
  if (isAnalysing) abortController?.abort();
  selectedFiles = [];
  renderPreviews();
  resultsSection.style.display = 'none';
  resultsContainer.innerHTML = '';
  document.getElementById('lightingWarning').style.display = 'none';
  await fetch(`${API}/clear`, { method: 'DELETE' });
});

uploadZone.addEventListener('dragover', e => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  addFiles([...e.dataTransfer.files]);
});
fileInput.addEventListener('change', () => addFiles([...fileInput.files]));

/* ── File Management ── */
function addFiles(files) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'];
  files.filter(f => allowed.includes(f.type)).forEach(f => {
    if (!selectedFiles.find(x => x.name === f.name && x.size === f.size)) {
      selectedFiles.push(f);
    }
  });
  renderPreviews();
}

function renderPreviews() {
  const hasFiles = selectedFiles.length > 0;

  emptyState.style.display  = hasFiles ? 'none'  : 'block';
  filesState.style.display  = hasFiles ? 'block' : 'none';
  uploadZone.classList.toggle('has-files', hasFiles);
  analyseWrap.classList.toggle('visible', hasFiles);

  previewGrid.innerHTML = '';
  selectedFiles.forEach(file => {
    const url   = URL.createObjectURL(file);
    const thumb = document.createElement('div');
    thumb.className = 'preview-thumb';
    thumb.innerHTML = `
      <img src="${url}" alt="${file.name}" />
      <div class="thumb-name">${file.name}</div>
    `;
    previewGrid.appendChild(thumb);
  });

  fileInput.value = '';
}


/* ── Analyse ── */
function resetAnalyseBtn() {
  isAnalysing = false;
  abortController = null;
  analyseBtn.disabled = false;
  analyseBtn.className = 'btn-analyse';
  analyseBtn.innerHTML = 'Analyse Images';
}

analyseBtn.addEventListener('click', async () => {
  // Cancel if already running
  if (isAnalysing) {
    abortController?.abort();
    return;
  }

  if (!selectedFiles.length) return;

  isAnalysing = true;
  abortController = new AbortController();
  const signal = abortController.signal;

  analyseBtn.className = 'btn-analyse btn-cancel';
  analyseBtn.innerHTML = '<span class="spinner"></span> Uploading... &nbsp;✕ Cancel';
  resultsSection.style.display = 'none';
  resultsContainer.innerHTML = '';

  try {
    // 1. Clear old uploads, then upload current files
    await fetch(`${API}/clear`, { method: 'DELETE', signal });
    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));
    const uploadRes = await fetch(`${API}/upload`, { method: 'POST', body: formData, signal });
    if (!uploadRes.ok) throw new Error(`Upload failed: ${uploadRes.statusText}`);

    // 2. Analyse
    analyseBtn.innerHTML = '<span class="spinner"></span> Analysing... &nbsp;✕ Cancel';
    const analyseRes = await fetch(`${API}/analyze?n_runs=${nRuns}`, { method: 'POST', signal });
    if (!analyseRes.ok) throw new Error(`Analysis failed: ${analyseRes.statusText}`);
    const data = await analyseRes.json();

    // 3. Render — match by filename, not index
    resultsSection.style.display = 'block';
    data.results.forEach((result, idx) => {
      const file = selectedFiles.find(f => f.name === result.filename);
      const card = result.error
        ? buildErrorCard(result)
        : buildResultCard(result, file);
      resultsContainer.appendChild(card);
      card.style.animationDelay = `${idx * 0.1}s`;
    });

    // Animate bars after render
    requestAnimationFrame(() => {
      document.querySelectorAll('.prob-fill[data-pct]').forEach(el => {
        el.style.width = el.dataset.pct + '%';
      });
    });

    // Lighting warning
    const poorLit = data.results.filter(r => !r.error && r.lighting_ok === false);
    const lwSection = document.getElementById('lightingWarning');
    const lwThumbs  = document.getElementById('lwThumbs');
    if (poorLit.length > 0) {
      lwThumbs.innerHTML = '';
      poorLit.forEach(r => {
        const file = selectedFiles.find(f => f.name === r.filename);
        const wrap = document.createElement('div');
        wrap.className = 'lw-thumb';
        const img = document.createElement('img');
        img.src = file ? URL.createObjectURL(file) : '';
        img.alt = r.filename;
        const label = document.createElement('span');
        label.textContent = r.filename;
        wrap.appendChild(img);
        wrap.appendChild(label);
        lwThumbs.appendChild(wrap);
      });
      lwSection.style.display = 'block';
    } else {
      lwSection.style.display = 'none';
    }

    // Chat: update context and auto-generate summary
    currentResults = data.results;
    generateSummary(data.results);

  } catch (err) {
    if (err.name === 'AbortError') {
      // User cancelled — silently reset, keep existing results visible
    } else {
      resultsContainer.innerHTML = `<div class="error-card">⚠ ${err.message}</div>`;
      resultsSection.style.display = 'block';
    }
  } finally {
    resetAnalyseBtn();
  }
});

/* ── Card Builders ── */
function buildResultCard(result, file) {
  const imgUrl     = file ? URL.createObjectURL(file) : '';
  const isHighRisk = result.is_high_risk;
  const pct        = result.cancer_total;

  const card = document.createElement('div');
  card.className = 'result-card';
  card.innerHTML = `
    <div class="card-inner">
      <div class="card-image">
        <img src="${imgUrl}" alt="${result.filename}" />
        <div class="img-label">${result.filename}</div>
      </div>
      <div class="card-analysis">

        <div class="risk-banner ${isHighRisk ? 'high' : 'low'}">
          <span class="risk-icon">${isHighRisk ? '⚠️' : '✅'}</span>
          <div class="risk-text">
            ${isHighRisk ? 'High Risk — Malignant features detected' : 'Low Risk — Likely benign'}
          </div>
          <div class="risk-pct">${pct}%</div>
        </div>

        <div>
          <div class="section-label">Malignant probabilities</div>
          ${Object.entries(result.cancer).map(([cls, p]) => probRow(cls, p, 'cancer')).join('')}
        </div>

        ${Object.keys(result.non_cancer).length ? `
        <div>
          <div class="divider"></div>
          <div class="section-label" style="margin-top:16px;">Other conditions &gt;20%</div>
          ${Object.entries(result.non_cancer).map(([cls, p]) => probRow(cls, p, 'benign')).join('')}
        </div>` : ''}

        <div>
          <div class="top-chip">Top prediction &nbsp;·&nbsp; <span>${result.top_prediction}</span></div>
        </div>

      </div>
    </div>
  `;
  return card;
}

function probRow(cls, pct, type) {
  const capped = Math.min(100, Math.round(pct));
  return `
    <div class="prob-row">
      <div class="prob-name">${CLASS_LABEL[cls] || cls}</div>
      <div class="prob-track">
        <div class="prob-fill ${type}" data-pct="${capped}"></div>
      </div>
      <div class="prob-pct ${type}">${pct.toFixed(1)}%</div>
    </div>`;
}

function buildErrorCard(result) {
  const card = document.createElement('div');
  card.className = 'error-card';
  card.textContent = `⚠ ${result.filename}: ${result.error}`;
  return card;
}
