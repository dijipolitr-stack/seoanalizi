"""
Akıllı Watchdog — LLM-Destekli Akıllı Doğrulama (Katman 2)
Groq Llama modelini kullanarak:
  1. Sheet header'larının form yapısıyla uyumlu olup olmadığını semantik analiz eder
  2. Son lead verilerinin kalitesini kontrol eder
  3. Pipeline tutarlılığını (Sheets ↔ Notion) değerlendirir
"""
import json
import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """Groq LLM ile akıllı veri doğrulama."""

    def __init__(self):
        self.api_key = Config.GROQ_API_KEY
        self.base_url = Config.GROQ_BASE_URL
        self.model = Config.GROQ_MODEL

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        """Groq API'ye chat completion isteği gönderir."""
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1024,
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"❌ Groq API hatası: {e}")
            return f"LLM_ERROR: {e}"

    def analyze_schema_drift(
        self,
        project_name: str,
        current_headers: list[str],
        expected_columns: list[str],
        expected_keywords: list[str],
    ) -> dict:
        """
        Sheet header'larını LLM ile analiz eder.
        Semantik değişiklikleri (örn: "full_name" → "ad_soyad") yakalar.

        Returns:
            {"status": "OK"|"WARNING"|"CRITICAL", "analysis": str, "suggestions": list[str]}
        """
        system_prompt = """Sen bir veri mühendisisin. Google Sheets form verilerinin
yapısal sağlığını kontrol ediyorsun.

GÖREV: Mevcut Sheet header'larını incele ve beklenen yapıyla karşılaştır.
Özellikle dikkat et:
- Sütun isimlerinin anlamsal olarak eşleşip eşleşmediği (örn: "full_name" vs "ad_soyad")
- Eksik kritik sütunlar
- Form yapısında potansiyel değişiklik belirtileri
- Türkçe ve İngilizce sütun isimlerinin karışması

CEVAP FORMATI (sadece JSON, açıklama yok):
{
  "status": "OK" | "WARNING" | "CRITICAL",
  "issues": ["sorun açıklaması"],
  "mapping_suggestions": [{"from": "mevcut_header", "to": "beklenen_sütun"}],
  "summary": "tek satır özet"
}"""

        user_prompt = f"""Proje: {project_name}

Mevcut Sheet Header'ları:
{json.dumps(current_headers, ensure_ascii=False, indent=2)}

Beklenen Sabit Sütunlar:
{json.dumps(expected_columns, ensure_ascii=False, indent=2)}

Beklenen Keyword Sütunları (regex pattern):
{json.dumps(expected_keywords, ensure_ascii=False, indent=2)}

Bu header'lar beklenen yapıyla uyuşuyor mu? Anlamsal kayma var mı?"""

        raw_response = self._call_groq(system_prompt, user_prompt)

        if raw_response.startswith("LLM_ERROR"):
            return {
                "status": "ERROR",
                "analysis": raw_response,
                "suggestions": [],
            }

        try:
            # JSON parse dene
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            return {
                "status": parsed.get("status", "UNKNOWN"),
                "analysis": parsed.get("summary", raw_response),
                "issues": parsed.get("issues", []),
                "mapping_suggestions": parsed.get("mapping_suggestions", []),
            }
        except json.JSONDecodeError:
            return {
                "status": "WARNING",
                "analysis": raw_response[:500],
                "suggestions": [],
            }

    def analyze_data_quality(
        self,
        project_name: str,
        sample_rows: list[dict],
        pipeline_type: str,
    ) -> dict:
        """
        Son lead verilerinin kalitesini LLM ile kontrol eder.

        Returns:
            {"status": "OK"|"WARNING"|"CRITICAL", "analysis": str, "issues": list[str]}
        """
        if not sample_rows:
            return {
                "status": "OK",
                "analysis": "Kontrol edilecek veri yok",
                "issues": [],
            }

        system_prompt = """Sen bir veri kalite kontrol uzmanısın. Türkiye emlak sektöründe
faaliyet gösteren bir şirketin CRM lead verilerini kontrol ediyorsun.

GÖREV: Aşağıdaki lead verilerinin kalitesini değerlendir.
Özellikle kontrol et:
- Telefon numaraları geçerli Türkiye numarası mı? (5XX ile başlamalı, 10-11 hane)
- E-posta adresleri geçerli formatta mı?
- İsimler mantıklı mı (bot/spam olmadığından emin ol)?
- Veri tutarlılığı (aynı kişi farklı bilgilerle mi gelmiş?)
- Boş/eksik kritik alanlar

CEVAP FORMATI (sadece JSON):
{
  "status": "OK" | "WARNING" | "CRITICAL",
  "quality_score": 0-100,
  "issues": ["sorun açıklaması"],
  "summary": "tek satır özet"
}"""

        user_prompt = f"""Proje: {project_name}
Pipeline: {pipeline_type}

Son 5 lead verisi (örnek):
{json.dumps(sample_rows, ensure_ascii=False, indent=2)}

Bu verilerin kalitesini değerlendir."""

        raw_response = self._call_groq(system_prompt, user_prompt)

        if raw_response.startswith("LLM_ERROR"):
            return {
                "status": "ERROR",
                "analysis": raw_response,
                "issues": [],
            }

        try:
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            return {
                "status": parsed.get("status", "UNKNOWN"),
                "quality_score": parsed.get("quality_score", -1),
                "analysis": parsed.get("summary", raw_response),
                "issues": parsed.get("issues", []),
            }
        except json.JSONDecodeError:
            return {
                "status": "WARNING",
                "analysis": raw_response[:500],
                "issues": [],
            }

    def analyze_pipeline_consistency(
        self,
        project_name: str,
        sheets_row_count: int,
        notion_24h_count: int,
        pipeline_type: str,
    ) -> dict:
        """
        Sheet ve Notion arasındaki veri tutarlılığını analiz eder.
        """
        if pipeline_type != "sheets_to_notion":
            return {
                "status": "OK",
                "analysis": f"Bu pipeline ({pipeline_type}) Notion kontrolüne tabi değil",
                "gap": 0,
                "gap_percent": 0,
            }

        # Notion'daki 24 saatlik veri sayısına göre cron job'un çalışıp çalışmadığını değerlendir
        if notion_24h_count == 0:
            status = "CRITICAL"
            analysis = (
                f"🚨 [Cron Job Check] Notion'da son 24 saatte YENİ KAYIT YOK (0 kayıt). "
                f"Sheets'te toplam {sheets_row_count} satır var. "
                f"Eğer beklenen bir lead akışı var idiyse cron job çökmüş veya takılmış olabilir!"
            )
        else:
            status = "OK"
            analysis = (
                f"✅ [Cron Job Check] Pipeline çalışıyor. Son 24 saatte Notion'a {notion_24h_count} lead "
                f"işlenmiş. (Sheets Toplam: {sheets_row_count})"
            )

        return {
            "status": status,
            "analysis": analysis,
            "gap": -1,
            "gap_percent": -1.0,
        }

    def full_analysis(
        self, project: dict, sheets_result: dict, notion_result: dict | None
    ) -> dict:
        """
        Tek bir proje için tam LLM analizi.

        Returns:
            {"project_name": str, "overall_status": str, "analyses": list[dict], "critical_issues": list[str]}
        """
        name = project["name"]
        pipeline = project.get("pipeline", "unknown")

        result = {
            "project_name": name,
            "overall_status": "OK",
            "analyses": [],
            "critical_issues": [],
        }

        # 1. Her tab için şema analizi
        for tab_name, tab_data in sheets_result.get("tab_results", {}).items():
            headers = tab_data.get("headers", [])
            if not headers:
                continue

            schema_analysis = self.analyze_schema_drift(
                name,
                headers,
                project.get("expected_columns", []),
                project.get("expected_column_keywords", []),
            )
            schema_analysis["tab"] = tab_name
            schema_analysis["type"] = "schema_drift"
            result["analyses"].append(schema_analysis)

            if schema_analysis["status"] == "CRITICAL":
                result["overall_status"] = "CRITICAL"
                result["critical_issues"].extend(schema_analysis.get("issues", []))
            elif schema_analysis["status"] == "WARNING" and result["overall_status"] == "OK":
                result["overall_status"] = "WARNING"

            # 2. Veri kalitesi analizi (ilk tab'ın sample'ı yeterli)
            sample_rows = tab_data.get("sample_rows", [])
            if sample_rows:
                quality_analysis = self.analyze_data_quality(
                    name, sample_rows, pipeline
                )
                quality_analysis["tab"] = tab_name
                quality_analysis["type"] = "data_quality"
                result["analyses"].append(quality_analysis)

                if quality_analysis["status"] == "CRITICAL":
                    result["overall_status"] = "CRITICAL"
                    result["critical_issues"].extend(quality_analysis.get("issues", []))
                elif quality_analysis["status"] == "WARNING" and result["overall_status"] == "OK":
                    result["overall_status"] = "WARNING"

                break  # İlk tab'ın sample'ı yeterli

        # 3. Pipeline tutarlılık analizi (Notion olan projeler için)
        if notion_result and pipeline == "sheets_to_notion":
            # primary_tab varsa sadece onun satır sayısını kullan,
            # yoksa tüm tab'ları topla (geriye uyumluluk)
            primary_tab = project.get("primary_tab")
            if primary_tab and primary_tab in sheets_result.get("tab_results", {}):
                total_sheets = sheets_result["tab_results"][primary_tab].get("total_rows", 0)
                logger.info(
                    f"📊 [{name}] Pipeline tutarlılık: sadece '{primary_tab}' tab'ı "
                    f"({total_sheets} satır) kullanılıyor"
                )
            else:
                total_sheets = sum(
                    td.get("total_rows", 0)
                    for td in sheets_result.get("tab_results", {}).values()
                )

            notion_24h = notion_result.get("details", {}).get("recent_count_24h", {}).get("count", -1)

            if notion_24h >= 0:
                consistency = self.analyze_pipeline_consistency(
                    name, total_sheets, notion_24h, pipeline
                )
                consistency["type"] = "pipeline_consistency"
                result["analyses"].append(consistency)

                if consistency["status"] == "CRITICAL":
                    result["overall_status"] = "CRITICAL"
                    result["critical_issues"].append(consistency["analysis"])

        return result
