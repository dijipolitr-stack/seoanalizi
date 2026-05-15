import os
from typing import Dict, Any
import time
from openai import OpenAI
from app.core.config import settings

class ReportGenerator:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        if self.api_key and self.api_key != "mock_api_key":
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None

    def _generate_section(self, prompt: str, system_instruction: str) -> str:
        """Call OpenAI GPT-4o to generate a section, or return mock if no key."""
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=8192,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI API Error: {e}")
                return f"## Hata Oluştu\nOpenAI API ile bağlantı kurulamadı: {e}"
        else:
            return f"## MOCK BÖLÜM (API KEY YOK)\n\n{system_instruction}\n\n*İçerik buraya gelecek...*\n\n"

    def generate_full_report(self, target_url: str, serp_data: list, site_data: dict) -> Dict[str, Any]:
        """
        Multi-step generation of the 4 reports using OpenAI GPT-4o.
        Each section uses a strict heading structure cloned from the original 4 sample PDFs.
        """
        print(f"Generating comprehensive GPT-4o reports for {target_url}...")
        
        # 1. TAM SEO RAPORU
        sys_seo = """Sen üst düzey bir Kurumsal SEO Danışmanısın. Amacın, verilen domainin SEO durumunu analiz edip, tam olarak aşağıdaki formatta ve başlıklarda bir 'Tam SEO Raporu' oluşturmaktır. Kullanıcıya 'Sorun -> Çözüm' (Pain -> Solution) dilinde, son derece ciddi ve stratejik bir tonda hitap etmelisin. Çıktı formatı Markdown olmalı ve en az 1500 kelime içermelidir. Her bölüm derinlemesine analiz, somut rakamlar ve aksiyon önerileri barındırmalıdır.

Zorunlu Başlık Yapısı (Birebir kopyala):
# 1. Tam SEO Raporu: Yönetici Özeti ve Teknik Altyapı
## A. Teknik Mimariler ve Hatalar
(Burada Site Verisini analiz et, Bot Protection, Schema, H1 durumunu vb. yorumla. Her hata için etkisini ve çözümünü ayrıntılı anlat.)
## B. Tarama ve İndekslenme Verimliliği
(Derin analizler: robots.txt, sitemap.xml, canonical yapıları, crawl budget optimizasyonu)
## C. İçerik Kalitesi ve Thin Content
(Stratejik çıkarımlar: Duplicate content riskleri, içerik derinliği analizi, E-E-A-T değerlendirmesi)
## D. Sayfa Hızı ve Core Web Vitals
(LCP, FID, CLS metrikleri, mobil uyumluluk, performans darboğazları)
## E. Kopyalanabilir Prensip: Pain -> Solution
(Yalnızca negatifleri değil, bu negatiflerin nasıl fırsata çevrileceğini detaylı anlat. Her sorun için somut çözüm adımları sun.)
"""
        prompt_seo = f"Domain: {target_url}\nSite Verisi: {site_data}\nLütfen raporu zorunlu başlıklara göre, derinlemesine ve en az 1500 kelime olarak oluştur. Her bölümde tablolar ve bullet point'ler kullan."
        tam_seo_md = self._generate_section(prompt_seo, sys_seo)
        time.sleep(2)

        # 2. ETKİ RAPORU
        sys_etki = """Sen bir Finansal SEO Analistisin. Amacın, hedeflenen URL için 'SEO Etki Raporu' stilinde ROI hesabı, organik pazar payı tahmini yapan finansal bir SEO raporu yazmaktır. Çıktı formatı Markdown olmalı ve en az 1000 kelime içermelidir. Somut formüller, hesaplamalar ve senaryolar kullan.

Zorunlu Başlık Yapısı (Birebir kopyala):
# 2. SEO Etki Raporu: Finansal Dönüşüm ve Pazar Payı
## A. Ciro Beklentisi ve Benchmark Oranları
(Sektör ortalamalarına göre formülize edilmiş tahminler yap. Tablo formatında 3 senaryo göster: Pesimist, Baz, Optimist)
## B. Direct Traffic Çarpanı ve Marka Bilinirliği
(Marka gücü ile organik büyümenin birbirini nasıl beslediğini açıkla. Somut oranlar ver.)
## C. Organik vs Ücretli Karşılaştırması
(Google Ads ile aynı trafiği elde etmenin maliyetini hesapla, tasarruf tablosu oluştur)
## D. Yıllık Organik ROI Hesaplaması
(Organik trafiğin reklam maliyetinden ne kadar tasarruf sağladığını matematiksel olarak göster. 12 aylık projeksiyon tablosu sun.)
"""
        prompt_etki = f"Domain: {target_url}\nLütfen etki raporunu zorunlu başlıklara göre, somut hesaplamalar ve tablolarla en az 1000 kelime olarak oluştur."
        etki_md = self._generate_section(prompt_etki, sys_etki)
        time.sleep(2)
        
        # 3. POZİSYON RAPORU
        sys_poz = """Sen bir SEO Veri Stratejistisin. SERP verisine bakarak sitenin 'Sektörel Pusula'sını çıkaracaksın. Çıktı formatı Markdown olmalı ve en az 1200 kelime içermelidir. Mutlaka detaylı tablolar kullanmalısın.

Zorunlu Başlık Yapısı (Birebir kopyala):
# 3. Pozisyon Raporu: Kategori Bazlı Pusula
## A. Ebat ve Kategori Kelimelerindeki Dominans
(Hangi alanlarda güçlüyüz, hangi kelimelerde gerideyiz tablosu. Anahtar kelime - Pozisyon - Hacim - Zorluk tablosu oluştur.)
## B. Mevsimsel ve Marka Arama Analizi
(Burada SERP Verisini detaylıca incele ve zayıf olunan alanları listele. Trend analizi yap.)
## C. Rakip Karşılaştırma Matrisi
(En az 5 rakiple karşılaştırmalı tablo oluştur: Domain Rating, Organik Trafik, Anahtar Kelime Sayısı)
## D. Sektörel Pusula Stratejisi
(Tüm verileri toparlayan ve rakiplere göre nerede durduğumuzu gösteren nihai özet. SWOT analizi formatında sun.)
"""
        prompt_poz = f"Domain: {target_url}\nSERP Verisi: {serp_data}\nLütfen pozisyon raporunu zorunlu başlıklara göre, detaylı tablolarla en az 1200 kelime olarak oluştur."
        poz_md = self._generate_section(prompt_poz, sys_poz)
        time.sleep(2)
        
        # 4. YOL HARİTASI
        sys_yol = """Sen bir Proje Yöneticisi ve Büyüme (Growth) Liderisin. Önceki analizlere dayanarak 12 aylık, önceliklendirilmiş bir Yol Haritası dokümanı oluştur. ICE (Impact, Confidence, Ease) skorlamasını içermelidir. Çıktı formatı Markdown olmalı ve tablolar kullanılmalıdır (en az 1500 kelime).

Zorunlu Başlık Yapısı (Birebir kopyala):
# 4. Yol Haritası: 12 Aylık P0-P3 Aksiyon Planı
## A. Acil Eylem Planı (P0) — İlk 30 Gün
(Hemen yapılması gereken, en yüksek ICE skorlu işler. Her aksiyon için tahmini süre ve sorumlu birim belirt.)
## B. Kısa Vadeli Kazanımlar (P1) — 1-3 Ay
(Hızlı sonuç verecek taktiksel hamleler)
## C. Büyüme ve Ölçeklenme (P2) — 3-6 Ay
(Orta vadeli yapısal değişiklikler ve içerik stratejisi)
## D. Uzun Vadeli Vizyon (P3) — 6-12 Ay
(Rekabet avantajı için stratejik yatırımlar)
## E. ICE Skor Matrisi ve Yatırım vs Dönüş Tablosu
(Bütün aksiyonların Impact, Confidence, Ease skorlarını (1-10) ve tahmini maliyet/ciro getirisini gösteren büyük bir Markdown tablosu. En az 15 aksiyon satırı olmalı.)
## F. Aylık Milestone ve KPI Hedefleri
(12 ay boyunca takip edilecek KPI tablosu: Organik trafik, sıralama, dönüşüm oranı hedefleri)
"""
        prompt_yol = f"Domain: {target_url}\nLütfen yol haritasını zorunlu başlıklara göre, detaylı ICE tabloları ve KPI hedefleriyle en az 1500 kelime olarak oluştur."
        yol_md = self._generate_section(prompt_yol, sys_yol)

        # Birleştirme
        full_markdown = f"""
{tam_seo_md}

<div class="page-break-before"></div>

{etki_md}

<div class="page-break-before"></div>

{poz_md}

<div class="page-break-before"></div>

{yol_md}
"""
        
        return {
            "markdown_content": full_markdown,
            "meta": {
                "target_url": target_url,
                "date": "2026-05",
                "bot_version": "5.0 (OpenAI GPT-4o Pipeline)"
            }
        }

report_generator = ReportGenerator()
