"""
Akıllı Watchdog — Ana Orkestrasyon Modülü
3 katmanlı sağlık kontrolünü orkestre eder:
  Katman 1: Yapısal kontrol (Sheet tab/header, Notion DB property)
  Katman 2: LLM analiz (şema kayması, veri kalitesi, pipeline tutarlılığı)

Çalıştırma:
  python main.py           # Tek seferlik kontrol (günlük cron için ideal)
  python main.py --force   # Sorun olmasa bile rapor e-postası gönder
  python main.py --loop    # Sürekli döngü (CHECK_INTERVAL_HOURS aralığında)
"""
import sys
import time
import signal
import logging
import argparse
import requests
from datetime import datetime, timezone, timedelta

from config import Config
from sheets_checker import SheetsChecker
from notion_checker import NotionChecker
from llm_analyzer import LLMAnalyzer
from alerter import send_alert_email

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AkilliWatchdog")

# ── Graceful Shutdown ────────────────────────────────────────
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info("🛑 Kapatma sinyali alındı...")
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _now_tr() -> str:
    """Türkiye saatini string olarak döner."""
    tr_tz = timezone(timedelta(hours=3))
    return datetime.now(tr_tz).strftime("%Y-%m-%d %H:%M:%S UTC+3")


def check_token_freshness() -> list[dict]:
    """
    Token expire takibi — config'deki TOKEN_EXPIRY_TRACKING listesini kontrol eder.
    14 gün kala WARNING, expire olduysa CRITICAL döner.

    Returns:
        list[dict]: [{"name": str, "status": OK|WARNING|CRITICAL, "message": str, "days_remaining": int}]
    """
    results = []
    today = datetime.now(timezone.utc).date()

    for token_info in Config.TOKEN_EXPIRY_TRACKING:
        try:
            expiry_date = datetime.strptime(token_info["expiry_date"], "%Y-%m-%d").date()
            issued_date = datetime.strptime(token_info["issued_date"], "%Y-%m-%d").date()
            days_remaining = (expiry_date - today).days
            warning_threshold = token_info.get("warning_days_before", 14)

            if days_remaining <= 0:
                status = "CRITICAL"
                message = (
                    f"🚨 {token_info['name']} EXPIRED! "
                    f"Expire tarihi: {token_info['expiry_date']}. "
                    f"Hemen yenile: {token_info.get('renewal_url', 'N/A')}"
                )
            elif days_remaining <= warning_threshold:
                status = "WARNING"
                message = (
                    f"⚠️ {token_info['name']} {days_remaining} gün sonra expire olacak! "
                    f"Expire tarihi: {token_info['expiry_date']}. "
                    f"Yenile: {token_info.get('renewal_url', 'N/A')}"
                )
            else:
                status = "OK"
                message = (
                    f"✅ {token_info['name']} sağlıklı — {days_remaining} gün kaldı "
                    f"(expire: {token_info['expiry_date']})"
                )

            results.append({
                "name": token_info["name"],
                "description": token_info.get("description", ""),
                "status": status,
                "message": message,
                "days_remaining": days_remaining,
                "expiry_date": token_info["expiry_date"],
                "issued_date": token_info["issued_date"],
            })
        except Exception as e:
            logger.error(f"Token freshness kontrolü hatası ({token_info.get('name', '?')}): {e}", exc_info=True)
            results.append({
                "name": token_info.get("name", "?"),
                "status": "ERROR",
                "message": f"Token kontrolü yapılamadı: {e}",
                "days_remaining": -1,
            })
    return results


