"""
Content Quality Scorer
=======================
Lastikcim ters mühendislik analizinden türetilen formül.
Her makaleye 0-100 arası kalite skoru hesaplar ve
"neden #1" / "neden sıralamada yok" açıklaması üretir.

FORMÜL:
  SKOR =
    + soru_baslik_sayisi   × 1.5   (H2/H3'de "?" işareti)
    + numerik_veri         × 2.0   ("8-10 yıl", "2.4 bar" gibi spesifik sayılar)
    + otorite_link         × 3.0   (.gov.tr, .edu.tr, üretici siteleri, sektör dernekleri)
    + tazelik_skoru        × 1.8   (son güncelleme < 90 gün = tam puan)
    + ic_link_sayisi       × 1.2   (max 10 ile sınırlanır)
    - belirsizlik_kelime   × 2.5   ("olabilir", "muhtemelen", "sanırım", "tahminen")
    - subjektif_sifat      × 1.5   ("harika", "muhteşem", "süper", "mükemmel")
    - satis_dili           × 3.0   ("hemen al", "sipariş ver", "stok tükeniyor")

  Sonuç 0-100 arasına normalize edilir.
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Kelime Listeleri ───────────────────────────────────────────────────────────

UNCERTAINTY_WORDS = [
    "olabilir", "muhtemelen", "sanırım", "tahminen", "belki", "galiba",
    "gibi görünüyor", "olası", "ihtimal", "sanki", "zannediyorum",
    "probably", "maybe", "perhaps", "might", "could be", "seems like",
]

SUBJECTIVE_ADJECTIVES = [
    "harika", "muhteşem", "süper", "mükemmel", "olağanüstü", "inanılmaz",
    "enfes", "efsane", "fevkalade", "benzersiz", "eşsiz",
    "amazing", "awesome", "incredible", "fantastic", "wonderful",
]

SALES_LANGUAGE = [
    "hemen al", "hemen satın al", "sipariş ver", "stok tükeniyor",
    "sınırlı stok", "kaçırma", "fırsatı kaçırma", "son şans",
    "indirim sadece bugün", "özel fiyat", "kampanya bitiyor",
    "buy now", "order now", "limited stock", "don't miss",
]

AUTHORITY_DOMAINS = [
    ".gov.tr", ".edu.tr", ".org.tr",
    "tse.org.tr", "atonet.org.tr", "gtb.gov.tr",
    "michelin.com", "continental.com", "bridgestone.com", "goodyear.com",
    "pirelli.com", "nokian.com", "dunlop.com", "hankook.com",
    "jatma.or.jp", "etrma.org", "ustma.org",
    "resmigazete.gov.tr", "saglik.gov.tr", "tuik.gov.tr",
    "wikipedia.org",  # Wikipedia kabul edilebilir ama üçüncü sıra
]

# Regex: spesifik sayısal veri ("8-10 yıl", "2.4 bar", "205/55R16", "70%" gibi)
NUMERIC_PATTERN = re.compile(
    r'\b\d+(?:[.,]\d+)?'           # Sayı
    r'(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?'  # Opsiyonel aralık (8-10)
    r'\s*(?:yıl|ay|km|bar|°c|°|%|mm|kg|lt|litre|adet|saat|dakika|'
    r'year|km/h|mph|psi|inch|cm|metre|m²|year|month)\b',
    re.IGNORECASE
)


# ── Veri Yapıları ──────────────────────────────────────────────────────────────

@dataclass
class QualitySignal:
    """Tek bir kalite sinyali."""
    name: str
    value: float       # Ham değer (sayı)
    weight: float      # Ağırlık katsayısı
    contribution: float  # value × weight (pozitif veya negatif)
    direction: str     # "positive" | "negative"
    examples: list[str] = field(default_factory=list)  # Örnekler


@dataclass
class ContentQualityResult:
    """Bir makale için kalite analiz sonucu."""
    url: str
    raw_score: float = 0.0         # Ham skor (normalize edilmemiş)
    quality_score: float = 0.0     # 0-100 normalize skor
    grade: str = ""                # A / B / C / D / F
    signals: list[QualitySignal] = field(default_factory=list)

    # Açıklama metinleri
    why_ranking: str = ""          # "Neden iyi sıralıyor?" (skor > 65)
    why_not_ranking: str = ""      # "Neden sıralamada yok?" (skor < 50)
    recommendations: list[str] = field(default_factory=list)  # Adım adım öneriler

    # Sinyal sayıları (kolayca erişim için)
    question_headers: int = 0
    numeric_data_count: int = 0
    authority_links: int = 0
    internal_link_count: int = 0
    uncertainty_count: int = 0
    subjective_count: int = 0
    sales_language_count: int = 0
    last_updated: str = ""
    freshness_days: int = -1


# ── Ana Sınıf ─────────────────────────────────────────────────────────────────

class ContentQualityScorer:
    """
    HTML içeriğini analiz ederek kalite skoru hesaplar.
    Lastikcim ters mühendislik formülünü uygular.
    """

    MAX_THEORETICAL_SCORE = (
        5 * 1.5   +  # 5 soru başlık
        15 * 2.0  +  # 15 numerik veri
        4 * 3.0   +  # 4 otorite link
        1.8       +  # tam tazelik
        10 * 1.2     # 10 iç link (max)
    )  # ≈ 56.3 → normalize için kullanılır

    def score(self, text_content: str, headings: list[str],
              internal_links: list[str], external_links: list[str],
              lastmod: str = "", word_count: int = 0,
              url: str = "") -> ContentQualityResult:
        """
        Makale verilerini alıp ContentQualityResult döner.

        Parametreler:
            text_content: Sayfanın ham metin içeriği
            headings:     H2 ve H3 başlıkları listesi
            internal_links: İç link URL'leri
            external_links: Dış link URL'leri
            lastmod:      sitemap.xml'den gelen son güncelleme tarihi
            word_count:   Kelime sayısı
            url:          Sayfa URL'i
        """
        result = ContentQualityResult(url=url)
        signals = []
        raw = 0.0

        # ── 1. Soru Başlıkları ─────────────────────────────────────────────
        question_hs = [h for h in headings if "?" in h]
        q_count = len(question_hs)
        result.question_headers = q_count
        contribution = q_count * 1.5
        raw += contribution
        signals.append(QualitySignal(
            name="Soru Formatı Başlıklar",
            value=q_count,
            weight=1.5,
            contribution=contribution,
            direction="positive",
            examples=question_hs[:3],
        ))

        # ── 2. Numerik Veri ────────────────────────────────────────────────
        numeric_matches = NUMERIC_PATTERN.findall(text_content)
        # Tekrarlananları say ama örnekler için unique al
        unique_numerics = list(dict.fromkeys(numeric_matches))
        n_count = min(len(unique_numerics), 20)  # Max 20
        result.numeric_data_count = n_count
        contribution = n_count * 2.0
        raw += contribution
        signals.append(QualitySignal(
            name="Numerik / Spesifik Veri",
            value=n_count,
            weight=2.0,
            contribution=contribution,
            direction="positive",
            examples=unique_numerics[:5],
        ))

        # ── 3. Otorite Dış Linkler ─────────────────────────────────────────
        authority_count = 0
        authority_examples = []
        for link in external_links:
            for domain in AUTHORITY_DOMAINS:
                if domain in link.lower():
                    authority_count += 1
                    authority_examples.append(link)
                    break
        result.authority_links = authority_count
        contribution = min(authority_count, 5) * 3.0  # Max 5
        raw += contribution
        signals.append(QualitySignal(
            name="Otorite Kaynak Linkleri",
            value=authority_count,
            weight=3.0,
            contribution=contribution,
            direction="positive",
            examples=[urlparse(u).netloc for u in authority_examples[:3]],
        ))

        # ── 4. İçerik Tazeliği ─────────────────────────────────────────────
        freshness_score = 0.0
        freshness_days = -1
        result.last_updated = lastmod
        if lastmod:
            try:
                lastmod_date = datetime.fromisoformat(lastmod[:10])
                freshness_days = (datetime.now() - lastmod_date).days
                result.freshness_days = freshness_days
                if freshness_days <= 30:
                    freshness_score = 1.8
                elif freshness_days <= 90:
                    freshness_score = 1.4
                elif freshness_days <= 180:
                    freshness_score = 1.0
                elif freshness_days <= 365:
                    freshness_score = 0.5
                else:
                    freshness_score = 0.1
            except Exception:
                pass

        raw += freshness_score
        signals.append(QualitySignal(
            name="İçerik Tazeliği",
            value=freshness_days if freshness_days >= 0 else 999,
            weight=1.8,
            contribution=freshness_score,
            direction="positive",
            examples=[f"{freshness_days} gün önce güncellendi" if freshness_days >= 0 else "Tarih bilinmiyor"],
        ))

        # ── 5. İç Link Sayısı ──────────────────────────────────────────────
        ic_count = min(len(internal_links), 10)  # Max 10
        result.internal_link_count = len(internal_links)
        contribution = ic_count * 1.2
        raw += contribution
        signals.append(QualitySignal(
            name="İç Link Sayısı",
            value=len(internal_links),
            weight=1.2,
            contribution=contribution,
            direction="positive",
            examples=[],
        ))

        # ── 6. Belirsizlik Kelimeleri (EKSI) ───────────────────────────────
        text_lower = text_content.lower()
        uncertainty_found = []
        for w in UNCERTAINTY_WORDS:
            count = text_lower.count(w)
            if count > 0:
                uncertainty_found.extend([w] * count)

        u_count = len(uncertainty_found)
        result.uncertainty_count = u_count
        deduction = min(u_count, 8) * 2.5  # Max 8
        raw -= deduction
        signals.append(QualitySignal(
            name="Belirsizlik Kelimeleri",
            value=u_count,
            weight=2.5,
            contribution=-deduction,
            direction="negative",
            examples=list(dict.fromkeys(uncertainty_found))[:5],
        ))

        # ── 7. Subjektif Sıfatlar (EKSI) ──────────────────────────────────
        subjective_found = []
        for w in SUBJECTIVE_ADJECTIVES:
            count = text_lower.count(w)
            if count > 0:
                subjective_found.extend([w] * count)

        s_count = len(subjective_found)
        result.subjective_count = s_count
        deduction = min(s_count, 5) * 1.5
        raw -= deduction
        signals.append(QualitySignal(
            name="Subjektif Sıfatlar",
            value=s_count,
            weight=1.5,
            contribution=-deduction,
            direction="negative",
            examples=list(dict.fromkeys(subjective_found))[:5],
        ))

        # ── 8. Satış Dili (EKSI) ──────────────────────────────────────────
        sales_found = []
        for phrase in SALES_LANGUAGE:
            if phrase in text_lower:
                sales_found.append(phrase)

        sl_count = len(sales_found)
        result.sales_language_count = sl_count
        deduction = min(sl_count, 4) * 3.0
        raw -= deduction
        signals.append(QualitySignal(
            name="Satış Dili",
            value=sl_count,
            weight=3.0,
            contribution=-deduction,
            direction="negative",
            examples=sales_found[:3],
        ))

        # ── Normalize & Grade ──────────────────────────────────────────────
        result.raw_score = raw
        result.signals = signals

        # 0-100 arası normalize (teorik max ~56.3 → 100'e scale)
        normalized = (raw / self.MAX_THEORETICAL_SCORE) * 100
        result.quality_score = round(max(0.0, min(100.0, normalized)), 1)

        if result.quality_score >= 75:
            result.grade = "A"
        elif result.quality_score >= 60:
            result.grade = "B"
        elif result.quality_score >= 45:
            result.grade = "C"
        elif result.quality_score >= 30:
            result.grade = "D"
        else:
            result.grade = "F"

        # ── Açıklama & Öneriler ────────────────────────────────────────────
        result.why_ranking, result.why_not_ranking = self._explain(result)
        result.recommendations = self._recommendations(result)

        return result

    def _explain(self, r: ContentQualityResult) -> tuple[str, str]:
        """Neden sıralıyor / Neden sıralamada yok açıklaması üretir."""
        strong_points = []
        weak_points = []

        if r.question_headers >= 3:
            strong_points.append(f"soru formatı H2/H3 başlıkları ({r.question_headers} adet)")
        elif r.question_headers == 0:
            weak_points.append("hiç soru formatı başlık yok")

        if r.numeric_data_count >= 5:
            strong_points.append(f"spesifik numerik veri ({r.numeric_data_count} adet)")
        elif r.numeric_data_count < 3:
            weak_points.append(f"yetersiz spesifik veri ({r.numeric_data_count} adet — en az 5 olmalı)")

        if r.authority_links >= 2:
            strong_points.append(f"otorite kaynak linkleri ({r.authority_links} adet)")
        elif r.authority_links == 0:
            weak_points.append("otorite kaynak linki yok (.gov, .edu, üretici siteleri)")

        if r.freshness_days >= 0 and r.freshness_days <= 90:
            strong_points.append(f"güncel içerik ({r.freshness_days} gün önce güncellendi)")
        elif r.freshness_days > 180:
            weak_points.append(f"eski içerik ({r.freshness_days} gün güncellenmemiş)")

        if r.uncertainty_count > 3:
            weak_points.append(f"çok fazla belirsizlik kelimesi ({r.uncertainty_count} adet: olabilir, muhtemelen...)")

        if r.sales_language_count > 0:
            weak_points.append(f"satış dili içeriyor ({r.sales_language_count} cümle)")

        if strong_points and r.quality_score >= 55:
            why_ranking = "Bu içerik şu güçlü sinyaller nedeniyle iyi sıralıyor: " + ", ".join(strong_points) + "."
        else:
            why_ranking = ""

        if weak_points and r.quality_score < 65:
            why_not_ranking = "Bu içerik şu zayıflıklar nedeniyle sıralamada görünmüyor: " + ", ".join(weak_points) + "."
        else:
            why_not_ranking = ""

        return why_ranking, why_not_ranking

    def _recommendations(self, r: ContentQualityResult) -> list[str]:
        """Somut iyileştirme önerileri üretir."""
        recs = []

        if r.question_headers < 3:
            recs.append(
                f"H2/H3 başlıklarını soru formatına çevir. "
                f"Mevcut: {r.question_headers} soru başlık. "
                f"Hedef: en az 4. Örn: 'Nasıl yapılır?' → 'X nasıl yapılır?' "
                f"Kullanıcının arama sorgusunu başlık olarak kullan."
            )

        if r.numeric_data_count < 5:
            recs.append(
                f"Spesifik sayılar ekle. Mevcut: {r.numeric_data_count} numerik veri. "
                f"'Uzun süre dayanır' → '4-6 yıl veya 40.000-60.000 km dayanır'. "
                f"'Yeterli basınç' → '2.2-2.4 bar olmalıdır'."
            )

        if r.authority_links == 0:
            recs.append(
                "En az 1 otorite kaynak linki ekle. "
                "Tercih sırası: TSE, Ticaret Bakanlığı, Ankara Ticaret Odası (atonet.org.tr), "
                "üretici resmi siteleri (michelin.com, continental.com), "
                "JATMA/ETRMA gibi sektör dernekleri."
            )
        elif r.authority_links == 1:
            recs.append("Otorite kaynak sayısını 2-3'e çıkar. Tekil link yetmez.")

        if r.freshness_days > 180 or r.freshness_days < 0:
            recs.append(
                "İçeriği güncelle ve 'Son güncelleme: [Ay Yıl]' notunu en üste ekle. "
                "Google güncel içerikleri tercih eder. Yılda en az 2 kez güncelleme yap."
            )

        if r.uncertainty_count > 0:
            recs.append(
                f"Belirsizlik kelimelerini sil/değiştir ({r.uncertainty_count} adet). "
                f"'Olabilir' → 'Genellikle şu sebeple olur:' | "
                f"'Muhtemelen' → 'Verilere göre:' | "
                f"'Tahminen' → 'Yaklaşık [spesifik sayı]' | "
                f"'Sanırım' → SİL."
            )

        if r.sales_language_count > 0:
            recs.append(
                f"Satış dilini içerikten kaldır ({r.sales_language_count} cümle). "
                f"'Hemen satın al', 'Stok tükeniyor' gibi ifadeler Google'ı bilgi niyetli "
                f"aramalarda bu içeriği göstermekten alıkoyar. "
                f"Bilgi içeriği = bilgi dili."
            )

        if r.internal_link_count < 5:
            recs.append(
                f"İç link sayısını artır. Mevcut: {r.internal_link_count}. "
                f"Hedef: 8-15 arası. İlgili ürün kategorileri, marka sayfaları "
                f"ve popüler ebat sayfalarına link ver."
            )

        return recs
