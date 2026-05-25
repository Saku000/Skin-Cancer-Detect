'use strict';

const API = window.location.origin;

const CLASS_LABEL = {
  MEL:       'Melanoma (MEL)',
  BCC:       'Basal Cell Carcinoma (BCC)',
  AKIEC:     'Actinic Keratosis / SCC',
  NV:        'Melanocytic Nevi (NV)',
  BKL:       'Benign Keratosis (BKL)',
  DF:        'Dermatofibroma (DF)',
  VASC:      'Vascular Lesion (VASC)',
  WART:      'Wart / Verruca',
  ECZEMA:    'Eczema / Dermatitis',
  PSORIASIS: 'Psoriasis',
  ACNE:      'Acne',
  SEBDERM:   'Seborrheic Dermatitis',
  ROSACEA:   'Rosacea',
  TINEA:     'Tinea / Fungal',
  VITILIGO:  'Vitiligo',
  OTHER:     'Other Condition',
};

// ── State ─────────────────────────────────────────────────────────────────────
let selectedFiles    = [];
let chatHistory      = [];
let currentResults   = null;
let isAnalysing      = false;
let nRuns            = 3;
let lastUserLocation = null;

// Map state
let leafletMap = null;
let userMarker = null;
let userCoord  = null;
let mapInited  = false;

// ── DOM ───────────────────────────────────────────────────────────────────────
const screenMain    = document.getElementById('screenMain');
const screenGallery = document.getElementById('screenGallery');
const screenMap     = document.getElementById('screenMap');

const chatMessages    = document.getElementById('chatMessages');
const chatInput       = document.getElementById('chatInput');
const chatSendBtn     = document.getElementById('chatSendBtn');
const chatPlaceholder = document.getElementById('chatPlaceholder');

const navGallery = document.getElementById('navGallery');
const navUpload  = document.getElementById('navUpload');
const navMap     = document.getElementById('navMap');

const galleryBack  = document.getElementById('galleryBack');
const galleryGrid  = document.getElementById('galleryGrid');
const galleryEmpty = document.getElementById('galleryEmpty');

const mapBack      = document.getElementById('mapBack');
const mapContainer = document.getElementById('mapContainer');
const mapLocateBtn = document.getElementById('mapLocateBtn');
const mapAddrInput = document.getElementById('mapAddrInput');
const mapAddrBtn   = document.getElementById('mapAddrBtn');

const reportOverlay = document.getElementById('reportOverlay');
const reportDrawer  = document.getElementById('reportDrawer');
const reportBackBtn = document.getElementById('reportBackBtn');
const clearAllBtn   = document.getElementById('clearAllBtn');
const pendingThumbs = document.getElementById('pendingThumbs');
const analyseWrap   = document.getElementById('analyseWrap');
const analyseBtn    = document.getElementById('analyseBtn');
const reportResults = document.getElementById('reportResults');
const reportTab     = document.getElementById('reportTab');

const sheetOverlay   = document.getElementById('sheetOverlay');
const uploadSheet    = document.getElementById('uploadSheet');
const btnCamera      = document.getElementById('btnCamera');
const btnLibrary     = document.getElementById('btnLibrary');
const btnSheetCancel = document.getElementById('btnSheetCancel');
const cameraInput    = document.getElementById('cameraInput');
const fileInput      = document.getElementById('fileInput');

const galleryModal       = document.getElementById('galleryModal');
const galleryModalClose  = document.getElementById('galleryModalClose');
const galleryModalImg    = document.getElementById('galleryModalImg');
const galleryModalResult = document.getElementById('galleryModalResult');

// ── Screen Navigation ─────────────────────────────────────────────────────────

function showScreen(screen) {
  if (screen === screenMain) {
    screenGallery.classList.remove('active');
    screenMap.classList.remove('active');
  } else {
    screen.classList.add('active');
  }
}

navGallery.addEventListener('click', () => {
  renderGallery();
  showScreen(screenGallery);
});

navMap.addEventListener('click', () => {
  showScreen(screenMap);
  // Small delay so the screen is visible before Leaflet measures it
  setTimeout(initMapIfNeeded, 80);
});

galleryBack.addEventListener('click', () => showScreen(screenMain));
mapBack.addEventListener('click',     () => showScreen(screenMain));

// ── Upload Sheet ──────────────────────────────────────────────────────────────

function openSheet() {
  sheetOverlay.classList.add('visible');
  uploadSheet.classList.add('open');
}

function closeSheet() {
  sheetOverlay.classList.remove('visible');
  uploadSheet.classList.remove('open');
}

