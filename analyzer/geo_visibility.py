"""
GEO Görünürlük Analizi — "Yapay zeka bu siteyi kaynak gösteriyor mu?"
====================================================================
SEO analizi Google'da nerede olduğunu ölçer; GEO analizi yapay zeka aramalarında
(ChatGPT, Gemini, Perplexity, Google AI Overviews) nerede olduğunu ölçer.

Sektörün gerçek sorularını web aramalı bir modele sorar ve şunları raporlar:
  1. Marka yapay zekanın cevabında geçiyor mu?
  2. Site, yapay zekanın ALINTILADIĞI kaynaklar arasında mı, kaçıncı sırada?
  3. Yapay zeka en çok hangi domainlere güveniyor? (rakip istihbaratı)

Test soruları siteden otomatik türetilir (sayfa başlıkları/H1'lerden, LLM ile doğal
kullanıcı sorgusuna çevrilerek). Bağımlılık: requests (SDK gerekmez).
"""
import os
import re
import json
import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import requests

from seo_config import SEOConfig

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def geo_openai_key() -> str:
    """GEO için OpenAI anahtarı.

    Önce GEO_OPENAI_API_KEY (GEO web aramasını destekleyen ayrı anahtar), yoksa
    genel OPENAI_API_KEY. Böylece SEO'nun anahtarına dokunmadan GEO'ya web arama
    destekli bir anahtar verilebilir.
    """
    return os.environ.get("GEO_OPENAI_API_KEY") or SEOConfig.OPENAI_API_KEY


def _geo_model() -> str:
    """GEO denetimi için model: çok çağrı yapılır, ucuz model varsayılan."""
    return os.environ.get("GEO_MODEL", "gpt-4o-mini")


def openai_diagnostic() -> dict:
    """Tek bir küçük web aramalı çağrı yapıp anahtarın GEO için çalışıp çalışmadığını
    test eder. Sessiz başarısızlıkların gerçek nedenini görünür kılar."""
    key = geo_openai_key()
    if not key:
        return {"ok": False, "stage": "key", "detail": "OpenAI anahtarı yok (GEO_OPENAI_API_KEY / OPENAI_API_KEY)"}
    try:
        r = requests.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": _geo_model(), "tools": [{"type": "web_search_preview"}],
                  "tool_choice": {"type": "web_search_preview"}, "input": "test"},
            timeout=60,
        )
        if r.status_code == 200:
            return {"ok": True, "stage": "web_search", "detail": "Responses + web_search çalışıyor",
                    "key_tail": key[-6:]}
        return {"ok": False, "stage": "web_search", "http_status": r.status_code,
                "detail": r.text[:300], "key_tail": key[-6:]}
    except Exception as e:
        return {"ok": False, "stage": "request", "detail": f"{type(e).__name__}: {e}"}


def _quality_model() -> str:
    """Tek seferlik, kalite gerektiren çağrılar (plan, sorgu türetme) için."""
    return SEOConfig.OPENAI_MODEL or "gpt-4o"


# ── Domain normalizasyonu ────────────────────────────────────────────────
def domain_root(value: Optional[str]) -> str:
    """'https://www.x.com/y' -> 'x.com'."""
    if not value:
        return ""
    v = value.strip().lower()
    if "://" not in v:
        v = "//" + v
    parsed = urllib.parse.urlparse(v)
    netloc = parsed.netloc or parsed.path
    netloc = netloc.split("/")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def brand_token(domain: str) -> str:
    """'lastikborsasi.com' -> 'lastikborsasi'."""
    root = domain_root(domain)
    return root.split(".")[0] if root else ""


