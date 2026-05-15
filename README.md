# 🐕 Akıllı Watchdog

**LLM-destekli pipeline sağlık izleme sistemi**

Lead pipeline'larınızın 7/24 sağlıklı çalışıp çalışmadığını kontrol eder.
Form değişiklikleri, şema kaymaları ve veri kalitesi sorunlarını **proaktif olarak** tespit eder.
Sorun bulduğunda detaylı HTML e-posta raporu gönderir.

---

## 📁 Dosya Yapısı

```
Akilli_Watchdog/
├── main.py              # Ana orkestrasyon — CLI giriş noktası (tek sefer / loop)
├── config.py            # Environment variable tabanlı konfigürasyon
├── sheets_checker.py    # Google Sheets yapısal sağlık kontrolü (Katman 1)
├── notion_checker.py    # Notion DB erişim ve property kontrolü (Katman 1)
├── llm_analyzer.py      # Groq LLM ile şema kayması + veri kalitesi analizi (Katman 2)
├── alerter.py           # HTML alarm raporu + Gmail API (OAuth2) ile gönderim
├── requirements.txt     # Python bağımlılıkları
├── railway.json         # Railway deploy konfigürasyonu
└── .gitignore
```

---

## 🏗️ Mimari: 2 Katmanlı Kontrol

### Katman 1 — Yapısal Kontrol (LLM Yok)

| Modül | Kontrol | Detay |
|-------|---------|-------|
| `sheets_checker.py` | Tab varlığı | Beklenen tab isimleri Sheet'te var mı? |
| `sheets_checker.py` | Header uyumu | Sütun isimleri beklenen yapıyla eşleşiyor mu? |
| `sheets_checker.py` | Veri istatistikleri | Toplam satır, son 5 satır sample, son 20 satırda boşluk oranı |
| `notion_checker.py` | DB erişim | Notion veritabanına API ile ulaşılabiliyor mu? |
| `notion_checker.py` | Property uyumu | Beklenen property isimleri DB'de var mı? |
| `notion_checker.py` | Son 24h lead sayısı | Sheets ile karşılaştırma için Notion entry count |

### Katman 2 — LLM Akıllı Analiz (Groq)

| Modül | Analiz | Detay |
|-------|--------|-------|
| `llm_analyzer.py` | Şema kayması | `"full_name"` → `"ad_soyad"` gibi semantik değişiklikleri yakalar |
| `llm_analyzer.py` | Veri kalitesi | Telefon formatı, email geçerliliği, spam/bot tespiti (0-100 skor) |
| `llm_analyzer.py` | Pipeline tutarlılığı | Sheets ↔ Notion satır sayısı farkı analizi |

---

## 📋 İzlenen Projeler

| Proje | Pipeline | Kontrol |
|-------|----------|---------|
| Tele Satış CRM | Sheets → Notion | Tab, Header, Notion Property, Veri Kalitesi |
| Lead Notifier Bot | Sheets → Telegram/Email | Tab, Header, Veri Kalitesi |
| Tele Satış Notifier | Sheets → Email (Zamanlı) | Tab, Header, Veri Kalitesi |

> İzlenen projeler `config.py` → `MONITORED_PROJECTS` listesinde tanımlıdır.
> Yeni bir proje eklemek için listeye bir `dict` entry eklemek yeterlidir.

---

## 📦 Modül Detayları

### `main.py` — Ana Orkestrasyon

CLI giriş noktası. Tüm kontrol katmanlarını sırasıyla çalıştırır:

1. **Config doğrulama** — Zorunlu env var kontrolü
2. **Sheets kontrolü** — Her proje için `SheetsChecker.full_check()`
3. **Notion kontrolü** — Sadece `sheets_to_notion` pipeline'ları
4. **LLM analizi** — Şema kayması + veri kalitesi + pipeline tutarlılığı
5. **Alarm** — Sorun varsa veya `--force` ise e-posta gönderimi

Desteklenen modlar: tek seferlik, force rapor, sürekli döngü (SIGTERM/SIGINT graceful shutdown destekli).

### `config.py` — Konfigürasyon

Environment variable tabanlı merkezi ayarlar:
- Groq LLM ayarları (API key, model, base URL)
- SMTP alarm ayarları (Gmail App Password)
- Notion API token ve DB ID'leri
- Google Auth (Service Account JSON)
- İzlenen projelerin spreadsheet ID, tab, beklenen sütun tanımları
- `Config.validate()` ile zorunlu alan kontrolü

### `sheets_checker.py` — Google Sheets Kontrolü

Google Sheets API (v4) ile yapısal kontrol:
- **Auth sırası:** OAuth token (env) → Service Account (env) → Lokal merkezi OAuth
- `check_tab_exists()` — Tab varlık kontrolü
- `check_headers()` — Header uyumu (tam eşleşme + regex keyword)
- `get_row_stats()` — Toplam satır, son 5 satır sample, sütun bazlı boşluk oranı
- `full_check()` — Tek proje için tam kontrol orkestrasyon

### `notion_checker.py` — Notion DB Kontrolü

