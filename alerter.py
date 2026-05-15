"""
Akıllı Watchdog — E-posta Alarm Modülü (Gmail API)
===================================================
Sağlık kontrolü sonuçlarını HTML e-posta olarak gönderir.

v2 Değişiklikleri:
  - SMTP tamamen kaldırıldı (Railway port engellemesi)
  - Gmail API (OAuth2) ile e-posta gönderimi
  - Railway: GOOGLE_OUTREACH_TOKEN_JSON env variable'ından token okunur
  - Lokal: Merkezi google_auth modülü kullanılır
"""
import os
import sys
import json
import base64
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import Config

logger = logging.getLogger(__name__)


# ── GMAIL API ────────────────────────────────────────────────

def _get_gmail_service():
    """Gmail API service objesi döndür (EMAIL_ADRESI_BURAYA hesabı).

    Öncelik:
      1. Railway (prod): GOOGLE_OUTREACH_TOKEN_JSON env variable
      2. Lokal (dev): Merkezi google_auth modülü
    """
    env_token = os.environ.get("GOOGLE_OUTREACH_TOKEN_JSON", "")
    if env_token:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_data = json.loads(env_token)
        scopes = [
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify',
        ]
        creds = Credentials.from_authorized_user_info(token_data, scopes)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logger.info("🔄 Gmail OAuth token yenilendi (Railway)")
            else:
                raise RuntimeError("Gmail token geçersiz ve yenilenemiyor (Railway)")
        return build('gmail', 'v1', credentials=creds)

    # Lokal: Merkezi google_auth kullan
    _antigravity_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    sys.path.insert(0, os.path.join(
        _antigravity_root, "_knowledge", "credentials", "oauth"
    ))
    from google_auth import get_gmail_service
    return get_gmail_service("outreach")


def _status_badge(status: str) -> tuple[str, str, str]:
    """Status'a göre emoji, renk ve arka plan döner."""
    mapping = {
        "OK": ("✅", "#22c55e", "#052e16"),
        "HEALTHY": ("✅", "#22c55e", "#052e16"),
        "WARNING": ("⚠️", "#f59e0b", "#78350f"),
        "CRITICAL": ("🚨", "#dc2626", "#ffffff"),
        "ERROR": ("❌", "#dc2626", "#ffffff"),
        "TAB_MISSING": ("🚨", "#dc2626", "#ffffff"),
        "HEADER_MISMATCH": ("⚠️", "#f59e0b", "#78350f"),
    }
    return mapping.get(status, ("❓", "#6b7280", "#ffffff"))


