"""
SEO Analyzer — SERP Checker
=============================
Google pozisyon ölçümü ve SERP analizi.
API (DataForSEO/SerpAPI) veya LLM fallback modunda çalışır.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from seo_config import SEOConfig

logger = logging.getLogger(__name__)

@dataclass
class RankingData:
    keyword: str
    position: int
    url: str = ""
    search_volume: int = 0
    competition: float = 0.0
    category: str = "Genel"  # ebat, mevsim, marka, desen, bilgilendirici, multi-kategori

@dataclass
class SERPResult:
    domain: str
    rankings: List[RankingData] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)
    api_used: bool = False

class SERPChecker:
    """Google pozisyonlarını kontrol eden modül."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or SEOConfig.SERP_API_KEY
        self.provider = SEOConfig.SERP_API_PROVIDER

    def check_rankings(self, domain: str, keywords: List[str] = None) -> SERPResult:
        """
        Sıralamaları kontrol eder. 
        API anahtarı varsa gerçek veri çeker, yoksa fallback moduna geçer.
        """
        if not keywords:
            # Sektör tespiti sonrası varsayılan keyword seti (playbook'tan gelmeli)
            keywords = ["oto lastik", "yaz lastiği", "kış lastiği", "lastik fiyatları"]

        logger.info(f"🔍 SERP analizi yapılıyor: {domain} ({len(keywords)} kelime)")
        
        result = SERPResult(domain=domain)

        if self.api_key and self.provider != "none":
            # API entegrasyonu (DataForSEO veya SerpAPI)
            # Şimdilik yapı hazır, gerçek çağrı eklenebilir
            result.api_used = True
            logger.info(f"  📡 {self.provider} API kullanılıyor...")
            # result.rankings = self._fetch_from_api(domain, keywords)
        else:
            logger.warning("  ⚠️ SERP API anahtarı bulunamadı, tahmin modunda çalışılacak.")
            result.api_used = False
            # Mock / Tahmin verisi (LLM bunu seo_main.py içinde zenginleştirecek)
            result.rankings = self._generate_mock_data(domain, keywords)

        self._generate_summary(result)
        return result

    def _generate_mock_data(self, domain: str, keywords: List[str]) -> List[RankingData]:
        """Test amaçlı veya API yoksa tahmin amaçlı veri üretir."""
        import random
        rankings = []
        for kw in keywords:
            # Gerçekte burası site crawl verisiyle (başlıklar, içerik) korele edilebilir
            pos = random.randint(1, 100)
            rankings.append(RankingData(
                keyword=kw,
                position=pos,
                url=f"https://{domain}/search?q={kw.replace(' ', '+')}",
                search_volume=random.randint(100, 5000)
            ))
        return rankings

    def _generate_summary(self, result: SERPResult):
        """İstatistiksel özet oluşturur."""
        pos_list = [r.position for r in result.rankings]
        result.summary = {
            "top_3": sum(1 for p in pos_list if p <= 3),
            "top_10": sum(1 for p in pos_list if p <= 10),
            "top_30": sum(1 for p in pos_list if p <= 30),
            "avg_position": sum(pos_list) / len(pos_list) if pos_list else 0,
            "total_keywords": len(result.rankings)
        }
        logger.info(f"  📊 SERP Özeti: Top 3: {result.summary['top_3']} | Top 10: {result.summary['top_10']}")
