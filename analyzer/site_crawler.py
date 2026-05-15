"""
SEO Analyzer — Site Crawler
=============================
Hedef web sitesini tarar ve SEO analizi için veri toplar.
Ana sayfa + iç sayfaları crawl eder, meta bilgileri çıkarır.
"""
import re
import time
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from seo_config import SEOConfig

logger = logging.getLogger(__name__)


@dataclass
class PageData:
    """Tek bir sayfanın crawl sonuçları."""
    url: str
    status_code: int = 0
    title: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    h3: list[str] = field(default_factory=list)
    h4: list[str] = field(default_factory=list)
    h5: list[str] = field(default_factory=list)
    h6: list[str] = field(default_factory=list)
    canonical: str = ""
    robots_meta: str = ""
    og_tags: dict = field(default_factory=dict)
    schema_types: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)  # [{src, alt, has_alt}]
    word_count: int = 0
    text_content: str = ""
    load_time: float = 0.0
    content_type: str = ""
    has_viewport: bool = False
    has_lang: bool = False
    lang: str = ""
    charset: str = ""
    error: str = ""


@dataclass
class CrawlResult:
    """Tüm site crawl sonuçları."""
    base_url: str
    domain: str
    pages: list[PageData] = field(default_factory=list)
    robots_txt: str = ""
    robots_accessible: bool = False
    sitemap_url: str = ""
    sitemap_accessible: bool = False
    sitemap_urls: list[str] = field(default_factory=list)
    ssl_valid: bool = False
    ssl_issuer: str = ""
    ssl_expiry: str = ""
    www_redirect: bool = False
    https_redirect: bool = False
    total_pages_found: int = 0
    crawl_duration: float = 0.0
    errors: list[str] = field(default_factory=list)