def build_html_report(
    sheets_results: list[dict],
    notion_results: list[dict],
    llm_results: list[dict],
    all_issues: list[str],
    timestamp: str,
    token_results: list[dict] | None = None,
    railway_results: list[dict] | None = None,
) -> str:
    """Sağlık kontrolü sonuçlarını HTML rapora çevirir."""

    has_critical = any(
        r.get("overall_status") == "CRITICAL" or not r.get("healthy", True)
        for r in sheets_results + notion_results + llm_results
    )
    has_warning = any(
        r.get("overall_status") == "WARNING"
        for r in llm_results
    )

    if has_critical:
        header_bg = "linear-gradient(135deg, #dc2626, #991b1b)"
        header_icon = "🚨"
        header_text = "Kritik Sorun Tespit Edildi"
    elif has_warning:
        header_bg = "linear-gradient(135deg, #f59e0b, #d97706)"
        header_icon = "⚠️"
        header_text = "Uyarı — Dikkat Gerektiren Durumlar"
    else:
        header_bg = "linear-gradient(135deg, #22c55e, #16a34a)"
        header_icon = "✅"
        header_text = "Tüm Sistemler Sağlıklı"

    # Issues bölümü
    issues_html = ""
    if all_issues:
        issues_items = ""
        for issue in all_issues:
            issues_items += f'<li style="padding: 8px 0; color: #e2e8f0; font-size: 14px; line-height: 1.5; border-bottom: 1px solid #334155;">{issue}</li>'

        issues_html = f"""
        <div style="margin-bottom: 24px;">
            <h2 style="color: #f8fafc; font-size: 16px; margin: 0 0 12px; padding: 12px 24px; background: #1e293b; border-radius: 8px 8px 0 0;">
                📋 Tespit Edilen Sorunlar ({len(all_issues)})
            </h2>
            <ul style="margin: 0; padding: 0 24px; list-style: none; background: #0f172a; border-radius: 0 0 8px 8px;">
                {issues_items}
            </ul>
        </div>"""

    # Proje durumları tablosu
    project_rows = ""
    for sr in sheets_results:
        name = sr["project_name"]
        healthy = sr.get("healthy", True)
        status_text = "Sağlıklı" if healthy else "Sorunlu"
        emoji, badge_bg, badge_color = _status_badge("OK" if healthy else "CRITICAL")

        tab_details = []
        for tab_name, td in sr.get("tab_results", {}).items():
            tab_status = td.get("status", "UNKNOWN")
            tab_rows = td.get("total_rows", "?")
            tab_details.append(f"{tab_name}: {tab_rows} satır ({tab_status})")

        detail_text = "<br>".join(tab_details) if tab_details else "—"

        project_rows += f"""
        <tr>
            <td style="padding: 14px 20px; border-bottom: 1px solid #334155; color: #e2e8f0; font-size: 14px;">
                {emoji} {name}
            </td>
            <td style="padding: 14px 16px; border-bottom: 1px solid #334155; text-align: center;">
                <span style="background: {badge_bg}; color: {badge_color}; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                    {status_text}
                </span>
            </td>
            <td style="padding: 14px 20px; border-bottom: 1px solid #334155; font-size: 12px; color: #94a3b8; line-height: 1.6;">
                {detail_text}
            </td>
        </tr>"""

    # LLM analiz bölümü
    llm_html = ""
    if llm_results:
        llm_items = ""
        for lr in llm_results:
            name = lr["project_name"]
            overall = lr.get("overall_status", "?")
            emoji, _, _ = _status_badge(overall)

            analyses_text = []
            for a in lr.get("analyses", []):
                a_type = a.get("type", "")
                a_status = a.get("status", "?")
                a_text = a.get("analysis", a.get("summary", ""))
                if a_text:
                    analyses_text.append(f"<b>[{a_type}]</b> {a_text}")

            detail = "<br>".join(analyses_text) if analyses_text else "—"
            llm_items += f"""
            <tr>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; color: #e2e8f0; font-size: 14px;">
                    {emoji} {name}
                </td>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; font-size: 12px; color: #94a3b8; line-height: 1.6;">
                    {detail}
                </td>
            </tr>"""

        llm_html = f"""
        <div style="margin-top: 24px;">
            <h2 style="color: #f8fafc; font-size: 16px; margin: 0 0 12px; padding: 12px 24px; background: #1e293b; border-radius: 8px 8px 0 0;">
                🧠 LLM Analiz Sonuçları
            </h2>
            <table style="width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 0 0 8px 8px;">
                <thead>
                    <tr style="background: #1e293b;">
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Proje</th>
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Analiz</th>
                    </tr>
                </thead>
                <tbody>
                    {llm_items}
                </tbody>
            </table>
        </div>"""

    # Token Freshness bölümü
    token_html = ""
    if token_results:
        token_rows = ""
        for tr in token_results:
            status = tr.get("status", "?")
            if status == "CRITICAL":
                badge_bg, badge_color = "#dc2626", "#ffffff"
                emoji = "🚨"
            elif status == "WARNING":
                badge_bg, badge_color = "#f59e0b", "#78350f"
                emoji = "⚠️"
            elif status == "OK":
                badge_bg, badge_color = "#22c55e", "#052e16"
                emoji = "✅"
            else:
                badge_bg, badge_color = "#6b7280", "#ffffff"
                emoji = "❓"

            days = tr.get("days_remaining", "?")
            token_rows += f"""
            <tr>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; color: #e2e8f0; font-size: 14px;">
                    {emoji} {tr['name']}
                </td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #334155; text-align: center;">
                    <span style="background: {badge_bg}; color: {badge_color}; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                        {days} gün
                    </span>
                </td>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; font-size: 12px; color: #94a3b8;">
                    Expire: {tr.get('expiry_date', '?')}
                </td>
            </tr>"""

        token_html = f"""
        <div style="margin-top: 24px;">
            <h2 style="color: #f8fafc; font-size: 16px; margin: 0 0 12px; padding: 12px 24px; background: #1e293b; border-radius: 8px 8px 0 0;">
                🔐 Token Expire Takibi
            </h2>
            <table style="width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 0 0 8px 8px;">
                <thead>
                    <tr style="background: #1e293b;">
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Token</th>
                        <th style="padding: 10px 16px; text-align: center; font-size: 12px; color: #64748b;">Kalan Gün</th>
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Expire</th>
                    </tr>
                </thead>
                <tbody>
                    {token_rows}
                </tbody>
            </table>
        </div>"""

    # Railway Deployment Status bölümü
    railway_html = ""
    if railway_results:
        railway_rows = ""
        for rr in railway_results:
            deploy_status = rr.get("status", "?")
            is_healthy = rr.get("healthy", True)
            if is_healthy:
                badge_bg, badge_color = "#22c55e", "#052e16"
                emoji = "✅"
            else:
                badge_bg, badge_color = "#dc2626", "#ffffff"
                emoji = "🚨"

            railway_rows += f"""
            <tr>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; color: #e2e8f0; font-size: 14px;">
                    {emoji} {rr['name']}
                </td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #334155; text-align: center;">
                    <span style="background: {badge_bg}; color: {badge_color}; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                        {deploy_status}
                    </span>
                </td>
                <td style="padding: 12px 20px; border-bottom: 1px solid #334155; font-size: 12px; color: #94a3b8;">
                    {rr.get('created_at', '?')}
                </td>
            </tr>"""

        railway_html = f"""
        <div style="margin-top: 24px;">
            <h2 style="color: #f8fafc; font-size: 16px; margin: 0 0 12px; padding: 12px 24px; background: #1e293b; border-radius: 8px 8px 0 0;">
                🚂 Railway Deployment Status
            </h2>
            <table style="width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 0 0 8px 8px;">
                <thead>
                    <tr style="background: #1e293b;">
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Servis</th>
                        <th style="padding: 10px 16px; text-align: center; font-size: 12px; color: #64748b;">Durum</th>
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Son Deploy</th>
                    </tr>
                </thead>
                <tbody>
                    {railway_rows}
                </tbody>
            </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a;">
    <div style="max-width: 680px; margin: 0 auto; background: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.4);">

        <!-- Header -->
        <div style="background: {header_bg}; padding: 28px 24px; text-align: center;">
            <h1 style="margin: 0; font-size: 22px; color: #ffffff; font-weight: 700;">
                {header_icon} Akıllı Watchdog Raporu
            </h1>
            <p style="margin: 8px 0 0; font-size: 14px; color: rgba(255,255,255,0.85);">
                {header_text}
            </p>
        </div>

        <div style="padding: 24px;">
            {issues_html}

            <!-- Proje Durumları -->
            <h2 style="color: #f8fafc; font-size: 16px; margin: 0 0 12px; padding: 12px 24px; background: #1e293b; border-radius: 8px 8px 0 0; border: 1px solid #334155;">
                📊 Proje Sağlık Durumları
            </h2>
            <table style="width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 0 0 8px 8px;">
                <thead>
                    <tr style="background: #1e293b;">
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Proje</th>
                        <th style="padding: 10px 16px; text-align: center; font-size: 12px; color: #64748b;">Durum</th>
                        <th style="padding: 10px 20px; text-align: left; font-size: 12px; color: #64748b;">Detay</th>
                    </tr>
                </thead>
                <tbody>
                    {project_rows}
                </tbody>
            </table>

            {llm_html}

            {token_html}

            {railway_html}
        </div>

        <!-- Footer -->
        <div style="padding: 16px 24px; background: #0f172a; text-align: center; border-top: 1px solid #334155;">
            <p style="margin: 0; font-size: 12px; color: #64748b;">
                Kontrol zamanı: {timestamp} | Akıllı Watchdog v2.0 (Gmail API)
            </p>
        </div>
    </div>
</body>
</html>"""

    return html


