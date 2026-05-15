import os
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

# Uygulama ve Gizli Anahtar
app = Flask(__name__)
app.secret_key = 'super_secret_seo_key_for_watchdog'

# Hardcoded Kullanıcı (Veritabanı olmadan hızlı test için)
USERS = {
    "admin": generate_password_hash("123456")
}

# Çalışma durumunu tutmak için basit memory dict
TASK_STATUS = {}

def run_seo_bot_async(domain: str):
    """Arka planda seo_main.py'nin çalışmasını tetikler."""
    TASK_STATUS[domain] = "running"
    try:
        from seo_main import main as run_seo
        # main() fonksiyonu artık --no-llm gibi argümanlarla çalışıyor ama 
        # kodda sys.argv tabanlı bir yapı var.
        # seo_main.py içerisindeki main() fonksiyonu argümanları sys.argv'den okuyor.
        # sys.argv'yi geçici olarak değiştirelim veya bir process çağıralım.
        import subprocess
        subprocess.run(["python", "seo_main.py", domain], check=True)
        TASK_STATUS[domain] = "completed"
    except Exception as e:
        print(f"Hata oluştu: {e}")
        TASK_STATUS[domain] = "failed"

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
            
        # Botu asenkron başlat
        thread = threading.Thread(target=run_seo_bot_async, args=(domain,))
        thread.daemon = True
        thread.start()
        
        flash(f"{domain} için analiz arka planda başlatıldı! Yaklaşık 5 dakika sürebilir.", "info")
        return redirect(url_for('dashboard'))
        
    # Mevcut raporları listele
    reports = []
    if os.path.exists("reports"):
        for filename in os.listdir("reports"):
            if filename.endswith(".pdf"):
                reports.append(filename)
                
    return render_template('dashboard.html', reports=reports, tasks=TASK_STATUS)

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
