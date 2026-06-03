"""
GEO Görünürlük Analizi — Ana Giriş Noktası
==========================================
SEO analizinin (seo_main.py) kardeşi. Yapay zeka aramalarında (ChatGPT, Gemini,
Perplexity, Google AI Overviews) sitenin görünürlüğünü ölçer ve rapor üretir.

Akış: siteyi tara → başlıklardan sorgu türet → yapay zekaya sor → görünürlüğü ölç
      → aksiyon planı (satış reçetesi) → reports/{slug}-geo-gorunurluk-raporu.pdf

Kullanım:
    python geo_main.py lastikborsasi.com
    python geo_main.py example.com --queries 20
    python geo_main.py example.com --max-pages 30
"""
import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from seo_config import SEOConfig
from analyzer.site_crawler import SiteCrawler
from analyzer.geo_visibility import (
    run_audit, generate_action_plan, derive_queries_from_site,
    build_geo_report_markdown, brand_token, geo_openai_key, openai_diagnostic,
)
from report.pdf_generator import _generate_generic_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s │ %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def _write_status(report_dir: str, slug: str, status: dict):
    """Çalışma durumunu/hatayı reports/ içine görünür biçimde yazar (panelden okunabilir)."""
    try:
        os.makedirs(report_dir, exist_ok=True)
        status["timestamp"] = datetime.now().isoformat()
        with open(os.path.join(report_dir, f"{slug}-geo-status.json"), "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_geo_analysis(url: str, num_queries: int = 15, max_pages: int = 25,
                     use_plan: bool = True, output_dir: str = None) -> dict:
    start = time.time()
    if output_dir:
        SEOConfig.REPORT_OUTPUT_DIR = output_dir
    SEOConfig.CRAWL_MAX_PAGES = max_pages

    if not url.startswith("http"):
        url = f"https://{url}"
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    slug = domain.replace(".", "-").replace("www-", "")
    brand = brand_token(domain).capitalize()

    logger.info("=" * 60)
    logger.info(f"🤖 GEO GÖRÜNÜRLÜK ANALİZİ — {domain}")
    logger.info("=" * 60)

    if not geo_openai_key():
        logger.error("❌ OpenAI anahtarı tanımlı değil — GEO analizi yapılamaz.")
        _write_status(SEOConfig.REPORT_OUTPUT_DIR, slug,
                      {"ok": False, "phase": "key", "error": "OpenAI anahtarı yok",
                       "diagnostic": openai_diagnostic()})
        return {"error": "OpenAI anahtarı yok"}

    # Anahtarın GEO (web arama) için gerçekten çalıştığını baştan test et
    diag = openai_diagnostic()
    if not diag.get("ok"):
        logger.error(f"❌ OpenAI web arama testi başarısız: {diag}")
        _write_status(SEOConfig.REPORT_OUTPUT_DIR, slug,
                      {"ok": False, "phase": "openai_web_search", "error": "Web arama çalışmıyor",
                       "diagnostic": diag})
        return {"error": f"OpenAI web arama çalışmıyor: {diag.get('detail', '')[:120]}"}

    # ── FAZ 1: Site tarama (sorgu türetmek için) ──
    logger.info("")
    logger.info("━━━ FAZ 1: Site Tarama ━━━")
    crawler = SiteCrawler()
    crawl_result = crawler.crawl(url)
    if not crawl_result.pages:
        logger.error("❌ Hiçbir sayfa taranamadı, site erişilemez olabilir.")
        _write_status(SEOConfig.REPORT_OUTPUT_DIR, slug,
                      {"ok": False, "phase": "crawl", "error": "Site erişilemez / sayfa taranamadı"})
        return {"error": "Site erişilemez"}
    titles = [p.title for p in crawl_result.pages if p.title]
    h1s = [p.h1[0] for p in crawl_result.pages if p.h1]
    logger.info(f"  ✅ {len(crawl_result.pages)} sayfa, {len(titles)} başlık toplandı")

    # ── FAZ 2: Sorgu türetme ──
    logger.info("")
    logger.info("━━━ FAZ 2: Sorgu Türetme (siteden, LLM) ━━━")
    queries = derive_queries_from_site(domain, titles, h1s, geo_openai_key(), limit=num_queries)
    if not queries:
        logger.error("❌ Sorgu türetilemedi.")
        _write_status(SEOConfig.REPORT_OUTPUT_DIR, slug,
                      {"ok": False, "phase": "derive_queries",
                       "error": "Sorgu türetilemedi (LLM boş döndü)", "diagnostic": openai_diagnostic()})
        return {"error": "Sorgu türetilemedi"}
    logger.info(f"  ✅ {len(queries)} sorgu türetildi")

    # ── FAZ 3: Yapay zeka görünürlük denetimi ──
    logger.info("")
    logger.info("━━━ FAZ 3: Yapay Zeka Görünürlük Denetimi ━━━")
    audit = run_audit(brand, domain, queries)

    # ── FAZ 4: Aksiyon planı ──
    action_plan = None
    if use_plan:
        logger.info("")
        logger.info("━━━ FAZ 4: Aksiyon Planı (satış reçetesi) ━━━")
        action_plan = generate_action_plan(audit)
        if action_plan:
            logger.info("  ✅ Aksiyon planı üretildi")

    # ── FAZ 5: Rapor üretimi ──
    logger.info("")
    logger.info("━━━ FAZ 5: Rapor Üretimi ━━━")
    report_dir = SEOConfig.REPORT_OUTPUT_DIR
    os.makedirs(report_dir, exist_ok=True)

    body_md = build_geo_report_markdown(audit, action_plan=action_plan)
    pdf_path = os.path.join(report_dir, f"{slug}-geo-gorunurluk-raporu.pdf")
    _generate_generic_pdf(domain, "GEO Görünürlük Raporu (Yapay Zeka Aramaları)", body_md, pdf_path,
                          header_suffix="GEO Görünürlük")

    json_path = os.path.join(report_dir, f"{slug}-geo-analiz-verisi.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "domain": domain,
            "analysis_date": datetime.now().isoformat(),
            "summary": audit["summary"],
            "top_sources": audit["top_sources"],
            "queries": queries,
            "results": [vars(r) for r in audit["results"]],
        }, f, ensure_ascii=False, indent=2)

    s = audit["summary"]
    _write_status(report_dir, slug, {"ok": True, "phase": "done", "summary": s,
                                     "report": f"{slug}-geo-gorunurluk-raporu.pdf"})
    elapsed = time.time() - start
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✅ GEO ANALİZİ TAMAMLANDI — {elapsed:.1f} saniye")
    logger.info("=" * 60)
    logger.info(f"  🤖 Marka cevapta: {s['brand_in_answer']}/{s['answered']} (%{s['brand_in_answer_pct']})")
    logger.info(f"  🔗 Kaynak gösterildi: {s['domain_cited']}/{s['answered']} (%{s['domain_cited_pct']})")
    logger.info(f"  📄 Rapor: {os.path.abspath(pdf_path)}")
    logger.info("")

    return {"domain": domain, "summary": s, "report_pdf": os.path.abspath(pdf_path),
            "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(
        description="🤖 GEO Görünürlük Analizi — Yapay zeka aramalarında site görünürlüğü.")
    parser.add_argument("url", help="Analiz edilecek site (örn: example.com)")
    parser.add_argument("--queries", "-q", type=int, default=15, help="Test sorgu sayısı (varsayılan 15)")
    parser.add_argument("--max-pages", "-m", type=int, default=25, help="Taranacak max sayfa (varsayılan 25)")
    parser.add_argument("--no-plan", action="store_true", help="Aksiyon planı üretme")
    parser.add_argument("--output", "-o", default="reports", help="Rapor çıktı dizini")
    args = parser.parse_args()

    try:
        result = run_geo_analysis(
            url=args.url, num_queries=args.queries, max_pages=args.max_pages,
            use_plan=not args.no_plan, output_dir=args.output,
        )
        if "error" in result:
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n⏹️ İptal edildi.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Beklenmeyen hata: {e}", exc_info=True)
        try:
            dom = args.url.replace("https://", "").replace("http://", "").split("/")[0]
            slug = dom.replace(".", "-").replace("www-", "")
            _write_status(SEOConfig.REPORT_OUTPUT_DIR, slug,
                          {"ok": False, "phase": "exception", "error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
