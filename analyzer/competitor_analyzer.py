"""
SEO Analyzer — Competitor Analyzer
====================================
Rakip karşılaştırma ve sektör benchmark analizi.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict

logger = logging.getLogger(__name__)

@dataclass
class CompetitorData:
    domain: str
    seo_score: float
    est_traffic: int = 0
    keyword_count: int = 0
    backlink_count: int = 0

class CompetitorAnalyzer:
    """Rakiplerle site performansını kıyaslayan modül."""

    def __init__(self):
        # Varsayılan benchmark verileri (ileride JSON'dan yüklenebilir)
        self.benchmarks = {
            "ecommerce": {
                "avg_seo_score": 75,
                "avg_page_count": 500,
                "avg_load_time": 2.5,
                "schema_coverage": 80
            },
            "saas": {
                "avg_seo_score": 80,
                "avg_page_count": 100,
                "avg_load_time": 1.5,
                "schema_coverage": 60
            }
        }

    def analyze(self, site_summary: Dict, industry: str = "ecommerce") -> Dict:
        """Siteyi rakiplerle kıyaslar."""
        logger.info(f"🏁 Rakip analizi yapılıyor (Sektör: {industry})")
        
        bench = self.benchmarks.get(industry, self.benchmarks["ecommerce"])
        
        comparison = {
            "industry": industry,
            "metrics": {
                "score": {
                    "site": site_summary.get("overall_score", 0),
                    "benchmark": bench["avg_seo_score"],
                    "status": "above" if site_summary.get("overall_score", 0) > bench["avg_seo_score"] else "below"
                },
                "speed": {
                    "site": site_summary.get("avg_load_time", 0),
                    "benchmark": bench["avg_load_time"],
                    "status": "faster" if site_summary.get("avg_load_time", 0) < bench["avg_load_time"] else "slower"
                }
            },
            "gaps": self._identify_gaps(site_summary, bench)
        }
        
        return comparison

    def _identify_gaps(self, site_summary: Dict, bench: Dict) -> List[str]:
        """Eksiklikleri tespit eder."""
        gaps = []
        if site_summary.get("schema_coverage", 0) < bench["schema_coverage"]:
            gaps.append(f"Yapısal veri (Schema) kullanımı sektör ortalamasının (%{bench['schema_coverage']}) altında.")
        
        if site_summary.get("technical_score", 0) < 60:
            gaps.append("Teknik altyapı rakiplere göre ciddi risk taşıyor.")
            
        return gaps