navUpload.addEventListener('click',       openSheet);
sheetOverlay.addEventListener('click',    closeSheet);
btnSheetCancel.addEventListener('click',  closeSheet);

btnCamera.addEventListener('click', () => {
  closeSheet();
  cameraInput.value = '';
  cameraInput.click();
});

btnLibrary.addEventListener('click', () => {
  closeSheet();
  fileInput.value = '';
  fileInput.click();
});

cameraInput.addEventListener('change', () => addFiles([...cameraInput.files]));
fileInput.addEventListener('change',   () => addFiles([...fileInput.files]));

// ── File Management ───────────────────────────────────────────────────────────

function addFiles(files) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'];
  files.filter(f => allowed.includes(f.type)).forEach(f => {
    if (!selectedFiles.find(x => x.name === f.name && x.size === f.size)) {
      selectedFiles.push(f);
    }
  });
  renderPendingThumbs();
  openDrawer();
}

function renderPendingThumbs() {
  pendingThumbs.innerHTML = '';

  selectedFiles.forEach((file, idx) => {
    const url  = URL.createObjectURL(file);
    const wrap = document.createElement('div');
    wrap.className = 'pending-thumb';
    wrap.innerHTML = `
      <img src="${url}" alt="${file.name}" />
      <button class="pending-thumb-remove" data-idx="${idx}" aria-label="Remove">✕</button>
    `;
    pendingThumbs.appendChild(wrap);
  });

  analyseWrap.style.display = selectedFiles.length ? 'flex' : 'none';
  updateReportTab();

  pendingThumbs.querySelectorAll('.pending-thumb-remove').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      selectedFiles.splice(parseInt(btn.dataset.idx), 1);
      renderPendingThumbs();
    });
  });
}

// ── Report Drawer ─────────────────────────────────────────────────────────────

function updateReportTab() {
  const hasContent = selectedFiles.length > 0 || reportResults.children.length > 0;
  // Tab count = pending files + result cards
  const count = selectedFiles.length + reportResults.children.length;
  const countEl = reportTab.querySelector('.report-tab-count');
  if (countEl) countEl.textContent = count > 0 ? count : '';
}

function openDrawer() {
  reportOverlay.classList.add('visible');
  reportDrawer.classList.add('open');
  reportTab.classList.remove('visible');
}

function closeDrawer() {
  reportOverlay.classList.remove('visible');
  reportDrawer.classList.remove('open');
  const hasContent = selectedFiles.length > 0 || reportResults.children.length > 0;
  reportTab.classList.toggle('visible', hasContent);
}

reportBackBtn.addEventListener('click',  closeDrawer);
reportOverlay.addEventListener('click',  closeDrawer);
reportTab.addEventListener('click',      openDrawer);

clearAllBtn.addEventListener('click', async () => {
  selectedFiles = [];
  renderPendingThumbs();
  reportResults.innerHTML = '';
  currentResults = null;
  closeDrawer();
  reportTab.classList.remove('visible');
  await fetch(`${API}/clear`, { method: 'DELETE' }).catch(() => {});
});

// ── Analyse ───────────────────────────────────────────────────────────────────

analyseBtn.addEventListener('click', async () => {
  if (isAnalysing || !selectedFiles.length) return;

  isAnalysing = true;
  analyseBtn.disabled = true;
  analyseBtn.innerHTML = '<span class="spinner"></span> Uploading…';
  reportResults.innerHTML = '';

  try {
    await fetch(`${API}/clear`, { method: 'DELETE' });

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));
    const uploadRes = await fetch(`${API}/upload`, { method: 'POST', body: formData });
    if (!uploadRes.ok) throw new Error(`Upload failed: ${uploadRes.statusText}`);

    analyseBtn.innerHTML = '<span class="spinner"></span> Analysing…';

    const analyseRes = await fetch(`${API}/analyze?n_runs=${nRuns}`, { method: 'POST' });
    if (!analyseRes.ok) throw new Error(`Analysis failed: ${analyseRes.statusText}`);
    const data = await analyseRes.json();

    data.results.forEach((result, idx) => {
      const file = selectedFiles.find(f => f.name === result.filename);
      const card = result.error ? buildErrorCard(result) : buildResultCard(result, file);
      card.style.animationDelay = `${idx * 0.07}s`;
      reportResults.appendChild(card);

      if (!result.error && file) {
        addToGallery(result, file); // async, non-blocking
      }
    });

    // Animate probability bars
    requestAnimationFrame(() => {
      reportResults.querySelectorAll('.prob-fill[data-pct]').forEach(el => {
        el.style.width = el.dataset.pct + '%';
      });
    });

    selectedFiles = [];
    renderPendingThumbs();
    updateReportTab();

    currentResults = data.results;
    generateSummary(data.results);

  } catch (err) {
    const errDiv = document.createElement('div');
    errDiv.className = 'error-card-mobile';
    errDiv.textContent = `⚠ ${err.message}`;
    reportResults.appendChild(errDiv);
  } finally {
    isAnalysing = false;
    analyseBtn.disabled = false;
    analyseBtn.innerHTML = 'Analyse Images';
    updateReportTab();
  }
});