# ── OpenAI çağrıları ─────────────────────────────────────────────────────
def ask_openai_web(question: str, openai_key: str, model: str, timeout: int = 120) -> dict:
    """Web aramalı sorgu (aramayı zorlar). Returns {answer, cited_urls, error}."""
    payload = {
        "model": model,
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": {"type": "web_search_preview"},
        "input": f"{question}\n\nGüncel web kaynaklarını kullanarak cevapla ve kaynak göster.",
    }
    try:
        r = requests.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json=payload, timeout=timeout,
        )
        if r.status_code != 200:
            return {"answer": "", "cited_urls": [], "error": f"HTTP {r.status_code}: {r.text[:160]}"}
        data = r.json()
        answer, cited = "", []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    answer += c.get("text", "")
                    for ann in (c.get("annotations") or []):
                        if ann.get("type") == "url_citation" and ann.get("url"):
                            cited.append(ann["url"])
        seen = set()
        cited = [u for u in cited if not (u in seen or seen.add(u))]
        return {"answer": answer, "cited_urls": cited, "error": None}
    except Exception as e:
        return {"answer": "", "cited_urls": [], "error": f"{type(e).__name__}: {e}"}


def ask_openai_text(prompt: str, openai_key: str, model: str, timeout: int = 120) -> str:
    """Web araması olmadan düz metin üretimi. Boş str hata durumunda."""
    try:
        r = requests.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt}, timeout=timeout,
        )
        if r.status_code != 200:
            return ""
        data = r.json()
        out = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    out += c.get("text", "")
        return out.strip()
    except Exception:
        return ""


# ── Soru türetme (siteden otomatik) ──────────────────────────────────────
def derive_queries_from_site(
    domain: str, page_titles: list, page_h1s: list, openai_key: str, limit: int = 15
) -> list:
    """
    Sayfa başlıkları ve H1'lerden, yapay zekaya sorulacak gerçek kullanıcı sorgularını
    LLM ile türetir. Başlıklar = sitenin gerçek konuları; LLM bunları "kullanıcının
    ChatGPT'ye soracağı" doğal sorulara çevirir.
    """
    samples = [t.strip() for t in (page_titles + page_h1s) if t and t.strip()]
    # tekille, çok uzun listeyi kırp
    seen = set()
    samples = [s for s in samples if not (s in seen or seen.add(s))][:60]
    if not samples:
        return []

    sample_block = "\n".join(f"- {s}" for s in samples)
    prompt = f"""Aşağıda {domain_root(domain)} sitesinin sayfa başlıkları ve H1'leri var. Bu siteyi ziyaret eden tipik bir kullanıcının, bilgi ararken yapay zekaya (ChatGPT, Gemini) soracağı {limit} adet doğal arama sorgusu üret.

# Sitenin konuları
{sample_block}

# Kurallar
- Sorgular gerçek kullanıcı dilinde olsun (kim/nedir/nasıl/kaç/hangisi tarzı), başlıkları kopyalama.
- Markanın adını sorguya KOYMA; bilgi/araştırma sorgusu olsun (kullanıcı markayı bilmiyor).
- Sitenin sektörüne ve gerçek konularına dayan, alakasız genel sorgu üretme.
- Türkçe, sade. Her satır bir sorgu, numara/madde işareti YOK.

Sadece sorgu listesini döndür, başka açıklama ekleme."""

    text = ask_openai_text(prompt, openai_key, _quality_model())
    queries = []
    for line in text.splitlines():
        q = line.strip().lstrip("-*0123456789. ").strip()
        if len(q) > 8:
            queries.append(q)
    return queries[:limit]


# ── Tek sorgu denetimi ───────────────────────────────────────────────────
@dataclass
class QueryAudit:
    query: str
    brand_in_answer: bool = False
    domain_in_citations: bool = False
    citation_position: Optional[int] = None
    cited_domains: list = field(default_factory=list)
    serp_rank: Optional[int] = None
    error: Optional[str] = None


def audit_one(query: str, brand: str, domain: str, openai_key: str, model: str) -> QueryAudit:
    our_root = domain_root(domain)
    our_token = brand_token(domain) or brand.lower()

    res = ask_openai_web(query, openai_key, model)
    qa = QueryAudit(query=query, error=res["error"])
    if res["error"]:
        return qa

    answer_lower = res["answer"].lower()
    qa.brand_in_answer = (brand.lower() in answer_lower) or (bool(our_token) and our_token in answer_lower)

    cited_domains = [domain_root(u) for u in res["cited_urls"]]
    qa.cited_domains = cited_domains
    for i, d in enumerate(cited_domains, start=1):
        if our_root and (d == our_root or our_root in d or (our_token and our_token in d)):
            qa.domain_in_citations = True
            qa.citation_position = i
            break
    return qa


