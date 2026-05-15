"""
SEO Analyzer — Teknik SEO Kontrolü
====================================
SSL, robots.txt, sitemap, URL yapısı, meta tags, heading hiyerarşisi,
schema markup, mobil uyumluluk ve sayfa hızı analizi.
"""
import re
import logging
from urllib.parse import urlparse
from dataclasses import dataclass, field

from analyzer.site_crawler import CrawlResult, PageData

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIssue:
    """Tek bir teknik SEO sorunu."""
    severity: str  # CRITICAL, WARNING, INFO
    category: str  # ssl, robots, sitemap, url, meta, heading, schema, speed, mobile
    title: str
    description: str
    affected_urls: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class TechnicalSEOResult:
    """Teknik SEO analiz sonuçları."""
    score: float = 0.0  # 0-100
    issues: list[TechnicalIssue] = field(default_factory=list)
    ssl_status: dict = field(default_factory=dict)
    robots_status: dict = field(default_factory=dict)
    sitemap_status: dict = field(default_factory=dict)
    url_analysis: dict = field(default_factory=dict)
    meta_analysis: dict = field(default_factory=dict)
    heading_analysis: dict = field(default_factory=dict)
    schema_analysis: dict = field(default_factory=dict)
    speed_analysis: dict = field(default_factory=dict)
    mobile_analysis: dict = field(default_factory=dict)
    redirect_analysis: dict = field(default_factory=dict)