// ── Card Builders ─────────────────────────────────────────────────────────────

function buildResultCard(result, file) {
  const imgUrl  = file ? URL.createObjectURL(file) : '';
  const isHigh  = result.is_high_risk;
  const pct     = result.cancer_total;

  const cancerRows = Object.entries(result.cancer)
    .map(([cls, p]) => probRowHTML(cls, p, 'cancer')).join('');

  const nonCancerBlock = Object.keys(result.non_cancer || {}).length
    ? `<div style="margin-top:10px">
         <div class="section-label-mobile">Other conditions &gt;20%</div>
         ${Object.entries(result.non_cancer).map(([cls, p]) => probRowHTML(cls, p, 'benign')).join('')}
       </div>` : '';

  const card = document.createElement('div');
  card.className = 'result-card-mobile';
  card.innerHTML = `
    <div class="rcm-img-wrap">
      <img src="${imgUrl}" alt="${result.filename}" loading="lazy" />
    </div>
    <div class="rcm-body">
      <div class="rcm-filename">${result.filename}</div>
      <div class="risk-banner ${isHigh ? 'high' : 'low'}">
        <span>${isHigh ? '⚠️' : '✅'}</span>
        <span style="flex:1">${isHigh ? 'High Risk — Malignant features detected' : 'Low Risk — Likely benign'}</span>
        <span class="risk-pct">${pct}%</span>
      </div>
      <div class="section-label-mobile">Malignant probabilities</div>
      <div class="prob-list">${cancerRows}</div>
      ${nonCancerBlock}
      <div class="top-chip-mobile">Top: <span>${result.top_prediction}</span></div>
    </div>
  `;
  return card;
}

function probRowHTML(cls, pct, type) {
  const capped = Math.min(100, Math.round(pct));
  return `
    <div class="prob-row">
      <div class="prob-name">${CLASS_LABEL[cls] || cls}</div>
      <div class="prob-track"><div class="prob-fill ${type}" data-pct="${capped}"></div></div>
      <div class="prob-pct ${type}">${pct.toFixed(1)}%</div>
    </div>`;
}

function buildErrorCard(result) {
  const card = document.createElement('div');
  card.className = 'error-card-mobile';
  card.textContent = `⚠ ${result.filename}: ${result.error}`;
  return card;
}

// ── Gallery ───────────────────────────────────────────────────────────────────

const GALLERY_KEY = 'skin_lesion_gallery';

function _mgLoad() {
  try { return JSON.parse(localStorage.getItem(GALLERY_KEY) || '[]'); }
  catch { return []; }
}

function _mgSave(items) {
  try {
    localStorage.setItem(GALLERY_KEY, JSON.stringify(items));
  } catch {
    // Storage full — drop oldest until it fits
    while (items.length > 1) {
      items.pop();
      try { localStorage.setItem(GALLERY_KEY, JSON.stringify(items)); break; }
      catch { /* keep dropping */ }
    }
  }
}

function _compressImg(file, maxPx = 400, quality = 0.75) {
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
  const thumb = await _compressImg(file);
  if (!thumb) return;
  const items = _mgLoad();
  const entry = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2),
    filename: result.filename,
    thumb,
    result,
    ts: Date.now(),
  };
  const idx = items.findIndex(i => i.filename === result.filename);
  if (idx >= 0) items[idx] = entry;
  else items.unshift(entry);
  _mgSave(items);
}

function renderGallery() {
  const items = _mgLoad();
  galleryGrid.innerHTML = '';
  const empty = items.length === 0;
  galleryEmpty.style.display = empty ? 'flex' : 'none';
  galleryGrid.style.display  = empty ? 'none' : 'grid';

  items.forEach(item => {
    const thumb = document.createElement('div');
    thumb.className = 'gallery-thumb';
    const isHigh = item.result?.is_high_risk;
    thumb.innerHTML = `
      <img src="${item.thumb}" alt="${item.filename}" loading="lazy" />
      <div class="thumb-badge ${isHigh ? 'high' : 'low'}">${isHigh ? 'High' : 'Low'}</div>
    `;
    thumb.addEventListener('click', () => openGalleryModal(item));
    galleryGrid.appendChild(thumb);
  });
}

