"""
SEO Analyzer — Konfigürasyon Modülü
====================================
Environment variable tabanlı merkezi ayarlar.
Groq LLM, SERP API ve crawl parametreleri.
"""
import os
import logging
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

logger = logging.getLogger(__name__)


class SEOConfig:
    """SEO Analyzer için merkezi konfigürasyon."""

    # ── OpenAI LLM ────────────────────────────────────────
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

    # ── SERP API (opsiyonel — yoksa LLM fallback) ────────
    SERP_API_KEY = os.environ.get("SERP_API_KEY", "")
    SERP_API_PROVIDER = os.environ.get("SERP_API_PROVIDER", "dataforseo")
    # dataforseo | serpapi | none

    # ── Crawl Ayarları ────────────────────────────────────
    CRAWL_MAX_PAGES = int(os.environ.get("CRAWL_MAX_PAGES", "50"))
    CRAWL_TIMEOUT = int(os.environ.get("CRAWL_TIMEOUT", "15"))
    CRAWL_DELAY = float(os.environ.get("CRAWL_DELAY", "1.0"))
    CRAWL_USER_AGENT = os.environ.get(
        "CRAWL_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    # ── Keyword Analiz ────────────────────────────────────
    DEFAULT_KEYWORD_COUNT = int(os.environ.get("DEFAULT_KEYWORD_COUNT", "30"))

    # ── Rapor Ayarları ────────────────────────────────────
    REPORT_LANGUAGE = os.environ.get("REPORT_LANGUAGE", "tr")
    REPORT_OUTPUT_DIR = os.environ.get("REPORT_OUTPUT_DIR", "reports")
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "SEO Analyzer")

    # ── E-E-A-T Kriterleri ────────────────────────────────
    EEAT_CRITERIA = [
        {"id": "company_info", "name": "Şirket bilgisi", "weight": 1.0},
        {"id": "management", "name": "Yönetim/ekip bilgisi", "weight": 0.8},
        {"id": "contact", "name": "Adres / iletişim", "weight": 1.0},
        {"id": "privacy", "name": "KVKK / Gizlilik Politikası", "weight": 0.9},
        {"id": "return_policy", "name": "İade / iptal politikası", "weight": 0.7},
        {"id": "terms", "name": "Üyelik / kullanım sözleşmesi", "weight": 0.6},
        {"id": "help_center", "name": "Yardım Merkezi", "weight": 0.5},
        {"id": "reviews", "name": "Müşteri yorumları", "weight": 1.0},
        {"id": "ssl", "name": "SSL / güvenlik", "weight": 1.0},
        {"id": "social_media", "name": "Sosyal medya hesapları", "weight": 0.7},
        {"id": "press", "name": "Basında çıkma", "weight": 0.6},
        {"id": "author_profiles", "name": "Yazar profilleri", "weight": 0.8},
        {"id": "editorial_policy", "name": "Editöryel ilke beyanı", "weight": 0.7},
    ]

    # ── ICE Scoring Eşik Değerleri ────────────────────────
    ICE_THRESHOLDS = {
        "P0": 70,   # ≥70 → "ŞİMDİ BAŞLAYIN"
        "P1": 50,   # 50-69 → "NEXT (3-6 ay)"
        "P2": 30,   # 30-49 → "SONRA (6-12 ay)"
        "P3": 0,    # <30 → "DİKKATLE"
    }

    @classmethod
    def validate(cls) -> bool:
        """Zorunlu konfigürasyon değerlerini kontrol eder."""
        warnings = []

        if not cls.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY tanımlı değil — LLM analizi devre dışı")

        if not cls.SERP_API_KEY:
            warnings.append(
                "SERP_API_KEY tanımlı değil — Google pozisyon ölçümü "
                "LLM tahmin modu ile çalışacak"
            )

        for w in warnings:
            logger.warning(f"⚠️ {w}")

        # SEO Analyzer OpenAI olmadan da çalışabilir (sadece teknik kontroller)
        logger.info("✅ SEO Analyzer konfigürasyonu hazır")
        return True