class TechnicalSEOAnalyzer:
    """Teknik SEO kontrolü yapan analiz modülü."""

    def analyze(self, crawl: CrawlResult) -> TechnicalSEOResult:
        """Tam teknik SEO analizi çalıştırır."""
        result = TechnicalSEOResult()

        logger.info("🔧 Teknik SEO analizi başlıyor...")

        self._analyze_ssl(crawl, result)
        self._analyze_redirects(crawl, result)
        self._analyze_robots(crawl, result)
        self._analyze_sitemap(crawl, result)
        self._analyze_urls(crawl, result)
        self._analyze_meta(crawl, result)
        self._analyze_headings(crawl, result)
        self._analyze_schema(crawl, result)
        self._analyze_speed(crawl, result)
        self._analyze_mobile(crawl, result)

        # Skor hesapla
        result.score = self._calculate_score(result)

        logger.info(f"  📊 Teknik SEO Skoru: {result.score:.0f}/100")
        logger.info(
            f"  🔴 {sum(1 for i in result.issues if i.severity == 'CRITICAL')} kritik | "
            f"⚠️ {sum(1 for i in result.issues if i.severity == 'WARNING')} uyarı | "
            f"ℹ️ {sum(1 for i in result.issues if i.severity == 'INFO')} bilgi"
        )

        return result

    def _analyze_ssl(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """SSL sertifika analizi."""
        result.ssl_status = {
            "valid": crawl.ssl_valid,
            "issuer": crawl.ssl_issuer,
            "expiry": crawl.ssl_expiry,
        }

        if not crawl.ssl_valid:
            result.issues.append(TechnicalIssue(
                severity="CRITICAL",
                category="ssl",
                title="SSL sertifikası geçersiz veya yok",
                description=(
                    "Site HTTPS ile güvenli bağlantı sağlayamıyor. "
                    "Google, SSL'siz siteleri arama sonuçlarında cezalandırır."
                ),
                recommendation="Geçerli bir SSL sertifikası yükleyin (Let's Encrypt ücretsiz).",
            ))

    def _analyze_redirects(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Redirect analizi."""
        result.redirect_analysis = {
            "https_redirect": crawl.https_redirect,
            "www_redirect": crawl.www_redirect,
        }

        if not crawl.https_redirect:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="redirect",
                title="HTTP → HTTPS yönlendirmesi yok",
                description="HTTP versiyonundan HTTPS'e otomatik yönlendirme tespit edilemedi.",
                recommendation="Tüm HTTP trafiğini 301 redirect ile HTTPS'e yönlendirin.",
            ))

    def _analyze_robots(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """robots.txt analizi."""
        result.robots_status = {
            "accessible": crawl.robots_accessible,
            "content_length": len(crawl.robots_txt),
            "has_sitemap_ref": "sitemap" in crawl.robots_txt.lower() if crawl.robots_txt else False,
            "has_disallow": "disallow" in crawl.robots_txt.lower() if crawl.robots_txt else False,
        }

        if not crawl.robots_accessible:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="robots",
                title="robots.txt erişilemiyor",
                description=(
                    "robots.txt dosyasına erişilemiyor. Bu dosya arama motoru "
                    "botlarına hangi sayfaları tarayabileceklerini söyler."
                ),
                recommendation="Kök dizine uygun bir robots.txt dosyası ekleyin.",
            ))

        if crawl.robots_accessible and not result.robots_status["has_sitemap_ref"]:
            result.issues.append(TechnicalIssue(
                severity="INFO",
                category="robots",
                title="robots.txt'te sitemap referansı yok",
                description="robots.txt dosyasında Sitemap: satırı bulunamadı.",
                recommendation="robots.txt'e 'Sitemap: https://domain.com/sitemap.xml' satırı ekleyin.",
            ))

    def _analyze_sitemap(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Sitemap analizi."""
        result.sitemap_status = {
            "accessible": crawl.sitemap_accessible,
            "url": crawl.sitemap_url,
            "url_count": len(crawl.sitemap_urls),
        }

        if not crawl.sitemap_accessible:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="sitemap",
                title="XML Sitemap bulunamadı",
                description=(
                    "sitemap.xml veya sitemap_index.xml erişilemiyor. "
                    "Sitemap, Google'ın sayfalarınızı keşfetmesini hızlandırır."
                ),
                recommendation="XML sitemap oluşturup /sitemap.xml adresinde yayınlayın.",
            ))

    def _analyze_urls(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """URL yapısı analizi."""
        long_urls = []
        param_urls = []
        uppercase_urls = []
        underscore_urls = []
        depth_issues = []

        for page in crawl.pages:
            parsed = urlparse(page.url)
            path = parsed.path

            # Uzun URL (80+ karakter)
            if len(path) > 80:
                long_urls.append(page.url)

            # Query parameter'lı URL'ler
            if parsed.query:
                param_urls.append(page.url)

            # Büyük harf içeren URL
            if path != path.lower():
                uppercase_urls.append(page.url)

            # Alt çizgi
            if "_" in path:
                underscore_urls.append(page.url)

            # Derinlik (4+ seviye)
            depth = len([p for p in path.split("/") if p])
            if depth > 4:
                depth_issues.append(page.url)

        result.url_analysis = {
            "total_urls": len(crawl.pages),
            "long_urls": len(long_urls),
            "param_urls": len(param_urls),
            "uppercase_urls": len(uppercase_urls),
            "underscore_urls": len(underscore_urls),
            "deep_urls": len(depth_issues),
        }

        if long_urls:
            result.issues.append(TechnicalIssue(
                severity="INFO",
                category="url",
                title=f"{len(long_urls)} sayfa çok uzun URL'e sahip (80+ karakter)",
                description="Uzun URL'ler paylaşılabilirliği düşürür ve snippet'te truncate olur.",
                affected_urls=long_urls[:5],
                recommendation="URL slug'larını kısaltın, gereksiz parametreleri kaldırın.",
            ))

        if uppercase_urls:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="url",
                title=f"{len(uppercase_urls)} URL'de büyük harf var",
                description="Büyük harf içeren URL'ler duplicate content riski oluşturur.",
                affected_urls=uppercase_urls[:5],
                recommendation="Tüm URL'leri küçük harfe çevirin, 301 redirect kurun.",
            ))

    def _analyze_meta(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Meta tag analizi."""
        missing_title = []
        long_title = []
        short_title = []
        duplicate_titles = {}
        missing_desc = []
        long_desc = []
        short_desc = []
        missing_canonical = []

        for page in crawl.pages:
            if page.status_code != 200:
                continue

            # Title
            if not page.title:
                missing_title.append(page.url)
            elif len(page.title) > 60:
                long_title.append(page.url)
            elif len(page.title) < 20:
                short_title.append(page.url)

            # Duplicate title tespiti
            if page.title:
                duplicate_titles.setdefault(page.title, []).append(page.url)

            # Meta description
            if not page.meta_description:
                missing_desc.append(page.url)
            elif len(page.meta_description) > 160:
                long_desc.append(page.url)
            elif len(page.meta_description) < 50:
                short_desc.append(page.url)

            # Canonical
            if not page.canonical:
                missing_canonical.append(page.url)

        dup_titles = {t: urls for t, urls in duplicate_titles.items() if len(urls) > 1}

        result.meta_analysis = {
            "missing_title": len(missing_title),
            "long_title": len(long_title),
            "short_title": len(short_title),
            "duplicate_titles": len(dup_titles),
            "missing_description": len(missing_desc),
            "long_description": len(long_desc),
            "short_description": len(short_desc),
            "missing_canonical": len(missing_canonical),
        }

        if missing_title:
            result.issues.append(TechnicalIssue(
                severity="CRITICAL",
                category="meta",
                title=f"{len(missing_title)} sayfada title tag eksik",
                description="Title tag olmayan sayfalar Google'da düzgün indekslenmez.",
                affected_urls=missing_title[:5],
                recommendation="Her sayfaya benzersiz, 30-60 karakter arası title tag ekleyin.",
            ))

        if missing_desc:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="meta",
                title=f"{len(missing_desc)} sayfada meta description eksik",
                description="Meta description olmayan sayfalarda Google kendi snippet'ini oluşturur.",
                affected_urls=missing_desc[:5],
                recommendation="Her sayfaya 120-160 karakter arası özgün meta description yazın.",
            ))

        if dup_titles:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="meta",
                title=f"{len(dup_titles)} adet yinelenen (duplicate) title tespit edildi",
                description="Aynı title'ı paylaşan sayfalar Google'da cannibalization yaratır.",
                recommendation="Her sayfanın benzersiz bir title'ı olmalı.",
            ))

    def _analyze_headings(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """H1-H6 heading hiyerarşi analizi."""
        missing_h1 = []
        multiple_h1 = []
        empty_h1 = []

        for page in crawl.pages:
            if page.status_code != 200:
                continue

            if not page.h1:
                missing_h1.append(page.url)
            elif len(page.h1) > 1:
                multiple_h1.append(page.url)
            elif page.h1 and not page.h1[0].strip():
                empty_h1.append(page.url)

        result.heading_analysis = {
            "missing_h1": len(missing_h1),
            "multiple_h1": len(multiple_h1),
            "empty_h1": len(empty_h1),
        }

        if missing_h1:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="heading",
                title=f"{len(missing_h1)} sayfada H1 etiketi eksik",
                description="H1 etiketi sayfanın ana konusunu belirler, SEO için kritiktir.",
                affected_urls=missing_h1[:5],
                recommendation="Her sayfaya tek bir, açıklayıcı H1 etiketi ekleyin.",
            ))

        if multiple_h1:
            result.issues.append(TechnicalIssue(
                severity="INFO",
                category="heading",
                title=f"{len(multiple_h1)} sayfada birden fazla H1 var",
                description="Birden fazla H1 Google'a karışık sinyal verir.",
                affected_urls=multiple_h1[:5],
                recommendation="Her sayfada sadece bir H1 kullanın, diğerlerini H2'ye çevirin.",
            ))

    def _analyze_schema(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Schema.org yapısal veri analizi."""
        all_schemas: dict[str, int] = {}
        pages_with_schema = 0
        pages_without_schema = []

        for page in crawl.pages:
            if page.status_code != 200:
                continue

            if page.schema_types:
                pages_with_schema += 1
                for st in page.schema_types:
                    all_schemas[st] = all_schemas.get(st, 0) + 1
            else:
                pages_without_schema.append(page.url)

        total_pages = sum(1 for p in crawl.pages if p.status_code == 200)
        coverage = (pages_with_schema / total_pages * 100) if total_pages > 0 else 0

        result.schema_analysis = {
            "total_pages": total_pages,
            "pages_with_schema": pages_with_schema,
            "coverage_percent": round(coverage, 1),
            "schema_types": all_schemas,
            "pages_without_schema": len(pages_without_schema),
        }

        if coverage < 30:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="schema",
                title=f"Schema markup kapsamı düşük (%{coverage:.0f})",
                description=(
                    f"{total_pages} sayfanın sadece {pages_with_schema}'inde schema var. "
                    "Schema markup SERP'te rich snippet gösterimini sağlar."
                ),
                recommendation=(
                    "Ürün sayfalarına Product, kategori sayfalarına ItemList, "
                    "blog yazılarına Article schema ekleyin."
                ),
            ))

    def _analyze_speed(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Sayfa hızı analizi (crawl sırasında ölçülen response time)."""
        load_times = [p.load_time for p in crawl.pages if p.status_code == 200 and p.load_time > 0]

        if not load_times:
            result.speed_analysis = {"avg_load_time": 0, "slow_pages": 0}
            return

        avg_time = sum(load_times) / len(load_times)
        slow_pages = [p.url for p in crawl.pages if p.load_time > 3.0]

        result.speed_analysis = {
            "avg_load_time": round(avg_time, 2),
            "min_load_time": round(min(load_times), 2),
            "max_load_time": round(max(load_times), 2),
            "slow_pages": len(slow_pages),
        }

        if avg_time > 3.0:
            result.issues.append(TechnicalIssue(
                severity="WARNING",
                category="speed",
                title=f"Ortalama sayfa yükleme süresi yüksek ({avg_time:.1f}s)",
                description="3 saniyeden uzun yüklenen sayfalar hem UX hem SEO'yu olumsuz etkiler.",
                affected_urls=slow_pages[:5],
                recommendation="Görsel optimizasyonu (WebP), lazy loading, CDN ve cache uygulayın.",
            ))

    def _analyze_mobile(self, crawl: CrawlResult, result: TechnicalSEOResult):
        """Mobil uyumluluk analizi."""
        pages_without_viewport = []

        for page in crawl.pages:
            if page.status_code != 200:
                continue
            if not page.has_viewport:
                pages_without_viewport.append(page.url)

        total_pages = sum(1 for p in crawl.pages if p.status_code == 200)
        viewport_coverage = (
            ((total_pages - len(pages_without_viewport)) / total_pages * 100)
            if total_pages > 0 else 0
        )

        result.mobile_analysis = {
            "viewport_coverage": round(viewport_coverage, 1),
            "pages_without_viewport": len(pages_without_viewport),
        }

        if pages_without_viewport:
            result.issues.append(TechnicalIssue(
                severity="CRITICAL",
                category="mobile",
                title=f"{len(pages_without_viewport)} sayfada viewport meta tag eksik",
                description=(
                    "Viewport meta tag'ı olmayan sayfalar mobil cihazlarda düzgün görüntülenmez. "
                    "Google mobile-first indexing kullanıyor."
                ),
                affected_urls=pages_without_viewport[:5],
                recommendation='<meta name="viewport" content="width=device-width, initial-scale=1"> ekleyin.',
            ))

    def _calculate_score(self, result: TechnicalSEOResult) -> float:
        """Teknik SEO skorunu hesaplar (0-100)."""
        score = 100.0

        for issue in result.issues:
            if issue.severity == "CRITICAL":
                score -= 15
            elif issue.severity == "WARNING":
                score -= 5
            elif issue.severity == "INFO":
                score -= 1

        # Pozitif sinyaller ekle
        if result.ssl_status.get("valid"):
            score += 2
        if result.redirect_analysis.get("https_redirect"):
            score += 2
        if result.sitemap_status.get("accessible"):
            score += 3
        if result.robots_status.get("accessible"):
            score += 2
        if result.schema_analysis.get("coverage_percent", 0) > 50:
            score += 5

        return max(0, min(100, score))
