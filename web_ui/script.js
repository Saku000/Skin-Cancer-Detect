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
  MEL:   'Melanoma (MEL)',
  NV:    'Melanocytic Nevi (NV)',
  BCC:   'Basal Cell Carcinoma (BCC)',
  AKIEC: 'Actinic Keratosis / SCC (AKIEC)',
  BKL:   'Benign Keratosis (BKL)',
  DF:    'Dermatofibroma (DF)',
  VASC:  'Vascular Lesion (VASC)',
};

let selectedFiles = [];

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
  selectedFiles = [];
  renderPreviews();
  resultsSection.style.display = 'none';
  resultsContainer.innerHTML = '';
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
analyseBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;

  analyseBtn.disabled = true;
  analyseBtn.innerHTML = '<span class="spinner"></span> Uploading...';
  resultsSection.style.display = 'none';
  resultsContainer.innerHTML = '';

  try {
    // 1. Clear old uploads, then upload current files
    await fetch(`${API}/clear`, { method: 'DELETE' });
    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));
    const uploadRes = await fetch(`${API}/upload`, { method: 'POST', body: formData });
    if (!uploadRes.ok) throw new Error(`Upload failed: ${uploadRes.statusText}`);

    // 2. Analyse
    analyseBtn.innerHTML = '<span class="spinner"></span> Analysing...';
    const analyseRes = await fetch(`${API}/analyze`, { method: 'POST' });
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

  } catch (err) {
    resultsContainer.innerHTML = `<div class="error-card">⚠ ${err.message}</div>`;
    resultsSection.style.display = 'block';
  } finally {
    analyseBtn.disabled = false;
    analyseBtn.innerHTML = 'Analyse Images';
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
