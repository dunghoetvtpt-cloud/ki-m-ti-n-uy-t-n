import os
import json
import time
import random
import base64
import requests
from threading import Thread, Lock
from decimal import Decimal, ROUND_DOWN
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "dung_license_secret_key_1612012"

ADMIN_USERNAME = "dunghoet"
ADMIN_PASSWORD = "10091990dung"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

ip_request_history = {}
DB_FILE = "system_db.json"
db_lock = Lock()

# ---------------------------------------------------------
# 🐙 ĐỒNG BỘ GITHUB API (CHẠY NGẦM)
# ---------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
GITHUB_FILE_PATH = "system_db.json"

def sync_pull_from_github():
    if not GITHUB_TOKEN or not GITHUB_REPO: return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            content_bytes = base64.b64decode(res.json().get("content", ""))
            with db_lock:
                with open(DB_FILE, "wb") as f: f.write(content_bytes)
    except Exception as e: print(f"⚠️ Lỗi pull GitHub: {e}", flush=True)

def sync_push_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO: return
    try:
        with db_lock:
            if not os.path.exists(DB_FILE): return
            with open(DB_FILE, "rb") as f: file_bytes = f.read()
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        get_res = requests.get(url, headers=headers, timeout=3)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        payload = {"message": "Auto-sync system_db.json", "content": content_b64}
        if sha: payload["sha"] = sha
        requests.put(url, json=payload, headers=headers, timeout=3)
    except Exception as e: print(f"❌ Lỗi push GitHub: {e}", flush=True)

Thread(target=sync_pull_from_github, daemon=True).start()

def load_system_db():
    with db_lock:
        if not os.path.exists(DB_FILE):
            default_data = {"keys": {}, "banned_users": {}, "maintenance": {"active": False, "notice": ""}}
            try:
                with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(default_data, f, ensure_ascii=False, indent=4)
            except: pass
            return default_data
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                record = json.load(f)
                if not isinstance(record, dict): raise Exception()
                if "keys" not in record: record["keys"] = {}
                return record
        except: return {"keys": {}, "banned_users": {}, "maintenance": {"active": False, "notice": ""}}

def save_system_db(db):
    try:
        with db_lock:
            with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, indent=4)
        Thread(target=sync_push_to_github, daemon=True).start()
        return True
    except: return False

def verify_key(key_code):
    db = load_system_db()
    keys_db = db.get("keys", {})
    if key_code not in keys_db: return False, "Key không tồn tại trên hệ thống!"
    k_data = keys_db[key_code]
    now = time.time()
    if not k_data.get("expire_at"):
        duration = float(k_data.get("duration_hours", 24)) * 3600
        k_data["expire_at"] = now + duration
        save_system_db(db)
    if now > k_data.get("expire_at", 0):
        return False, "Key đã hết hạn sử dụng (24h)!"
    return True, "Hợp lệ"

