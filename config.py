"""
Akıllı Watchdog — Konfigürasyon Modülü
LLM-destekli pipeline sağlık kontrolü.

İzlenen projeler:
  1. Tele Satış CRM (Sheets → Notion)
  2. Lead Notifier Bot (Sheets → Telegram/Email)
  3. Tele Satış Notifier (Sheets → Email zamanlı)
  4. Marka İş Birliği (Notion custom)
  5. Blog Yazıcı (Notion Operations Log)
  6. [İSİM] Reels Kapak (Notion)
  7. İşbirliği Tahsilat Takip (Notion)
  8. LinkedIn Video Paylaşım (Notion)
  9. LinkedIn Text Paylaşım (Notion)
  10. Twitter Video Paylaşım (Notion)
  11. SWC Email Responder (Railway deployment)

Ek Katmanlar:
  - Token Freshness: LinkedIn OAuth2 token expire takibi (14 gün kala uyarı)
  - Railway Probe: Tüm aktif projelerin son deployment durumu kontrolü
"""
import os
from datetime import datetime, timezone, timedelta
import json
import logging

logger = logging.getLogger(__name__)


def _parse_tabs(csv_str: str) -> list[str]:
    """Virgülle ayrılmış tab isimlerini parse eder."""
    return [t.strip() for t in csv_str.split(",") if t.strip()]


