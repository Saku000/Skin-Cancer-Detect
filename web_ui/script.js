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
let lastUserLocation = null;  // persists across follow-up turns
let lastFacilities = null;            // for map reopen button
let lastUserLocationForMap = null;

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
  return msg;
}

/* ── Facility Map Panel ── */
let leafletMap = null;
let userMarker = null;
let userCoord  = null;   // persists so "My Location" button always works

const appLayout = document.getElementById('appLayout');
const pageRoot  = document.getElementById('pageRoot');
const mapPanel  = document.getElementById('mapPanel');

async function _geocode(query, countryCode = 'us') {
  const cc = countryCode ? `&countrycodes=${countryCode}` : '';
  const r = await fetch(
    `https://nominatim.openstreetmap.org/search?format=json&limit=1${cc}&q=${encodeURIComponent(query)}`
  );
  if (!r.ok) { console.warn('[map] geocode HTTP', r.status, 'for:', query); return null; }
  const d = await r.json();
  if (d[0]) return { lat: parseFloat(d[0].lat), lon: parseFloat(d[0].lon) };
  return null;
}

async function _geocodeFacility(f) {
  const addr = (f.address || '').trim();
  // Parenthetical placeholders like "(Address not specified…)" have no real street data — skip to name
  const hasRealAddress = addr && !addr.startsWith('(');

  if (hasRealAddress) {
    // Attempt 1: full address as-is
    const pos1 = await _geocode(addr);
    if (pos1) return pos1;
    await _delay(1100);

    // Attempt 2: strip floor/suite/unit qualifier then retry
    const cleaned = addr.replace(/,?\s*(?:\d+(?:st|nd|rd|th)\s+floor|floor\s+\d+|suite\s+[\w#-]+|apt\.?\s*[\w#]+|unit\s+[\w#]+)/gi, '').trim();
    if (cleaned && cleaned !== addr) {
      const pos2 = await _geocode(cleaned);
      if (pos2) return pos2;
      await _delay(1100);
    }

    // Attempt 3: name + last two comma-parts (city, state/zip)
    const parts = addr.split(',');
    if (parts.length >= 2) {
      const cityState = parts.slice(-2).join(',').trim();
      const pos3 = await _geocode(`${f.name || ''} ${cityState}`.trim());
      if (pos3) return pos3;
      await _delay(1100);
    }
  }

  // Final: facility name alone (works even when address is fake/missing)
  if (f.name) {
    const pos = await _geocode(f.name);
    if (pos) return pos;
  }
  return null;
}

function _delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function _makeCircle(color) {
  return { radius: 9, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.9 };
}

function _haversineMi(lat1, lon1, lat2, lon2) {
  const R = 3958.8; // Earth radius in miles
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function _fmtDist(mi) {
  return mi < 0.1 ? `${Math.round(mi * 5280)} ft` : `${mi.toFixed(1)} mi`;
}

function _setUserMarker(pos) {
  userCoord = pos;
  if (userMarker) userMarker.remove();
  userMarker = L.circleMarker([pos.lat, pos.lon], _makeCircle('#00c4d2'))
    .addTo(leafletMap)
    .bindPopup('Your location');
  document.getElementById('mapLocateBtn').disabled = false;
}

async function openMapPanel(facilities, userLocation) {
  appLayout.classList.add('map-open');

  // Store for manual reopen via toggle button
  lastFacilities = facilities;
  lastUserLocationForMap = userLocation;
  const mapToggleBtn = document.getElementById('mapToggleBtn');
  mapToggleBtn.disabled = false;
  mapToggleBtn.classList.add('active');

  // Reset state
  const mapFull = document.getElementById('mapFull');
  mapFull.innerHTML = '';
  userMarker = null;
  userCoord  = null;
  document.getElementById('mapLocateBtn').disabled = true;
  if (leafletMap) { leafletMap.remove(); leafletMap = null; }

  // Init Leaflet
  leafletMap = L.map('mapFull', { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 18,
  }).addTo(leafletMap);
  leafletMap.setView([37.5, -119.0], 9);

  // Wait for panel to render before Leaflet measures it
  await _delay(80);
  leafletMap.invalidateSize();

  // 1. Geocode user location — either a zip ("92617") or full address ("73000 Verano Rd, Irvine, CA")
  if (userLocation) {
    const isZip  = /^\d{5}$/.test(userLocation.trim());
    const query  = isZip ? `${userLocation.trim()}, USA` : userLocation;
    const pos    = await _geocode(query);
    if (pos) {
      _setUserMarker(pos);
      leafletMap.setView([pos.lat, pos.lon], 13);
    }
    await _delay(1100);
  }

  // 2. Geocode each facility with fallback strategies + rate-limit spacing
  const bounds = userCoord ? [[userCoord.lat, userCoord.lon]] : [];

  for (const f of facilities) {
    const pos = await _geocodeFacility(f);
    if (pos) {
      bounds.push([pos.lat, pos.lon]);
      const mapsQuery = encodeURIComponent([f.name, f.address].filter(Boolean).join(', '));
      const navUrl    = `https://www.google.com/maps/dir/?api=1&destination=${mapsQuery}&travelmode=driving`;
      const distLine  = userCoord
        ? `<br><span style="font-size:11px;color:#4285f4;font-weight:600">📍 ${_fmtDist(_haversineMi(userCoord.lat, userCoord.lon, pos.lat, pos.lon))} away</span>`
        : '';
      const popup = `
        <div style="font-family:sans-serif;min-width:170px;line-height:1.5">
          <b style="font-size:13px">${f.name}</b><br>
          <span style="font-size:11px;color:#555">${f.address || ''}</span>
          ${f.phone ? `<br><span style="font-size:11px;color:#555">${f.phone}</span>` : ''}
          ${distLine}
          <br>
          <a href="${navUrl}" target="_blank" rel="noopener"
             style="display:inline-block;margin-top:7px;padding:5px 11px;
                    background:#4285f4;color:#fff;border-radius:4px;
                    text-decoration:none;font-size:11px;font-weight:600">
            🗺 Navigate in Google Maps
          </a>
        </div>`;
      L.circleMarker([pos.lat, pos.lon], _makeCircle('#ff4d6d'))
        .addTo(leafletMap)
        .bindPopup(popup, { maxWidth: 220 });
      if (!userCoord && bounds.length === 1) {
        leafletMap.setView([pos.lat, pos.lon], 13);
      }
    }
    await _delay(1100);
  }

  if (bounds.length > 1) leafletMap.fitBounds(bounds, { padding: [40, 40] });
  leafletMap.invalidateSize();
}

function closeMapPanel() {
  appLayout.classList.remove('map-open');
  document.getElementById('mapToggleBtn').classList.remove('active');
  if (leafletMap) { leafletMap.remove(); leafletMap = null; }
  userMarker = null;
  userCoord  = null;
}

document.getElementById('mapCloseBtn').addEventListener('click', closeMapPanel);

document.getElementById('mapToggleBtn').addEventListener('click', () => {
  if (appLayout.classList.contains('map-open')) {
    closeMapPanel();
  } else if (lastFacilities) {
    openMapPanel(lastFacilities, lastUserLocationForMap);
  }
});

document.getElementById('mapLocateBtn').addEventListener('click', () => {
  if (!userCoord || !leafletMap) return;
  leafletMap.setView([userCoord.lat, userCoord.lon], 14);
  if (userMarker) userMarker.openPopup();
});

document.getElementById('mapAddrBtn').addEventListener('click', async () => {
  const input = document.getElementById('mapAddrInput');
  const addr  = input.value.trim();
  if (!addr || !leafletMap) return;
  input.disabled = true;
  const pos = await _geocode(addr);
  if (pos) {
    _setUserMarker(pos);
    leafletMap.setView([pos.lat, pos.lon], 14);
    userMarker.openPopup();
  } else {
    const orig = input.placeholder;
    input.placeholder = 'Address not found, try again…';
    setTimeout(() => { input.placeholder = orig; }, 2000);
  }
  input.disabled = false;
});

document.getElementById('mapAddrInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('mapAddrBtn').click();
});

function renderFacilityMap(facilities, userLocation) {
  openMapPanel(facilities, userLocation);
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
    console.log('[chat] data keys:', Object.keys(data), '| facilities:', data.facilities?.length ?? 'none');
    typing.remove();
    const msgEl = appendMessage('assistant', data.reply);
    chatHistory.push({ role: 'assistant', content: data.reply });
    if (data.facilities && data.facilities.length > 0) {
      if (data.user_location) lastUserLocation = data.user_location;
      renderFacilityMap(data.facilities, data.user_location || lastUserLocation);
    }
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
  lastUserLocation = null;
  chatMessages.innerHTML = '';
  const ph = document.createElement('div');
  ph.className = 'chat-placeholder';
  ph.id = 'chatPlaceholder';
  ph.innerHTML = '<div class="chat-placeholder-icon">💬</div><p>Run an analysis to get<br>AI insights and recommendations</p>';
  chatMessages.appendChild(ph);
  // Clear map markers and disable reopen button
  if (appLayout.classList.contains('map-open')) closeMapPanel();
  lastFacilities = null;
  lastUserLocationForMap = null;
  const mapToggleBtn = document.getElementById('mapToggleBtn');
  mapToggleBtn.disabled = true;
  mapToggleBtn.classList.remove('active');
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

    // Save to gallery (async, non-blocking)
    data.results.forEach(result => {
      if (!result.error) {
        const file = selectedFiles.find(f => f.name === result.filename);
        addToGallery(result, file);
      }
    });

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

/* ── Gallery ──────────────────────────────────────────────── */
const GALLERY_KEY = 'skin_lesion_gallery';

function _loadGallery() {
  try { return JSON.parse(localStorage.getItem(GALLERY_KEY) || '[]'); }
  catch { return []; }
}

function _saveGallery(items) {
  try {
    localStorage.setItem(GALLERY_KEY, JSON.stringify(items));
  } catch {
    // Storage full — drop oldest entries until it fits
    while (items.length > 1) {
      items.pop();
      try { localStorage.setItem(GALLERY_KEY, JSON.stringify(items)); break; }
      catch { /* keep dropping */ }
    }
  }
}

function _compressToDataUrl(file, maxPx = 400, quality = 0.75) {
  return new Promise(resolve => {
    const img = new Image();
    const blobUrl = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(blobUrl);
      const scale = Math.min(1, maxPx / Math.max(img.width, img.height));
      const canvas = document.createElement('canvas');
      canvas.width  = Math.round(img.width  * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', quality));
    };
    img.onerror = () => { URL.revokeObjectURL(blobUrl); resolve(null); };
    img.src = blobUrl;
  });
}

async function addToGallery(result, file) {
  if (!file) return;
  const thumb = await _compressToDataUrl(file);
  if (!thumb) return;

  const items = _loadGallery();
  const entry = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2),
    filename: result.filename,
    thumb,
    result,
    ts: Date.now(),
  };
  // Replace existing entry for same filename, otherwise prepend
  const idx = items.findIndex(i => i.filename === result.filename);
  if (idx >= 0) items[idx] = entry;
  else items.unshift(entry);

  _saveGallery(items);
  _updateGalleryCount();
  // Refresh grid if modal is open
  if (document.getElementById('galleryOverlay').classList.contains('open')) {
    _renderGalleryGrid();
  }
}

function _updateGalleryCount() {
  // count badge removed — no-op kept for call-site compatibility
}

function _renderGalleryGrid() {
  const items  = _loadGallery();
  const grid   = document.getElementById('galleryThumbGrid');
  const empty  = document.getElementById('galleryEmptyState');

  if (!items.length) {
    grid.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  grid.innerHTML = '';
  items.forEach(item => {
    const thumb = document.createElement('div');
    thumb.className = 'gallery-thumb';
    const isHigh = item.result?.is_high_risk;
    thumb.innerHTML = `
      <img src="${item.thumb}" alt="${item.filename}" loading="lazy" />
      <div class="risk-dot ${isHigh ? 'high' : 'low'}"></div>
    `;
    thumb.addEventListener('click', () => _openGalleryDetail(item));
    grid.appendChild(thumb);
  });
}

function _openGalleryDetail(item) {
  document.getElementById('galleryDetailImg').src = item.thumb;
  document.getElementById('galleryDetailFname').textContent = item.filename;

  const resultEl = document.getElementById('galleryDetailResult');
  const r = item.result;
  if (r && !r.error) {
    const isHigh = r.is_high_risk;
    resultEl.innerHTML = `
      <div class="risk-banner ${isHigh ? 'high' : 'low'}" style="margin-bottom:16px">
        <span class="risk-icon">${isHigh ? '⚠️' : '✅'}</span>
        <div class="risk-text">${isHigh ? 'High Risk — Malignant features detected' : 'Low Risk — Likely benign'}</div>
        <div class="risk-pct">${r.cancer_total}%</div>
      </div>
      <div class="section-label">Malignant probabilities</div>
      ${Object.entries(r.cancer).map(([cls, p]) => probRow(cls, p, 'cancer')).join('')}
      ${Object.keys(r.non_cancer || {}).length ? `
        <div class="divider" style="margin:14px 0"></div>
        <div class="section-label">Other conditions &gt;20%</div>
        ${Object.entries(r.non_cancer).map(([cls, p]) => probRow(cls, p, 'benign')).join('')}
      ` : ''}
      <div style="margin-top:14px">
        <div class="top-chip">Top prediction &nbsp;·&nbsp; <span>${r.top_prediction}</span></div>
      </div>
    `;
    requestAnimationFrame(() => {
      resultEl.querySelectorAll('.prob-fill[data-pct]').forEach(el => {
        el.style.width = el.dataset.pct + '%';
      });
    });
  } else {
    resultEl.innerHTML = `<div class="error-card">⚠ Analysis failed</div>`;
  }

  document.getElementById('galleryGridView').classList.add('hidden');
  document.getElementById('galleryDetailView').classList.remove('hidden');
}

function _openGallery() {
  _renderGalleryGrid();
  // Always start on grid view
  document.getElementById('galleryGridView').classList.remove('hidden');
  document.getElementById('galleryDetailView').classList.add('hidden');
  document.getElementById('galleryOverlay').classList.add('open');
}

function _closeGallery() {
  document.getElementById('galleryOverlay').classList.remove('open');
}

// Init gallery count on load
_updateGalleryCount();

document.getElementById('galleryBtn').addEventListener('click', _openGallery);
document.getElementById('galleryCloseBtn').addEventListener('click', _closeGallery);
document.getElementById('galleryOverlay').addEventListener('click', e => {
  if (e.target === document.getElementById('galleryOverlay')) _closeGallery();
});
document.getElementById('galleryDetailBackBtn').addEventListener('click', () => {
  document.getElementById('galleryDetailView').classList.add('hidden');
  document.getElementById('galleryGridView').classList.remove('hidden');
});
document.getElementById('galleryClearBtn').addEventListener('click', () => {
  localStorage.removeItem(GALLERY_KEY);
  _updateGalleryCount();
  _renderGalleryGrid();
});