class SiteCrawler:
    """Web sitesi SEO crawler."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": SEOConfig.CRAWL_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        })
        self._visited: set[str] = set()

    def crawl(self, url: str) -> CrawlResult:
        """
        Ana crawl fonksiyonu. Siteyi tarar ve CrawlResult döner.

        Args:
            url: Hedef site URL'i (örn: "lastikborsasi.com" veya "https://lastikborsasi.com")
        """
        start_time = time.time()

        # URL normalize
        if not url.startswith("http"):
            url = f"https://{url}"

        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        base_url = f"{parsed.scheme}://{domain}"

        logger.info(f"🕷️ Crawl başlıyor: {base_url}")
        logger.info(f"   Max sayfa: {SEOConfig.CRAWL_MAX_PAGES}")

        result = CrawlResult(base_url=base_url, domain=domain)

        # 1. SSL kontrolü
        self._check_ssl(result)

        # 2. Redirect kontrolü (HTTP → HTTPS, www)
        self._check_redirects(result)

        # 3. robots.txt
        self._fetch_robots(result)

        # 4. sitemap.xml
        self._fetch_sitemap(result)

        # 5. Ana sayfadan başlayarak crawl
        self._crawl_page(base_url, result)

        # 6. İç linklerden keşfedilen sayfaları crawl et
        pages_to_visit = []
        for page in result.pages:
            for link in page.internal_links:
                if link not in self._visited and len(result.pages) < SEOConfig.CRAWL_MAX_PAGES:
                    pages_to_visit.append(link)

        for link in pages_to_visit[:SEOConfig.CRAWL_MAX_PAGES - len(result.pages)]:
            if link not in self._visited:
                time.sleep(SEOConfig.CRAWL_DELAY)
                self._crawl_page(link, result)

        result.total_pages_found = len(self._visited)
        result.crawl_duration = time.time() - start_time

        logger.info(
            f"✅ Crawl tamamlandı: {len(result.pages)} sayfa, "
            f"{result.crawl_duration:.1f}s"
        )

        return result

    def _check_ssl(self, result: CrawlResult):
        """SSL sertifika kontrolü."""
        try:
            import ssl
            import socket
            from datetime import datetime

            hostname = result.domain.replace("www.", "")
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
                s.settimeout(10)
                s.connect((hostname, 443))
                cert = s.getpeercert()

                result.ssl_valid = True
                result.ssl_issuer = dict(x[0] for x in cert.get("issuer", [()])).get(
                    "organizationName", "Bilinmiyor"
                )
                expire_str = cert.get("notAfter", "")
                if expire_str:
                    result.ssl_expiry = expire_str

                logger.info(f"  🔒 SSL geçerli — {result.ssl_issuer}")

        except Exception as e:
            result.ssl_valid = False
            result.errors.append(f"SSL kontrolü başarısız: {e}")
            logger.warning(f"  ⚠️ SSL kontrolü başarısız: {e}")

    def _check_redirects(self, result: CrawlResult):
        """HTTP→HTTPS ve www redirect kontrolü."""
        domain_bare = result.domain.replace("www.", "")

        # HTTP → HTTPS redirect
        try:
            resp = self.session.get(
                f"http://{domain_bare}",
                allow_redirects=False,
                timeout=SEOConfig.CRAWL_TIMEOUT
            )
            if resp.status_code in (301, 302, 307, 308):
                location = resp.headers.get("Location", "")
                if "https://" in location:
                    result.https_redirect = True
                    logger.info("  🔄 HTTP → HTTPS redirect: Evet")
        except Exception:
            pass

        # www redirect
        try:
            resp = self.session.get(
                f"https://{domain_bare}",
                allow_redirects=True,
                timeout=SEOConfig.CRAWL_TIMEOUT
            )
            if "www." in resp.url:
                result.www_redirect = True
                logger.info("  🔄 www redirect: Evet")
        except Exception:
            pass

    def _fetch_robots(self, result: CrawlResult):
        """robots.txt kontrolü."""
        try:
            resp = self.session.get(
                f"{result.base_url}/robots.txt",
                timeout=SEOConfig.CRAWL_TIMEOUT
            )
            if resp.status_code == 200:
                result.robots_txt = resp.text[:5000]
                result.robots_accessible = True
                logger.info("  🤖 robots.txt: Erişilebilir")
            else:
                result.robots_accessible = False
                logger.info(f"  🤖 robots.txt: HTTP {resp.status_code}")
        except Exception as e:
            result.robots_accessible = False
            result.errors.append(f"robots.txt erişim hatası: {e}")

    def _fetch_sitemap(self, result: CrawlResult):
        """sitemap.xml kontrolü."""
        sitemap_paths = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]

        # robots.txt'ten sitemap URL'i çıkar
        if result.robots_txt:
            for line in result.robots_txt.split("\n"):
                if line.strip().lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    sitemap_paths.insert(0, sitemap_url)

        for path in sitemap_paths:
            try:
                url = path if path.startswith("http") else f"{result.base_url}{path}"
                resp = self.session.get(url, timeout=SEOConfig.CRAWL_TIMEOUT)
                if resp.status_code == 200 and ("<?xml" in resp.text[:100] or "<urlset" in resp.text[:200]):
                    result.sitemap_url = url
                    result.sitemap_accessible = True

                    # URL'leri çıkar (ilk 100)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    locs = soup.find_all("loc")
                    result.sitemap_urls = [loc.text.strip() for loc in locs[:100]]

                    logger.info(
                        f"  🗺️ sitemap.xml: {url} ({len(result.sitemap_urls)} URL)"
                    )
                    break
            except Exception:
                continue

        if not result.sitemap_accessible:
            logger.info("  🗺️ sitemap.xml: Bulunamadı")

    def _crawl_page(self, url: str, result: CrawlResult):
        """Tek bir sayfayı crawl eder ve PageData döner."""
        if url in self._visited:
            return
        if len(result.pages) >= SEOConfig.CRAWL_MAX_PAGES:
            return

        self._visited.add(url)
        page = PageData(url=url)

        try:
            start = time.time()
            resp = self.session.get(url, timeout=SEOConfig.CRAWL_TIMEOUT)
            page.load_time = time.time() - start
            page.status_code = resp.status_code
            page.content_type = resp.headers.get("Content-Type", "")

            if resp.status_code != 200:
                page.error = f"HTTP {resp.status_code}"
                result.pages.append(page)
                return

            if "text/html" not in page.content_type:
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            self._extract_meta(soup, page)
            self._extract_headings(soup, page)
            self._extract_links(soup, page, result)
            self._extract_images(soup, page)
            self._extract_schema(soup, page)
            self._extract_content(soup, page)

            result.pages.append(page)

            logger.debug(
                f"  📄 {url} — {page.status_code} | "
                f"{page.word_count} kelime | {page.load_time:.2f}s"
            )

        except Exception as e:
            page.error = str(e)
            page.status_code = 0
            result.pages.append(page)
            result.errors.append(f"Crawl hatası ({url}): {e}")

    def _extract_meta(self, soup: BeautifulSoup, page: PageData):
        """Meta bilgileri çıkar."""
        # Title
        title_tag = soup.find("title")
        if title_tag:
            page.title = title_tag.get_text(strip=True)

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if meta_desc:
            page.meta_description = meta_desc.get("content", "")

        # Meta keywords
        meta_kw = soup.find("meta", attrs={"name": re.compile(r"keywords", re.I)})
        if meta_kw:
            page.meta_keywords = meta_kw.get("content", "")

        # Canonical
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            page.canonical = canonical.get("href", "")

        # Robots meta
        robots = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        if robots:
            page.robots_meta = robots.get("content", "")

        # Viewport (mobil uyumluluk)
        viewport = soup.find("meta", attrs={"name": "viewport"})
        page.has_viewport = viewport is not None

        # Lang
        html_tag = soup.find("html")
        if html_tag:
            lang = html_tag.get("lang", "")
            page.has_lang = bool(lang)
            page.lang = lang

        # Charset
        meta_charset = soup.find("meta", attrs={"charset": True})
        if meta_charset:
            page.charset = meta_charset.get("charset", "")
        else:
            content_type_meta = soup.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
            if content_type_meta:
                content = content_type_meta.get("content", "")
                if "charset=" in content:
                    page.charset = content.split("charset=")[-1].strip()

        # OG tags
        for og_tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:", re.I)}):
            prop = og_tag.get("property", "")
            content = og_tag.get("content", "")
            if prop and content:
                page.og_tags[prop] = content

    def _extract_headings(self, soup: BeautifulSoup, page: PageData):
        """H1-H6 heading yapısını çıkar."""
        for level in range(1, 7):
            headings = soup.find_all(f"h{level}")
            texts = [h.get_text(strip=True) for h in headings if h.get_text(strip=True)]
            setattr(page, f"h{level}", texts)

    def _extract_links(self, soup: BeautifulSoup, page: PageData, result: CrawlResult):
        """İç ve dış linkleri çıkar."""
        base_domain = urlparse(result.base_url).netloc.replace("www.", "")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]

            # Fragment ve javascript skip
            if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                continue

            # Absolute URL'e çevir
            full_url = urljoin(page.url, href)
            parsed = urlparse(full_url)

            # Sadece HTTP(S) linkler
            if parsed.scheme not in ("http", "https"):
                continue

            link_domain = parsed.netloc.replace("www.", "")

            if link_domain == base_domain or link_domain == f"www.{base_domain}":
                # Parametresiz, fragmentsiz URL
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url.endswith("/"):
                    clean_url = clean_url.rstrip("/") or clean_url
                page.internal_links.append(clean_url)
            else:
                page.external_links.append(full_url)

        # Deduplicate
        page.internal_links = list(dict.fromkeys(page.internal_links))
        page.external_links = list(dict.fromkeys(page.external_links))

    def _extract_images(self, soup: BeautifulSoup, page: PageData):
        """Görsel bilgilerini çıkar."""
        for img in soup.find_all("img"):
            src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
            alt = img.get("alt", "")
            page.images.append({
                "src": src,
                "alt": alt,
                "has_alt": bool(alt.strip()),
            })

    def _extract_schema(self, soup: BeautifulSoup, page: PageData):
        """Schema.org yapısal veri türlerini çıkar."""
        import json

        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    schema_type = data.get("@type", "")
                    if schema_type:
                        if isinstance(schema_type, list):
                            page.schema_types.extend(schema_type)
                        else:
                            page.schema_types.append(schema_type)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            st = item.get("@type", "")
                            if st:
                                page.schema_types.append(st if isinstance(st, str) else str(st))
            except (json.JSONDecodeError, TypeError):
                pass

        # Microdata (itemtype)
        for elem in soup.find_all(attrs={"itemtype": True}):
            itype = elem["itemtype"]
            # https://schema.org/Product → Product
            if "schema.org/" in itype:
                schema_type = itype.split("/")[-1]
                page.schema_types.append(schema_type)

        page.schema_types = list(dict.fromkeys(page.schema_types))

    def _extract_content(self, soup: BeautifulSoup, page: PageData):
        """Sayfa metin içeriğini çıkar ve kelime sayısını hesaplar."""
        # Script ve style tag'larını kaldır
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # Fazla boşlukları temizle
        text = re.sub(r"\s+", " ", text).strip()

        page.text_content = text[:10000]  # İlk 10K karakter (LLM için)
        page.word_count = len(text.split())