def check_railway_deployments() -> list[dict]:
    """
    Railway GraphQL API ile tüm aktif projelerin son deployment durumunu kontrol eder.

    Returns:
        list[dict]: [{"name": str, "service_id": str, "status": str, "created_at": str, "healthy": bool}]
    """
    if not Config.RAILWAY_TOKEN:
        logger.warning("⚠️ RAILWAY_TOKEN tanımlı değil, deployment probe atlandı")
        return []

    services = Config.get_railway_service_ids()
    if not services:
        logger.info("ℹ️ Railway service ID'si olan proje yok, probe atlandı")
        return []

    results = []
    headers = {
        "Authorization": f"Bearer {Config.RAILWAY_TOKEN}",
        "Content-Type": "application/json",
    }

    for svc in services:
        query = """
        query($serviceId: String!) {
            deployments(input: { serviceId: $serviceId }, first: 1) {
                edges {
                    node {
                        id
                        status
                        createdAt
                    }
                }
            }
        }
        """
        variables = {"serviceId": svc["service_id"]}

        try:
            resp = requests.post(
                Config.RAILWAY_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            edges = data.get("data", {}).get("deployments", {}).get("edges", [])
            if edges:
                node = edges[0]["node"]
                deploy_status = node.get("status", "UNKNOWN")
                created_at = node.get("createdAt", "?")
                # Railway deployment statuses: SUCCESS, FAILED, CRASHED, BUILDING, DEPLOYING, etc.
                is_healthy = deploy_status in ("SUCCESS", "SLEEPING", "BUILDING", "DEPLOYING")
                results.append({
                    "name": svc["name"],
                    "service_id": svc["service_id"],
                    "status": deploy_status,
                    "created_at": created_at,
                    "healthy": is_healthy,
                })
            else:
                results.append({
                    "name": svc["name"],
                    "service_id": svc["service_id"],
                    "status": "NO_DEPLOYMENTS",
                    "created_at": "—",
                    "healthy": True,  # Deployment yok ama sorun değil
                })

        except Exception as e:
            logger.error(f"Railway probe hatası ({svc['name']}): {e}", exc_info=True)
            results.append({
                "name": svc["name"],
                "service_id": svc["service_id"],
                "status": "PROBE_ERROR",
                "created_at": "—",
                "healthy": True,  # Probe hatası = alarm değil, sadece log
            })

    return results


def run_health_check(force_email: bool = False) -> dict:
    """
    Tam sağlık kontrolü çalıştırır.

    Returns:
        {
            "timestamp": str,
            "all_healthy": bool,
            "total_issues": int,
            "issues": list[str],
            "sheets_results": list[dict],
            "notion_results": list[dict],
            "llm_results": list[dict],
        }
    """
    logger.info("=" * 65)
    logger.info("🐕 Akıllı Watchdog — Sağlık Kontrolü Başlıyor")
    logger.info(f"   Zaman: {_now_tr()}")
    logger.info(f"   İzlenen proje sayısı: {len(Config.MONITORED_PROJECTS)}")
    logger.info("=" * 65)

    all_issues: list[str] = []
    sheets_results: list[dict] = []
    notion_results: list[dict] = []
    llm_results: list[dict] = []
    token_results: list[dict] = []
    railway_results: list[dict] = []

    # ── KATMAN 0: Token Freshness Kontrolü ───────────────────
    logger.info("── Katman 0: Token Freshness ──")
    token_results = check_token_freshness()
    for tr in token_results:
        if tr["status"] == "CRITICAL":
            all_issues.append(tr["message"])
            logger.critical(f"  {tr['message']}")
        elif tr["status"] == "WARNING":
            all_issues.append(tr["message"])
            logger.warning(f"  {tr['message']}")
        else:
            logger.info(f"  {tr['message']}")

    # ── KATMAN 1: Yapısal Kontrol ────────────────────────────
    logger.info("── Katman 1: Yapısal Kontrol ──")

    # 1a. Google Sheets kontrolü (sadece spreadsheet_id'si olan projeler)
    sheets_projects = [
        p for p in Config.MONITORED_PROJECTS if p.get("spreadsheet_id")
    ]
    sheets_checker = SheetsChecker()
    if sheets_projects:
        try:
            sheets_checker.authenticate()
        except Exception as e:
            logger.error(f"❌ Google Sheets authentication başarısız: {e}")
            all_issues.append(f"🚨 Google Sheets'e bağlanılamadı: {e}")
            return _build_result(all_issues, sheets_results, notion_results, llm_results,
                                   token_results, railway_results)

    for project in Config.MONITORED_PROJECTS:
        if not project.get("spreadsheet_id"):
            # Notion-only veya Railway-only projeler — Sheets kontrolü atla
            sheets_results.append({
                "project_name": project["name"],
                "healthy": True,
                "tab_results": {},
                "issues": [],
            })
            continue

        logger.info(f"📋 [{project['name']}] Sheets kontrolü...")
        result = sheets_checker.full_check(project)
        sheets_results.append(result)
        all_issues.extend(result.get("issues", []))

        if result["healthy"]:
            logger.info(f"  ✅ {project['name']} → Sağlıklı")
        else:
            logger.warning(f"  ⚠️ {project['name']} → {len(result['issues'])} sorun")

    # 1b. Notion kontrolü (sheets_to_notion + custom_notion pipeline'ları)
    notion_pipelines = ("sheets_to_notion", "custom_notion")
    notion_projects = [
        p for p in Config.MONITORED_PROJECTS
        if p.get("pipeline") in notion_pipelines and p.get("notion_db_id")
    ]

    if notion_projects:
        # shared_notion_db_group ile aynı DB'yi paylaşan projeler için dedupe
        checked_db_groups: dict[str, dict] = {}  # group_key → full_check result
        notion_checker_cache: dict[str, NotionChecker] = {}  # token_key → checker

        for project in notion_projects:
            token_key = project.get("notion_token_key", "NOTION_API_TOKEN")

            # Token var mı kontrol et
            effective_token = Config.get_notion_token(token_key)
            if not effective_token:
                logger.warning(
                    f"⚠️ [{project['name']}] {token_key} tanımlı değil, "
                    f"Notion kontrolü atlandı"
                )
                continue

            # Token bazlı checker cache
            if token_key not in notion_checker_cache:
                notion_checker_cache[token_key] = NotionChecker(token=effective_token)
            checker = notion_checker_cache[token_key]

            # Shared DB grubu kontrolü — aynı DB'yi tekrar sorgulamayı engelle
            db_group = project.get("shared_notion_db_group")
            if db_group and db_group in checked_db_groups:
                # Aynı DB zaten kontrol edildi — sadece property kontrolü yap
                cached = checked_db_groups[db_group]
                logger.info(
                    f"📋 [{project['name']}] Notion kontrolü (paylaşımlı DB, cache)..."
                )
                # Property kontrolü (her projenin beklentisi farklı olabilir)
                expected_props = project.get("notion_properties", [])
                if expected_props and cached.get("details", {}).get("access", {}).get("accessible"):
                    actual_props = cached.get("details", {}).get("access", {}).get("properties", [])
                    missing = [p for p in expected_props if p not in actual_props]
                    result = {
                        "project_name": project["name"],
                        "healthy": len(missing) == 0,
                        "issues": [],
                        "details": cached.get("details", {}),
                    }
                    if missing:
                        result["issues"].append(
                            f"🚨 [{project['name']}] Notion DB'de eksik property'ler: "
                            f"{missing}. DB şeması değişmiş olabilir!"
                        )
                else:
                    result = {
                        "project_name": project["name"],
                        "healthy": cached.get("healthy", True),
                        "issues": [],
                        "details": cached.get("details", {}),
                    }
            else:
                # Tam kontrol
                logger.info(f"📋 [{project['name']}] Notion kontrolü...")
                result = checker.full_check(project)

                # Grubu cache'le
                if db_group:
                    checked_db_groups[db_group] = result

            notion_results.append(result)
            all_issues.extend(result.get("issues", []))

            if result.get("healthy", True):
                logger.info(f"  ✅ {project['name']} → Notion sağlıklı")
            else:
                logger.warning(f"  ⚠️ {project['name']} → Notion sorunlu")
    else:
        logger.warning("⚠️ Notion token tanımlı değil veya izlenecek Notion projesi yok")

    # ── KATMAN 1b: Railway Deployment Probe ───────────────────
    logger.info("── Katman 1b: Railway Deployment Probe ──")
    railway_results = check_railway_deployments()
    for rr in railway_results:
        if rr["healthy"]:
            logger.info(f"  ✅ {rr['name']} → {rr['status']} ({rr['created_at']})")
        else:
            msg = (
                f"🚨 [{rr['name']}] Railway deployment FAILED! "
                f"Status: {rr['status']}, Son deploy: {rr['created_at']}"
            )
            all_issues.append(msg)
            logger.critical(f"  {msg}")

    # ── KATMAN 2: LLM Analiz ─────────────────────────────────
    logger.info("── Katman 2: LLM Akıllı Analiz ──")

    if Config.GROQ_API_KEY:
        llm = LLMAnalyzer()
        for i, project in enumerate(Config.MONITORED_PROJECTS):
            sheets_result = sheets_results[i] if i < len(sheets_results) else {}
            notion_result = next(
                (n for n in notion_results if n["project_name"] == project["name"]),
                None,
            )

            logger.info(f"🧠 [{project['name']}] LLM analizi...")
            result = llm.full_analysis(project, sheets_result, notion_result)
            llm_results.append(result)

            if result["critical_issues"]:
                all_issues.extend(result["critical_issues"])

            logger.info(f"  {result['overall_status']} {project['name']}")
    else:
        logger.warning("⚠️ GROQ_API_KEY tanımlı değil, LLM analizi atlandı")

    # ── SONUÇ & RAPOR ────────────────────────────────────────
    report = _build_result(all_issues, sheets_results, notion_results, llm_results,
                           token_results, railway_results)

    logger.info("=" * 65)
    if report["all_healthy"]:
        logger.info("✅ Tüm kontroller geçti — sistemler sağlıklı!")
    else:
        logger.warning(
            f"⚠️ {report['total_issues']} sorun tespit edildi — "
            f"detaylar e-posta raporunda"
        )
    logger.info("=" * 65)

    # E-posta gönder
    send_alert_email(
        sheets_results, notion_results, llm_results,
        all_issues, force=force_email,
        token_results=token_results,
        railway_results=railway_results,
    )

    return report


def _build_result(
    all_issues: list[str],
    sheets_results: list[dict],
    notion_results: list[dict],
    llm_results: list[dict],
    token_results: list[dict] | None = None,
    railway_results: list[dict] | None = None,
) -> dict:
    """Sonuçları standart yapıda toplar."""
    return {
        "timestamp": _now_tr(),
        "all_healthy": len(all_issues) == 0,
        "total_issues": len(all_issues),
        "issues": all_issues,
        "sheets_results": sheets_results,
        "notion_results": notion_results,
        "llm_results": llm_results,
        "token_results": token_results or [],
        "railway_results": railway_results or [],
    }


def main():
    """Ana giriş noktası."""
    parser = argparse.ArgumentParser(description="Akıllı Watchdog — Pipeline Sağlık Kontrolü")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sorun olmasa bile rapor e-postası gönder",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help=f"Sürekli döngü ({Config.CHECK_INTERVAL_HOURS}h aralık)",
    )
    args = parser.parse_args()

    if not Config.validate():
        logger.critical("❌ Konfigürasyon hatalı, çıkılıyor...")
        sys.exit(1)

    if args.loop:
        logger.info(
            f"♻️ Sürekli döngü modu — {Config.CHECK_INTERVAL_HOURS} saatte bir kontrol"
        )
        while _running:
            try:
                run_health_check(force_email=args.force)
            except Exception as e:
                logger.error(f"❌ Beklenmeyen hata: {e}", exc_info=True)

            # Bekleme
            wait_seconds = Config.CHECK_INTERVAL_HOURS * 3600
            logger.info(
                f"⏳ Sonraki kontrol: {Config.CHECK_INTERVAL_HOURS} saat sonra"
            )
            for _ in range(wait_seconds):
                if not _running:
                    break
                time.sleep(1)

        logger.info("👋 Akıllı Watchdog durduruldu.")
    else:
        # Tek seferlik kontrol (Railway Cron Job modu)
        result = run_health_check(force_email=args.force)
        # Railway Cron Job'da exit 1 kullanılmamalı — Railway bunu CRASHED olarak
        # algılar. Sorunlar zaten e-posta ile raporlanıyor, process başarıyla tamamlandı.
        if not result["all_healthy"]:
            logger.warning(f"⚠️ {result['total_issues']} sorun tespit edildi ama rapor gönderildi — exit 0")
        sys.exit(0)


if __name__ == "__main__":
    main()
