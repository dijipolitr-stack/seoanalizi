"""
Akıllı Watchdog — Notion Sağlık Kontrolü (Katman 1)
Tele Satış CRM'in Notion veritabanını kontrol eder:
  1. Notion DB erişilebilir mi?
  2. Property isimleri beklenen yapıda mı?
  3. Son 24 saatte kaç lead eklendi? (Sheet'le karşılaştırma için)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from config import Config

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionChecker:
    """Notion CRM veritabanı sağlık kontrolü (çoklu token desteği)."""

    def __init__(self, token: Optional[str] = None):
        """Token verilmezse Config.NOTION_API_TOKEN kullanılır."""
        effective_token = token or Config.NOTION_API_TOKEN
        self._token = effective_token
        self.headers = {
            "Authorization": f"Bearer {effective_token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def with_token(self, token_key: str) -> 'NotionChecker':
        """Farklı bir Notion token ile yeni checker instance döner."""
        new_token = Config.get_notion_token(token_key)
        if new_token and new_token != self._token:
            return NotionChecker(token=new_token)
        return self

    def check_database_access(self, db_id: str) -> dict:
        """
        Notion DB'ye erişilebilir mi kontrol eder.
        
        Returns:
            {"accessible": bool, "title": str, "properties": list[str], "error": str | None}
        """
        try:
            url = f"{NOTION_API_URL}/databases/{db_id}"
            resp = requests.get(url, headers=self.headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                title = ""
                title_parts = data.get("title", [])
                if title_parts:
                    title = title_parts[0].get("plain_text", "")

                properties = list(data.get("properties", {}).keys())

                return {
                    "accessible": True,
                    "title": title,
                    "properties": properties,
                    "error": None,
                }
            else:
                return {
                    "accessible": False,
                    "title": "",
                    "properties": [],
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }

        except Exception as e:
            return {
                "accessible": False,
                "title": "",
                "properties": [],
                "error": str(e),
            }

    def check_properties_match(
        self, db_id: str, expected_properties: list[str]
    ) -> dict:
        """
        Notion DB'deki property isimleri beklenen listeyle uyuşuyor mu kontrol eder.
        
        Returns:
            {"healthy": bool, "missing": list[str], "actual": list[str]}
        """
        access = self.check_database_access(db_id)
        if not access["accessible"]:
            return {
                "healthy": False,
                "missing": expected_properties,
                "actual": [],
                "error": access["error"],
            }

        actual = access["properties"]
        missing = [p for p in expected_properties if p not in actual]

        return {
            "healthy": len(missing) == 0,
            "missing": missing,
            "actual": actual,
            "error": None,
        }

    def count_recent_entries(self, db_id: str, hours: int = 24) -> dict:
        """
        Son N saat içinde oluşturulan Notion page sayısını döner.
        
        Returns:
            {"count": int, "error": str | None}
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_str = cutoff.isoformat()

            url = f"{NOTION_API_URL}/databases/{db_id}/query"
            payload = {
                "filter": {
                    "timestamp": "created_time",
                    "created_time": {
                        "on_or_after": cutoff_str,
                    },
                },
                "page_size": 100,
            }

            resp = requests.post(
                url, headers=self.headers, json=payload, timeout=15
            )
            resp.raise_for_status()

            data = resp.json()
            results = data.get("results", [])

            # Pagination — toplam sayıyı bul
            total = len(results)
            while data.get("has_more"):
                payload["start_cursor"] = data["next_cursor"]
                resp = requests.post(
                    url, headers=self.headers, json=payload, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                total += len(data.get("results", []))

            return {"count": total, "error": None}

        except Exception as e:
            return {"count": -1, "error": str(e)}

    def full_check(self, project: dict) -> dict:
        """
        Notion pipeline'ı olan projelerin tam sağlık kontrolü.
        
        Returns:
            {"project_name": str, "healthy": bool, "issues": list[str], "details": dict}
        """
        name = project["name"]
        db_id = project.get("notion_db_id", "")
        expected_props = project.get("notion_properties", [])

        result = {
            "project_name": name,
            "healthy": True,
            "issues": [],
            "details": {},
        }

        if not db_id:
            result["details"]["skipped"] = "Notion DB ID yok"
            return result

        # 1. DB Erişim
        access = self.check_database_access(db_id)
        result["details"]["access"] = access

        if not access["accessible"]:
            result["healthy"] = False
            result["issues"].append(
                f"🚨 [{name}] Notion DB'ye erişilemiyor: {access['error']}"
            )
            return result

        # 2. Property kontrolü
        prop_check = self.check_properties_match(db_id, expected_props)
        result["details"]["properties"] = prop_check

        if not prop_check["healthy"]:
            result["healthy"] = False
            result["issues"].append(
                f"🚨 [{name}] Notion DB'de eksik property'ler: "
                f"{prop_check['missing']}. DB şeması değişmiş olabilir!"
            )

        # 3. Son 24 saatteki lead sayısı ve boş kayıt kontrolü
        count_result = self.count_recent_entries(db_id, hours=24)
        result["details"]["recent_count_24h"] = count_result

        if count_result["error"]:
            result["issues"].append(
                f"⚠️ [{name}] Notion lead sayısı alınamadı: {count_result['error']}"
            )
        elif count_result["count"] == 0:
            if project.get("expected_daily_activity", True):
                result["healthy"] = False
                result["issues"].append(
                    f"🚨 [{name}] Son 24 saatte HİÇ YENİ LEAD işlenmedi! Pipeline durmuş olabilir."
                )

        # 4. Boş/Eksik Kritik Alan Kontrolü (İsim veya Telefon boş olan kayıtların artışı)
        critical_props = [p for p in ["İsim", "Phone", "Telefon"] if p in expected_props]
        if critical_props:
            empty_count = 0
            for prop in critical_props:
                empty_res = self.count_empty_entries(db_id, prop, hours=24)
                if not empty_res["error"]:
                    empty_count += empty_res["count"]
            
            result["details"]["empty_critical_fields_24h"] = empty_count
            if empty_count > 0:
                result["healthy"] = False
                result["issues"].append(
                    f"🚨 [{name}] Son 24 saatte {empty_count} adet BOŞ KAYIT (İsim/Telefon vb. eksik) eklendi! Şema veya veri kaynağı bozuk olabilir."
                )

        return result

    def count_empty_entries(self, db_id: str, property_name: str, hours: int = 24) -> dict:
        """
        Son N saat içinde oluşturulan ve belirtilen property'si BOŞ olan Notion page sayısını döner.
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_str = cutoff.isoformat()

            url = f"{NOTION_API_URL}/databases/{db_id}/query"
            payload = {
                "filter": {
                    "and": [
                        {
                            "timestamp": "created_time",
                            "created_time": {
                                "on_or_after": cutoff_str,
                            }
                        },
                        {
                            "property": property_name,
                            "rich_text": {
                                "is_empty": True
                            }
                        }
                    ]
                },
                "page_size": 100,
            }

            resp = requests.post(
                url, headers=self.headers, json=payload, timeout=15
            )
            # Property tipi rich_text değil de title, phone_number vbg ise API hata dönebilir.
            # O yüzden hata durumunda (400 Bad Request) property özel tipine göre fallback yapılabilir
            # Şimdilik genel kontrol yapıyoruz
            if resp.status_code != 200:
                # Eger property rich_text degilse, diger tipler icin sansimizi deneyelim (title, phone_number, vs)
                payload["filter"]["and"][1] = {
                    "property": property_name,
                    "title": {"is_empty": True}
                }
                resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
                if resp.status_code != 200:
                    payload["filter"]["and"][1] = {
                        "property": property_name,
                        "phone_number": {"is_empty": True}
                    }
                    resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
                    resp.raise_for_status()

            data = resp.json()
            results = data.get("results", [])

            total = len(results)
            while data.get("has_more"):
                payload["start_cursor"] = data["next_cursor"]
                resp = requests.post(
                    url, headers=self.headers, json=payload, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                total += len(data.get("results", []))

            return {"count": total, "error": None}

        except Exception as e:
            return {"count": -1, "error": str(e)}