document.getElementById('galleryClearAllBtn').addEventListener('click', () => {
  localStorage.removeItem(GALLERY_KEY);
  renderGallery();
});

function openGalleryModal(item) {
  const r      = item.result;
  const isHigh = r.is_high_risk;

  galleryModalImg.src = item.thumb;
  galleryModalImg.alt = r.filename;

  const cancerRows = Object.entries(r.cancer)
    .map(([cls, p]) => probRowHTML(cls, p, 'cancer')).join('');

  const nonCancerBlock = Object.keys(r.non_cancer || {}).length
    ? `<div style="margin-top:12px">
         <div class="section-label-mobile">Other conditions &gt;20%</div>
         ${Object.entries(r.non_cancer).map(([cls, p]) => probRowHTML(cls, p, 'benign')).join('')}
       </div>` : '';

  galleryModalResult.innerHTML = `
    <div class="rcm-filename">${r.filename}</div>
    <div class="risk-banner ${isHigh ? 'high' : 'low'}">
      <span>${isHigh ? '⚠️' : '✅'}</span>
      <span style="flex:1">${isHigh ? 'High Risk — Malignant features detected' : 'Low Risk — Likely benign'}</span>
      <span class="risk-pct">${r.cancer_total}%</span>
    </div>
    <div class="section-label-mobile">Malignant probabilities</div>
    <div class="prob-list">${cancerRows}</div>
    ${nonCancerBlock}
    <div class="top-chip-mobile" style="margin-top:10px">Top: <span>${r.top_prediction}</span></div>
  `;

  galleryModal.classList.add('open');

  requestAnimationFrame(() => {
    galleryModalResult.querySelectorAll('.prob-fill[data-pct]').forEach(el => {
      el.style.width = el.dataset.pct + '%';
    });
  });
}

galleryModalClose.addEventListener('click', () => galleryModal.classList.remove('open'));

// Swipe-down to close modal
(function () {
  let startY = 0;
  galleryModal.addEventListener('touchstart', e => { startY = e.touches[0].clientY; }, { passive: true });
  galleryModal.addEventListener('touchend', e => {
    if (e.changedTouches[0].clientY - startY > 70) galleryModal.classList.remove('open');
  }, { passive: true });
})();

// ── Chat ──────────────────────────────────────────────────────────────────────

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
  chatSendBtn.disabled = !chatInput.value.trim();
});

chatSendBtn.addEventListener('click', () => {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  chatInput.style.height = 'auto';
  chatSendBtn.disabled = true;
  sendMessage(text);
});

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatSendBtn.click(); }
});

function appendMessage(role, content) {
  if (chatPlaceholder && chatPlaceholder.parentNode) chatPlaceholder.remove();
  const msg = document.createElement('div');
  msg.className = `msg ${role}`;
  msg.textContent = content;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

function appendTyping() {
  if (chatPlaceholder && chatPlaceholder.parentNode) chatPlaceholder.remove();
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
    if (!res.ok) throw new Error();
    const data = await res.json();
    typing.remove();
    if (data.reply) appendMessage('assistant', data.reply);
  } catch {
    typing.remove();
  }
}

async function sendMessage(text) {
  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });
  const typing = appendTyping();
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

    if (data.facilities?.length) {
      if (data.user_location) lastUserLocation = data.user_location;
      showScreen(screenMap);
      setTimeout(() => {
        initMapIfNeeded();
        plotFacilities(data.facilities, data.user_location || lastUserLocation);
      }, 120);
    }
  } catch {
    typing.remove();
    appendMessage('assistant', 'Sorry, something went wrong. Please try again.');
  } finally {
    chatSendBtn.disabled = false;
  }
}

// ── Map ───────────────────────────────────────────────────────────────────────

