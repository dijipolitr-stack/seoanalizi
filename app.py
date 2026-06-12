import os
import json
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash

# Uygulama ve Gizli Anahtar
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "georank-dev-secret-change-me")

# GEORANK müşteri portalının raporları otomatik çekmesi için token korumalı API.
# Boşsa API kapalıdır (sadece elle JSON yapıştırma çalışır).
GEORANK_API_TOKEN = os.environ.get("GEORANK_API_TOKEN", "")

@app.route('/favicon.ico')
def favicon():
    return Response(status=204)  # No Content — tarayıcıya "yok ama hata da değil" der

# Hardcoded Kullanıcı (Veritabanı olmadan hızlı test için)
USERS = {
    "admin": generate_password_hash("123456")
}

# Çalışma durumunu tutmak için basit memory dict
TASK_STATUS = {}

# Article Intelligence sonuçlarını bellekte tut (Railway'de disk kalıcı değil)
AI_RESULTS: dict[str, dict] = {}


def run_seo_bot_async(domain: str):
    """Arka planda seo_main.py'nin çalışmasını tetikler."""
    TASK_STATUS[domain] = "running"
    try:
        import subprocess
        subprocess.run(["python", "seo_main.py", domain], check=True)
        TASK_STATUS[domain] = "completed"
    except Exception as e:
        print(f"Hata oluştu: {e}")
        TASK_STATUS[domain] = "failed"


def run_geo_bot_async(domain: str):
    """Arka planda geo_main.py'yi çalıştırır (yapay zeka görünürlük analizi)."""
    task_key = f"geo:{domain}"
    TASK_STATUS[task_key] = "running"
    try:
        import subprocess
        subprocess.run(["python", "geo_main.py", domain], check=True)
        TASK_STATUS[task_key] = "completed"
    except Exception as e:
        print(f"GEO analizi hatası: {e}")
        TASK_STATUS[task_key] = "failed"


