"""
SEO Analyzer — OpenAI LLM Entegrasyonu
=======================================
OpenAI API ile derinlemesine SEO analiz metni üretimi.
Her rapor bölümü için özel prompt'lar.
"""
import json
import logging
from typing import Optional

from seo_config import SEOConfig

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logger.warning("openai paketi yüklü değil — pip install openai")


class LLMSEOAnalyzer:
    """OpenAI LLM ile SEO derinlemesine analiz."""

    def __init__(self):
        self.client = None
        if OpenAI and SEOConfig.OPENAI_API_KEY:
            self.client = OpenAI(api_key=SEOConfig.OPENAI_API_KEY)
            logger.info(f"🤖 LLM hazır: {SEOConfig.OPENAI_MODEL}")
        else:
            logger.warning("⚠️ LLM kullanılamıyor — OPENAI_API_KEY eksik veya openai paketi yok")

    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
        """OpenAI API'ye istek gönderir."""
        if not self.client:
            return "[LLM analizi devre dışı — OPENAI_API_KEY gerekli]"

        try:
            response = self.client.chat.completions.create(
                model=SEOConfig.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM hatası: {e}")
            return f"[LLM analizi başarısız: {e}]"

    def generate_executive_summary(self, site_data: dict) -> str:
        """Yönetici özeti üretir."""
        system = (
            "Sen uzman bir SEO danışmanısın. Raporunun ilk sayfası olan yönetici özetini çok detaylı yazıyorsun. "
            "Her maddeyi uzun uzun açıklamalısın. Format tamamen Markdown."
        )

        user = f"""Aşağıdaki SEO analiz verilerine dayanarak en az 500 kelimelik bir YÖNETİCİ ÖZETİ yaz.
Aşağıdaki formata birebir uy:

# 0. YÖNETİCİ ÖZETİ
[Sitenin alan adını, sektördeki konumunu ve SEO mimari olgunluğunu anlatan en az 3 paragraflık profesyonel bir açılış.]

**Güçlü Yönler (En az 5 boyut):**
- [Her bir boyutu başlıklandırıp, altını 2-3 cümleyle doldurarak açıkla. Örneğin: Programatik landing mimarisi, Schema zenginliği vb.]

**Sayısal Özet Tablosu:**
[Teknik Skor, Toplam indekslenebilir sayfa, Tahmini Ölçek, vb. içeren bir Markdown tablosu oluştur.]

**Kritik Açıklar ve Risk Noktaları:**
[En az 2 paragraflık detaylı risk analizi.]

VERİLER:
{json.dumps(site_data, ensure_ascii=False, indent=2)[:6000]}
"""
        return self._call_llm(system, user, max_tokens=2500)

    def generate_technical_infrastructure(self, technical_data: dict) -> str:
        """Teknik SEO Altyapı analizi."""
        system = "Sen uzman bir teknik SEO danışmanısın. Verileri olabildiğince uzatarak ve her teknik terimi açıklayarak yaz."
        user = f"""Aşağıdaki teknik SEO verilerini analiz et. Raporun bu bölümü çok uzun (en az 800 kelime) ve detaylı olmalı.

# 1. TEKNİK SEO — ALTYAPI KATMANI

## 1.1 Domain ve Teknoloji Yığını (Gözlem)
[Domain, Subdomain, Bot Koruması, WAF ve sunucu yanıt süreçlerini çok detaylı, paragraf paragraf açıkla.]

## 1.2 URL Yapısı ve Değerlendirme
**Güçlü Yanlar:** [En az 3 madde, her madde 2-3 cümle]
**Zayıf Yanlar:** [En az 3 madde, her madde 2-3 cümle]
[URL parametreleri, slug mimarisi ve kategori ID'leri üzerine derin analiz.]

## 1.3 HTTPS, Redirect Zincirleri ve Canonical
[Sitenin redirect politikası ve canonical etiketlerinin doğruluğu üzerine 2-3 paragraf.]

## 1.4 Robots.txt ve Sitemap.xml Stratejisi
[Crawl bütçesi (crawl budget) optimizasyonu, sitemap indexleme stratejileri üzerine analiz.]

## 1.5 Mobil Uyumluluk ve Core Web Vitals (Hız)
[Mobil kullanım, LCP, CLS ve FID tahminleri üzerine performans yorumlaması.]

## 1.6 Schema Markup (Yapısal Veri) Ekosistemi
[Mevcut schemaları detaylı bir tabloda ver. Product, Review, BreadcrumbList, Organization gibi yapıların SERP'e etkisini 3-4 paragrafla tartış.]

VERİLER:
{json.dumps(technical_data, ensure_ascii=False, indent=2)[:6000]}
"""
        return self._call_llm(system, user, max_tokens=3500)

    def generate_site_architecture(self, technical_data: dict) -> str:
        """Site ve bilgi mimarisi analizi."""
        system = "Bilgi Mimarisi (Information Architecture) uzmanısın. E-ticaret kategori ağacını detaylı incelersin."
        user = f"""Aşağıdaki verileri incele. En az 600 kelimelik bir analiz çıkar.

# 2. SİTE MİMARİSİ — BİLGİ MİMARİSİ

## 2.1 Hiyerarşi Haritası
[Sitenin kategori, marka, ürün, blog ayrımını gösteren Markdown ağaç (tree) diyagramı çiz.]

## 2.2 Hiyerarşi Kalitesi ve Tıklama Derinliği (Click Depth)
[3 tıklama kuralı, yatay genişleme, dikey derinlik üzerine 3 paragraflık analiz.]

## 2.3 Subdomain vs. Subdirectory Kararı
[Sitenin (varsa) blog subdomain tercihini SEO otorite aktarımı (link equity) açısından uzun uzun değerlendir.]

VERİLER:
{json.dumps(technical_data, ensure_ascii=False, indent=2)[:6000]}
"""
        return self._call_llm(system, user, max_tokens=3000)

    def generate_onpage_seo(self, content_data: dict) -> str:
        """On-Page SEO detayları."""
        system = "Sen On-Page SEO ve içerik uzmanısın. Her sayfayı incelemişcesine detaylı yaz."
        user = f"""Aşağıdaki verileri analiz et ve detaylı, uzun (en az 800 kelime) bir metin yaz.

# 3. ON-PAGE SEO — ÜRÜN VE KATEGORİ SAYFALARI

## 3.1 Title ve Meta Description Şablonları
[Title uzunlukları, USP (benzersiz satış teklifleri) kullanımı, truncate (kesilme) riskleri üzerine derin değerlendirme.]

## 3.2 H1 / H2 / H3 Hiyerarşisi
[Ürün ve kategori sayfalarındaki başlık hiyerarşisinin semantik temizliği üzerine analiz.]

## 3.3 Ürün Açıklamaları ve Duplicate Content (Kopya İçerik) Riski
[Kritik bir gözlem yap: A kalite ürünlerin özgün uzun metinleri ile, düşük kuyruklu (long-tail) ürünlerin şablon (template) metinlerini karşılaştıran 3-4 paragraf yaz.]

## 3.4 Görsel Optimizasyon ve Alt Metinler (Alt Text)
[Görsel SEO'sunu detaylı açıkla.]

## 3.5 İç Linkleme (Internal Linking) ve Hub-Spoke Yapısı
[Sayfalar arası otorite akışını sağlayan linkleme stratejisi üzerine 3 paragraflık bir analiz.]

VERİLER:
{json.dumps(content_data, ensure_ascii=False, indent=2)[:6000]}
"""
        return self._call_llm(system, user, max_tokens=3500)

    def generate_content_strategy(self, content_data: dict) -> str:
        """İçerik stratejisi ve E-E-A-T."""
        system = "Sen AEO (Answer Engine Optimization) ve E-E-A-T uzmanısın. İçerik yapılarını çok detaylı yaz."
        user = f"""Aşağıdaki verileri analiz et ve en az 800 kelimelik bir rapor yaz.

# 4. İÇERİK STRATEJİSİ VE E-E-A-T DEĞERLENDİRMESİ

## 4.1 Blog Yapısı Genel Görünümü
[Büyük, çok detaylı bir Markdown tablosunda: CMS, Kategori sayısı, Yazı sayısı, Yayın sıklığı, Yazar profili varlığı vb. verileri göster.]

## 4.2 İçerik Tipolojisi (En az 4 farklı format analizi)
[Her bir formatı (Örn: Tanımlayıcı, Karşılaştırma, Rehber, Haber) başlıklar halinde 2'şer paragraf ile incele.]

## 4.3 Yapay Zeka (AI) İçerik Kokusu ve İnce İçerik (Thin Content)
[Bu çok önemli bir konudur. Google'ın Helpful Content güncellemeleri ışığında sitenin mevcut metin kalitesini, AI jenerasyonu ihtimalini detaylıca tartış.]

## 4.4 E-E-A-T Sinyalleri Paneli (Experience, Expertise, Authoritativeness, Trustworthiness)
[Aşağıdakilerin her birinin sitedeki varlığını değerlendiren geniş bir tablo ve alt paragraf analizi:
- Şirket Bilgisi / Hakkımızda
- İletişim / Adres / Vergi No
- KVKK ve İade Politikaları
- Editöryel İlke Beyanı
- Müşteri Yorumları (UGC)
- Gerçek Yazar Profilleri]

VERİLER:
{json.dumps(content_data, ensure_ascii=False, indent=2)[:6000]}
"""
        return self._call_llm(system, user, max_tokens=3500)

    def generate_performance_and_ux(self, technical_data: dict) -> str:
        """Performans ve UX detayları."""
        system = "Sen Performans (Core Web Vitals) ve UX uzmanısın. Çok detaylı teknik analiz yapıyorsun."
        user = f"""Aşağıdaki verileri incele ve en az 600 kelimelik bir analiz yaz.

# 5. PERFORMANS, UX VE KULLANICI DENEYİMİ

## 5.1 Core Web Vitals ve Sayfa Hızı Öngörüleri
[LCP, FID ve CLS metrikleri üzerinden e-ticaret sitelerinin yaşayabileceği problemleri tartış. Sitenin hızının SEO'ya etkisini açıkla.]

## 5.2 Bot Koruması ve Tarama Bütçesi
[Sitedeki agresif WAF (Web Application Firewall) veya Cloudflare korumasının Googlebot'a etkisini 3 paragrafla analiz et.]

VERİLER:
{json.dumps(technical_data, ensure_ascii=False, indent=2)[:4000]}
"""
        return self._call_llm(system, user, max_tokens=2500)

    # --- YOL HARİTASI (ROADMAP) ---
    def generate_roadmap_methodology(self, issues_data: dict) -> str:
        """Yol Haritası için Yönetici Özeti ve Metodoloji."""
        system = "Sen SEO Stratejisti ve Proje Yöneticisisin. Metodoloji ve yönetici özeti yazıyorsun."
        user = f"""Aşağıdaki SEO sorunlarına bakarak, 12 Aylık Yol Haritası için detaylı (en az 600 kelime) bir yönetici özeti ve metodoloji kısmı yaz.
# 0. YÖNETİCİ ÖZETİ
[Sitenin mevcut durumunu, neden aksiyon alınması gerektiğini çok detaylı anlatan 3 paragraflık özet.]

# 1. METODOLOJİ — AKSİYONLAR NASIL SIRALANDI?
[ICE (Impact, Confidence, Ease) skorlamasının mantığını, yatırım getirisini (ROI) nasıl etkileyeceğini detaylı bir şekilde açıkla. P0, P1, P2 önceliklendirmesinin anlamını belirt.]

SORUNLAR:
{json.dumps(issues_data, ensure_ascii=False, indent=2)[:3000]}
"""
        return self._call_llm(system, user, max_tokens=2500)

    def generate_roadmap_actions(self, actions_data: list) -> str:
        """Yol Haritası için detaylı aksiyon listesi."""
        system = "Sen SEO Stratejistisin. Her bir aksiyonu bütçe, süre, ROI analizleriyle inanılmaz detaylı açıklıyorsun."
        user = f"""Aşağıdaki ICE skorlu aksiyonları kullanarak ÇOK DETAYLI (en az 1000 kelime) bir eylem planı oluştur. Her aksiyon için uzun uzun gerekçelendirme yap.

# 2. AKSİYONLAR — ICE SKORUNA GÖRE SIRALI

[Her bir aksiyon için tam olarak bu yapıyı kullan ve ÇOK DETAYLANDIR:]
### Aksiyon [No]: [Aksiyon Başlığı] (ICE: [Skor])
**I:[Etki] — C:[Güven] — E:[Kolaylık]**
- **Sorun:** [Mevcut problem nedir, ne kaybediyoruz? Paragrafça açıkla]
- **Aksiyon:** [Teknik olarak tam olarak ne yapılacak? Geliştirici ne kodlayacak?]
- **Maliyet:** [Tahmini adam-gün, development maliyeti TL cinsinden]
- **Beklenen Fayda:** [Ciroya etkisi, ROI beklentisi]
- **Süre:** [Canlıya alma süresi ve Google'ın indeksleme süresi]

# 3. ZAMAN ÇİZELGESİ — 12 AY HARİTASI
[Hangi ayda hangi aksiyonların yapılacağını gösteren çok detaylı bir Markdown Tablosu]

# 4. FİNANSAL ÖZET
[Yatırım ve Ciro beklentilerini hesaplayan, ROI anlatan uzun bir bölüm]

AKSİYONLAR (ICE SIRALI):
{json.dumps(actions_data, ensure_ascii=False, indent=2)[:4000]}
"""
        return self._call_llm(system, user, max_tokens=4000)


    # --- POZİSYON RAPORU (POSITION) ---
    def generate_position_executive_summary(self, serp_data: dict) -> str:
        """Pozisyon raporu yönetici özeti."""
        system = "Sen bir Veri Analisti ve SEO Danışmanısın. SERP verilerini sayısal olarak çok iyi özetlersin."
        user = f"""Aşağıdaki SERP verilerine göre detaylı (en az 500 kelime) bir yönetici özeti yaz.

# 0. YÖNETİCİ ÖZETİ
[Sitenin SEO görünürlüğünü, hangi alanlarda dar bir dominasyonu olduğunu, hangi alanları kaçırdığını derinlemesine tartışan 3 paragraf.]

**Sayısal Panel:**
[Toplam test edilen keyword, İlk 3'te olanlar, İlk 10'da olmayanlar yüzdelik dilimleriyle tablo olarak.]

VERİLER:
{json.dumps(serp_data, ensure_ascii=False, indent=2)[:4000]}
"""
        return self._call_llm(system, user, max_tokens=2500)

    def generate_position_category_analysis(self, serp_data: dict) -> str:
        """Pozisyon raporu kategori analizi."""
        system = "Sen bir SEO Stratejistisin. Keyword'leri niyet ve kategori bazlı gruplandırıp çok detaylı yargılara varırsın."
        user = f"""Aşağıdaki SERP verilerini mantıklı kategorilere (Örn: Ebat, Marka, Mevsim) böl ve ÇOK UZUN (en az 1000 kelime) bir analiz yaz.

# 1. KATEGORİ BAZLI ANALİZ — GÜÇLÜ VE ZAYIF NEREDE?

[Her kategori için aşağıdaki formatı kopyala:]
## KATEGORİ [X]: [Kategori Adı] — [Başarı Yüzdesi], [Durum: GÜÇLÜ/ZAYIF]
[O kategoriye giren keywordler için Tablo: Keyword | Pozisyon | Yorum]
**Yargı:** [Bu kategorideki sıralamaların site cirosuna ve iş modeline etkisini 2-3 paragrafla ÇOK DETAYLI tartış. Rakiplerin durumunu belirt.]

# 2. STRATEJİK YORUM
[Dominasyon, karma ve zayıf alanların sentezi. En az 3 paragraf.]

VERİLER:
{json.dumps(serp_data, ensure_ascii=False, indent=2)[:5000]}
"""
        return self._call_llm(system, user, max_tokens=3500)


    # --- ETKİ RAPORU (IMPACT) ---
    def generate_impact_timeline(self, impact_data: dict) -> str:
        """Etki raporu zaman çizelgesi."""
        system = "Sen bir Büyüme (Growth) uzmanı ve SEO stratejistisin. Sitenin yıllar içindeki evrimini hikayeleştirerek ve verilerle anlatırsın."
        user = f"""Aşağıdaki verileri kullanarak, bu e-ticaret platformunun kuruluşundan bugüne kadarki SEO ve büyüme yolculuğunu ÇOK DETAYLI (en az 800 kelime) yaz.

# 0. YÖNETİCİ ÖZETİ — 30 SANİYELİK ÖZET
[Sitenin yıllar içinde sıfırdan nasıl devasa bir ciroya/trafiğe ulaştığını özetleyen güçlü bir paragraf.]

# 1. ZAMAN ÇİZELGESİ — YIL YIL NE OLDU?
[Sitenin muhtemel kuruluş yılından bugüne kadar her yıl için: (Örn: 2019, 2020, 2021...)
- O yıl SEO'da ne gibi altyapılar kuruldu?
- Otorite nasıl büyüdü?
- Programatik SEO veya Blog nasıl devreye girdi?
Her yıl için 2 paragraf detaylı büyüme hikayesi yaz.]

VERİLER:
{json.dumps(impact_data, ensure_ascii=False, indent=2)[:3000]}
"""
        return self._call_llm(system, user, max_tokens=3000)

    def generate_impact_financials(self, impact_data: dict) -> str:
        """Etki raporu finansal analiz."""
        system = "Sen bir Yatırım Analisti ve Dijital Pazarlama Direktörüsün. ROI (Yatırım Getirisi) hesaplamalarında ustasın."
        user = f"""Aşağıdaki verilere dayanarak SEO'nun finansal etkisini ÇOK DETAYLI (en az 800 kelime) yaz.

# 2. GOOGLE'DA MEVCUT PERFORMANS
[Similarweb vb. metrik verilerini tablo olarak sun. Ziyaretçi kalitesini yorumla.]

# 3. SEO YATIRIM GERİ DÖNÜŞ HESABI (ROI)
[Bu organik trafik Google Ads ile (Tıklama Başı Maliyet - CPC ile) satın alınsaydı aylık/yıllık kaç milyon TL reklam bütçesi gerekirdi?
SEO'nun sağladığı inanılmaz reklam tasarrufunu ve ROI oranını matematiksel tahminlerle (formüllerle) uzun uzun hesapla.]

# 4. SEO'NUN CİRO BÜYÜMESİNDEKİ ROLÜ
[SEO'nun sadece trafik değil, Pazar Payı (Market Share) ve Marka Otoritesini nasıl katladığını 3 aşamada açıkla.]

VERİLER:
{json.dumps(impact_data, ensure_ascii=False, indent=2)[:3000]}
"""
        return self._call_llm(system, user, max_tokens=3000)
