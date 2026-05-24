"""
SEO Analyzer — Article Intelligence
=====================================
Rakip sitenin en önemli makalelerini tespit eder ve
içlerindeki gizli (semantik/LSI) kelimeleri çıkarır.

Hiçbir ücretli API kullanmaz. Sinyaller:
  1. sitemap.xml → priority + lastmod
  2. İç link grafiği → hangi URL kaç kez referans alıyor
  3. İçerik yapısı → makale mi, ürün sayfası mı?
  4. OpenAI → semantik anahtar kelime çıkarımı
"""
import re
import time
import logging
import json
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── Veri Yapıları ────────────────────────────────────────────────────────────

@dataclass
class ArticleResult:
    """Tek bir makalenin analiz sonucu."""
    url: str
    title: str = ""
    h1: str = ""
    meta_description: str = ""
    word_count: int = 0
    text_content: str = ""          # İlk 8000 karakter (LLM için)
    headings: list[str] = field(default_factory=list)  # H2-H3 başlıklar
    internal_link_count: int = 0    # Kaç iç sayfa bu URL'e link veriyor
    sitemap_priority: float = 0.5   # sitemap.xml'deki priority değeri
    sitemap_lastmod: str = ""       # Son güncelleme tarihi
    is_article: bool = False        # Makale mi?
    importance_score: float = 0.0   # Hesaplanan önem skoru (0-100)

    # LLM çıktısı
    primary_keywords: list[str] = field(default_factory=list)
    secondary_keywords: list[str] = field(default_factory=list)
    lsi_keywords: list[str] = field(default_factory=list)
    search_intent: str = ""         # informational / transactional / navigational
    content_gaps: list[str] = field(default_factory=list)
    suggested_title: str = ""
    llm_summary: str = ""


@dataclass
class ArticleIntelligenceResult:
    """Tüm analiz sonucu — seo-article-panel'e gönderilecek format."""
    domain: str
    top_articles: list[ArticleResult] = field(default_factory=list)
    total_sitemap_urls: int = 0
    analysis_duration: float = 0.0
    error: str = ""


# ─── Ana Sınıf ────────────────────────────────────────────────────────────────