function _delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function _geocode(query, cc = 'us') {
  const ccParam = cc ? `&countrycodes=${cc}` : '';
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&limit=1${ccParam}&q=${encodeURIComponent(query)}`
      );
      if (r.status === 429) { await _delay(2500 * (attempt + 1)); continue; }
      if (!r.ok) return null;
      const d = await r.json();
      return d[0] ? { lat: parseFloat(d[0].lat), lon: parseFloat(d[0].lon) } : null;
    } catch { return null; }
  }
  return null;
}

async function _geocodeStructured(street, city, state, zip) {
  const params = new URLSearchParams({ format: 'json', limit: '1', countrycodes: 'us' });
  if (street) params.set('street', street);
  if (city)   params.set('city', city);
  if (state)  params.set('state', state);
  if (zip)    params.set('postalcode', zip);
  try {
    const r = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
    if (!r.ok) return null;
    const d = await r.json();
    return d[0] ? { lat: parseFloat(d[0].lat), lon: parseFloat(d[0].lon) } : null;
  } catch { return null; }
}

async function _geocodeFacility(f) {
  const addr  = (f.address || '').trim();
  const real  = addr && !addr.startsWith('(');
  const parts = addr.split(',').map(s => s.trim());

  // Parse address components for structured queries
  const street   = parts[0] || '';
  const city     = parts[1] || '';
  const stateZip = parts[2] || '';
  const stateM   = stateZip.match(/^([A-Z]{2})\s*(\d{5})?/i);
  const state    = stateM ? stateM[1] : '';
  const zip      = stateM ? (stateM[2] || '') : '';

  if (real) {
    // 1. Free-text full address
    const p1 = await _geocode(addr);
    if (p1) return p1;
    await _delay(1200);

    // 2. Structured Nominatim query (often finds addresses that free-text misses)
    if (street && city && state) {
      const p2 = await _geocodeStructured(street, city, state, zip);
      if (p2) return p2;
      await _delay(1200);
    }

    // 3. Strip suite/floor then free-text
    const cleaned = addr.replace(/,?\s*(?:\d+(?:st|nd|rd|th)\s+floor|floor\s+\d+|suite\s+[\w#-]+|apt\.?\s*[\w#]+|unit\s+[\w#]+)/gi, '').trim();
    if (cleaned !== addr) {
      const p3 = await _geocode(cleaned);
      if (p3) return p3;
      await _delay(1200);
    }

    // 4. Name + city, state
    if (f.name && city && state) {
      const p4 = await _geocode(`${f.name} ${city}, ${state}`);
      if (p4) return p4;
      await _delay(1200);
    }
  }

  if (f.name) {
    // 5. Name only (US)
    const p5 = await _geocode(f.name, 'us');
    if (p5) return p5;
    await _delay(1200);

    // 6. Name only (no country restriction)
    const p6 = await _geocode(f.name, '');
    if (p6) return p6;
    await _delay(1200);

    // 7. Drop leading brand word ("MemorialCare Saddleback…" → "Saddleback…")
    const shortName = f.name.replace(/^\S+\s+/, '');
    if (shortName && shortName !== f.name) {
      const p7 = await _geocode(shortName, 'us');
      if (p7) return p7;
      await _delay(1200);

      // 8. Short name + city
      if (city && state) {
        const p8 = await _geocode(`${shortName} ${city}, ${state}`);
        if (p8) return p8;
        await _delay(1200);
      }
    }
  }

  // 9. Last resort: zip code center (gives approximate area marker)
  if (zip) {
    const p9 = await _geocode(`${zip}, USA`, '');
    if (p9) {
      console.warn('[map] using zip fallback for:', f.name);
      return p9;
    }
  }

  console.warn('[map] geocode totally failed:', f.name, '|', f.address);
  return null;
}

function _haversineMi(la1, lo1, la2, lo2) {
  const R = 3958.8, dl = (la2-la1)*Math.PI/180, dL = (lo2-lo1)*Math.PI/180;
  const a = Math.sin(dl/2)**2 + Math.cos(la1*Math.PI/180)*Math.cos(la2*Math.PI/180)*Math.sin(dL/2)**2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function _fmtDist(mi) { return mi < 0.1 ? `${Math.round(mi*5280)} ft` : `${mi.toFixed(1)} mi`; }

function _circle(color) { return { radius: 9, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.92 }; }

function _setUserMarker(pos) {
  userCoord = pos;
  if (userMarker) userMarker.remove();
  userMarker = L.circleMarker([pos.lat, pos.lon], _circle('#00c4d2'))
    .addTo(leafletMap).bindPopup('Your location');
  mapLocateBtn.disabled = false;
}

function initMapIfNeeded() {
  if (mapInited) { leafletMap?.invalidateSize(); return; }
  mapInited = true;

  leafletMap = L.map(mapContainer, { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap', maxZoom: 18,
  }).addTo(leafletMap);
  leafletMap.setView([37.5, -119.0], 6);
  setTimeout(() => leafletMap.invalidateSize(), 120);
}

async function _geocodeUserAddr(addr) {
  // 1. Full address
  const p1 = await _geocode(addr);
  if (p1) return p1;
  await _delay(1200);

  // 2. City, state — last 2 comma-parts (e.g. "Irvine, CA")
  const parts = addr.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length >= 2) {
    const cityState = parts.slice(-2).join(', ');
    const p2 = await _geocode(cityState);
    if (p2) return p2;
    await _delay(1200);
  }

  // 3. Last segment only (city or state)
  const last = parts[parts.length - 1];
  if (last) return _geocode(last);
  return null;
}

async function plotFacilities(facilities, userLocation) {
  leafletMap.invalidateSize();

  if (userLocation) {
    const isZip = /^\d{5}$/.test(userLocation.trim());
    const pos   = isZip
      ? await _geocode(`${userLocation.trim()}, USA`)
      : await _geocodeUserAddr(userLocation);
    if (pos) { _setUserMarker(pos); leafletMap.setView([pos.lat, pos.lon], 13); }
    await _delay(1200);
  }

  const bounds = userCoord ? [[userCoord.lat, userCoord.lon]] : [];

  for (const f of facilities) {
    // If backend already sent exact coords (Overpass data), use them directly
    const pos = (f.lat && f.lon)
      ? { lat: f.lat, lon: f.lon }
      : await _geocodeFacility(f);
    if (!pos) { await _delay(1100); continue; }
    bounds.push([pos.lat, pos.lon]);
    const q   = encodeURIComponent([f.name, f.address].filter(Boolean).join(', '));
    const nav = `https://www.google.com/maps/dir/?api=1&destination=${q}&travelmode=driving`;
    const distMi = userCoord ? _haversineMi(userCoord.lat, userCoord.lon, pos.lat, pos.lon) : null;
    const distLabel = f.distance_mi != null
      ? `<br><span style="font-size:11px;color:#4285f4;font-weight:600">📍 ${_fmtDist(f.distance_mi)} away</span>`
      : distMi != null
        ? `<br><span style="font-size:11px;color:#4285f4;font-weight:600">📍 ${_fmtDist(distMi)} away</span>`
        : '';
    L.circleMarker([pos.lat, pos.lon], _circle('#ff4d6d'))
      .addTo(leafletMap)
      .bindPopup(`
        <div style="font-family:sans-serif;min-width:160px;line-height:1.5">
          <b style="font-size:13px">${f.name}</b><br>
          <span style="font-size:11px;color:#555">${f.address || ''}</span>
          ${f.phone ? `<br><span style="font-size:11px;color:#555">${f.phone}</span>` : ''}
          ${distLabel}
          <br>
          <a href="${nav}" target="_blank" rel="noopener"
             style="display:inline-block;margin-top:7px;padding:5px 11px;
                    background:#4285f4;color:#fff;border-radius:4px;
                    text-decoration:none;font-size:11px;font-weight:600">
            🗺 Navigate
          </a>
        </div>`, { maxWidth: 220 });
    if (!f.lat) await _delay(1100); // only rate-limit when we had to geocode
  }

  if (bounds.length > 1) leafletMap.fitBounds(bounds, { padding: [50, 50] });
  leafletMap.invalidateSize();
}

mapLocateBtn.addEventListener('click', () => {
  if (!userCoord || !leafletMap) return;
  leafletMap.setView([userCoord.lat, userCoord.lon], 14);
  userMarker?.openPopup();
});

mapAddrBtn.addEventListener('click', async () => {
  const addr = mapAddrInput.value.trim();
  if (!addr || !leafletMap) return;
  mapAddrInput.disabled = true;
  const pos = await _geocode(addr);
  if (pos) {
    _setUserMarker(pos);
    leafletMap.setView([pos.lat, pos.lon], 14);
    userMarker.openPopup();
  } else {
    const orig = mapAddrInput.placeholder;
    mapAddrInput.placeholder = 'Address not found, try again…';
    setTimeout(() => { mapAddrInput.placeholder = orig; }, 2200);
  }
  mapAddrInput.disabled = false;
});

mapAddrInput.addEventListener('keydown', e => { if (e.key === 'Enter') mapAddrBtn.click(); });

// ── Report tab count label ────────────────────────────────────────────────────
// Inject count span into the tab on init
reportTab.innerHTML = `
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
  <span class="report-tab-count"></span>
`;
