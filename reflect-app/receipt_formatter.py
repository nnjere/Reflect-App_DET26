# ── receipt_formatter.py ──────────────────────────────
# Single source of truth for all receipt formatting.
# Used by /receipt/individual and /receipt/blend endpoints.
# ESP32 and browser both pull from the same endpoints.

from datetime import datetime

# ── Layout constants ───────────────────────────────────
WIDTH = 32

def center(text):
    text = str(text)
    if len(text) >= WIDTH:
        return text[:WIDTH]
    pad = (WIDTH - len(text)) // 2
    return ' ' * pad + text

def divider(char='-'):
    return char * WIDTH

def wrap(text, width=WIDTH):
    if not text:
        return ''
    words = str(text).split()
    lines = []
    current = ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return '\n'.join(lines)

def header(timestamp=None):
    ts = timestamp or datetime.now().strftime('%Y-%m-%d %H:%M')
    return '\n'.join([
        center('* R E F L E C T *'),
        center('Media Consumption Report'),
        divider(),
        center(ts),
    ])

def footer():
    return '\n'.join([
        divider('='),
        center('reflect.app'),
        center('know your feed'),
        '', '', ''
    ])

# ── Individual report receipt ──────────────────────────
def format_individual(report: dict) -> str:
    a = report.get('analysis', {})
    user = a.get('user', {})
    themes = a.get('thematic_analysis', {})
    dims = a.get('dimensionality_analysis', {})
    pol = dims.get('polarity', {})
    emo = dims.get('emotional_tone', {})
    echo = dims.get('echo_chamber', {})
    ps = a.get('print_summary', {})

    theme_lines = []
    for t in (themes.get('themes') or [])[:5]:
        name = t.get('theme', '')
        pct = t.get('percentage', 0)
        bar_width = round(pct / 100 * (WIDTH - len(str(pct)) - 2))
        bar = '█' * bar_width
        theme_lines.append(f'{name[:16]:<16} {pct:>3}% {bar}')

    lines = [
        header(),
        divider(),
        center(report.get('report_id', 'User')),
        center(user.get('overall_label', '')),
        divider(),
        'CONTENT THEMES',
        divider(),
        *theme_lines,
        divider(),
        'SCORES',
        f"  Polarity   {pol.get('score', 0)}/10",
        f"  Emotional  {emo.get('score', 0)}/10",
        f"  Diversity  {echo.get('score', 0)}/10",
        divider(),
        'INSIGHT',
        wrap(ps.get('headline', '')),
        '',
        wrap(ps.get('line1', '')),
        wrap(ps.get('line2', '')),
        wrap(ps.get('line3', '')),
        divider(),
        'RECOMMENDATION',
        wrap(ps.get('recommendation', '')),
        footer()
    ]

    return '\n'.join(lines)

# ── Blend report receipt ───────────────────────────────
def format_blend(blend_data: dict) -> str:
    ba = blend_data.get('blend_analysis', {})
    names = blend_data.get('members', [])
    ps = ba.get('print_summary', {})
    div = ba.get('group_diversity', {})
    cp = ba.get('closest_pair', {})
    fp = ba.get('furthest_pair', {})

    lines = [
        header(),
        divider(),
        center('GROUP BLEND'),
        center(f'{len(names)} People'),
        divider(),
        'MEMBERS',
        *[f'  {n}' for n in names],
        divider(),
        f"Group: {div.get('label', '')}",
        wrap(div.get('summary', '')),
        divider(),
        'SHARED THEMES',
        *[f"  + {t}" for t in (ba.get('key_common_themes') or [])[:5]],
        divider(),
    ]

    if cp.get('members'):
        lines += [
            'MOST ALIGNED',
            f"  {cp['members'][0]} & {cp['members'][1]}",
            wrap(cp.get('reason', '')),
        ]

    if fp.get('members'):
        lines += [
            '',
            'MOST DIFFERENT',
            f"  {fp['members'][0]} & {fp['members'][1]}",
            wrap(fp.get('reason', '')),
        ]

    lines += [
        divider(),
        'GROUP INSIGHT',
        wrap(ps.get('headline', '')),
        '',
        wrap(ps.get('line1', '')),
        wrap(ps.get('line2', '')),
        wrap(ps.get('recommendation', '')),
        footer()
    ]

    return '\n'.join(lines)