class ArticleIntelligence:
    """
    Rakip sitenin en önemli makalelerini bulur ve
    içlerindeki semantik kelimeleri çıkarır.
    """

    def __init__(self, openai_api_key: Optional[str] = None, top_n: int = 15):
        self.openai_api_key = openai_api_key
        self.top_n = top_n
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ── Genel Pipeline ────────────────────────────────────────────────────────

    def analyze(self, domain: str) -> ArticleIntelligenceResult:
        """
        Ana analiz fonksiyonu.
        domain: "lastikborsasi.com" veya "https://lastikborsasi.com"
        """
        start = time.time()

        if not domain.startswith("http"):
            domain = f"https://{domain}"
        base_url = domain.rstrip("/")

        result = ArticleIntelligenceResult(domain=base_url)

        try:
            logger.info(f"🔍 Article Intelligence başlıyor: {base_url}")

            # 1. Sitemap'ten URL listesi + priority/lastmod al
            sitemap_data = self._parse_sitemap(base_url)
            result.total_sitemap_urls = len(sitemap_data)
            logger.info(f"   📄 Sitemap'ten {len(sitemap_data)} URL alındı")

            if not sitemap_data:
                # Sitemap yoksa ana sayfadan crawl et
                sitemap_data = self._discover_urls_from_homepage(base_url)
                logger.info(f"   🕷️ Ana sayfadan {len(sitemap_data)} URL keşfedildi")

            # 2. İlk tarama — URL'leri crawl edip metadata çek
            candidates = self._crawl_candidates(base_url, sitemap_data)
            logger.info(f"   ✅ {len(candidates)} sayfa crawl edildi")

            # 3. İç link grafiği — hangi URL kaç referans alıyor
            self._build_link_graph(candidates)

            # 4. Makale tespiti + önem skoru hesapla
            articles = [c for c in candidates if self._is_article(c)]
            self._score_articles(articles)

            # 5. En önemli TOP N makaleyi seç
            top = sorted(articles, key=lambda x: x.importance_score, reverse=True)[:self.top_n]
            logger.info(f"   🏆 Top {len(top)} makale seçildi")

            # 6. LLM ile gizli kelime analizi (sadece top makaleler)
            if self.openai_api_key:
                for i, article in enumerate(top):
                    logger.info(f"   🤖 LLM analiz: {i+1}/{len(top)} — {article.url[:60]}...")
                    self._llm_keyword_extraction(article)
                    time.sleep(0.5)  # Rate limit
            else:
                logger.warning("   ⚠️ OpenAI API key yok — LLM analizi atlandı")
                for article in top:
                    article.primary_keywords = self._basic_keyword_extraction(article.text_content)

            result.top_articles = top

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Article Intelligence hatası: {e}", exc_info=True)

        result.analysis_duration = time.time() - start
        logger.info(f"🏁 Tamamlandı: {result.analysis_duration:.1f}s")
        return result

    # ── Sitemap Parsing ────────────────────────────────────────────────────────

    def _parse_sitemap(self, base_url: str) -> list[dict]:
        """
        sitemap.xml'i parse eder.
        Sitemap index'i varsa alt sitemaplara da girer.
        Döner: [{"url": ..., "priority": ..., "lastmod": ...}]
        """
        sitemap_urls = []

        # Olası sitemap konumları
        candidates = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap/",
            f"{base_url}/post-sitemap.xml",
            f"{base_url}/page-sitemap.xml",
        ]

        # robots.txt'ten sitemap URL'i ara
        try:
            robots = self.session.get(f"{base_url}/robots.txt", timeout=10)
            if robots.status_code == 200:
                for line in robots.text.split("\n"):
                    if line.strip().lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        if sm_url not in candidates:
                            candidates.insert(0, sm_url)
        except Exception:
            pass

        for sm_url in candidates:
            try:
                resp = self.session.get(sm_url, timeout=15)
                if resp.status_code != 200:
                    continue

                content = resp.text
                if "<urlset" in content:
                    # Normal sitemap
                    parsed = self._extract_sitemap_urls(content)
                    sitemap_urls.extend(parsed)
                    break
                elif "<sitemapindex" in content:
                    # Sitemap index — alt sitemapları da işle
                    soup = BeautifulSoup(content, "xml")
                    sub_sitemaps = [loc.text.strip() for loc in soup.find_all("loc")]
                    for sub_url in sub_sitemaps[:5]:  # İlk 5 alt sitemap yeterli
                        try:
                            sub_resp = self.session.get(sub_url, timeout=15)
                            if sub_resp.status_code == 200:
                                sitemap_urls.extend(self._extract_sitemap_urls(sub_resp.text))
                        except Exception:
                            continue
                    break
            except Exception:
                continue

        return sitemap_urls[:500]  # Max 500 URL

    def _extract_sitemap_urls(self, xml_content: str) -> list[dict]:
        """XML sitemap içeriğinden URL + meta bilgileri çıkarır."""
        results = []
        try:
            soup = BeautifulSoup(xml_content, "xml")
            for url_tag in soup.find_all("url"):
                loc = url_tag.find("loc")
                if not loc:
                    continue

                priority_tag = url_tag.find("priority")
                lastmod_tag = url_tag.find("lastmod")
                changefreq_tag = url_tag.find("changefreq")

                results.append({
                    "url": loc.text.strip(),
                    "priority": float(priority_tag.text.strip()) if priority_tag else 0.5,
                    "lastmod": lastmod_tag.text.strip() if lastmod_tag else "",
                    "changefreq": changefreq_tag.text.strip() if changefreq_tag else "",
                })
        except Exception:
            pass
        return results

    def _discover_urls_from_homepage(self, base_url: str) -> list[dict]:
        """Sitemap yoksa ana sayfadan link keşfi yapar."""
        discovered = []
        try:
            resp = self.session.get(base_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            base_domain = urlparse(base_url).netloc.replace("www.", "")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                link_domain = parsed.netloc.replace("www.", "")

                if link_domain == base_domain and parsed.scheme in ("http", "https"):
                    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
                    if clean != base_url and clean not in [d["url"] for d in discovered]:
                        discovered.append({"url": clean, "priority": 0.5, "lastmod": ""})
        except Exception:
            pass
        return discovered

    # ── Crawl ─────────────────────────────────────────────────────────────────

    def _crawl_candidates(self, base_url: str, sitemap_data: list[dict]) -> list[ArticleResult]:
        """
        Sitemap URL'lerini crawl eder.
        Önce priority'ye göre sıralar, en fazla 60 URL crawl eder.
        """
        # Priority'ye göre sırala (yüksek önce)
        sorted_data = sorted(sitemap_data, key=lambda x: x.get("priority", 0.5), reverse=True)

        # Makale olmayan URL'leri filtrele (login, cart, admin vb.)
        SKIP_PATTERNS = re.compile(
            r"/(login|logout|cart|sepet|uye|account|admin|wp-admin|"
            r"tag|etiket|yazar|author|feed|rss|xml|\.pdf|\.zip|"
            r"contact|iletisim|hakkimizda|about|privacy|gizlilik)(/|$)",
            re.I
        )
        filtered = [d for d in sorted_data if not SKIP_PATTERNS.search(d["url"])][:60]

        results = []
        base_domain = urlparse(base_url).netloc.replace("www.", "")

        for item in filtered:
            url = item["url"]
            # Sadece aynı domain
            if urlparse(url).netloc.replace("www.", "") != base_domain:
                continue

            try:
                time.sleep(0.3)
                resp = self.session.get(url, timeout=12, allow_redirects=True)
                if resp.status_code != 200:
                    continue
                if "text/html" not in resp.headers.get("Content-Type", ""):
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                article = self._extract_article_data(url, soup, item)
                results.append(article)

            except Exception as e:
                logger.debug(f"  Crawl hatası ({url}): {e}")
                continue

        return results

    def _extract_article_data(self, url: str, soup: BeautifulSoup, sitemap_item: dict) -> ArticleResult:
        """Sayfadan ArticleResult verisi çıkarır."""
        # Script/style/nav temizle
        for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
            tag.decompose()

        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)

        h1_tag = soup.find("h1")
        h1 = h1_tag.get_text(strip=True) if h1_tag else ""

        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        meta_description = meta_desc.get("content", "") if meta_desc else ""

        h2_h3 = [
            tag.get_text(strip=True)
            for tag in soup.find_all(["h2", "h3"])
            if tag.get_text(strip=True)
        ][:10]

        # İç linkler — link grafiği için
        base_domain = urlparse(url).netloc.replace("www.", "")
        internal_links = []
        for a in soup.find_all("a", href=True):
            full = urljoin(url, a["href"])
            parsed = urlparse(full)
            if parsed.netloc.replace("www.", "") == base_domain:
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
                internal_links.append(clean)

        # Metin içeriği
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        return ArticleResult(
            url=url,
            title=title,
            h1=h1,
            meta_description=meta_description,
            headings=h2_h3,
            word_count=len(text.split()),
            text_content=text[:8000],
            sitemap_priority=sitemap_item.get("priority", 0.5),
            sitemap_lastmod=sitemap_item.get("lastmod", ""),
            # internal_link_count sonradan link graph'tan doldurulacak
        )

    # ── İç Link Grafiği ───────────────────────────────────────────────────────

    def _build_link_graph(self, articles: list[ArticleResult]):
        """
        Crawl edilen sayfalar arasındaki iç link ilişkisini analiz eder.
        Her URL'e kaç sayfa link veriyor → internal_link_count.
        """
        url_set = {a.url.rstrip("/") for a in articles}
        link_counter: Counter = Counter()

        for article in articles:
            # Bu makalenin text_content'inden iç linkleri çıkar
            # (zaten crawl'da çıkardık ama ArticleResult'ta saklamıyoruz — burada yeniden çıkaralım)
            # Daha verimli: sitemap URL'leri sayfalarda kaç kez geçiyor
            for candidate_url in url_set:
                if candidate_url in (article.text_content or "") or candidate_url in article.url:
                    continue
                # Kaba bir yaklaşım: URL'nin path'i metin içinde geçiyor mu?
                path = urlparse(candidate_url).path.rstrip("/")
                if path and len(path) > 3 and path in article.text_content:
                    link_counter[candidate_url] += 1

        for article in articles:
            article.internal_link_count = link_counter.get(article.url.rstrip("/"), 0)

    # ── Makale Tespiti ────────────────────────────────────────────────────────

    def _is_article(self, article: ArticleResult) -> bool:
        """
        Sayfanın içerik makalesi olup olmadığını belirler.
        Basit heuristikler kullanır.
        """
        url = article.url.lower()
        text_len = article.word_count

        # Çok kısa sayfa — makale değil
        if text_len < 200:
            return False

        # URL'de makale/blog sinyali
        ARTICLE_PATTERNS = re.compile(
            r"/(blog|makale|yazi|haber|icerik|rehber|guide|article|post|"
            r"nasil|nedir|ne-dir|ne-kadar|ne-zaman|ipucu|tips|"
            r"\d{4}/\d{2})",
            re.I
        )
        if ARTICLE_PATTERNS.search(url):
            return True

        # H2/H3 başlıkları varsa muhtemelen makale
        if len(article.headings) >= 2 and text_len >= 300:
            return True

        # Yeterince uzun içerik
        if text_len >= 500:
            return True

        return False

    # ── Önem Skoru ────────────────────────────────────────────────────────────

    def _score_articles(self, articles: list[ArticleResult]):
        """
        Her makale için 0-100 arası önem skoru hesaplar.
        Sinyaller: priority, word_count, internal_link_count, lastmod
        """
        max_links = max((a.internal_link_count for a in articles), default=1) or 1
        max_words = max((a.word_count for a in articles), default=1) or 1

        for a in articles:
            score = 0.0

            # Sitemap priority (0-1 → 0-30 puan)
            score += a.sitemap_priority * 30

            # İç link sayısı (0-40 puan)
            score += (a.internal_link_count / max_links) * 40

            # Kelime sayısı (0-20 puan) — zengin içerik daha değerli
            word_score = min(a.word_count / 1500, 1.0)
            score += word_score * 20

            # Son güncelleme tarihi (0-10 puan) — yeni içerik daha değerli
            if a.sitemap_lastmod:
                try:
                    from datetime import datetime
                    lastmod = datetime.fromisoformat(a.sitemap_lastmod[:10])
                    days_old = (datetime.now() - lastmod).days
                    recency_score = max(0, 1 - days_old / 365)
                    score += recency_score * 10
                except Exception:
                    pass

            a.importance_score = round(score, 2)

    # ── LLM Keyword Extraction ────────────────────────────────────────────────

    def _llm_keyword_extraction(self, article: ArticleResult):
        """
        OpenAI ile semantik anahtar kelime analizi yapar.
        """
        if not article.text_content:
            return

        prompt = f"""Sen uzman bir SEO analistisin. Aşağıdaki makaleyi analiz et.

MAKALE URL: {article.url}
BAŞLIK: {article.title}
ALT BAŞLIKLAR: {", ".join(article.headings[:8])}

İÇERİK (ilk 4000 karakter):
{article.text_content[:4000]}

Lütfen aşağıdaki JSON formatında analiz döndür:
{{
  "primary_keywords": ["Ana anahtar kelime 1", "Ana anahtar kelime 2", "Ana anahtar kelime 3"],
  "secondary_keywords": ["İkincil kelime 1", "İkincil kelime 2", ..., "İkincil kelime 5"],
  "lsi_keywords": ["LSI/semantik kelime 1", ..., "LSI/semantik kelime 8"],
  "search_intent": "informational|transactional|navigational|commercial",
  "content_gaps": ["Bu makalede eksik olan konu 1", "eksik konu 2", "eksik konu 3"],
  "suggested_title": "Bu makaleyi daha iyi optimize edecek alternatif başlık",
  "llm_summary": "Makalenin 2 cümlelik özeti ve SEO açısından güçlü/zayıf yönleri"
}}

Sadece JSON döndür, başka açıklama ekleme."""

        try:
            import openai
            client = openai.OpenAI(api_key=self.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            raw = response.choices[0].message.content.strip()
            # JSON bloğunu temizle
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)
            article.primary_keywords = data.get("primary_keywords", [])
            article.secondary_keywords = data.get("secondary_keywords", [])
            article.lsi_keywords = data.get("lsi_keywords", [])
            article.search_intent = data.get("search_intent", "")
            article.content_gaps = data.get("content_gaps", [])
            article.suggested_title = data.get("suggested_title", "")
            article.llm_summary = data.get("llm_summary", "")

        except Exception as e:
            logger.warning(f"  LLM hatası ({article.url}): {e}")
            article.primary_keywords = self._basic_keyword_extraction(article.text_content)

    def _basic_keyword_extraction(self, text: str, top_n: int = 10) -> list[str]:
        """
        LLM yoksa basit TF-IDF benzeri kelime çıkarımı.
        """
        # Türkçe stop words (minimal)
        stop_words = {
            "ve", "bir", "bu", "için", "ile", "de", "da", "den", "dan",
            "mi", "mı", "mu", "mü", "ne", "ki", "en", "çok", "daha",
            "olan", "var", "gibi", "ise", "the", "a", "an", "is", "are",
            "in", "on", "at", "to", "of", "or", "and", "but", "not",
        }
        words = re.findall(r"\b[a-zA-ZğüşıöçĞÜŞİÖÇ]{4,}\b", text.lower())
        filtered = [w for w in words if w not in stop_words]
        counter = Counter(filtered)
        return [word for word, _ in counter.most_common(top_n)]

    # ── JSON Export ───────────────────────────────────────────────────────────

    def to_json(self, result: ArticleIntelligenceResult) -> dict:
        """
        Sonucu seo-article-panel'in anlayacağı JSON formatına çevirir.
        """
        return {
            "domain": result.domain,
            "total_sitemap_urls": result.total_sitemap_urls,
            "analysis_duration_sec": round(result.analysis_duration, 1),
            "error": result.error,
            "top_articles": [
                {
                    "rank": i + 1,
                    "url": a.url,
                    "title": a.title,
                    "importance_score": a.importance_score,
                    "word_count": a.word_count,
                    "search_intent": a.search_intent,
                    "primary_keywords": a.primary_keywords,
                    "secondary_keywords": a.secondary_keywords,
                    "lsi_keywords": a.lsi_keywords,
                    "content_gaps": a.content_gaps,
                    "suggested_title": a.suggested_title,
                    "summary": a.llm_summary,
                    "sitemap_priority": a.sitemap_priority,
                    "last_updated": a.sitemap_lastmod,
                }
                for i, a in enumerate(result.top_articles)
            ],
        }