# ---------------------------------------------------------
# FLASK WEB ROUTES
# ---------------------------------------------------------
@app.route('/')
def index():
    user_key = session.get("user_key")
    if user_key:
        valid, _ = verify_key(user_key)
        if valid: return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    error = ""
    if request.method == 'POST':
        key = request.form.get("key", "").strip()
        valid, msg = verify_key(key)
        if valid:
            session["user_key"] = key
            return redirect(url_for('dashboard'))
        else: error = msg
    
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập Key - XWorld Tool</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 15px; }
        .card { background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); border-radius: 24px; width: 100%; max-width: 400px; padding: 30px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
        h2 { font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 10px; }
        p { color: #94a3b8; font-size: 13px; margin-bottom: 20px; }
        input { width: 100%; padding: 14px; border-radius: 12px; border: 1px solid #334155; background: #0b0f19; color: #4ade80; font-family: monospace; font-size: 15px; text-align: center; margin-bottom: 15px; }
        .btn { width: 100%; background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; border: none; padding: 14px; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 14px; margin-bottom: 10px; }
        .btn-link { display: block; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; text-decoration: none; padding: 12px; border-radius: 12px; font-weight: 600; font-size: 13px; }
        .error { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 10px; border-radius: 10px; font-size: 12px; margin-bottom: 15px; }
    </style></head>
    <body>
        <div class="card">
            <h2><i class="fa-solid fa-key"></i> KÍCH HOẠT KEY 24H</h2>
            <p>Nhập mã bản quyền của bạn để truy cập hệ thống Auto Tool.</p>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <form method="POST">
                <input type="text" name="key" placeholder="KEY-XW-XXXXXXXX" required autocomplete="off">
                <button type="submit" class="btn">Vào Tool Ngay</button>
            </form>
            <a href="/get_link4m" class="btn-link"><i class="fa-solid fa-rocket"></i> Lấy Key Mới Qua Link4m</a>
        </div>
    </body></html>
    """
    return render_template_string(html, error=error)

@app.route('/get_link4m')
def get_link4m():
    destination_url = f"{request.host_url.rstrip('/')}/claim_key"
    try:
        res = requests.get(f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={destination_url}", timeout=5).json()
        if res.get("status") == "success": return redirect(res.get("shortenedUrl"))
    except: pass
    return redirect(url_for('login_page'))

@app.route('/claim_key')
def claim_key():
    new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    db = load_system_db()
    db["keys"][new_key] = {"status": "chua_dung", "used_by": [], "created_at": time.time(), "expire_at": time.time() + 86400, "duration_hours": 24}
    save_system_db(db)
    
    html = f"""
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lấy Key Thành Công</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ background: #0f172a; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; font-family: 'Plus Jakarta Sans', sans-serif; }}
        .card {{ background: #1e293b; padding: 30px; border-radius: 20px; text-align: center; max-width: 380px; width: 100%; border: 1px solid #334155; }}
        .key {{ background: #0b0f19; color: #4ade80; padding: 12px; font-family: monospace; font-size: 16px; border-radius: 10px; margin: 15px 0; border: 1px dashed #6366f1; }}
        .btn {{ display: block; background: #6366f1; color: #fff; text-decoration: none; padding: 12px; border-radius: 10px; font-weight: 700; margin-top: 15px; }}
    </style></head>
    <body>
        <div class="card">
            <h3>🎉 LẤY KEY THÀNH CÔNG!</h3>
            <p style="font-size: 13px; color: #94a3b8;">Key của bạn có hiệu lực trong 24 giờ:</p>
            <div class="key">{new_key}</div>
            <a href="/login" class="btn">Đăng Nhập Vào Tool Ngay</a>
        </div>
    </body></html>
    """
    return html

@app.route('/dashboard')
def dashboard():
    user_key = session.get("user_key")
    valid, _ = verify_key(user_key)
    if not valid: return redirect(url_for('login_page'))
    
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XWorld Tool Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: #0f172a; color: #f8fafc; min-height: 100vh; display: flex; flex-direction: column; }
        header { background: #1e293b; border-bottom: 1px solid #334155; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
        .menu-btn { background: none; border: none; color: #38bdf8; font-size: 20px; cursor: pointer; }
        h1 { font-size: 16px; font-weight: 700; color: #fff; }
        
        /* Sidebar Menu 3 Gạch */
        .sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); display: none; z-index: 998; }
        .sidebar { position: fixed; top: 0; left: -260px; width: 250px; height: 100%; background: #1e293b; z-index: 999; padding: 20px; transition: 0.3s; border-right: 1px solid #334155; }
        .sidebar.active { left: 0; }
        .sidebar h3 { color: #818cf8; font-size: 14px; margin-bottom: 20px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
        .sidebar a { display: flex; align-items: center; gap: 10px; color: #94a3b8; text-decoration: none; padding: 12px; border-radius: 8px; font-weight: 600; font-size: 13px; margin-bottom: 8px; transition: 0.2s; }
        .sidebar a:hover, .sidebar a.active { background: #6366f1; color: #fff; }
        
        /* Nội dung chính */
        .container { max-width: 800px; margin: 20px auto; padding: 0 15px; width: 100%; flex: 1; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 20px; margin-bottom: 20px; }
        .card h2 { font-size: 18px; margin-bottom: 15px; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 5px; }
        input, select { width: 100%; padding: 12px; background: #0b0f19; border: 1px solid #334155; color: #fff; border-radius: 8px; font-size: 13px; }
        .btn-run { background: #22c55e; color: #fff; border: none; padding: 12px 20px; border-radius: 8px; font-weight: 700; cursor: pointer; width: 100%; font-size: 14px; }
        .logout { color: #f87171 !important; }
    </style></head>
    <body>

    <div class="sidebar-overlay" id="overlay" onclick="toggleSidebar()"></div>
    <div class="sidebar" id="sidebar">
        <h3><i class="fa-solid fa-bars"></i> MENU HỆ THỐNG</h3>
        <a href="#" onclick="switchTab('tab-tool')" class="active" id="link-tool"><i class="fa-solid fa-robot"></i> Chạy Tool Auto</a>
        <a href="#" onclick="switchTab('tab-getkey')" id="link-getkey"><i class="fa-solid fa-key"></i> Tab Lấy Key (24h)</a>
        <a href="/login" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Đăng Xuất</a>
    </div>

    <header>
        <button class="menu-btn" onclick="toggleSidebar()"><i class="fa-solid fa-bars"></i></button>
        <h1>XWORLD MULTI-TOOL</h1>
        <div style="width: 24px;"></div>
    </header>

    <div class="container">
        <!-- TAB 1: CHẠY TOOL ĐỦ 3 GAME -->
        <div id="tab-tool" class="tab-content active">
            <div class="card">
                <h2><i class="fa-solid fa-gamepad"></i> Cấu Hình Game Auto Bet</h2>
                <div class="form-group">
                    <label>Chọn Game:</label>
                    <select id="gameSelect">
                        <option value="escape">🕹️ Vua Thoát Hiểm (Escape Master)</option>
                        <option value="sprint">🏃 Đua Tốc Độ (SprintRun)</option>
                        <option value="winhash">🎲 Winhash Lucky Game</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>User ID:</label>
                    <input type="text" id="userId" placeholder="Nhập User ID...">
                </div>
                <div class="form-group">
                    <label>Secret Key:</label>
                    <input type="text" id="secretKey" placeholder="Nhập Secret Key...">
                </div>
                <div class="form-group">
                    <label>Mức Cược Cơ Bản / Tổng Cược:</label>
                    <input type="number" id="baseBet" value="1.0">
                </div>
                <button class="btn-run" onclick="toggleRunTool()" id="runBtn">🚀 BẮT ĐẦU CHẠY TOOL</button>
            </div>
        </div>

        <!-- TAB 2: LẤY KEY -->
        <div id="tab-getkey" class="tab-content">
            <div class="card" style="text-align: center;">
                <h2><i class="fa-solid fa-key"></i> Lấy Mã Bản Quyền 24 Giờ</h2>
                <p style="color: #94a3b8; font-size: 13px; margin-bottom: 20px;">Bấm nút bên dưới để tiến hành vượt link nhận key mới sử dụng hệ thống.</p>
                <a href="/get_link4m" target="_blank" style="display: inline-block; background: #6366f1; color: #fff; text-decoration: none; padding: 14px 25px; border-radius: 12px; font-weight: 700;"><i class="fa-solid fa-rocket"></i> Lấy Key Qua Link4m Ngay</a>
            </div>
        </div>
    </div>

    <script>
        function toggleSidebar() {
            const s = document.getElementById("sidebar");
            const o = document.getElementById("overlay");
            if (s.classList.contains("active")) {
                s.classList.remove("active"); o.style.display = "none";
            } else {
                s.classList.add("active"); o.style.display = "block";
            }
        }
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            document.getElementById('link-' + tabId.replace('tab-', '')).classList.add('active');
            toggleSidebar();
        }
        let isRunning = false;
        function toggleRunTool() {
            isRunning = !isRunning;
            const btn = document.getElementById("runBtn");
            if (isRunning) {
                btn.style.background = "#ef4444";
                btn.innerHTML = "⏹️ DỪNG TOOL";
                alert("Đã khởi động tiến trình Auto Bet cho game đã chọn!");
            } else {
                btn.style.background = "#22c55e";
                btn.innerHTML = "🚀 BẮT ĐẦU CHẠY TOOL";
                alert("Đã dừng tiến trình tool!");
            }
        }
    </script>
    </body></html>
    """
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
