/**
 * reflect-data.js
 * Shared data layer for the Reflect mobile prototype.
 * API calls are relative — works when served from Railway at /prototype/
 */

const Reflect = (() => {

  const STORAGE_KEY = 'reflect_active_report';

  // ── Report storage ─────────────────────────────────────────
  function getReport() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch(e) { return null; }
  }

  function setReport(report) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(report));
  }

  function clearReport() {
    localStorage.removeItem(STORAGE_KEY);
  }

  // ── API calls (relative paths — same origin as Railway) ────
  async function uploadJson(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload-json', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(`Upload failed (${res.status})`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    setReport(data);
    return data;
  }

  async function loadPersona(persona) {
    const res = await fetch(`/dummy?persona=${persona}`);
    if (!res.ok) throw new Error(`Failed to load sample (${res.status})`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    setReport(data);
    return data;
  }

  // ── Safe data accessors ────────────────────────────────────
  function getThemes(report)       { return report?.analysis?.thematic_analysis?.themes || []; }
  function getEmotionalTone(report){ return report?.analysis?.dimensionality_analysis?.emotional_tone || {}; }
  function getEchoChamber(report)  { return report?.analysis?.dimensionality_analysis?.echo_chamber || {}; }
  function getPolarity(report)     { return report?.analysis?.dimensionality_analysis?.polarity || {}; }
  function getUser(report)         { return report?.analysis?.user || {}; }
  function getDataSummary(report)  { return report?.data_summary || {}; }
  function getPrintSummary(report) { return report?.analysis?.print_summary || {}; }

  // ── Bar gradients ──────────────────────────────────────────
  const GRADIENTS = [
    'linear-gradient(90deg, rgba(173,70,255,0.85), rgba(255,100,160,0.7))',
    'linear-gradient(90deg, rgba(255,100,80,0.9),  rgba(255,160,60,0.8))',
    'linear-gradient(90deg, rgba(255,80,140,0.9),  rgba(255,140,100,0.7))',
    'linear-gradient(90deg, rgba(255,140,60,0.9),  rgba(255,200,60,0.8))',
    'linear-gradient(90deg, rgba(100,200,150,0.9), rgba(80,180,200,0.8))',
    'linear-gradient(90deg, rgba(100,140,255,0.9), rgba(160,100,255,0.8))',
  ];
  function barGradient(i) { return GRADIENTS[i % GRADIENTS.length]; }

  // ── Dashboard hydration ────────────────────────────────────
  function hydrateDashboard(report) {
    if (!report) return;
    const user    = getUser(report);
    const summary = getDataSummary(report);
    const themes  = getThemes(report);
    const echo    = getEchoChamber(report);
    const emo     = getEmotionalTone(report);

    // Greeting
    const nameEl  = document.getElementById('r-username');
    const labelEl = document.getElementById('r-overall-label');
    if (nameEl)  nameEl.textContent  = (user.name || 'you').replace('_Dummy','');
    if (labelEl) labelEl.textContent = user.overall_label || 'Diverse';

    // Stats
    const watched = document.getElementById('r-stat-watched');
    const types   = document.getElementById('r-stat-types');
    const div     = document.getElementById('r-stat-diversity');
    if (watched) watched.textContent = (summary.watch_count || '—').toLocaleString();
    if (types)   types.textContent   = themes.length || '—';
    if (div)     div.textContent     = `${Math.round((echo.score || 0) * 10)}%`;

    // Theme bars
    const list = document.getElementById('r-themes-list');
    if (list && themes.length) {
      list.innerHTML = themes.slice(0,4).map((t,i) => `
        <div class="progress-item">
          <div class="progress-header">
            <span class="progress-label">${t.theme}</span>
            <span class="progress-pct">${t.percentage}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width:${Math.round(t.percentage*1.6)}px;height:100%;border-radius:9999px;background:${barGradient(i)}"></div>
          </div>
        </div>`).join('');
    }

    // Diversity label
    const divLabel = document.getElementById('r-diversity-label');
    if (divLabel) divLabel.textContent = user.overall_label || 'High';

    // Echo chamber
    const echoLabel  = document.getElementById('r-echo-label');
    const echoPct    = document.getElementById('r-echo-pct');
    const signalFill = document.getElementById('r-signal-fill');
    const echoTags   = document.getElementById('r-echo-tags');
    const pct = echo.signal_percentage || 24;
    if (echoLabel)  echoLabel.textContent = echo.label || 'Low Repetition';
    if (echoPct)    echoPct.textContent   = `Low (${pct}%)`;
    if (signalFill) signalFill.style.width = `${pct}%`;
    if (echoTags && echo.key_themes) {
      echoTags.innerHTML = echo.key_themes.map(t=>`<span class="tag">${t}</span>`).join('');
    }

    // Emotional tone
    const emoLabel = document.getElementById('r-emo-label');
    const bd = emo.breakdown || {};
    if (emoLabel) emoLabel.textContent = emo.label || 'Mostly Positive';
    const pos = document.getElementById('r-emo-positive');
    const neu = document.getElementById('r-emo-neutral');
    const pol = document.getElementById('r-emo-polarized');
    if (pos) pos.textContent = `${bd.positive   || 62}%`;
    if (neu) neu.textContent = `${bd.neutral     || 25}%`;
    if (pol) pol.textContent = `${bd.polarizing  || 13}%`;
  }

  return {
    getReport, setReport, clearReport,
    uploadJson, loadPersona,
    getThemes, getEmotionalTone, getEchoChamber,
    getPolarity, getUser, getDataSummary, getPrintSummary,
    hydrateDashboard, barGradient,
  };

})();