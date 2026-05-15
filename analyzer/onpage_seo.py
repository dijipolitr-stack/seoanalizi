"""
SEO Analyzer — On-Page SEO Analizi
====================================
İçerik kalitesi, heading yapısı, görsel optimizasyon, iç/dış link analizi,
E-E-A-T sinyalleri ve kelime/öbek stratejisi.
"""
import re
import logging
from dataclasses import dataclass, field
from collections import Counter

from analyzer.site_crawler import CrawlResult, PageData

logger = logging.getLogger(__name__)


@dataclass
class OnPageIssue:
    """On-page SEO sorunu."""
    severity: str  # CRITICAL, WARNING, INFO
    category: str
    title: str
    description: str
    affected_urls: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class ContentStats:
    """Site geneli içerik istatistikleri."""
    total_pages: int = 0
    avg_word_count: float = 0.0
    min_word_count: int = 0
    max_word_count: int = 0
    thin_content_pages: list[str] = field(default_factory=list)  # <300 kelime
    pages_without_images: list[str] = field(default_factory=list)
    images_without_alt: int = 0
    total_images: int = 0
    alt_coverage: float = 0.0


@dataclass
class LinkStats:
    """İç/dış link istatistikleri."""
    avg_internal_links: float = 0.0
    avg_external_links: float = 0.0
    orphan_pages: list[str] = field(default_factory=list)
    pages_without_internal_links: list[str] = field(default_factory=list)
    total_unique_internal: int = 0
    total_unique_external: int = 0
    external_domains: dict[str, int] = field(default_factory=dict)


@dataclass
class EEATSignals:
    """E-E-A-T sinyal analizi."""
    signals: dict[str, bool] = field(default_factory=dict)
    score: float = 0.0  # 0-10
    details: dict[str, str] = field(default_factory=dict)


@dataclass
class OnPageSEOResult:
    """On-Page SEO analiz sonuçları."""
    score: float = 0.0  # 0-100
    issues: list[OnPageIssue] = field(default_factory=list)
    content_stats: ContentStats = field(default_factory=ContentStats)
    link_stats: LinkStats = field(default_factory=LinkStats)
    eeat_signals: EEATSignals = field(default_factory=EEATSignals)
    title_analysis: dict = field(default_factory=dict)
    keyword_patterns: dict = field(default_factory=dict)


