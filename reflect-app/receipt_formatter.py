# ── receipt_formatter.py ──────────────────────────────
from datetime import datetime

WIDTH = 32
MEMBER_CHARS = ['/', '.', '+', 'o', '*', '=']

# ── Helpers ────────────────────────────────────────────
def center(text):
    text = str(text)
    if len(text) >= WIDTH:
        return text
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

def truncate_words(text, max_words=50):
    if not text:
        return ''
    words = text.split()
    if len(words) <= max_words:
        return wrap(text)
    return wrap(' '.join(words[:max_words]) + '...')

def bar(pct, width=12):
    filled = round(pct / 100 * width)
    return '\u2588' * filled + '\u2591' * (width - filled)

def clean(name):
    return name.replace('_Dummy', '')

def short(name, length=4):
    return clean(name)[:length]

def header():
    ts = datetime.now().strftime('%B %-d, %Y')
    return '\n'.join([
        center('* R E F L E C T *'),
        center('Media Consumption Report'),
        divider(),
        center(f'Week of {ts}'),
        center('a snapshot of your shared digital patterns'),
    ])

def footer():
    return '\n'.join([
        divider('='),
        center('reflect.app'),
        center('know your digital patterns'),
        center('not a judgment, just a reflection'),
        '', ''
    ])

# ── Group overlap bars ─────────────────────────────────
def overlap_bars(names, comparisons):
    lines = []
    char_map = {n: MEMBER_CHARS[i % len(MEMBER_CHARS)] for i, n in enumerate(names)}

    scores = {}
    for c in comparisons:
        a, b = c.get('member_a', ''), c.get('member_b', '')
        s = c.get('overlap_score', 50)
        scores[a] = max(scores.get(a, 0), s)
        scores[b] = max(scores.get(b, 0), s)

    shared_pct = round(sum(scores.values()) / len(scores)) if scores else 40
    bar_max = 20

    for name in names:
        ch = char_map[name]
        score = scores.get(name, 50)
        length = max(4, round(score / 100 * bar_max))
        label = clean(name)[:11]
        lines.append(f'{label:<12} {ch * length}')

    shared_len = max(4, round(shared_pct / 100 * bar_max))
    lines.append(f'{"SHARED":<12} {"#" * shared_len}')
    lines.append(center(f'{shared_pct}% group overlap'))
    return '\n'.join(lines)