# ── Toplu denetim ────────────────────────────────────────────────────────
def run_audit(brand: str, domain: str, queries: list) -> dict:
    openai_key = geo_openai_key()
    if not openai_key:
        raise EnvironmentError("OpenAI anahtarı tanımlı değil — GEO denetimi yapılamaz.")
    model = _geo_model()
    results: list[QueryAudit] = []

    logger.info(f"  🤖 {len(queries)} sorgu yapay zekaya soruluyor (model: {model})...")
    for i, q in enumerate(queries, start=1):
        qa = audit_one(q, brand, domain, openai_key, model)
        status = "kaynak#%s" % qa.citation_position if qa.domain_in_citations else (
            "marka✓" if qa.brand_in_answer else "görünmez")
        logger.info(f"    ({i}/{len(queries)}) {status} — {q[:55]}")
        results.append(qa)

    ok = [r for r in results if not r.error]
    n = len(ok) or 1
    summary = {
        "total_queries": len(queries),
        "answered": len(ok),
        "brand_in_answer": sum(r.brand_in_answer for r in ok),
        "domain_cited": sum(r.domain_in_citations for r in ok),
        "brand_in_answer_pct": round(100 * sum(r.brand_in_answer for r in ok) / n),
        "domain_cited_pct": round(100 * sum(r.domain_in_citations for r in ok) / n),
    }
    freq: dict = {}
    for r in ok:
        for d in r.cited_domains:
            if d:
                freq[d] = freq.get(d, 0) + 1
    top_sources = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return {"summary": summary, "results": results, "top_sources": top_sources,
            "brand": brand, "domain": domain}


# ── Aksiyon planı (veriye dayalı satış reçetesi) ─────────────────────────
def generate_action_plan(audit: dict) -> str:
    s = audit["summary"]
    brand = audit["brand"]
    root = domain_root(audit["domain"])
    invisible = [r.query for r in audit["results"]
                 if not r.error and not r.brand_in_answer and not r.domain_in_citations]
    top_sources = audit["top_sources"][:15]
    sources_str = "\n".join(f"- {d} ({cnt} atıf)" for d, cnt in top_sources) or "- (atıf yok)"
    invisible_str = "\n".join(f"- {q}" for q in invisible[:20]) or "- (yok)"

    prompt = f"""Bir SEO/GEO ajansının danışmanı olarak, aşağıdaki yapay zeka görünürlük denetimine dayanarak müşteriye sunulacak "Durum değerlendirmesi ve aksiyon planı" bölümünü yaz.

# Müşteri
- Marka: {brand} ({root})

# Bulgular (GERÇEK VERİ)
- Test edilen sorgu: {s['total_queries']}
- Marka yapay zeka cevabında anıldı: {s['brand_in_answer']}/{s['answered']} (%{s['brand_in_answer_pct']})
- Site kaynak gösterildi: {s['domain_cited']}/{s['answered']} (%{s['domain_cited_pct']})

## Yapay zekanın en çok güvendiği kaynaklar
{sources_str}

## Markayı/siteyi hiç anmadığı sorgular
{invisible_str}

# Yazım kuralları
- Türkçe, sade, yönetici diliyle. Uzun tire (em dash) KULLANMA.
- Abartı ve boş vaat yok; bulgulara dayan, sayı ver. Satış odaklı ama dürüst.
- Çözüm araçlarımız: cevap-önce içerik (TL;DR), FAQ blokları, JSON-LD yapısal veri, E-E-A-T yazar kimliği üretebiliyoruz. Site dışı varlık (pazar yeri, video, sektör dizini, tutarlı marka bahsi) de plana girmeli; kaynak listesi bunu gösteriyor.

# İstenen yapı (### alt başlıklarla)
### Durum değerlendirmesi
2-3 cümle: marka yapay zekada nerede duruyor.
### Neden böyle
Kaynak listesini yorumla (video/pazar yeri/rakip baskın mı).
### Aksiyon planı
"İlk 30 gün" ve "30-90 gün" fazları; her madde: ne, neden (veriye bağla), beklenen etki.
### Başarı ölçütü
Aylık tekrar + 90 günlük gerçekçi hedef.

Sadece bu markdown bölümünü döndür. Üst seviye başlık (# veya ##) EKLEME, doğrudan ### ile başla."""

    plan = ask_openai_text(prompt, geo_openai_key(), _quality_model()).strip()
    plan = re.sub(r"\s+—\s+", ", ", plan).replace("—", "-")
    return plan


