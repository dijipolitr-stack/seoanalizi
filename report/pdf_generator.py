"""
SEO Analyzer — PDF Rapor Üretici
==================================
Markdown verilerini HTML şablonları + playwright ile profesyonel PDF raporlara dönüştürür.
4 rapor tipi: Full Audit, Pozisyon, Etki, Yol Haritası.
"""
import os
import logging
from datetime import datetime
from pathlib import Path
import markdown
from playwright.sync_api import sync_playwright

from seo_config import SEOConfig

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

def _get_report_css() -> str:
    """Rapor CSS stilleri (Markdown destekli, referans PDF stiline uygun)."""
    return """
    @page {
        margin: 2cm 1.5cm;
        size: A4;
        @top-right {
            content: "Lastikborsasi.com SEO Audit"; /* TODO: Dinamik yapılabilir, ama sağ üst gri başlık */
            font-size: 9pt;
            color: #999;
        }
        @bottom-center {
            content: "Sayfa " counter(page) " / " counter(pages);
            font-size: 10pt;
            color: #999;
        }
    }

    * { box-sizing: border-box; }

    body {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
        color: #2c3e50;
        line-height: 1.6;
        font-size: 11pt;
        max-width: 100%;
        margin: 0;
        padding: 0;
    }

    /* Ana Başlık */
    .main-title {
        text-align: center;
        font-size: 26pt;
        font-weight: bold;
        color: #0d2040;
        margin-top: 1cm;
        margin-bottom: 0.3cm;
    }

    .main-title-divider {
        border-bottom: 3px solid #d4af37;
        margin: 0 auto 1cm auto;
        width: 100%;
    }

    /* Meta kutusu (Hazırlayan vs) */
    .meta-box {
        background-color: #fcf9f2;
        border-left: 6px solid #d4af37;
        padding: 15px 20px;
        margin-bottom: 30px;
        font-size: 10.5pt;
        color: #555;
        font-style: italic;
    }
    
    .meta-box strong {
        font-style: normal;
        color: #333;
    }

    /* Başlık 1 (H1) - Sarı sol çizgili bej kutu */
    h1 {
        background-color: #fcf9f2;
        border-left: 8px solid #d4af37;
        color: #0d2040;
        font-size: 16pt;
        font-weight: bold;
        padding: 12px 15px;
        margin-top: 2em;
        margin-bottom: 1em;
        text-transform: uppercase;
        page-break-after: avoid;
    }

    /* Başlık 2 (H2) - Lacivert metin */
    h2 {
        color: #0d2040;
        font-size: 14pt;
        font-weight: bold;
        margin-top: 1.5em;
        margin-bottom: 0.8em;
        page-break-after: avoid;
    }

    /* Başlık 3 (H3) */
    h3 {
        color: #2c3e50;
        font-size: 12pt;
        margin-top: 1.2em;
        margin-bottom: 0.5em;
        page-break-after: avoid;
    }

    /* Satır içi kod (inline code) - Kırmızımsı arka plan */
    code {
        background-color: #faebeb;
        color: #c0392b;
        padding: 2px 6px;
        border-radius: 3px;
        font-family: Consolas, monospace;
        font-size: 10pt;
    }
    
    pre code {
        background-color: transparent;
        color: inherit;
        padding: 0;
    }

    pre {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #e9ecef;
        overflow-x: auto;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        font-size: 10.5pt;
        page-break-inside: avoid;
    }

    td, th {
        padding: 10px 14px;
        border-bottom: 1px solid #e0e0e0;
        text-align: left;
    }
    
    th {
        background: #fcf9f2;
        color: #0d2040;
        font-weight: bold;
        border-bottom: 2px solid #d4af37;
    }

    tr:nth-child(even) {
        background: #fafafa;
    }

    p {
        margin-bottom: 1.2em;
        orphans: 3;
        widows: 3;
    }
    
    ul, ol {
        margin-bottom: 1.2em;
        padding-left: 25px;
    }
    
    li {
        margin-bottom: 6px;
    }

    strong {
        color: #0d2040;
    }
    """

def _save_as_pdf(html: str, output_path: str):
    """Playwright kullanarak HTML'i PDF'e dönüştürür."""
    # HTML'i debug için de kaydedelim
    html_path = output_path.replace(".pdf", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # HTML string olarak yükle
            page.set_content(html, wait_until="networkidle")
            # PDF olarak kaydet
            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"}
            )
            browser.close()
    except Exception as e:
        logger.error(f"❌ Playwright PDF üretim hatası: {e}")
        logger.warning(f"⚠️ HTML olarak bırakıldı: {html_path}")

