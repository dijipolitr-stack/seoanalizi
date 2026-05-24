"""
Article Intelligence — HTML Rapor Üretici
==========================================
Analiz sonucunu güzel, yazdırılabilir bir HTML raporuna dönüştürür.
Top 5 makale + tüm kelimeler ayrı bölümlerde gösterilir.
"""
from datetime import datetime
from collections import Counter


def generate_html_report(data: dict) -> str:
    """
    ArticleIntelligence.to_json() çıktısını alıp HTML rapor döner.
    data: {domain, top_articles, total_sitemap_urls, analysis_duration_sec, ...}
    """
    domain = data.get("domain", "")
    articles = data.get("top_articles", [])
    top5 = articles[:5]
    total_sitemap = data.get("total_sitemap_urls", 0)
    duration = data.get("analysis_duration_sec", 0)
    generated_at = datetime.now().strftime("%d %B %Y, %H:%M")

    # ── Tüm kelime havuzu (top 5 makaleden) ──────────────────────────────────
    all_primary    = []
    all_secondary  = []
    all_lsi        = []
    all_gaps       = []

    for a in top5:
        all_primary.extend(a.get("primary_keywords", []))
        all_secondary.extend(a.get("secondary_keywords", []))
        all_lsi.extend(a.get("lsi_keywords", []))
        all_gaps.extend(a.get("content_gaps", []))

    # Tekrarları say ve sırala
    primary_counter   = Counter(all_primary)
    secondary_counter = Counter(all_secondary)
    lsi_counter       = Counter(all_lsi)
    gaps_counter      = Counter(all_gaps)

    # ── HTML oluştur ──────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Article Intelligence Raporu — {domain}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #21262d;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --blue: #58a6ff;
    --green: #3fb950;
    --yellow: #d29922;
    --purple: #bc8cff;
    --red: #f85149;
    --orange: #db6d28;
  }}

  body {{
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 40px 24px;
    max-width: 960px;
    margin: 0 auto;
    font-size: 14px;
    line-height: 1.6;
  }}

  /* ── Header ── */
  .report-header {{
    border-bottom: 2px solid var(--blue);
    padding-bottom: 24px;
    margin-bottom: 32px;
  }}
  .report-header .label {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--blue);
    margin-bottom: 8px;
  }}
  .report-header h1 {{
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 4px;
  }}
  .report-header .domain-url {{
    color: var(--blue);
    font-size: 16px;
    font-weight: 600;
  }}
  .meta-row {{
    display: flex;
    gap: 24px;
    margin-top: 16px;
    flex-wrap: wrap;
  }}
  .meta-item {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
  }}
  .meta-item .val {{
    font-weight: 700;
    font-size: 18px;
    color: var(--blue);
    display: block;
  }}
  .meta-item .lbl {{ color: var(--muted); }}

  /* ── Section ── */
  .section {{
    margin-bottom: 40px;
  }}
  .section-title {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  /* ── Article Cards ── */
  .article-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    position: relative;
  }}
  .article-card:hover {{ border-color: var(--blue); }}

  .article-rank {{
    position: absolute;
    top: 16px;
    right: 16px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
  }}

  .article-title {{
    font-size: 17px;
    font-weight: 700;
    margin-bottom: 4px;
    padding-right: 60px;
  }}
  .article-url {{
    color: var(--muted);
    font-size: 12px;
    text-decoration: none;
    display: block;
    margin-bottom: 12px;
    word-break: break-all;
  }}
  .article-url:hover {{ color: var(--blue); }}

  .article-stats {{
    display: flex;
    gap: 16px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }}
  .stat {{
    font-size: 12px;
    color: var(--muted);
  }}
  .stat b {{ color: var(--text); }}

  .score-bar-wrap {{
    height: 4px;
    background: var(--surface2);
    border-radius: 2px;
    margin-bottom: 16px;
    overflow: hidden;
  }}
  .score-bar {{
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--blue), var(--purple));
    transition: width 0.4s ease;
  }}

  /* ── Keyword Groups ── */
  .kw-groups {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  @media (max-width: 600px) {{ .kw-groups {{ grid-template-columns: 1fr; }} }}

  .kw-group {{
    background: var(--surface2);
    border-radius: 8px;
    padding: 12px 14px;
  }}
  .kw-group .kw-group-title {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
  }}
  .kw-group.primary .kw-group-title   {{ color: var(--blue); }}
  .kw-group.secondary .kw-group-title {{ color: var(--green); }}
  .kw-group.lsi .kw-group-title       {{ color: var(--purple); }}
  .kw-group.gaps .kw-group-title      {{ color: var(--red); }}

  .tags {{ display: flex; flex-wrap: wrap; gap: 5px; }}
  .tag {{
    border-radius: 5px;
    font-size: 12px;
    padding: 3px 9px;
    font-weight: 500;
  }}
  .tag.primary   {{ background: #132032; color: var(--blue);   border: 1px solid #1f4a7a; }}
  .tag.secondary {{ background: #122316; color: var(--green);  border: 1px solid #1a472a; }}
  .tag.lsi       {{ background: #1e1535; color: var(--purple); border: 1px solid #3d2870; }}
  .tag.gap       {{ background: #2d1117; color: var(--red);    border: 1px solid #6e2020; font-style: italic; }}

  .intent-badge {{
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .intent-informational  {{ background: #132032; color: var(--blue); }}
  .intent-transactional  {{ background: #122316; color: var(--green); }}
  .intent-commercial     {{ background: #2d1f08; color: var(--yellow); }}
  .intent-navigational   {{ background: #1e1535; color: var(--purple); }}

  .summary-text {{
    font-size: 13px;
    color: var(--muted);
    border-left: 3px solid var(--border);
    padding-left: 12px;
    margin-top: 12px;
    font-style: italic;
  }}

  /* ── Consolidated Keyword Pool ── */
  .pool-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 600px) {{ .pool-grid {{ grid-template-columns: 1fr; }} }}

  .pool-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }}
  .pool-card h3 {{
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 12px;
  }}
  .pool-card.primary h3   {{ color: var(--blue); }}
  .pool-card.secondary h3 {{ color: var(--green); }}
  .pool-card.lsi h3       {{ color: var(--purple); }}
  .pool-card.gaps h3      {{ color: var(--red); }}

  .pool-item {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid var(--surface2);
    font-size: 13px;
  }}
  .pool-item:last-child {{ border-bottom: none; }}
  .pool-item .count {{
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
    background: var(--surface2);
    border-radius: 4px;
    padding: 1px 6px;
  }}
  .pool-item .count.multi {{ color: var(--blue); }}

  /* ── Footer ── */
  .report-footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}

  /* ── Print ── */
  @media print {{
    body {{ background: #fff; color: #111; padding: 20px; }}
    :root {{
      --bg: #fff; --surface: #f5f5f5; --surface2: #ebebeb;
      --border: #ddd; --text: #111; --muted: #555;
      --blue: #0066cc; --green: #1a7a2a; --purple: #5500aa;
      --red: #cc2200; --yellow: #996600;
    }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>

<!-- ── HEADER ── -->
<div class="report-header">
  <div class="label">🔍 Article Intelligence Raporu</div>
  <h1>Rakip İçerik Analizi</h1>
  <div class="domain-url">{domain}</div>

  <div class="meta-row">
    <div class="meta-item">
      <span class="val">{len(top5)}</span>
      <span class="lbl">Analiz Edilen Makale</span>
    </div>
    <div class="meta-item">
      <span class="val">{total_sitemap}</span>
      <span class="lbl">Toplam Sitemap URL</span>
    </div>
    <div class="meta-item">
      <span class="val">{len(set(all_primary + all_secondary + all_lsi))}</span>
      <span class="lbl">Benzersiz Kelime</span>
    </div>
    <div class="meta-item">
      <span class="val">{duration}s</span>
      <span class="lbl">Analiz Süresi</span>
    </div>
  </div>
</div>

<!-- ── TOP 5 MAKALELER ── -->
<div class="section">
  <div class="section-title">
    📄 Top 5 En Önemli Makale
  </div>

  {_render_articles(top5)}
</div>

<!-- ── KELİME HAVUZU ── -->
<div class="section">
  <div class="section-title">
    🔑 Tüm Kelime Havuzu (Top 5 Makaleden)
  </div>
  <div class="pool-grid">
    <div class="pool-card primary">
      <h3>🎯 Ana Anahtar Kelimeler</h3>
      {_render_pool(primary_counter, 'primary')}
    </div>
    <div class="pool-card secondary">
      <h3>📌 İkincil Kelimeler</h3>
      {_render_pool(secondary_counter, 'secondary')}
    </div>
    <div class="pool-card lsi">
      <h3>🧠 LSI / Semantik Kelimeler</h3>
      {_render_pool(lsi_counter, 'lsi')}
    </div>
    <div class="pool-card gaps">
      <h3>⚠️ İçerik Boşlukları (Fırsatlar)</h3>
      {_render_pool(gaps_counter, 'gap')}
    </div>
  </div>
</div>

<!-- ── FOOTER ── -->
<div class="report-footer">
  <span>Oluşturulma: {generated_at}</span>
  <span>SEO Analyzer — Article Intelligence</span>
  <button class="no-print" onclick="window.print()" style="
    background:#238636; border:none; border-radius:6px;
    color:#fff; cursor:pointer; font-family:inherit;
    font-size:12px; font-weight:600; padding:6px 14px;
  ">🖨 PDF Olarak Kaydet</button>
</div>

</body>
</html>"""
    return html


# ── Yardımcı render fonksiyonları ─────────────────────────────────────────────

def _render_articles(articles: list) -> str:
    html = ""
    for a in articles:
        score = a.get("importance_score", 0)
        score_pct = min(score, 100)
        intent = a.get("search_intent", "")
        intent_html = (
            f'<span class="intent-badge intent-{intent}">{intent}</span>'
            if intent else ""
        )
        summary = a.get("summary", "")
        last_updated = a.get("last_updated", "")[:10] if a.get("last_updated") else "—"

        html += f"""
<div class="article-card">
  <div class="article-rank">#{a.get('rank', '?')}</div>
  <div class="article-title">{a.get('title') or '(Başlık yok)'}</div>
  <a href="{a.get('url','')}" class="article-url" target="_blank">{a.get('url','')}</a>

  <div class="article-stats">
    <span class="stat"><b>{score}</b> önem skoru</span>
    <span class="stat"><b>{a.get('word_count', 0)}</b> kelime</span>
    <span class="stat">Güncelleme: <b>{last_updated}</b></span>
    {f'<span>{intent_html}</span>' if intent_html else ''}
  </div>

  <div class="score-bar-wrap">
    <div class="score-bar" style="width:{score_pct}%"></div>
  </div>

  <div class="kw-groups">
    <div class="kw-group primary">
      <div class="kw-group-title">🎯 Ana Kelimeler</div>
      <div class="tags">
        {_tags(a.get('primary_keywords', []), 'primary')}
      </div>
    </div>
    <div class="kw-group secondary">
      <div class="kw-group-title">📌 İkincil Kelimeler</div>
      <div class="tags">
        {_tags(a.get('secondary_keywords', []), 'secondary')}
      </div>
    </div>
    <div class="kw-group lsi">
      <div class="kw-group-title">🧠 LSI / Gizli Kelimeler</div>
      <div class="tags">
        {_tags(a.get('lsi_keywords', []), 'lsi')}
      </div>
    </div>
    <div class="kw-group gaps">
      <div class="kw-group-title">⚠️ İçerik Boşlukları</div>
      <div class="tags">
        {_tags(a.get('content_gaps', []), 'gap')}
      </div>
    </div>
  </div>

  {f'<div class="summary-text">{summary}</div>' if summary else ''}
</div>"""
    return html


def _tags(keywords: list, cls: str) -> str:
    if not keywords:
        return '<span style="color:#484f58; font-size:12px;">—</span>'
    return "".join(f'<span class="tag {cls}">{kw}</span>' for kw in keywords)


def _render_pool(counter: Counter, cls: str) -> str:
    if not counter:
        return '<div style="color:#484f58; font-size:12px; padding:8px 0;">Veri yok</div>'

    items = counter.most_common(20)
    html = ""
    for word, count in items:
        count_cls = "multi" if count > 1 else ""
        label = f"×{count}" if count > 1 else "×1"
        html += f"""
<div class="pool-item">
  <span>{word}</span>
  <span class="count {count_cls}">{label}</span>
</div>"""
    return html