def send_alert_email(
    sheets_results: list[dict],
    notion_results: list[dict],
    llm_results: list[dict],
    all_issues: list[str],
    force: bool = False,
    token_results: list[dict] | None = None,
    railway_results: list[dict] | None = None,
) -> bool:
    """
    Sağlık raporu e-postası gönderir — Gmail API (OAuth2) ile.
    İssue yoksa (force=False ise) göndermez.
    
    Returns:
        True: başarılı gönderim, False: gönderilmedi veya hata
    """
    # Issue yoksa ve force değilse gönderme
    has_problem = bool(all_issues)
    has_critical = any(
        r.get("overall_status") == "CRITICAL" or not r.get("healthy", True)
        for r in sheets_results + notion_results + llm_results
    )

    if not has_problem and not has_critical and not force:
        logger.info("📧 Sorun yok, alarm e-postası gönderilmedi")
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_body = build_html_report(
        sheets_results, notion_results, llm_results,
        all_issues, timestamp,
        token_results=token_results or [],
        railway_results=railway_results or [],
    )

    # Subject
    if has_critical:
        subject = f"🚨 Watchdog: {len(all_issues)} kritik sorun tespit edildi"
    elif all_issues:
        subject = f"⚠️ Watchdog: {len(all_issues)} uyarı"
    else:
        subject = "✅ Watchdog: Tüm sistemler sağlıklı"

    # Gmail API ile gönder
    try:
        service = _get_gmail_service()
    except Exception as e:
        logger.error(f"❌ Gmail API bağlantısı kurulamadı: {e}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Akıllı Watchdog <EMAIL_ADRESI_BURAYA>"
    msg["To"] = Config.ALERT_EMAIL

    # Plain text fallback
    plain = f"Akıllı Watchdog Raporu\n{'='*40}\n"
    for issue in all_issues:
        plain += f"\n• {issue}"
    plain += f"\n\nKontrol zamanı: {timestamp}"

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info(f"📧 Alarm e-postası gönderildi → {Config.ALERT_EMAIL} | Message ID: {result.get('id', '?')}")
        return True
    except Exception as e:
        logger.error(f"❌ E-posta gönderilemedi (Gmail API): {e}")
        return False