def _generate_generic_pdf(domain: str, title: str, markdown_text: str, output_path: str):
    """Ortak Markdown to PDF generator."""
    now = datetime.now().strftime("%d %B %Y")
    
    # Markdown'u HTML'e çevir
    html_body = markdown.markdown(
        markdown_text, 
        extensions=['tables', 'fenced_code', 'nl2br']
    )
    
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>{domain} — {title}</title>
<style>
{_get_report_css()}
/* Header sağ üst metni PDF motoru için */
@page {{
    @top-right {{
        content: "{domain} SEO Audit";
        font-size: 9pt;
        color: #aaa;
    }}
}}
</style>
</head>
<body>

<div class="main-title">
    {domain} — {title}
</div>
<div class="main-title-divider"></div>

<div class="meta-box">
    <strong>Hazırlayan:</strong> {SEOConfig.COMPANY_NAME} Uzman Analizi &nbsp;&nbsp;&nbsp; 
    <strong>Tarih:</strong> {now} &nbsp;&nbsp;&nbsp; 
    <strong>Yöntem:</strong> Akıllı Watchdog Bot Crawler, OpenAI (GPT-4o) ve SERP Analizi Entegrasyonu üzerinden üretilmiştir.
</div>

{html_body}

</body>
</html>
"""
    _save_as_pdf(html, output_path)
    logger.info(f"📄 {title} oluşturuldu: {output_path}")

def generate_full_audit_pdf(
    domain: str,
    crawl_data: dict,
    technical_result: dict,
    onpage_result: dict,
    actions: list,
    llm_texts: dict,
    output_path: str,
):
    """360° SEO Audit Raporu PDF'i üretir."""
    
    # Tüm LLM bölümlerini birleştir
    combined_md = f"""
{llm_texts.get('executive_summary', 'Analiz bulunamadı.')}

{llm_texts.get('technical_analysis', '')}

{llm_texts.get('content_strategy', '')}
"""
    _generate_generic_pdf(domain, "360° SEO Audit Raporu", combined_md, output_path)

def generate_position_report_pdf(domain, serp_result, llm_texts, output_path):
    """Google Pozisyon Ölçüm Raporu."""
    md_text = llm_texts.get('position_analysis', 'Pozisyon analizi bulunamadı.')
    _generate_generic_pdf(domain, "Google Pozisyon Ölçüm Raporu", md_text, output_path)

def generate_impact_report_pdf(domain, comp_result, backlink_result, llm_texts, output_path):
    """SEO Çalışmalarının Etki Raporu."""
    md_text = llm_texts.get('impact_analysis', 'Etki analizi bulunamadı.')
    _generate_generic_pdf(domain, "SEO Etki ve Rekabet Raporu", md_text, output_path)

def generate_roadmap_pdf(domain, actions, llm_texts, output_path):
    """12 Aylık SEO Yol Haritası."""
    md_text = llm_texts.get('action_recommendations', 'Yol haritası bulunamadı.')
    _generate_generic_pdf(domain, "12 Aylık SEO Yol Haritası", md_text, output_path)

def generate_all_reports(
    domain: str,
    crawl_data: dict,
    technical_result: dict,
    onpage_result: dict,
    serp_result: dict,
    comp_result: dict,
    backlink_result: dict,
    actions: list,
    llm_texts: dict,
    output_dir: str,
):
    """4 raporun hepsini üretir."""
    os.makedirs(output_dir, exist_ok=True)
    slug = domain.replace(".", "-").replace("www-", "")

    # Rapor 1: Full Audit
    generate_full_audit_pdf(
        domain=domain,
        crawl_data=crawl_data,
        technical_result=technical_result,
        onpage_result=onpage_result,
        actions=actions,
        llm_texts=llm_texts,
        output_path=os.path.join(output_dir, f"{slug}-tam-seo-raporu.pdf"),
    )

    # Rapor 2: Pozisyon Raporu
    generate_position_report_pdf(
        domain=domain,
        serp_result=serp_result,
        llm_texts=llm_texts,
        output_path=os.path.join(output_dir, f"{slug}-pozisyon-raporu.pdf"),
    )

    # Rapor 3: Etki Raporu
    generate_impact_report_pdf(
        domain=domain,
        comp_result=comp_result,
        backlink_result=backlink_result,
        llm_texts=llm_texts,
        output_path=os.path.join(output_dir, f"{slug}-etki-raporu.pdf"),
    )

    # Rapor 4: Yol Haritası (Roadmap)
    generate_roadmap_pdf(
        domain=domain,
        actions=actions,
        llm_texts=llm_texts,
        output_path=os.path.join(output_dir, f"{slug}-yol-haritasi.pdf"),
    )

    logger.info(f"✅ Tüm raporlar {output_dir}/ dizinine kaydedildi")