Notion API ile CRM veritabanı sağlık kontrolü:
- `check_database_access()` — DB erişim testi, title ve property listesi
- `check_properties_match()` — Beklenen property'lerin DB'de olup olmadığı
- `count_recent_entries()` — Son N saatte oluşturulan page sayısı (pagination destekli)
- `full_check()` — Erişim + property + son 24h count

### `llm_analyzer.py` — LLM Akıllı Analiz

Groq API (Llama 3.3 70B) ile üç tip analiz:
- `analyze_schema_drift()` — Header'ları beklenen yapıyla semantik karşılaştırma
- `analyze_data_quality()` — Son lead verilerinin kalitesi (telefon, email, spam)
- `analyze_pipeline_consistency()` — Sheets vs Notion satır farkı değerlendirmesi
- `full_analysis()` — Tek proje için tüm analizlerin orkestrasyon

### `alerter.py` — E-posta Alarm

Sağlık raporu HTML e-posta oluşturma ve Gmail API (OAuth2) gönderim:
- `build_html_report()` — Kritik/Uyarı/Sağlıklı durumuna göre renk kodlu rapor
- `send_alert_email()` — Gmail API ile gönderim (Railway: env token, Lokal: merkezi OAuth)
- Sorun yoksa ve force değilse e-posta gönderilmez

---

## 🚀 Kullanım

```bash
# Tek seferlik kontrol (sorun varsa e-posta gönderir)
python main.py

# Her durumda e-posta gönder (tam rapor)
python main.py --force

# Sürekli döngü (24 saatte bir — Railway deploy için)
python main.py --loop

# Force + loop (her kontrolde rapor gönder)
python main.py --loop --force
```

---

## 🚨 Alarm Sistemi

Sorun tespit edildiğinde HTML e-posta raporu gönderilir:

| Seviye | Tetikleyici |
|--------|-------------|
| 🚨 **Kritik** | Tab silindi, header değişti, Notion property kayboldu, Notion DB erişilemez |
| ⚠️ **Uyarı** | Veri kalitesi düşük, keyword sütunu bulunamadı, Sheets-Notion farkı >%10 |
| ✅ **Sağlıklı** | Sorun yoksa `--force` ile tam rapor alınabilir |

---

## 💰 Maliyet

**$0** — Groq free tier, günlük ~5-6 LLM çağrısı (limit: 14.400/gün)

---

## ⚙️ Environment Variables

| Değişken | Açıklama | Zorunlu |
|----------|----------|---------|
| `GROQ_API_KEY` | Groq API anahtarı (LLM analizi için) | ✅ |
| `GROQ_MODEL` | Groq model adı (varsayılan: `llama-3.3-70b-versatile`) | ❌ |
| `GROQ_BASE_URL` | Groq API base URL | ❌ |
| `GOOGLE_OUTREACH_TOKEN_JSON` | Gmail API OAuth2 token JSON (Railway) | ✅ |
| `ALERT_EMAIL` | Alarm alacak e-posta (varsayılan: `EMAIL_ADRESI_BURAYA`) | ❌ |
| `NOTION_API_TOKEN` | Notion API token (Notion kontrolü için) | ⭐ |
| `NOTION_DATABASE_ID` | Tele Satış CRM Notion DB ID | ❌ |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service Account JSON (production auth) | 🔄 |
| `GOOGLE_OUTREACH_TOKEN_JSON` | OAuth2 token JSON (alternatif auth) | 🔄 |
| `CRM_SPREADSHEET_ID` | Tele Satış CRM Google Sheets ID | ❌ |
| `CRM_SHEET_TABS` | CRM Sheet tab isimleri (virgülle ayrılmış) | ❌ |
| `CRM_NOTION_DB_ID` | CRM Notion DB ID | ❌ |
| `NOTIFIER_SPREADSHEET_ID` | Lead Notifier Bot Sheets ID | ❌ |
| `NOTIFIER_SHEET_TABS` | Lead Notifier tab isimleri | ❌ |
| `ZAMANLAYICI_SPREADSHEET_ID` | Tele Satış Notifier Sheets ID | ❌ |
| `ZAMANLAYICI_SHEET_TABS` | Tele Satış Notifier tab isimleri | ❌ |
| `CHECK_INTERVAL_HOURS` | Döngü kontrol aralığı (varsayılan: `24`) | ❌ |

> **Zorunluluk:** ✅ Zorunlu | ⭐ Notion kontrolü için gerekli | 🔄 İkisinden biri (auth) | ❌ Opsiyonel (varsayılan değeri var)

---

## 🚂 Railway Deploy

```json
{
  "startCommand": "python main.py",
  "restartPolicyType": "NEVER",
  "cronSchedule": "0 0 * * *"
}
```

Sistem **Railway Cron Job** olarak çalışacak şekilde yapılandırılmıştır.
Sürekli ayakta kalarak (loop) beklemek yerine, günde bir kez (UTC 00:00) uyanır, görevlerini yapar ve `sys.exit(0)` ile tamamen kapanır (`restartPolicyType: NEVER`).
Bu yöntem, sunucu maliyetini en aza indirerek sadece ihtiyaç anında çalışmayı ve güvenilirliği sağlar. İşlemi biten servis anında kendini kapatır.

---

## 📦 Bağımlılıklar

```
requests>=2.31
google-api-python-client>=2.100
google-auth>=2.23
```
