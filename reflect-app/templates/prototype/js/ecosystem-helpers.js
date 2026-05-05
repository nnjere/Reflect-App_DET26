/**
 * ecosystem-helpers.js
 * Shared utilities for dynamic ecosystem pages.
 */

const EcoHelpers = (() => {

  // ── Consistent color per persona key ─────────────────────
  const PERSONA_COLORS = {
    mum:     '#ff7faa',
    dad:     '#60a5fa',
    alex:    '#a78bfa',
    grandma: '#85b87d',
    marcus:  '#f87171',
    emma:    '#c084fc',
    kai:     '#fb923c',
    zoe:     '#34d399',
  };

  const FALLBACK_COLORS = ['#c084fc','#e879b0','#fb923c','#60a5fa','#34d399','#fbbf24','#f87171','#a78bfa'];

  function colorFor(name, idx) {
    const key = (name || '').toLowerCase().replace('_dummy','').replace(/\s/g,'');
    return PERSONA_COLORS[key] || FALLBACK_COLORS[idx % FALLBACK_COLORS.length];
  }

  // ── Auto-generate group name from blend data ──────────────
  function generateName(blend) {
    const ba = blend?.blend_analysis || blend || {};

    // Use blend_title if Claude gave one
    if (ba.blend_title && ba.blend_title !== 'Group') return ba.blend_title;

    const members = blend?.members || ba.members || [];

    // Use closest pair
    const cp = ba.closest_pair?.members;
    if (cp?.length >= 2) {
      const a = clean(cp[0]);
      const b = clean(cp[1]);
      const rest = members.length > 2 ? ` +${members.length - 2}` : '';
      return `${a} & ${b}${rest}`;
    }

    // Fallback: first two members
    if (members.length >= 2) {
      return `${clean(members[0])} & ${clean(members[1])}`;
    }

    return 'My Ecosystem';
  }

  function clean(name) {
    return (name || '')
      .replace(/_Dummy$/i, '')
      .replace(/_dummy$/i, '')
      .replace('_Dummy', '')
      .replace('_dummy', '')
      .trim();
  }

  // ── Diversity label from blend data ──────────────────────
  function diversityLabel(eco) {
    const ba = eco?.blend_data?.blend_analysis || eco?.blend_data || {};
    if (ba.group_diversity?.label) return ba.group_diversity.label;
    const s = ba.group_diversity?.score || 0;
    if (s >= 7) return 'High diversity';
    if (s >= 4) return 'Mixed diversity';
    if (s > 0)  return 'Low diversity';
    return 'Mixed diversity';
  }

  // ── Closest pair alignment text ───────────────────────────
  function alignText(eco) {
    const ba = eco?.blend_data?.blend_analysis || eco?.blend_data || {};
    const cp = ba.closest_pair?.members;
    if (cp?.length >= 2) return `You align most with ${clean(cp[0])}`;
    return '';
  }

  // ── Venn SVG — colored circles for each member ───────────
  function vennSVG(members, width, height) {
    const n = members.length;
    const cx = width / 2;
    const cy = height / 2;
    const r  = Math.min(52, 110 / n);
    const spread = n <= 2 ? 36 : n <= 3 ? 46 : 54;

    const circles = members.map((name, i) => {
      const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
      const x = n === 1 ? cx : cx + spread * Math.cos(angle);
      const y = n === 1 ? cy : cy + spread * Math.sin(angle);
      const col = colorFor(name, i);
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${col}" opacity="0.6"/>`;
    }).join('');

    // Center "you" dot
    const youDot = `<circle cx="${cx}" cy="${cy}" r="12" fill="white" opacity="0.7"/>`;

    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" overflow="visible" xmlns="http://www.w3.org/2000/svg">
      ${circles}
      ${youDot}
    </svg>`;
  }

  // ── Member dot HTML (overlapping circles row) ─────────────
  function memberDots(members, size) {
    const s = size || 38;
    return members.slice(0, 5).map((name, i) => {
      const col = colorFor(name, i);
      const letter = clean(name)[0]?.toUpperCase() || '?';
      return `<div style="
        width:${s}px;height:${s}px;border-radius:50%;
        border:2px solid #fef7e5;margin-left:${i===0?0:-10}px;
        background:${col};display:inline-flex;align-items:center;
        justify-content:center;font-size:${Math.round(s*0.35)}px;
        font-weight:700;color:white;flex-shrink:0;">${letter}</div>`;
    }).join('');
  }

  // ── Get active ecosystem from localStorage ─────────────────
  function getActiveEco() {
    try {
      const raw = localStorage.getItem('reflect_active_ecosystem');
      return raw ? JSON.parse(raw) : null;
    } catch(e) { return null; }
  }

  // ── Get blend analysis safely ─────────────────────────────
  function getBlend(eco) {
    return eco?.blend_data?.blend_analysis || eco?.blend_data || {};
  }

  return {
    colorFor, generateName, clean, diversityLabel,
    alignText, vennSVG, memberDots, getActiveEco, getBlend,
    PERSONA_COLORS, FALLBACK_COLORS
  };
})();
