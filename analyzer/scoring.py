"""
SEO Analyzer — ICE Skorlama Sistemi
=====================================
Impact × Confidence × Ease skorlaması ile SEO aksiyonlarını önceliklendirme.
"""
import logging
from dataclasses import dataclass, field

from seo_config import SEOConfig

logger = logging.getLogger(__name__)


@dataclass
class SEOAction:
    """Tek bir SEO aksiyon önerisi."""
    id: int = 0
    title: str = ""
    category: str = ""
    impact: int = 5        # 1-10
    confidence: int = 5    # 1-10
    ease: int = 5          # 1-10
    ice_score: float = 0.0
    priority: str = ""     # P0, P1, P2, P3
    description: str = ""
    recommendation: str = ""
    estimated_cost: str = ""
    expected_benefit: str = ""
    timeline: str = ""
    source_issues: list[str] = field(default_factory=list)


def calculate_ice(impact: int, confidence: int, ease: int) -> float:
    """ICE skorunu hesaplar (max 100)."""
    return (impact * confidence * ease) / 10


def get_priority(ice_score: float) -> str:
    """ICE skorundan öncelik seviyesi belirler."""
    thresholds = SEOConfig.ICE_THRESHOLDS
    if ice_score >= thresholds["P0"]:
        return "P0"
    elif ice_score >= thresholds["P1"]:
        return "P1"
    elif ice_score >= thresholds["P2"]:
        return "P2"
    return "P3"


def get_priority_label(priority: str) -> str:
    """Öncelik seviyesinin Türkçe etiketini döner."""
    labels = {
        "P0": "🔴 ŞİMDİ BAŞLAYIN (Bu ay)",
        "P1": "🟠 SONRAKI (3-6 ay)",
        "P2": "🟡 PLANLANAN (6-12 ay)",
        "P3": "🟢 DİKKATLE İZLEYİN",
    }
    return labels.get(priority, "")


def generate_actions_from_issues(technical_issues, onpage_issues) -> list[SEOAction]:
    """Tespit edilen sorunlardan aksiyon önerileri üretir."""
    actions = []
    action_id = 1

    # ── Teknik SEO sorunlarından aksiyonlar ──
    issue_action_map = {
        "ssl": {"impact": 9, "confidence": 10, "ease": 9, "category": "Teknik SEO"},
        "redirect": {"impact": 7, "confidence": 9, "ease": 9, "category": "Teknik SEO"},
        "robots": {"impact": 6, "confidence": 8, "ease": 10, "category": "Teknik SEO"},
        "sitemap": {"impact": 7, "confidence": 9, "ease": 9, "category": "Teknik SEO"},
        "meta": {"impact": 8, "confidence": 9, "ease": 8, "category": "On-Page SEO"},
        "heading": {"impact": 6, "confidence": 8, "ease": 9, "category": "On-Page SEO"},
        "schema": {"impact": 7, "confidence": 8, "ease": 7, "category": "Teknik SEO"},
        "speed": {"impact": 7, "confidence": 7, "ease": 6, "category": "Performans"},
        "mobile": {"impact": 9, "confidence": 10, "ease": 8, "category": "Teknik SEO"},
        "url": {"impact": 5, "confidence": 7, "ease": 6, "category": "Teknik SEO"},
    }

    # Grupla: Aynı kategorideki sorunları birleştir
    grouped_issues: dict[str, list] = {}
    for issue in technical_issues:
        grouped_issues.setdefault(issue.category, []).append(issue)

    for category, issues in grouped_issues.items():
        params = issue_action_map.get(category, {
            "impact": 5, "confidence": 7, "ease": 7, "category": "Diğer"
        })

        # Severity'ye göre impact'i ayarla
        max_severity = max(
            ("CRITICAL", "WARNING", "INFO").index(i.severity)
            for i in issues
        )
        if max_severity == 0:  # CRITICAL
            adjusted_impact = min(10, params["impact"] + 2)
        elif max_severity == 1:  # WARNING
            adjusted_impact = params["impact"]
        else:
            adjusted_impact = max(3, params["impact"] - 2)

        ice = calculate_ice(adjusted_impact, params["confidence"], params["ease"])
        priority = get_priority(ice)

        action = SEOAction(
            id=action_id,
            title=f"{params['category']}: {issues[0].title}",
            category=params["category"],
            impact=adjusted_impact,
            confidence=params["confidence"],
            ease=params["ease"],
            ice_score=ice,
            priority=priority,
            description=issues[0].description,
            recommendation=issues[0].recommendation,
            source_issues=[i.title for i in issues],
        )
        actions.append(action)
        action_id += 1

    # ── On-Page sorunlarından aksiyonlar ──
    onpage_map = {
        "content": {"impact": 7, "confidence": 8, "ease": 6, "category": "İçerik"},
        "images": {"impact": 5, "confidence": 9, "ease": 8, "category": "Görsel SEO"},
        "links": {"impact": 7, "confidence": 8, "ease": 7, "category": "İç Linkleme"},
        "eeat": {"impact": 8, "confidence": 9, "ease": 7, "category": "E-E-A-T"},
    }

    grouped_onpage: dict[str, list] = {}
    for issue in onpage_issues:
        grouped_onpage.setdefault(issue.category, []).append(issue)

    for category, issues in grouped_onpage.items():
        params = onpage_map.get(category, {
            "impact": 5, "confidence": 7, "ease": 7, "category": "Diğer"
        })

        ice = calculate_ice(params["impact"], params["confidence"], params["ease"])
        priority = get_priority(ice)

        action = SEOAction(
            id=action_id,
            title=f"{params['category']}: {issues[0].title}",
            category=params["category"],
            impact=params["impact"],
            confidence=params["confidence"],
            ease=params["ease"],
            ice_score=ice,
            priority=priority,
            description=issues[0].description,
            recommendation=issues[0].recommendation,
            source_issues=[i.title for i in issues],
        )
        actions.append(action)
        action_id += 1

    # ICE skoruna göre sırala
    actions.sort(key=lambda a: a.ice_score, reverse=True)

    # ID'leri yeniden numaralandır
    for i, action in enumerate(actions, 1):
        action.id = i

    return actions