class Config:
    """Environment variable tabanlı konfigürasyon."""

    # ── Groq LLM ──────────────────────────────────────────
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_BASE_URL = os.environ.get(
        "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
    )
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ── Alarm ─────────────────────────────────────────────
    ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "EMAIL_ADRESI_BURAYA")

    # Gmail API OAuth2 (SMTP yerine — Railway port engellemesi nedeniyle)
    # Railway: GOOGLE_OUTREACH_TOKEN_JSON env variable
    # Lokal: Merkezi google_auth modülü otomatik kullanılır

    # ── Notion ─────────────────────────────────────────────
    NOTION_API_TOKEN = os.environ.get("NOTION_API_TOKEN", "")
    NOTION_SOCIAL_TOKEN = os.environ.get("NOTION_SOCIAL_TOKEN", "")
    NOTION_DATABASE_ID = os.environ.get(
        "NOTION_DATABASE_ID", "BURAYA_NOTION_DB_ID"
    )

    # Token registry — proje config'inde notion_token_key ile referans edilir
    NOTION_TOKENS = {
        "NOTION_API_TOKEN": os.environ.get("NOTION_API_TOKEN", ""),
        "NOTION_SOCIAL_TOKEN": os.environ.get("NOTION_SOCIAL_TOKEN", ""),
    }

    @classmethod
    def get_notion_token(cls, token_key: str) -> str:
        """Proje config'indeki token_key'e göre doğru Notion token'ı döner."""
        return cls.NOTION_TOKENS.get(token_key, cls.NOTION_API_TOKEN)

    # ── Google Auth (Production: Service Account) ─────────
    GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    # ── İzlenen Projeler ──────────────────────────────────
    MONITORED_PROJECTS = [

        {
            "name": "Marka İş Birliği",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": os.environ.get(
                "NOTION_DB_BRAND_REACHOUT",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": ["Marka Adı", "Email", "Outreach Status"],
            "expected_daily_activity": False,  # Pipeline runs 2 days a week
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        # ── Yeni Projeler (Mart 2026) ────────────────────────
        {
            "name": "Blog Yazıcı",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": "BURAYA_NOTION_DB_ID",
            "notion_properties": ["Title", "Message", "Level", "Component", "Zaman"],
            "expected_daily_activity": False,  # Günlük cron ama her çalışmada yeni blog üretilmeyebilir
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "[İSİM] Reels Kapak",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": os.environ.get(
                "NOTION_DB_REELS_KAPAK",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": ["Name", "Status"],
            "expected_daily_activity": False,  # Her çalışmada üretim olmayabilir
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "İşbirliği Tahsilat Takip",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": os.environ.get(
                "NOTION_DB_YOUTUBE_ISBIRLIKLERI",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": [],  # DB erişim + kayıt sayısı kontrolü yeterli
            "expected_daily_activity": False,  # Sadece vadesinde kontrol
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "LinkedIn Video Paylaşım",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": os.environ.get(
                "NOTION_LINKEDIN_DB_ID",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": ["Video ID", "Status", "Platform", "TikTok URL", "LinkedIn URL", "Paylaşım Tarihi"],
            "expected_daily_activity": True,  # Günlük cron UTC 10:00
            "shared_notion_db_group": "social_media_db",  # Aynı DB'yi paylaşan projeler
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "LinkedIn Text Paylaşım",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_SOCIAL_TOKEN",
            "notion_db_id": os.environ.get(
                "NOTION_LINKEDIN_DB_ID",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": ["Video ID", "Status", "Platform", "Post Tipi"],
            "expected_daily_activity": False,  # Haftada 2 kez: Pazartesi + Perşembe
            "shared_notion_db_group": "social_media_db",
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "Twitter Video Paylaşım",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "custom_notion",
            "notion_token_key": "NOTION_API_TOKEN",  # DİKKAT: Ana workspace token
            "notion_db_id": os.environ.get(
                "NOTION_TWITTER_DB_ID",
                "BURAYA_NOTION_DB_ID"
            ),
            "notion_properties": ["Video ID", "Platform", "Status", "TikTok URL", "Twitter URL", "Paylaşım Tarihi"],
            "expected_daily_activity": True,  # Günde 3 kez: UTC 08/11/14
            "shared_notion_db_group": "social_media_db",
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
        },
        {
            "name": "SWC Email Responder",
            "spreadsheet_id": "",
            "sheet_tabs": [],
            "expected_columns": [],
            "expected_column_keywords": [],
            "pipeline": "railway_only",  # Notion yok, sadece Railway health check
            "railway_service_id": "BURAYA_RAILWAY_SERVICE_ID",
            "expected_daily_activity": True,
        },
    ]

    # ── Token Expire Takibi ─────────────────────────────
    # Not: Tarihler master.env'deki yorum satırından alınmıştır
    # LinkedIn token 60 gün geçerli — yenilemek için LinkedIn Developer Portal
    TOKEN_EXPIRY_TRACKING = [
        {
            "name": "LINKEDIN_ACCESS_TOKEN",
            "issued_date": "2026-03-25",
            "expiry_date": "2026-05-24",
            "validity_days": 60,
            "warning_days_before": 14,  # 14 gün kala uyarı
            "description": "LinkedIn OAuth2 bearer token",
            "renewal_url": "https://www.linkedin.com/developers/apps",
        },
    ]

    # ── Railway Deployment Probe ────────────────────────
    RAILWAY_TOKEN = os.environ.get("RAILWAY_TOKEN", "")
    RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"

    @classmethod
    def get_railway_service_ids(cls) -> list[dict]:
        """Aktif projelerin Railway service ID'lerini toplar."""
        services = []
        for project in cls.MONITORED_PROJECTS:
            sid = project.get("railway_service_id")
            if sid:
                services.append({
                    "name": project["name"],
                    "service_id": sid,
                })
        return services

    # ── Zamanlama ────────────────────────────────────────
    CHECK_INTERVAL_HOURS = int(os.environ.get("CHECK_INTERVAL_HOURS", "24"))

    @classmethod
    def validate(cls) -> bool:
        """Zorunlu konfigürasyon değerlerini kontrol eder."""
        errors = []

        if not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY tanımlı değil")

        if errors:
            error_msg = f"Eksik konfigürasyon nedeniyle uygulama başlatılamadı: {', '.join(errors)}"
            for err in errors:
                logger.error(f"❌ Config hatası: {err}")
            raise EnvironmentError(error_msg)

        logger.info("✅ Konfigürasyon doğrulandı")
        return True

    @classmethod
    def get_google_credentials_info(cls):
        """Google credentials bilgisini döner."""
        if cls.GOOGLE_SERVICE_ACCOUNT_JSON:
            try:
                return json.loads(cls.GOOGLE_SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError:
                logger.error("GOOGLE_SERVICE_ACCOUNT_JSON parse edilemedi")
                return None
        return None
