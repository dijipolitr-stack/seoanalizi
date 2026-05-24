"""
SEO Analyzer Bot — Ana Giriş Noktası
========================================
Potansiyel müşterilerin sitelerini SEO açısından analiz eden
ve detaylı PDF raporlar üreten bot.

Kullanım:
    python seo_main.py https://example.com
    python seo_main.py example.com --max-pages 100
    python seo_main.py example.com --no-llm
    python seo_main.py example.com --output ./raporlar
"""
import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent))

from seo_config import SEOConfig
from analyzer.site_crawler import SiteCrawler, CrawlResult
from analyzer.technical_seo import TechnicalSEOAnalyzer, TechnicalSEOResult
from analyzer.onpage_seo import OnPageSEOAnalyzer, OnPageSEOResult
from analyzer.scoring import generate_actions_from_issues, SEOAction
from analyzer.serp_checker import SERPChecker
from analyzer.competitor_analyzer import CompetitorAnalyzer
from analyzer.backlink_estimator import BacklinkEstimator
from llm.openai_analyzer import LLMSEOAnalyzer
from report.pdf_generator import generate_full_audit_pdf, generate_all_reports

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _serialize(obj):
    """Dataclass'ları dict'e çevirir (JSON serialization için)."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    elif isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


def run_analysis(
    url: str,
    max_pages: int = None,
    use_llm: bool = True,
    output_dir: str = None,
) -> dict:
    """
    Tam SEO analizi çalıştırır.

    Args:
        url: Hedef site URL'i
        max_pages: Taranacak maksimum sayfa sayısı
        use_llm: LLM analizi kullanılsın mı?
        output_dir: Rapor çıktı dizini

    Returns:
        Analiz sonuçları dict'i
    """
    start_time = time.time()

    # ── Ayarlar ──
    if max_pages:
        SEOConfig.CRAWL_MAX_PAGES = max_pages
    if output_dir:
        SEOConfig.REPORT_OUTPUT_DIR = output_dir

    # URL normalize
    if not url.startswith("http"):
        url = f"https://{url}"

    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    slug = domain.replace(".", "-").replace("www-", "")

    logger.info("=" * 60)
    logger.info(f"🚀 SEO ANALİZ BOTU — {domain}")
    logger.info("=" * 60)

    # ── FAZ 1: Site Crawl ──
    logger.info("")
    logger.info("━━━ FAZ 1: Site Tarama ━━━")
    crawler = SiteCrawler()
    crawl_result = crawler.crawl(url)

    if not crawl_result.pages:
        logger.error("❌ Hiçbir sayfa taranamadı! Site erişilemez olabilir.")
        return {"error": "Site erişilemez"}

    logger.info(
        f"  ✅ {len(crawl_result.pages)} sayfa tarandı, "
        f"{crawl_result.crawl_duration:.1f}s sürdü"
    )

    # ── FAZ 2: Teknik SEO Analizi ──
    logger.info("")
    logger.info("━━━ FAZ 2: Teknik SEO Analizi ━━━")
    tech_analyzer = TechnicalSEOAnalyzer()
    tech_result = tech_analyzer.analyze(crawl_result)

    # ── FAZ 3: On-Page SEO Analizi ──
    logger.info("")
    logger.info("━━━ FAZ 3: On-Page SEO Analizi ━━━")
    onpage_analyzer = OnPageSEOAnalyzer()
    onpage_result = onpage_analyzer.analyze(crawl_result)

    # ── FAZ 4: ICE Skorlama ──
    logger.info("")
    logger.info("━━━ FAZ 4: Aksiyon Önceliklendirme (ICE) ━━━")
    actions = generate_actions_from_issues(
        tech_result.issues,
        onpage_result.issues,
    )

    p0_count = sum(1 for a in actions if a.priority == "P0")
    p1_count = sum(1 for a in actions if a.priority == "P1")
    p2_count = sum(1 for a in actions if a.priority == "P2")

    logger.info(
        f"  📋 {len(actions)} aksiyon oluşturuldu: "
        f"P0={p0_count} | P1={p1_count} | P2={p2_count}"
    )

    # ── FAZ 4.5: Pozisyon, Rakip ve Backlink Analizi ──
    logger.info("")
    logger.info("━━━ FAZ 4.5: Pozisyon & Rakip & Backlink ━━━")
    
    serp_checker = SERPChecker()
    serp_result = serp_checker.check_rankings(domain)
    
    comp_analyzer = CompetitorAnalyzer()
    comp_result = comp_analyzer.analyze({
        "overall_score": (tech_result.score + onpage_result.score) / 2,
        "avg_load_time": tech_result.speed_analysis.get("avg_load_time", 0),
        "schema_coverage": tech_result.schema_analysis.get("coverage_percent", 0),
        "technical_score": tech_result.score
    })
    
    backlink_estimator = BacklinkEstimator()
    backlink_result = backlink_estimator.analyze(domain, crawl_result)

    # ── FAZ 5: LLM Derinlemesine Analiz ──
    llm_texts = {}
    if use_llm and SEOConfig.OPENAI_API_KEY:
        logger.info("")
        logger.info("━━━ FAZ 5: LLM Derinlemesine Analiz (OpenAI) ━━━")
        llm = LLMSEOAnalyzer()

        # Veri hazırlığı
        site_summary = {
            "domain": domain,
            "pages_crawled": len(crawl_result.pages),
            "technical_score": tech_result.score,
            "onpage_score": onpage_result.score,
            "ssl_valid": crawl_result.ssl_valid,
            "robots_accessible": crawl_result.robots_accessible,
            "sitemap_accessible": crawl_result.sitemap_accessible,
            "avg_word_count": onpage_result.content_stats.avg_word_count,
            "thin_content_count": len(onpage_result.content_stats.thin_content_pages),
            "eeat_score": onpage_result.eeat_signals.score,
            "eeat_signals": onpage_result.eeat_signals.signals,
            "schema_coverage": tech_result.schema_analysis.get("coverage_percent", 0),
            "schema_types": tech_result.schema_analysis.get("schema_types", {}),
            "avg_load_time": tech_result.speed_analysis.get("avg_load_time", 0),
            "alt_coverage": onpage_result.content_stats.alt_coverage,
            "avg_internal_links": onpage_result.link_stats.avg_internal_links,
            "critical_issues": [
                i.title for i in tech_result.issues if i.severity == "CRITICAL"
            ],
            "warning_issues": [
                i.title for i in tech_result.issues if i.severity == "WARNING"
            ],
            "keyword_patterns": onpage_result.keyword_patterns,
            "serp_summary": serp_result.summary,
            "comp_metrics": comp_result["metrics"],
            "backlink_stats": {
                "da": backlink_result.domain_authority,
                "ref_domains": backlink_result.referring_domains
            }
        }

        # 1. Yönetici Özeti
        logger.info("  🤖 Yönetici özeti üretiliyor...")
        llm_texts["executive_summary"] = llm.generate_executive_summary(site_summary)

        # 2. Teknik Analiz (Multi-Stage)
        logger.info("  🤖 Teknik Altyapı analizi üretiliyor (Stage 1/5)...")
        tech_dict = _serialize(tech_result)
        tech_infra = llm.generate_technical_infrastructure(tech_dict)

        logger.info("  🤖 Site Mimarisi analizi üretiliyor (Stage 2/5)...")
        site_arch = llm.generate_site_architecture(tech_dict)

        logger.info("  🤖 Performans ve UX analizi üretiliyor (Stage 3/5)...")
        perf_ux = llm.generate_performance_and_ux(tech_dict)

        llm_texts["technical_analysis"] = f"{tech_infra}\n\n{site_arch}\n\n{perf_ux}"

        # 3. İçerik Stratejisi (Multi-Stage)
        logger.info("  🤖 On-Page SEO analizi üretiliyor (Stage 4/5)...")
        content_data = {
            "content_stats": _serialize(onpage_result.content_stats),
            "link_stats": _serialize(onpage_result.link_stats),
            "eeat_signals": _serialize(onpage_result.eeat_signals),
            "title_analysis": onpage_result.title_analysis,
            "keyword_patterns": onpage_result.keyword_patterns,
            "sample_titles": [p.title for p in crawl_result.pages[:20] if p.title],
            "sample_h1s": [p.h1[0] for p in crawl_result.pages[:20] if p.h1],
        }
        onpage_seo = llm.generate_onpage_seo(content_data)

        logger.info("  🤖 Blog ve E-E-A-T analizi üretiliyor (Stage 5/5)...")
        content_strat = llm.generate_content_strategy(content_data)

        llm_texts["content_strategy"] = f"{onpage_seo}\n\n{content_strat}"

        # 4. Aksiyon Önerileri / Yol Haritası (Multi-Stage)
        logger.info("  🤖 Yol Haritası Metodolojisi üretiliyor...")
        issues_data = {
            "technical": [_serialize(i) for i in tech_result.issues],
            "onpage": [_serialize(i) for i in onpage_result.issues],
        }
        actions_data = [_serialize(a) for a in actions]
        roadmap_methodology = llm.generate_roadmap_methodology(issues_data)
        
        logger.info("  🤖 Yol Haritası Aksiyonları üretiliyor...")
        roadmap_actions = llm.generate_roadmap_actions(actions_data)
        
        llm_texts["action_recommendations"] = f"{roadmap_methodology}\n\n{roadmap_actions}"

        # 5. Pozisyon Analizi (Multi-Stage)
        logger.info("  🤖 Pozisyon Raporu Yönetici Özeti üretiliyor...")
        serp_dict = _serialize(serp_result)
        pos_summary = llm.generate_position_executive_summary(serp_dict)
        
        logger.info("  🤖 Pozisyon Raporu Kategori Analizi üretiliyor...")
        pos_categories = llm.generate_position_category_analysis(serp_dict)
        
        llm_texts["position_analysis"] = f"{pos_summary}\n\n{pos_categories}"

        # 6. Etki Analizi (Multi-Stage)
        logger.info("  🤖 Etki Raporu Zaman Çizelgesi üretiliyor...")
        impact_data = {
            "comp_metrics": comp_result["metrics"],
            "backlink_stats": _serialize(backlink_result)
        }
        impact_timeline = llm.generate_impact_timeline(impact_data)
        
        logger.info("  🤖 Etki Raporu Finansal Analizi üretiliyor...")
        impact_financials = llm.generate_impact_financials(impact_data)
        
        llm_texts["impact_analysis"] = f"{impact_timeline}\n\n{impact_financials}"

        logger.info("  ✅ LLM analizi tamamlandı")
    else:
        if use_llm:
            logger.warning("  ⚠️ GROQ_API_KEY tanımlı değil — LLM analizi atlandı")
        else:
            logger.info("  ⏭️ LLM analizi devre dışı (--no-llm)")

    # ── FAZ 6: Rapor Üretimi ──
    logger.info("")
    logger.info("━━━ FAZ 6: Rapor Üretimi ━━━")

    report_dir = SEOConfig.REPORT_OUTPUT_DIR
    os.makedirs(report_dir, exist_ok=True)

    crawl_dict = _serialize(crawl_result)
    tech_dict = _serialize(tech_result)
    onpage_dict = _serialize(onpage_result)
    actions_list = [_serialize(a) for a in actions]

    generate_full_audit_pdf(
        domain=domain,
        crawl_data=crawl_dict,
        technical_result=tech_dict,
        onpage_result=onpage_dict,
        actions=actions_list,
        llm_texts=llm_texts,
        output_path=os.path.join(report_dir, f"{slug}-tam-seo-raporu.pdf"),
    )

    # Article Intelligence verisi varsa pozisyon raporuna ekle
    ai_data = None
    ai_json_path = os.path.join(report_dir, f"{slug}-article-intelligence.json")
    if os.path.exists(ai_json_path):
        try:
            with open(ai_json_path, encoding="utf-8") as _f:
                ai_data = json.load(_f)
            logger.info(f"  📄 Article Intelligence verisi yüklendi: {ai_json_path}")
        except Exception:
            pass

    # 4 raporu birden üret (Pozisyon, Etki ve Yol Haritası dahil)
    generate_all_reports(
        domain=domain,
        crawl_data=crawl_dict,
        technical_result=tech_dict,
        onpage_result=onpage_dict,
        serp_result=_serialize(serp_result),
        comp_result=comp_result,
        backlink_result=_serialize(backlink_result),
        actions=actions_list,
        llm_texts=llm_texts,
        output_dir=report_dir,
        article_intelligence_data=ai_data,
    )

    # JSON veri çıktısı da kaydet (debug/ileride kullanım için)
    json_path = os.path.join(report_dir, f"{slug}-analiz-verisi.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "domain": domain,
            "analysis_date": datetime.now().isoformat(),
            "crawl_summary": {
                "pages_crawled": len(crawl_result.pages),
                "duration": crawl_result.crawl_duration,
                "ssl_valid": crawl_result.ssl_valid,
                "robots_accessible": crawl_result.robots_accessible,
                "sitemap_accessible": crawl_result.sitemap_accessible,
            },
            "technical_seo": tech_dict,
            "onpage_seo": onpage_dict,
            "actions": actions_list,
        }, f, ensure_ascii=False, indent=2)

    # ── SONUÇ ──
    elapsed = time.time() - start_time
    overall_score = (tech_result.score + onpage_result.score) / 2

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✅ ANALİZ TAMAMLANDI — {elapsed:.1f} saniye")
    logger.info("=" * 60)
    logger.info(f"  📊 Genel SEO Skoru: {overall_score:.0f}/100")
    logger.info(f"     Teknik: {tech_result.score:.0f}/100 | On-Page: {onpage_result.score:.0f}/100")
    logger.info(f"  🔴 Kritik sorun: {sum(1 for i in tech_result.issues if i.severity == 'CRITICAL')}")
    logger.info(f"  ⚠️ Uyarı: {sum(1 for i in tech_result.issues if i.severity == 'WARNING')}")
    logger.info(f"  📋 Aksiyon sayısı: {len(actions)} (P0: {p0_count})")
    logger.info(f"  📄 Raporlar: {os.path.abspath(report_dir)}/")
    logger.info("")

    return {
        "domain": domain,
        "overall_score": overall_score,
        "technical_score": tech_result.score,
        "onpage_score": onpage_result.score,
        "actions_count": len(actions),
        "report_dir": os.path.abspath(report_dir),
        "elapsed": elapsed,
    }


def main():
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(
        description="🔍 SEO Analiz Botu — Web sitelerini SEO açısından analiz eder ve detaylı rapor üretir.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python seo_main.py lastikborsasi.com
  python seo_main.py https://example.com --max-pages 100
  python seo_main.py example.com --no-llm --output ./raporlar
        """
    )

    parser.add_argument(
        "url",
        help="Analiz edilecek web sitesinin URL'i (örn: example.com)"
    )
    parser.add_argument(
        "--max-pages", "-m",
        type=int,
        default=50,
        help="Taranacak maksimum sayfa sayısı (varsayılan: 50)"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM (Groq) analizini devre dışı bırak"
    )
    parser.add_argument(
        "--output", "-o",
        default="reports",
        help="Rapor çıktı dizini (varsayılan: reports)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Sayfa crawl arası bekleme süresi (saniye, varsayılan: 1.0)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Detaylı log çıktısı"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.delay:
        SEOConfig.CRAWL_DELAY = args.delay

    try:
        result = run_analysis(
            url=args.url,
            max_pages=args.max_pages,
            use_llm=not args.no_llm,
            output_dir=args.output,
        )

        if "error" in result:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\n⏹️ Analiz iptal edildi.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Beklenmeyen hata: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