class OnPageSEOAnalyzer:
    """On-Page SEO analiz modülü."""

    # Türkçe pozitif ve güven ifadeleri
    TRUST_KEYWORDS_TR = [
        "ücretsiz kargo", "ücretsiz montaj", "garantili", "güvenli", "iade",
        "taksit", "kampanya", "indirim", "avantajlı", "hızlı kargo",
        "7/24", "müşteri hizmetleri", "destek", "ssl", "güvenlik",
    ]

    EEAT_PAGE_PATTERNS = {
        "about": [r"hakkımızda", r"hakkinda", r"about", r"kurumsal"],
        "contact": [r"iletişim", r"iletisim", r"contact", r"bize.?ulaşın"],
        "privacy": [r"gizlilik", r"kvkk", r"privacy", r"kişisel.?veri"],
        "terms": [r"sözleşme", r"kullanım.?koşulları", r"terms", r"şartlar"],
        "return": [r"iade", r"iptal", r"return", r"değişim"],
        "faq": [r"sss", r"sık.?sorulan", r"faq", r"yardım"],
        "blog": [r"blog", r"haber", r"makale", r"rehber", r"bilgi"],
    }

    def analyze(self, crawl: CrawlResult) -> OnPageSEOResult:
        """Tam on-page SEO analizi."""
        result = OnPageSEOResult()

        logger.info("📝 On-Page SEO analizi başlıyor...")

        active_pages = [p for p in crawl.pages if p.status_code == 200]

        self._analyze_content(active_pages, result)
        self._analyze_titles(active_pages, result)
        self._analyze_images(active_pages, result)
        self._analyze_links(active_pages, crawl, result)
        self._analyze_eeat(active_pages, crawl, result)
        self._analyze_keyword_patterns(active_pages, result)

        result.score = self._calculate_score(result)

        logger.info(f"  📊 On-Page SEO Skoru: {result.score:.0f}/100")

        return result

    def _analyze_content(self, pages: list[PageData], result: OnPageSEOResult):
        """İçerik kalitesi analizi."""
        word_counts = [p.word_count for p in pages if p.word_count > 0]

        if not word_counts:
            return

        stats = result.content_stats
        stats.total_pages = len(pages)
        stats.avg_word_count = sum(word_counts) / len(word_counts)
        stats.min_word_count = min(word_counts)
        stats.max_word_count = max(word_counts)

        # Thin content (300 kelimeden az)
        stats.thin_content_pages = [
            p.url for p in pages if 0 < p.word_count < 300
        ]

        if len(stats.thin_content_pages) > len(pages) * 0.3:
            result.issues.append(OnPageIssue(
                severity="WARNING",
                category="content",
                title=f"{len(stats.thin_content_pages)} sayfada thin content var (<300 kelime)",
                description=(
                    "Az içerikli sayfalar Google'ın 'Helpful Content' filtresine takılabilir. "
                    f"Ortalama kelime sayısı: {stats.avg_word_count:.0f}"
                ),
                affected_urls=stats.thin_content_pages[:5],
                recommendation=(
                    "Thin content sayfalarını en az 500 kelimeye çıkarın, "
                    "veya ilgili sayfalarla birleştirin."
                ),
            ))

    def _analyze_titles(self, pages: list[PageData], result: OnPageSEOResult):
        """Title tag kalite analizi."""
        titles = [p.title for p in pages if p.title]
        title_lengths = [len(t) for t in titles]

        result.title_analysis = {
            "total_with_title": len(titles),
            "avg_length": sum(title_lengths) / len(title_lengths) if title_lengths else 0,
            "too_long": sum(1 for l in title_lengths if l > 60),
            "too_short": sum(1 for l in title_lengths if l < 20),
            "with_year": sum(1 for t in titles if re.search(r"20\d{2}", t)),
            "with_brand_suffix": 0,  # Marka tutarlılığı
        }

        # Marka tutarlılığı: En sık geçen suffix'i bul
        if titles:
            suffixes = []
            for t in titles:
                if " | " in t:
                    suffixes.append(t.split(" | ")[-1].strip())
                elif " - " in t:
                    suffixes.append(t.split(" - ")[-1].strip())

            if suffixes:
                most_common = Counter(suffixes).most_common(1)
                if most_common:
                    brand_suffix = most_common[0][0]
                    result.title_analysis["brand_suffix"] = brand_suffix
                    result.title_analysis["with_brand_suffix"] = sum(
                        1 for t in titles if brand_suffix in t
                    )

    def _analyze_images(self, pages: list[PageData], result: OnPageSEOResult):
        """Görsel optimizasyon analizi."""
        stats = result.content_stats
        total_images = 0
        images_without_alt = 0

        for page in pages:
            if not page.images:
                stats.pages_without_images.append(page.url)
            for img in page.images:
                total_images += 1
                if not img["has_alt"]:
                    images_without_alt += 1

        stats.total_images = total_images
        stats.images_without_alt = images_without_alt
        stats.alt_coverage = (
            ((total_images - images_without_alt) / total_images * 100)
            if total_images > 0 else 0
        )

        if stats.alt_coverage < 70:
            result.issues.append(OnPageIssue(
                severity="WARNING",
                category="images",
                title=f"Görsel alt text kapsamı düşük (%{stats.alt_coverage:.0f})",
                description=(
                    f"{total_images} görselden {images_without_alt}'inde alt text yok. "
                    "Alt text hem erişilebilirlik hem Google Görseller SEO'su için önemli."
                ),
                recommendation=(
                    "Tüm görsellere açıklayıcı alt text ekleyin. "
                    "Format: '{Ürün adı} {özellik}' (örn: '205/55R16 Michelin lastik')"
                ),
            ))

    def _analyze_links(self, pages: list[PageData], crawl: CrawlResult, result: OnPageSEOResult):
        """İç ve dış link analizi."""
        stats = result.link_stats
        all_internal = set()
        all_external = set()
        external_domains: dict[str, int] = {}

        internal_counts = []
        external_counts = []

        for page in pages:
            internal_counts.append(len(page.internal_links))
            external_counts.append(len(page.external_links))
            all_internal.update(page.internal_links)
            all_external.update(page.external_links)

            for ext in page.external_links:
                from urllib.parse import urlparse
                domain = urlparse(ext).netloc
                external_domains[domain] = external_domains.get(domain, 0) + 1

            if not page.internal_links:
                stats.pages_without_internal_links.append(page.url)

        stats.avg_internal_links = sum(internal_counts) / len(internal_counts) if internal_counts else 0
        stats.avg_external_links = sum(external_counts) / len(external_counts) if external_counts else 0
        stats.total_unique_internal = len(all_internal)
        stats.total_unique_external = len(all_external)
        stats.external_domains = dict(sorted(
            external_domains.items(), key=lambda x: x[1], reverse=True
        )[:20])

        # Yetim sayfalar (hiçbir sayfadan link almayan)
        linked_pages = set()
        for page in pages:
            linked_pages.update(page.internal_links)
        stats.orphan_pages = [
            p.url for p in pages if p.url not in linked_pages and p.url != crawl.base_url
        ]

        if stats.avg_internal_links < 3:
            result.issues.append(OnPageIssue(
                severity="WARNING",
                category="links",
                title=f"Ortalama iç link sayısı düşük ({stats.avg_internal_links:.1f})",
                description="Az iç link, crawl bütçesinin verimsiz kullanılması demektir.",
                recommendation="Her sayfada en az 5-10 ilgili iç link bulundurun.",
            ))

    def _analyze_eeat(self, pages: list[PageData], crawl: CrawlResult, result: OnPageSEOResult):
        """E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) sinyal analizi."""
        eeat = result.eeat_signals
        all_text = " ".join(p.text_content.lower() for p in pages)
        all_urls = [p.url.lower() for p in pages]

        # E-E-A-T sayfaları var mı?
        for signal_name, patterns in self.EEAT_PAGE_PATTERNS.items():
            found = False
            for pattern in patterns:
                # URL'de ara
                if any(re.search(pattern, url) for url in all_urls):
                    found = True
                    break
                # İçerikte ara (başlıklarda)
                for page in pages:
                    all_headings = page.h1 + page.h2
                    if any(re.search(pattern, h.lower()) for h in all_headings):
                        found = True
                        break
                if found:
                    break

            eeat.signals[signal_name] = found

        # Ek E-E-A-T sinyalleri
        eeat.signals["ssl"] = crawl.ssl_valid
        eeat.signals["social_media"] = bool(
            re.search(r"(instagram|facebook|linkedin|twitter|youtube|x\.com)", all_text)
        )
        eeat.signals["phone_number"] = bool(
            re.search(r"(\+90|0\d{3}|\d{3}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}|444\s?\d{2}\s?\d{2})", all_text)
        )
        eeat.signals["email"] = bool(
            re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", all_text)
        )
        eeat.signals["reviews"] = bool(
            re.search(r"(yorum|değerlendirme|review|puan|rating|müşteri.?görüş)", all_text)
        )

        # Skor hesapla (0-10)
        positive = sum(1 for v in eeat.signals.values() if v)
        total = len(eeat.signals)
        eeat.score = round(positive / total * 10, 1) if total > 0 else 0

        if eeat.score < 5:
            result.issues.append(OnPageIssue(
                severity="WARNING",
                category="eeat",
                title=f"E-E-A-T skoru düşük ({eeat.score}/10)",
                description=(
                    f"{total} kriterden sadece {positive}'i karşılanıyor. "
                    "Google, güvenilirlik sinyallerini sıralama için kullanır."
                ),
                recommendation=(
                    "Hakkımızda, İletişim, Gizlilik Politikası sayfaları ekleyin. "
                    "Sosyal medya linklerini footer'a koyun. "
                    "Müşteri yorumları/puanlama sistemi ekleyin."
                ),
            ))

    def _analyze_keyword_patterns(self, pages: list[PageData], result: OnPageSEOResult):
        """Kelime ve öbek stratejisi analizi."""
        all_text = " ".join(p.text_content.lower() for p in pages if p.text_content)

        # Trust keyword'leri say
        trust_counts = {}
        for kw in self.TRUST_KEYWORDS_TR:
            count = all_text.count(kw.lower())
            if count > 0:
                trust_counts[kw] = count

        # CTA pattern'leri
        cta_patterns = [
            r"hemen\s+(sipariş|satın al|ziyaret|başla|dene|üye ol|incele|göz at)",
            r"(satın al|sipariş ver|sepete ekle|şimdi al|hemen al)",
            r"(tıklayın|tıkla|inceleyin|keşfedin|göz atın)",
        ]
        cta_count = sum(
            len(re.findall(pattern, all_text, re.IGNORECASE))
            for pattern in cta_patterns
        )

        result.keyword_patterns = {
            "trust_keywords": trust_counts,
            "total_trust_mentions": sum(trust_counts.values()),
            "cta_count": cta_count,
            "has_pricing_language": bool(
                re.search(r"(fiyat|ücret|maliyet|tl|₺|taksit|indirim|kampanya)", all_text)
            ),
            "has_urgency_language": bool(
                re.search(r"(sınırlı|son\s+\d|hemen|acil|bugün|şimdi|kaçırma)", all_text)
            ),
        }

    def _calculate_score(self, result: OnPageSEOResult) -> float:
        """On-Page SEO skorunu hesaplar."""
        score = 100.0

        for issue in result.issues:
            if issue.severity == "CRITICAL":
                score -= 15
            elif issue.severity == "WARNING":
                score -= 7
            elif issue.severity == "INFO":
                score -= 2

        # Pozitif sinyaller
        if result.eeat_signals.score >= 7:
            score += 5
        if result.content_stats.alt_coverage > 80:
            score += 3
        if result.link_stats.avg_internal_links >= 5:
            score += 3

        return max(0, min(100, score))