def run_article_intelligence_async(domain: str):
    """Article Intelligence analizini arka planda çalıştırır."""
    task_key = f"ai:{domain}"
    TASK_STATUS[task_key] = "running"
    try:
        from analyzer.article_intelligence import ArticleIntelligence
        openai_key = os.environ.get("OPENAI_API_KEY")
        ai = ArticleIntelligence(openai_api_key=openai_key, top_n=15)
        result = ai.analyze(domain)
        AI_RESULTS[domain] = ai.to_json(result)

        # JSON ve HTML raporları diske kaydet
        os.makedirs("reports", exist_ok=True)
        safe_domain = domain.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")

        json_path = os.path.join("reports", f"{safe_domain}-article-intelligence.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(AI_RESULTS[domain], f, ensure_ascii=False, indent=2)

        # HTML raporu üret
        from report.article_intelligence_report import generate_html_report
        html_content = generate_html_report(AI_RESULTS[domain])
        html_path = os.path.join("reports", f"{safe_domain}-article-intelligence-rapor.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        TASK_STATUS[task_key] = "completed"
    except Exception as e:
        print(f"Article Intelligence hatası: {e}")
        TASK_STATUS[task_key] = "failed"
        AI_RESULTS[domain] = {"error": str(e)}


# ─── Rotalar ──────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and check_password_hash(USERS.get(username), password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            flash('Hatalı kullanıcı adı veya şifre.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        domain = request.form.get('domain')
        if not domain:
            flash('Lütfen geçerli bir domain girin.', 'warning')
            return redirect(url_for('dashboard'))

        thread = threading.Thread(target=run_seo_bot_async, args=(domain,))
        thread.daemon = True
        thread.start()

        flash(f"{domain} için SEO analizi arka planda başlatıldı!", "info")
        return redirect(url_for('dashboard'))

    reports = []
    all_files = []
    if os.path.exists("reports"):
        for filename in sorted(os.listdir("reports"), reverse=True):
            fpath = os.path.join("reports", filename)
            if not os.path.isfile(fpath):
                continue
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            size_bytes = os.path.getsize(fpath)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes // 1024} KB"
            else:
                size_str = f"{size_bytes / 1024 / 1024:.1f} MB"
            all_files.append({"name": filename, "ext": ext, "size": size_str})
            if ext == "pdf":
                reports.append(filename)

    return render_template('dashboard.html', reports=reports, tasks=TASK_STATUS, all_files=all_files)


@app.route('/geo-analiz', methods=['POST'])
def geo_analiz():
    """GEO görünürlük analizini arka planda başlatır."""
    if 'user' not in session:
        return redirect(url_for('login'))

    domain = request.form.get('domain', '').strip()
    if not domain:
        flash('Lütfen geçerli bir domain girin.', 'warning')
        return redirect(url_for('dashboard'))

    task_key = f"geo:{domain}"
    if TASK_STATUS.get(task_key) == "running":
        flash(f"{domain} için GEO analizi zaten çalışıyor.", "info")
        return redirect(url_for('dashboard'))

    thread = threading.Thread(target=run_geo_bot_async, args=(domain,))
    thread.daemon = True
    thread.start()

    flash(f"{domain} için GEO (yapay zeka görünürlük) analizi başlatıldı! Birkaç dakika sürebilir.", "info")
    return redirect(url_for('dashboard'))


@app.route('/status/<domain>')
def status(domain):
    """JS ile periyodik olarak durumu kontrol etmek için endpoint."""
    return jsonify({"status": TASK_STATUS.get(domain, "unknown")})


@app.route('/download/<filename>')
def download(filename):
    if 'user' not in session:
        return redirect(url_for('login'))
    filepath = os.path.join("reports", filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "Dosya bulunamadı", 404


@app.route('/files/download/<filename>')
def files_download(filename):
    """Herhangi bir rapor dosyasını indir (PDF, HTML, JSON)."""
    if 'user' not in session:
        return redirect(url_for('login'))
    # Güvenlik: sadece reports/ klasöründeki dosyalara izin ver
    filename = os.path.basename(filename)
    filepath = os.path.join("reports", filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "Dosya bulunamadı", 404


@app.route('/files/view/<filename>')
def files_view(filename):
    """HTML/JSON dosyasını tarayıcıda aç."""
    if 'user' not in session:
        return redirect(url_for('login'))
    filename = os.path.basename(filename)
    filepath = os.path.join("reports", filename)
    if not os.path.exists(filepath):
        return "Dosya bulunamadı", 404
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "html":
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    elif ext == "json":
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        return f'<pre style="background:#0d1117;color:#e6edf3;padding:24px;font-size:13px;">{content}</pre>'
    return send_file(filepath, as_attachment=False)


# ─── Article Intelligence Endpoint'leri ───────────────────────────────────────

@app.route('/article-intelligence', methods=['GET', 'POST'])
def article_intelligence():
    """
    En çok ziyaret edilen makaleleri bul + gizli kelime analizi.
    GET  → form göster
    POST → analizi başlat
    """
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        domain = request.form.get('domain', '').strip()
        if not domain:
            flash('Lütfen geçerli bir domain girin.', 'warning')
            return redirect(url_for('article_intelligence'))

        task_key = f"ai:{domain}"
        if TASK_STATUS.get(task_key) == "running":
            flash(f"{domain} için analiz zaten çalışıyor, lütfen bekleyin.", "info")
            return redirect(url_for('article_intelligence'))

        thread = threading.Thread(target=run_article_intelligence_async, args=(domain,))
        thread.daemon = True
        thread.start()

        flash(f"{domain} için makale analizi başlatıldı! Birkaç dakika sürebilir.", "info")
        return redirect(url_for('article_intelligence'))

    # Tamamlanan analizleri listele
    completed = {
        domain: result
        for domain, result in AI_RESULTS.items()
        if not result.get("error")
    }

    # Disk'teki JSON dosyaları da ekle (Railway restart sonrası)
    if os.path.exists("reports"):
        for fname in os.listdir("reports"):
            if fname.endswith("-article-intelligence.json"):
                domain_key = fname.replace("-article-intelligence.json", "")
                if domain_key not in completed:
                    try:
                        with open(os.path.join("reports", fname), encoding="utf-8") as f:
                            completed[domain_key] = json.load(f)
                    except Exception:
                        pass

    return render_template(
        'article_intelligence.html',
        tasks=TASK_STATUS,
        results=completed,
    )


@app.route('/article-intelligence/status/<path:domain>')
def ai_status(domain):
    """Article Intelligence analiz durumunu döner."""
    task_key = f"ai:{domain}"
    return jsonify({
        "status": TASK_STATUS.get(task_key, "unknown"),
        "has_result": domain in AI_RESULTS,
    })


@app.route('/article-intelligence/result/<path:domain>')
def ai_result(domain):
    """
    Article Intelligence JSON sonucunu döner.
    seo-article-panel botu bu endpoint'i çağıracak.
    """
    if domain not in AI_RESULTS:
        # Disk'ten dene
        safe = domain.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")
        fpath = os.path.join("reports", f"{safe}-article-intelligence.json")
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify({"error": "Sonuç bulunamadı"}), 404

    return jsonify(AI_RESULTS[domain])


@app.route('/article-intelligence/download/<path:domain>')
def ai_download(domain):
    """Article Intelligence JSON sonucunu dosya olarak indir."""
    if 'user' not in session:
        return redirect(url_for('login'))

    safe = domain.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")
    fpath = os.path.join("reports", f"{safe}-article-intelligence.json")
    if os.path.exists(fpath):
        return send_file(fpath, as_attachment=True)
    return "Dosya bulunamadı", 404


@app.route('/article-intelligence/report/<path:domain>')
def ai_report_view(domain):
    """HTML raporu tarayıcıda aç (yazdırılabilir)."""
    if 'user' not in session:
        return redirect(url_for('login'))

    safe = domain.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")
    fpath = os.path.join("reports", f"{safe}-article-intelligence-rapor.html")

    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            return f.read()

    # Dosya yoksa bellekten üret
    if domain in AI_RESULTS:
        from report.article_intelligence_report import generate_html_report
        return generate_html_report(AI_RESULTS[domain])

    return "Rapor bulunamadı — önce analizi tamamlayın.", 404


@app.route('/article-intelligence/report-download/<path:domain>')
def ai_report_download(domain):
    """HTML raporu dosya olarak indir."""
    if 'user' not in session:
        return redirect(url_for('login'))

    safe = domain.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")
    fpath = os.path.join("reports", f"{safe}-article-intelligence-rapor.html")
    if os.path.exists(fpath):
        return send_file(fpath, as_attachment=True, download_name=f"article-intelligence-{safe}.html")
    return "Dosya bulunamadı", 404


# ─── GEORANK Portalı için Token Korumalı API ──────────────────────────────

def _slugify_domain(domain: str) -> str:
    """Motorun rapor dosya adı kuralı: 'https://www.x.com/y' -> 'x-com'."""
    d = (domain or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d.replace(".", "-")


def _check_api_token() -> bool:
    if not GEORANK_API_TOKEN:
        return False
    token = request.args.get("token") or request.headers.get("X-API-Token", "")
    return token == GEORANK_API_TOKEN


def _serve_report_json(domain: str, kind: str):
    if not _check_api_token():
        return jsonify({"error": "unauthorized"}), 401
    slug = _slugify_domain(domain)
    fname = f"{slug}-geo-analiz-verisi.json" if kind == "geo" else f"{slug}-analiz-verisi.json"
    fpath = os.path.join("reports", fname)
    if not os.path.exists(fpath):
        return jsonify({"error": "not_found", "domain": domain, "kind": kind}), 404
    with open(fpath, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route('/api/geo/<path:domain>')
def api_geo(domain):
    """GEORANK portalı için GEO analiz verisini döndürür (token gerekli)."""
    return _serve_report_json(domain, "geo")


@app.route('/api/seo/<path:domain>')
def api_seo(domain):
    """GEORANK portalı için SEO analiz verisini döndürür (token gerekli)."""
    return _serve_report_json(domain, "seo")


@app.route('/api/domains')
def api_domains():
    """reports/ klasöründe mevcut domainleri ve rapor türlerini listeler (token gerekli)."""
    if not _check_api_token():
        return jsonify({"error": "unauthorized"}), 401
    found = {}
    if os.path.exists("reports"):
        for fname in os.listdir("reports"):
            if fname.endswith("-geo-analiz-verisi.json"):
                found.setdefault(fname.replace("-geo-analiz-verisi.json", ""), {})["geo"] = True
            elif fname.endswith("-analiz-verisi.json"):
                found.setdefault(fname.replace("-analiz-verisi.json", ""), {})["seo"] = True
    domains = [
        {"slug": s, "has_geo": k.get("geo", False), "has_seo": k.get("seo", False)}
        for s, k in sorted(found.items())
    ]
    return jsonify({"domains": domains})


if __name__ == '__main__':
    app.run(debug=True, port=5000)

