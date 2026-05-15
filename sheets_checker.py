"""
Akıllı Watchdog — Google Sheets Sağlık Kontrolü (Katman 1)
Her proje için:
  1. Tab isimlerinin hâlâ var olduğunu doğrular
  2. Beklenen sütunların header'da olduğunu kontrol eder
  3. Son 24 saatteki yeni satır sayısını raporlar
  4. Boş/eksik veri oranını hesaplar
"""
import os
import sys
import json
import re
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsChecker:
    """Google Sheets yapısal sağlık kontrolü."""

    def __init__(self):
        self.service = None

    def authenticate(self):
        """Google Sheets API'ye bağlanır.
        
        Auth sırası:
        1. GOOGLE_OUTREACH_TOKEN_JSON env variable → OAuth2
        2. GOOGLE_SERVICE_ACCOUNT_JSON env variable → Service Account
        3. Lokal: merkezi google_auth → OAuth2
        """
        # 1. OAuth token (env variable)
        env_token = os.environ.get("GOOGLE_OUTREACH_TOKEN_JSON", "")
        if env_token:
            logger.info("🔑 OAuth token (env) ile authentication yapılıyor...")
            try:
                import json as _json
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request

                token_data = _json.loads(env_token)
                creds = Credentials.from_authorized_user_info(token_data)
                if not creds.valid:
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        raise RuntimeError("OAuth token geçersiz ve yenilenemiyor")
                self.service = build("sheets", "v4", credentials=creds)
                logger.info("✅ Google Sheets API bağlantısı kuruldu (OAuth2)")
                return
            except Exception as e:
                logger.warning(f"⚠️ OAuth token auth başarısız: {e}")

        # 2. Service Account
        sa_info = Config.get_google_credentials_info()
        if sa_info:
            logger.info("🔑 Service Account ile authentication yapılıyor...")
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=SCOPES
            )
            self.service = build("sheets", "v4", credentials=creds)
            logger.info("✅ Google Sheets API bağlantısı kuruldu (Service Account)")
            return

        # 3. Lokal: merkezi google_auth
        logger.info("🔑 Merkezi google_auth ile authentication yapılıyor (Lokal)...")
        _antigravity_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        sys.path.insert(0, os.path.join(
            _antigravity_root, "_knowledge", "credentials", "oauth"
        ))
        from google_auth import get_sheets_service
        self.service = get_sheets_service("outreach")
        logger.info("✅ Google Sheets API bağlantısı kuruldu (Lokal OAuth2)")

    def check_tab_exists(self, spreadsheet_id: str, tab_name: str) -> dict:
        """
        Belirtilen tab'ın Sheet'te var olduğunu doğrular.

        Returns:
            {"exists": bool, "error": str | None}
        """
        try:
            meta = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties.title",
            ).execute()

            sheet_titles = [
                s["properties"]["title"]
                for s in meta.get("sheets", [])
            ]

            if tab_name in sheet_titles:
                return {"exists": True, "error": None}
            else:
                return {
                    "exists": False,
                    "error": f"Tab '{tab_name}' bulunamadı. Mevcut tab'lar: {sheet_titles}",
                }
        except Exception as e:
            return {"exists": False, "error": f"Sheet metadata alınamadı: {e}"}

    def check_headers(
        self,
        spreadsheet_id: str,
        tab_name: str,
        expected_columns: list[str],
        expected_keywords: list[str],
    ) -> dict:
        """
        Sheet header'larının beklenen sütunları içerdiğini kontrol eder.

        Returns:
            {
                "healthy": bool,
                "headers": list[str],
                "missing_columns": list[str],
                "missing_keywords": list[str],
                "error": str | None,
            }
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:Z1",
            ).execute()

            values = result.get("values", [])
            if not values:
                return {
                    "healthy": False,
                    "headers": [],
                    "missing_columns": expected_columns,
                    "missing_keywords": expected_keywords,
                    "error": f"'{tab_name}' tab'ı boş — header satırı yok",
                }

            headers = values[0]
            headers_lower = [h.lower() for h in headers]

            # Tam eşleşme kontrolü
            missing_columns = [
                col for col in expected_columns
                if col.lower() not in headers_lower
            ]

            # Keyword kontrolü (regex — "|" ile ayrılmış alternatifler)
            missing_keywords = []
            for kw_pattern in expected_keywords:
                pattern = re.compile(kw_pattern, re.IGNORECASE)
                found = any(pattern.search(h) for h in headers)
                if not found:
                    missing_keywords.append(kw_pattern)

            healthy = not missing_columns and not missing_keywords

            return {
                "healthy": healthy,
                "headers": headers,
                "missing_columns": missing_columns,
                "missing_keywords": missing_keywords,
                "error": None,
            }

        except Exception as e:
            return {
                "healthy": False,
                "headers": [],
                "missing_columns": expected_columns,
                "missing_keywords": expected_keywords,
                "error": f"Header okunamadı: {e}",
            }

    def get_row_stats(self, spreadsheet_id: str, tab_name: str) -> dict:
        """
        Tab'daki toplam satır sayısını ve son satırların kalitesini kontrol eder.

        Returns:
            {
                "total_rows": int,
                "sample_rows": list[dict],  (son 5 satır)
                "empty_rate": dict,         (sütun bazlı boşluk oranı — son 20 satır)
                "error": str | None,
            }
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A:Z",
            ).execute()

            values = result.get("values", [])
            if not values or len(values) < 2:
                return {
                    "total_rows": 0,
                    "sample_rows": [],
                    "empty_rate": {},
                    "error": None,
                }

            headers = values[0]
            data_rows = values[1:]
            total = len(data_rows)

            # Son 5 satırı sample olarak al
            sample_slice = data_rows[-5:] if total >= 5 else data_rows
            sample_rows = []
            for row_vals in sample_slice:
                row_dict = {}
                for i, h in enumerate(headers):
                    row_dict[h] = row_vals[i] if i < len(row_vals) else ""
                sample_rows.append(row_dict)

            # Son 20 satırda sütun bazlı boşluk oranı
            check_slice = data_rows[-20:] if total >= 20 else data_rows
            check_count = len(check_slice)
            empty_rate = {}
            for i, h in enumerate(headers):
                empty_count = sum(
                    1 for row in check_slice
                    if i >= len(row) or not str(row[i]).strip()
                )
                rate = round(empty_count / check_count * 100, 1)
                if rate > 0:
                    empty_rate[h] = f"{rate}%"

            return {
                "total_rows": total,
                "sample_rows": sample_rows,
                "empty_rate": empty_rate,
                "error": None,
            }

        except Exception as e:
            return {
                "total_rows": 0,
                "sample_rows": [],
                "empty_rate": {},
                "error": f"Veri okunamadı: {e}",
            }

    def full_check(self, project: dict) -> dict:
        """
        Tek bir proje için tam Sheet sağlık kontrolü.

        Returns:
            {
                "project_name": str,
                "healthy": bool,
                "tab_results": dict,
                "issues": list[str],
            }
        """
        name = project["name"]
        spreadsheet_id = project["spreadsheet_id"]
        tabs = project["sheet_tabs"]
        expected_cols = project.get("expected_columns", [])
        expected_kws = project.get("expected_column_keywords", [])
        tab_specific_kws = project.get("tab_specific_keywords", {})

        result = {
            "project_name": name,
            "healthy": True,
            "tab_results": {},
            "issues": [],
        }

        for tab_name in tabs:
            tab_result = {"tab": tab_name}

            # 1. Tab var mı?
            tab_check = self.check_tab_exists(spreadsheet_id, tab_name)
            if not tab_check["exists"]:
                tab_result["status"] = "TAB_MISSING"
                tab_result["error"] = tab_check["error"]
                result["healthy"] = False
                result["issues"].append(
                    f"🚨 [{name}] Tab '{tab_name}' Sheet'te bulunamadı! "
                    f"Form değişmiş veya tab silinmiş olabilir."
                )
                result["tab_results"][tab_name] = tab_result
                continue

            # 2. Header kontrol — tab-spesifik keyword'leri birleştir
            effective_kws = list(expected_kws)
            if tab_name in tab_specific_kws:
                effective_kws.extend(tab_specific_kws[tab_name])

            header_check = self.check_headers(
                spreadsheet_id, tab_name, expected_cols, effective_kws
            )
            tab_result["headers"] = header_check["headers"]

            if not header_check["healthy"]:
                tab_result["status"] = "HEADER_MISMATCH"
                result["healthy"] = False

                if header_check["missing_columns"]:
                    result["issues"].append(
                        f"🚨 [{name}] '{tab_name}' tab'ında eksik sütunlar: "
                        f"{header_check['missing_columns']}. "
                        f"Form yapısı değişmiş olabilir!"
                    )
                if header_check["missing_keywords"]:
                    result["issues"].append(
                        f"⚠️ [{name}] '{tab_name}' tab'ında beklenen keyword sütunları "
                        f"bulunamadı: {header_check['missing_keywords']}. "
                        f"Sütun isimleri değişmiş olabilir."
                    )

            # 3. Satır istatistikleri
            row_stats = self.get_row_stats(spreadsheet_id, tab_name)
            tab_result["total_rows"] = row_stats["total_rows"]
            tab_result["empty_rate"] = row_stats["empty_rate"]
            tab_result["sample_rows"] = row_stats["sample_rows"]

            # Kritik sütunlarda yüksek boşluk oranı kontrolü
            for col in expected_cols:
                rate_str = row_stats["empty_rate"].get(col, "0%")
                rate_val = float(rate_str.replace("%", ""))
                if rate_val > 50:
                    result["issues"].append(
                        f"⚠️ [{name}] '{tab_name}' tab'ında '{col}' sütunu "
                        f"son 20 satırda %{rate_val} boş. Veri kalitesi düşük."
                    )

            if not result["issues"] or header_check["healthy"]:
                tab_result["status"] = "HEALTHY"

            if row_stats["error"]:
                tab_result["error"] = row_stats["error"]

            result["tab_results"][tab_name] = tab_result

        return result