# ── Content differences by member ─────────────────────
def content_differences_section(names, diverging_themes):
    member_themes = {n: [] for n in names}
    for t in diverging_themes:
        engagers = t.get('members_who_engage', [])
        theme = t.get('theme', '')
        if not theme:
            continue
        if len(engagers) <= max(1, len(names) // 2):
            for e in engagers:
                if e in member_themes:
                    member_themes[e].append(theme)

    lines = []
    for name in names:
        themes = member_themes.get(name, [])
        if themes:
            lines.append(f'{clean(name)} ONLY')
            for theme in themes[:3]:
                lines.append(f'* {theme}')
    return '\n'.join(lines) if lines else '(no unique themes found)'

# ── Alignment matrix ───────────────────────────────────
def alignment_matrix(names, shared_themes, diverging_themes):
    n = len(names)
    col_w = max(5, (WIDTH - 10) // n)
    label_w = WIDTH - (col_w * n)

    short_names = [short(n, col_w - 1) for n in names]
    header_row = ' ' * label_w + ''.join(f'{s:^{col_w}}' for s in short_names)
    rows = [header_row]

    shared_set = {t.get('theme', '') for t in shared_themes[:4]}
    for theme in list(shared_set)[:4]:
        row = theme[:label_w - 1].ljust(label_w)
        row += ''.join(f'{"✓":^{col_w}}' for _ in names)
        rows.append(row)

    for t in diverging_themes[:4]:
        theme = t.get('theme', '')[:label_w - 1].ljust(label_w)
        engagers = set(t.get('members_who_engage', []))
        row = theme + ''.join(
            f'{"✓" if name in engagers else "✗":^{col_w}}' for name in names)
        rows.append(row)

    return '\n'.join(rows)

# ── Behaviour snapshot ─────────────────────────────────
def behaviour_section(names, reports):
    report_map = {r.get('report_id', ''): r for r in (reports or [])}

    peak_labels = {
        'early_morning': 'early morning',
        'morning': 'morning',
        'afternoon': 'afternoon',
        'evening': 'evening',
        'late_night': 'late night'
    }

    def get_summary(name):
        return report_map.get(name, {}).get('data_summary', {})

    def label(name):
        return f'{clean(name)[:11]}:'

    lines = []

    lines.append('Usage Patterns')
    for name in names:
        s = get_summary(name)
        avg = s.get('avg_session_videos', 0)
        lines.append(f'  {label(name):<14} {avg} videos/session')

    lines += ['', 'Peak Hours']
    for name in names:
        s = get_summary(name)
        peak = peak_labels.get(s.get('peak_hours', ''), s.get('peak_hours', '—'))
        lines.append(f'  {label(name):<14} {peak}')

    lines += ['', 'Engagement Style']
    for name in names:
        s = get_summary(name)
        lr = s.get('like_rate', 0)
        style = 'very active' if lr > 30 else 'active' if lr > 15 else 'moderate' if lr > 5 else 'passive'
        lines.append(f'  {label(name):<14} {style}')

    lines += ['', 'Like Rate']
    for name in names:
        s = get_summary(name)
        lines.append(f'  {label(name):<14} {s.get("like_rate", 0)}%')

    return '\n'.join(lines)

# ── Emotional tone per member ──────────────────────────
def emotional_tone_section(names, reports):
    report_map = {r.get('report_id', ''): r for r in (reports or [])}
    blocks = []

    for name in names:
        report = report_map.get(name, {})
        emo = (report.get('analysis', {})
                     .get('dimensionality_analysis', {})
                     .get('emotional_tone', {}))
        bd = emo.get('breakdown', {})
        pos = bd.get('positive', 0)
        neu = bd.get('neutral', 0)
        pol = bd.get('polarizing', 0)
        block = [
            clean(name),
            f'  Positive  {bar(pos)}  {pos}%',
            f'  Neutral   {bar(neu)}  {neu}%',
            f'  Polarized {bar(pol)}  {pol}%',
        ]
        blocks.append('\n'.join(block))

    return '\n\n'.join(blocks)

# ── Relationship distance ──────────────────────────────
def relationship_distance(names, comparisons):
    if len(names) < 2:
        return ''

    scores = {}
    for c in comparisons:
        a, b = c.get('member_a', ''), c.get('member_b', '')
        pair = tuple(sorted([a, b]))
        scores[pair] = c.get('overlap_score', 50)

    sorted_names = list(names)
    if len(names) >= 2:
        best_score = -1
        best_pair = (names[0], names[1])
        for pair, score in scores.items():
            if score > best_score:
                best_score = score
                best_pair = pair
        sorted_names = list(best_pair) + [n for n in names if n not in best_pair]

    parts = []
    for i, name in enumerate(sorted_names):
        parts.append(f'[{short(name, 5)}]')
        if i < len(sorted_names) - 1:
            pair = tuple(sorted([sorted_names[i], sorted_names[i + 1]]))
            score = scores.get(pair, 50)
            connector = '==' if score >= 60 else '----' if score <= 40 else '--'
            parts.append(connector)

    line = ''.join(parts)
    return line + '\ncloser \u2190' + '\u2014' * (WIDTH - 16) + '\u2192 further'

# ── Individual receipt ─────────────────────────────────
def format_individual(report: dict) -> str:
    a = report.get('analysis', {})
    user = a.get('user', {})
    themes = a.get('thematic_analysis', {})
    dims = a.get('dimensionality_analysis', {})
    pol = dims.get('polarity', {})
    emo = dims.get('emotional_tone', {})
    echo = dims.get('echo_chamber', {})
    ps = a.get('print_summary', {})
    summary = report.get('data_summary', {})

    peak_labels = {
        'early_morning': 'early morning', 'morning': 'morning',
        'afternoon': 'afternoon', 'evening': 'evening', 'late_night': 'late night'
    }

    theme_lines = []
    for t in (themes.get('themes') or [])[:5]:
        name = t.get('theme', '')
        pct = t.get('percentage', 0)
        theme_lines.append(f'  {name[:14]:<14} {bar(pct, 10)} {pct}%')

    emo_bd = emo.get('breakdown', {})
    ts = datetime.now().strftime('%B %-d, %Y')

    lines = [
        center('* R E F L E C T *'),
        center('Media Consumption Report'),
        divider(),
        center(f'Week of {ts}'),
        divider(),
        center(clean(report.get('report_id', 'User'))),
        center(user.get('overall_label', '')),
        divider(),
        'CONTENT THEMES',
        divider(),
        *theme_lines,
        divider(),
        'SCORES',
        f"  Polarity:   {pol.get('score', 0)}/10  {pol.get('label', '')}",
        f"  Emotional:  {emo.get('score', 0)}/10  {emo.get('label', '')}",
        f"  Diversity:  {echo.get('score', 0)}/10  {echo.get('label', '')}",
        divider(),
        'BEHAVIOUR SNAPSHOT',
        f"  Peak hours:   {peak_labels.get(summary.get('peak_hours', ''), '—')}",
        f"  Like rate:    {summary.get('like_rate', 0)}%",
        f"  Save rate:    {summary.get('save_rate', 0)}%",
        f"  Avg session:  {summary.get('avg_session_videos', 0)} videos",
        divider(),
        'EMOTIONAL TONE',
        f"  Positive:  {bar(emo_bd.get('positive', 0))}  {emo_bd.get('positive', 0)}%",
        f"  Neutral:   {bar(emo_bd.get('neutral', 0))}  {emo_bd.get('neutral', 0)}%",
        f"  Polarized: {bar(emo_bd.get('polarizing', 0))}  {emo_bd.get('polarizing', 0)}%",
        divider(),
        'INSIGHT',
        wrap(ps.get('headline', '')),
        '',
        truncate_words(ps.get('line1', ''), 30),
        truncate_words(ps.get('line2', ''), 30),
        divider(),
        'RECOMMENDATION',
        truncate_words(ps.get('recommendation', ''), 40),
        divider(),
        'REFLECTION',
        'does your digital world feel intentional?',
        '',
        'are you consuming or just scrolling?',
        footer()
    ]

    return '\n'.join(lines)

# ── Blend receipt ──────────────────────────────────────
def format_blend(blend_data: dict, reports: list = None) -> str:
    ba = blend_data.get('blend_analysis', blend_data)
    names = blend_data.get('members', ba.get('members', []))
    ps = ba.get('print_summary', {})
    cp = ba.get('closest_pair', {})
    fp = ba.get('furthest_pair', {})
    shared_themes = ba.get('shared_themes', [])
    diverging_themes = ba.get('diverging_themes', [])
    comparisons = ba.get('member_comparisons', [])
    key_themes = ba.get('key_common_themes', [])
    group_summary = ba.get('group_summary', '')

    lines = [
        header(),
        divider(),
        center('GROUP BLEND'),
        center(f'{len(names)} People'),
        divider(),
        'GROUP OVERLAP',
        overlap_bars(names, comparisons),
        divider(),
        'YOU ALL SEE',
        *[f'* {t}' for t in key_themes[:5]],
        divider(),
        'CONTENT DIFFERENCES',
        content_differences_section(names, diverging_themes),
        divider(),
        'ALIGNMENT MATRIX',
        alignment_matrix(names, shared_themes, diverging_themes),
        divider(),
        'BEHAVIOUR SNAPSHOT',
        behaviour_section(names, reports or []),
        divider(),
        'EMOTIONAL TONE',
        emotional_tone_section(names, reports or []),
        divider(),
        'RELATIONSHIP DISTANCE',
        relationship_distance(names, comparisons),
        divider(),
        'KEY INSIGHTS',
    ]

    if cp.get('members'):
        lines.append(f'Most aligned:   {" & ".join([clean(n) for n in cp["members"]])}')
    if fp.get('members'):
        lines.append(f'Most different: {" & ".join([clean(n) for n in fp["members"]])}')

    if group_summary:
        lines += ['', truncate_words(group_summary, 50)]

    lines += [
        divider(),
        'GROUP INSIGHT',
        center(ps.get('headline', '')),
        '',
        truncate_words(
            ' '.join(filter(None, [
                ps.get('line1', ''),
                ps.get('line2', ''),
                ps.get('recommendation', '')
            ])),
            50
        ),
        divider(),
        'REFLECTION',
        'does your digital world feel',
        'shared or separate?',
        '',
        'are you seeing the same ideas,',
        'or different versions of them?',
        footer()
    ]

    return '\n'.join(lines)