# ── Rapor markdown (gövde; _generate_generic_pdf başlığı kendi ekler) ────
def build_geo_report_markdown(audit: dict, action_plan: Optional[str] = None) -> str:
    s = audit["summary"]
    root = domain_root(audit["domain"])
    L = []
    L.append("Bu rapor, sektörün gerçek sorularını web aramalı bir yapay zekaya sorar ve "
             "yapay zekanın cevabında markanızın geçip geçmediğini, sitenizi kaynak gösterip "
             "göstermediğini ölçer. İnsanlar Google yerine ChatGPT, Gemini ve Perplexity'ye "
             "danışmaya kaydıkça bu görünürlük doğrudan trafiğe ve güvene dönüşür.")
    L.append("")
    L.append("# Özet")
    L.append("")
    L.append(f"- Test edilen sorgu: **{s['total_queries']}** (cevaplanan: {s['answered']})")
    L.append(f"- Marka cevapta anıldı: **{s['brand_in_answer']}/{s['answered']}** (%{s['brand_in_answer_pct']})")
    L.append(f"- Site kaynak gösterildi: **{s['domain_cited']}/{s['answered']}** (%{s['domain_cited_pct']})")
    L.append("")
    if action_plan:
        L.append("# Durum değerlendirmesi ve aksiyon planı")
        L.append("")
        L.append(action_plan.strip())
        L.append("")
    L.append("# Sorgu bazında görünürlük")
    L.append("")
    L.append("| Sorgu | Marka cevapta | Kaynak gösterildi | AI kaynak sırası |")
    L.append("|---|:--:|:--:|:--:|")
    for r in audit["results"]:
        if r.error:
            L.append(f"| {r.query[:55]} | hata | hata | - |")
            continue
        b = "Evet" if r.brand_in_answer else "Hayır"
        c = "Evet" if r.domain_in_citations else "Hayır"
        pos = str(r.citation_position) if r.citation_position else "-"
        L.append(f"| {r.query[:55]} | {b} | {c} | {pos} |")
    L.append("")
    invisible = [r for r in audit["results"] if not r.error and not r.brand_in_answer and not r.domain_in_citations]
    L.append("# İçerik fırsatı: yapay zekanın hiç anmadığı sorgular")
    L.append("")
    if invisible:
        L.append("Bu sorgularda ne marka anıldı ne site kaynak gösterildi. Öncelikli içerik alanları:")
        L.append("")
        for r in invisible:
            L.append(f"- {r.query}")
    else:
        L.append("Tüm sorgularda en az bir görünürlük sinyali yakalandı.")
    L.append("")
    L.append("# Yapay zekanın en çok güvendiği kaynaklar")
    L.append("")
    L.append("Test sorgularında en sık alıntılanan domainler. Bunlar yapay zeka gözünde "
             "sektörün otoriteleridir; hedef, bu listede yükselmektir.")
    L.append("")
    if audit["top_sources"]:
        L.append("| Domain | Atıf sayısı |")
        L.append("|---|:--:|")
        for d, cnt in audit["top_sources"][:15]:
            mark = " (BU SİTE)" if d == root else ""
            L.append(f"| {d}{mark} | {cnt} |")
    else:
        L.append("Atıf bulunamadı.")
    L.append("")
    L.append("> Not: Yapay zeka cevapları değişkendir; değer trenddedir, denetim aylık "
             "tekrarlanmalıdır. Google AI Overviews resmi API sunmadığından doğrudan ölçülemez; "
             "bu rapor en yakın temsilcisi olan web aramalı LLM cevaplarını baz alır.")
    return "\n".join(L)
