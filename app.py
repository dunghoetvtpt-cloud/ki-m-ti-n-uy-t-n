import os
import json
import time
import random
import base64
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock
from decimal import Decimal
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

# ---------------------------------------------------------
# CẤU HÌNH FLASK WEB
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = "dung_license_secret_key_1612012"

# THÔNG TIN TÀI KHOẢN QUẢN TRỊ BÍ MẬT
ADMIN_USERNAME = "dunghoet"
ADMIN_PASSWORD = "10091990dung"

LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

ip_request_history = {}
DB_FILE = "system_db.json"
db_lock = Lock()

# ---------------------------------------------------------
# 🐙 CẤU HÌNH ĐỒNG BỘ GITHUB API (CHẠY NGẦM KHÔNG TREO WEB)
# ---------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
GITHUB_FILE_PATH = "system_db.json"

def sync_pull_from_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            content_b64 = res.json().get("content", "")
            content_bytes = base64.b64decode(content_b64)
            with db_lock:
                with open(DB_FILE, "wb") as f:
                    f.write(content_bytes)
            print("📥 Đã đồng bộ dữ liệu từ GitHub thành công!", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi pull từ GitHub: {e}", flush=True)

def sync_push_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        with db_lock:
            if not os.path.exists(DB_FILE): return
            with open(DB_FILE, "rb") as f:
                file_bytes = f.read()
        
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        
        get_res = requests.get(url, headers=headers, timeout=3)
        sha = None
        if get_res.status_code == 200:
            sha = get_res.json().get("sha")
        
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        payload = {"message": "Auto-sync system_db.json from Web App", "content": content_b64}
        if sha: payload["sha"] = sha
            
        put_res = requests.put(url, json=payload, headers=headers, timeout=3)
        if put_res.status_code in [200, 201]:
            print("📤 Đã đẩy dữ liệu lên GitHub thành công!", flush=True)
    except Exception as e:
        print(f"❌ Lỗi push lên GitHub: {e}", flush=True)

Thread(target=sync_pull_from_github, daemon=True).start()

# ---------------------------------------------------------
# 🗄️ HỆ THỐNG LƯU TRỮ DỮ LIỆU
# ---------------------------------------------------------
def load_system_db():
    with db_lock:
        if not os.path.exists(DB_FILE):
            default_data = {
                "keys": {}, 
                "banned_users": {}, 
                "maintenance": {"active": False, "notice": ""}
            }
            try:
                with open(DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=4)
            except: pass
            return default_data
        
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                record = json.load(f)
                if not isinstance(record, dict): raise Exception()
                if "keys" not in record: record["keys"] = {}
                if "banned_users" not in record or isinstance(record["banned_users"], list): record["banned_users"] = {}
                if "maintenance" not in record: record["maintenance"] = {"active": False, "notice": ""}
                
                clean_keys = {}
                for k, info in record["keys"].items():
                    if not isinstance(info, dict): continue
                    ub = info.get("used_by", [])
                    if isinstance(ub, (str, int)): info["used_by"] = [str(ub)] if ub else []
                    elif ub is None: info["used_by"] = []
                    elif not isinstance(ub, list): info["used_by"] = []
                    else: info["used_by"] = [str(x) for x in ub if x is not None]
                    
                    info["max_uses"] = int(info.get("max_uses", 1))
                    info["is_vip"] = bool(info.get("is_vip", False))
                    info["total_bets_count"] = int(info.get("total_bets_count", 0))
                    clean_keys[k] = info
                record["keys"] = clean_keys
                return record
        except:
            return {"keys": {}, "banned_users": {}, "maintenance": {"active": False, "notice": ""}}

def save_system_db(db):
    try:
        with db_lock:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=4)
        Thread(target=sync_push_to_github, daemon=True).start()
        return True
    except Exception as e:
        print(f"❌ Lỗi ghi file: {e}", flush=True)
        return False

def save_key_to_cloud(key_code, data):
    db = load_system_db()
    if "keys" not in db: db["keys"] = {}
    ub = data.get("used_by", [])
    if isinstance(ub, (str, int)): ub = [str(ub)] if ub else []
    elif ub is None: ub = []
    else: ub = [str(x) for x in ub if x is not None]

    db["keys"][key_code] = {
        "status": data.get("status", "chua_dung"),
        "used_by": ub,
        "created_at": data.get("created_at", time.time()),
        "expire_at": data.get("expire_at"),
        "duration_hours": data.get("duration_hours", 24),
        "is_vip": bool(data.get("is_vip", False)),
        "max_uses": int(data.get("max_uses", 1)),
        "total_bets_count": int(data.get("total_bets_count", 0))
    }
    return save_system_db(db)

def delete_key_from_cloud(key_code):
    db = load_system_db()
    if "keys" in db and key_code in db["keys"]:
        del db["keys"][key_code]
        save_system_db(db)

# ---------------------------------------------------------
# FLASK WEB ROUTES (TRANG CHỦ TÍCH HỢP BẤM 10 LẦN TIA SÉT)
# ---------------------------------------------------------
@app.route('/')
def home():
    new_key = request.args.get("key", "")
    error = request.args.get("error", "")
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWORLD LICENSE GATEWAY - VIP</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
            body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 15px; overflow-x: hidden; }
            .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); border-radius: 24px; width: 100%; max-width: 440px; padding: 30px 20px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }
            .icon-box { width: 60px; height: 60px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 15px; box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.5); color: #fff; cursor: pointer; user-select: none; transition: transform 0.1s; }
            .icon-box:active { transform: scale(0.9); }
            .badge { display: inline-block; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 5px 14px; border-radius: 30px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
            h2 { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 10px; }
            p { color: #94a3b8; font-size: 13px; line-height: 1.5; margin-bottom: 25px; }
            .btn { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; text-decoration: none; padding: 14px; border-radius: 14px; font-weight: 700; font-size: 14px; box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.5); border: none; cursor: pointer; }
            .key-container { background: #0b0f19; border: 2px dashed #6366f1; padding: 15px; border-radius: 16px; margin-top: 15px; }
            .key-text { font-family: monospace; font-size: 16px; color: #4ade80; font-weight: 700; word-break: break-all; margin-bottom: 10px; }
            .btn-copy { background: #22c55e; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 700; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
            .error { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 10px; border-radius: 10px; font-size: 12px; margin-top: 15px; font-weight: 500; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-box" id="secretLightning" onclick="handleSecretClick()"><i class="fa-solid fa-bolt"></i></div>
            <span class="badge">Hệ Thống Tự Động 24/7</span>
            <h2>XWORLD GATEWAY</h2>
            <p>Vượt link an toàn và nhanh chóng để nhận mã bản quyền chính thức sử dụng trong 24 giờ.</p>
            {% if new_key %}
                <div class="key-container">
                    <div class="key-text" id="keyText">{{ new_key }}</div>
                    <button class="btn-copy" onclick="copyKey()"><i class="fa-regular fa-copy"></i> Sao Chép Key Ngay</button>
                </div>
                <p style="color: #4ade80; margin-top: 12px; font-weight: 600; font-size: 12px;">✨ Đã tạo key thành công!</p>
            {% else %}
                <a href="/get_link4m" class="btn"><i class="fa-solid fa-rocket"></i> TIẾN HÀNH LẤY KEY (24H)</a>
            {% endif %}
            {% if error %} <div class="error">{{ error }}</div> {% endif %}
        </div>
        <script>
            let clickCount = 0;
            function handleSecretClick() {
                clickCount++;
                if (clickCount >= 10) {
                    window.location.href = "/quan-ly-bi-mat-dunghoet";
                }
                setTimeout(() => { clickCount = 0; }, 3000);
            }

            function copyKey() {
                const keyText = document.getElementById("keyText").innerText;
                navigator.clipboard.writeText(keyText).then(() => {
                    const btn = document.querySelector(".btn-copy");
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> Đã Sao Chép!';
                    setTimeout(() => { btn.innerHTML = '<i class="fa-regular fa-copy"></i> Sao Chép Key Ngay'; }, 2000);
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, new_key=new_key, error=error)

@app.route('/get_link4m')
def get_link4m():
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    now = time.time()
    if client_ip not in ip_request_history: ip_request_history[client_ip] = []
    ip_request_history[client_ip] = [t for t in ip_request_history[client_ip] if now - t < 60]
    if len(ip_request_history[client_ip]) >= 3:
        return redirect(url_for('home', error="⚠️ Phát hiện spam! Thao tác quá nhanh, vui lòng thử lại sau 1 phút."))
    ip_request_history[client_ip].append(now)

    current_domain = request.host_url.rstrip('/')
    destination_url = f"{current_domain}/claim_key"
    api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={destination_url}"
    try:
        res = requests.get(api_url, timeout=5)
        result = res.json()
        if result.get("status") == "success": return redirect(result.get("shortenedUrl"))
        else: return redirect(url_for('home', error=result.get("message", "Lỗi tạo link")))
    except: return redirect(url_for('home', error="Không thể kết nối Link4m API"))

@app.route('/claim_key')
def claim_key():
    new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    key_data = {"status": "chua_dung", "used_by": [], "created_at": time.time(), "expire_at": None, "duration_hours": 24, "is_vip": False, "max_uses": 1, "total_bets_count": 0}
    
    if save_key_to_cloud(new_key, key_data):
        return redirect(url_for('home', key=new_key))
    return redirect(url_for('home', error="⚠️ Lỗi lưu key. Vui lòng thử lại!"))

@app.route('/quan-ly-bi-mat-dunghoet', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else: error = "Tài khoản hoặc mật khẩu không chính xác!"
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập Quản Trị</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 15px; overflow-x: hidden; }
        .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 30px 20px; border-radius: 24px; width: 100%; max-width: 380px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
        h2 { color: #fff; margin-bottom: 20px; font-size: 20px; font-weight: 700; }
        input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #334155; background: #0b0f19; color: #fff; margin-bottom: 12px; font-size: 14px; text-align: center; }
        .btn { width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; border: none; padding: 12px; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 14px; }
        .error { color: #f87171; font-size: 12px; margin-bottom: 12px; }
        .back { display: inline-block; margin-top: 15px; color: #64748b; font-size: 12px; text-decoration: none; }
    </style></head>
    <body><div class="card">
        <h2><i class="fa-solid fa-lock"></i> Đăng Nhập Hệ Thống</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Nhập tài khoản..." required autocomplete="off">
            <input type="password" name="password" placeholder="Nhập mật khẩu..." required>
            <button type="submit" class="btn">Đăng Nhập</button>
        </form>
        <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i> Về trang chủ</a>
    </div></body></html>
    """
    return render_template_string(html, error=error)

@app.route('/quan-ly-bi-mat-dunghoet/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    keys_db = db.get("keys", {})
    banned_users = db.get("banned_users", {})
    maint = db.get("maintenance", {"active": False, "notice": ""})
    now = time.time()
    
    total_keys_count = len(keys_db)
    used_keys_count = sum(1 for k, info in keys_db.items() if len(info.get('used_by', [])) > 0)
    unused_keys_count = total_keys_count - used_keys_count

    users_list = {}
    for k, info in keys_db.items():
        for uid in info.get("used_by", []):
            ban_info = banned_users.get(uid)
            is_banned = False
            ban_until = 0
            if ban_info:
                if ban_info.get("type") == "perm": is_banned = True
                elif ban_info.get("type") == "temp" and ban_info.get("until", 0) > now:
                    is_banned = True
                    ban_until = ban_info.get("until", 0)

            if uid not in users_list:
                users_list[uid] = {
                    "chat_id": uid,
                    "keys_used": [k],
                    "total_bets": info.get("total_bets_count", 0),
                    "is_vip": info.get("is_vip", False),
                    "expire_at": info.get("expire_at", 0),
                    "is_banned": is_banned,
                    "ban_type": ban_info.get("type") if ban_info else None,
                    "ban_until": ban_until
                }
            else:
                users_list[uid]["keys_used"].append(k)
                users_list[uid]["total_bets"] += info.get("total_bets_count", 0)
                if info.get("is_vip"): users_list[uid]["is_vip"] = True
                if info.get("expire_at", 0) > users_list[uid]["expire_at"]:
                    users_list[uid]["expire_at"] = info.get("expire_at", 0)

    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Quản Lý Hệ Thống VIP</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: #0f172a; color: #f8fafc; padding: 10px; overflow-x: hidden; }
        .container { max-width: 1100px; margin: 0 auto; background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 15px; border-radius: 16px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); width: 100%; word-break: break-word; }
        .header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 12px; gap: 8px; flex-wrap: nowrap; }
        .menu-toggle { font-size: 13px; font-weight: 600; color: #38bdf8; cursor: pointer; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); padding: 6px 10px; border-radius: 8px; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; transition: 0.2s; }
        .menu-toggle:hover { background: rgba(56, 189, 248, 0.2); }
        h2 { color: #f8fafc; font-size: 14px; font-weight: 700; white-space: nowrap; letter-spacing: 0.5px; display: flex; align-items: center; gap: 6px; }
        h2 i { color: #38bdf8; }
        .logout { color: #f87171; text-decoration: none; font-size: 11px; font-weight: 600; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); padding: 6px 10px; border-radius: 8px; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; transition: 0.2s; }
        .logout:hover { background: rgba(239, 68, 68, 0.2); }
        .sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 999; display: none; }
        .sidebar { position: fixed; top: 0; left: -260px; width: 250px; height: 100%; background: #1e293b; z-index: 1000; padding: 20px 15px; transition: 0.3s ease; border-right: 1px solid #334155; }
        .sidebar.active { left: 0; }
        .sidebar h3 { color: #818cf8; font-size: 15px; margin-bottom: 20px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
        .sidebar-menu { display: flex; flex-direction: column; gap: 10px; }
        .sidebar-btn { background: #0b0f19; color: #94a3b8; border: 1px solid #334155; padding: 12px; border-radius: 10px; text-align: left; cursor: pointer; font-weight: 600; font-size: 13px; display: flex; align-items: center; gap: 10px; width: 100%; }
        .sidebar-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }
        .tab-content { display: none; width: 100%; }
        .tab-content.active { display: block; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 15px; width: 100%; }
        .stat-card { background: #0b0f19; border: 1px solid #334155; padding: 12px; border-radius: 12px; text-align: center; }
        .stat-card h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 600; }
        .stat-card span { font-size: 18px; font-weight: 800; color: #38bdf8; }
        .table-responsive { width: 100%; overflow-x: auto; max-width: 100%; border-radius: 10px; border: 1px solid #334155; }
        table { width: 100%; border-collapse: collapse; font-size: 11px; min-width: 650px; }
        th, td { padding: 8px 10px; border-bottom: 1px solid #334155; text-align: left; vertical-align: middle; white-space: nowrap; }
        th { color: #94a3b8; font-weight: 600; background: #0b0f19; }
        code { background: #0b0f19; padding: 3px 6px; border-radius: 6px; color: #4ade80; font-family: monospace; font-size: 11px; }
        .btn-action { border: none; padding: 5px 8px; border-radius: 6px; cursor: pointer; font-size: 10px; font-weight: 600; display: inline-flex; align-items: center; gap: 3px; text-decoration: none; }
        .btn-add-time { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
        .btn-sub-time { background: rgba(239, 68, 68, 0.2); color: #f87171; }
        .btn-del { background: rgba(239, 68, 68, 0.15); color: #f87171; }
        .btn-del-all { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 11px; text-decoration: none; display: inline-block; }
        .btn-copy-code { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
        .btn-add { background: #22c55e; color: #fff; border: none; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 11px; }
        .btn-vip { background: #eab308; color: #000; border: none; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 11px; }
        .box-create { background: #0b0f19; padding: 12px; border-radius: 12px; margin-bottom: 15px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; border: 1px solid #334155; width: 100%; }
        .box-create input { padding: 6px 10px; border-radius: 6px; border: 1px solid #475569; background: #1e293b; color: #fff; font-size: 12px; }
        .input-time { padding: 4px; border-radius: 4px; border: 1px solid #475569; background: #1e293b; color: #fff; width: 50px; text-align: center; font-size: 11px; }
        .toast { position: fixed; bottom: 20px; right: 20px; background: #22c55e; color: white; padding: 8px 14px; border-radius: 8px; font-weight: 600; display: none; box-shadow: 0 10px 25px rgba(0,0,0,0.5); z-index: 1000; font-size: 12px; }
    </style></head>
    <body>
    
    <div class="sidebar-overlay" id="overlay" onclick="toggleSidebar()"></div>
    <div class="sidebar" id="sidebar">
        <h3><i class="fa-solid fa-bars"></i> DANH MỤC TRANG</h3>
        <div class="sidebar-menu">
            <button class="sidebar-btn active" id="btn-tab-keys" onclick="switchTab('tab-keys')"><i class="fa-solid fa-key"></i> 1. Quản Lý Key & VIP</button>
            <button class="sidebar-btn" id="btn-tab-users" onclick="switchTab('tab-users')"><i class="fa-solid fa-users-gear"></i> 2. Quản Lý Người Dùng</button>
            <button class="sidebar-btn" id="btn-tab-system" onclick="switchTab('tab-system')"><i class="fa-solid fa-tower-broadcast"></i> 3. Hệ Thống & Bảo Trì</button>
        </div>
    </div>

    <div class="toast" id="toastMsg">✅ Thành công!</div>
    <div class="container">
        <div class="header-flex">
            <div class="menu-toggle" onclick="toggleSidebar()"><i class="fa-solid fa-bars"></i> Menu</div>
            <h2><i class="fa-solid fa-shield-halved"></i> QUẢN TRỊ SYSTEM</h2>
            <a href="/quan-ly-bi-mat-dunghoet/logout" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Thoát</a>
        </div>

        <div id="tab-keys" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card"><h4>Tổng số Key</h4><span>{{ total_keys_count }}</span></div>
                <div class="stat-card"><h4>Đã kích hoạt</h4><span style="color: #f87171;">{{ used_keys_count }}</span></div>
                <div class="stat-card"><h4>Chưa kích hoạt</h4><span style="color: #4ade80;">{{ unused_keys_count }}</span></div>
            </div>

            <div class="box-create">
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <label style="font-size: 10px; font-weight: 600; color: #94a3b8;">Thời hạn (H):</label>
                    <input type="number" id="customHours" value="24" min="1" style="width: 70px; text-align: center;">
                </div>
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <label style="font-size: 10px; font-weight: 600; color: #94a3b8;">Số lượng:</label>
                    <input type="number" id="customQty" value="1" min="1" max="100" style="width: 70px; text-align: center;">
                </div>
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <label style="font-size: 10px; font-weight: 600; color: #94a3b8;">Lượt dùng:</label>
                    <input type="number" id="maxUses" value="1" min="1" max="1000" style="width: 70px; text-align: center;">
                </div>
                <div style="display: flex; gap: 6px; margin-top: 12px; flex-wrap: wrap;">
                    <button class="btn-add" onclick="createCustomKey(false)"><i class="fa-solid fa-plus"></i> Key Thường</button>
                    <button class="btn-vip" onclick="createCustomKey(true)"><i class="fa-solid fa-crown"></i> Code VIP</button>
                    <a href="/quan-ly-bi-mat-dunghoet/delete_all" class="btn-del-all" onclick="return confirm('Cảnh báo: Xóa sạch toàn bộ kho key?')"><i class="fa-solid fa-trash-can"></i> Xóa Sạch</a>
                </div>
            </div>

            <div class="table-responsive">
                <table>
                    <tr>
                        <th>Mã Key / VIP</th>
                        <th>Loại</th>
                        <th>Cộng/Trừ H</th>
                        <th>Thời Gian Còn</th>
                        <th>Số Người/Ván</th>
                        <th>Thao Tác</th>
                    </tr>
                    {% for k, info in keys.items() %}
                    {% set expire_at = info.get('expire_at', 0) %}
                    {% set remain = (expire_at - now) if expire_at and expire_at > now else 0 %}
                    {% set rem_h = (remain // 3600)|int %}
                    {% set rem_m = ((remain % 3600) // 60)|int %}
                    {% set used_list = info.get('used_by', []) %}
                    {% set max_u = info.get('max_uses', 1) %}
                    {% set tot_bets = info.get('total_bets_count', 0) %}
                    <tr>
                        <td><code>{{ k }}</code></td>
                        <td>{% if info.get('is_vip') %}<b style="color:#eab308">VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                        <td>
                            <div style="display: flex; gap: 2px; align-items: center;">
                                <input type="number" id="time_{{ k }}" value="24" class="input-time">
                                <button class="btn-action btn-add-time" onclick="modifyKeyTime('{{ k }}', 'add')">+</button>
                                <button class="btn-action btn-sub-time" onclick="modifyKeyTime('{{ k }}', 'sub')">-</button>
                            </div>
                        </td>
                        <td>
                            {% if expire_at and expire_at > now %}
                                <b style="color: #38bdf8;">{{ rem_h }}h {{ rem_m }}p</b>
                            {% else %}
                                <small style="color: #f87171;">Chưa dùng/Hết hạn</small>
                            {% endif %}
                        </td>
                        <td><span>{{ used_list|length }}/{{ max_u }} người</span> | <b>{{ tot_bets }} ván</b></td>
                        <td>
                            <div style="display: flex; gap: 3px;">
                                <button class="btn-action btn-copy-code" onclick="copyThisKey('{{ k }}')">Copy</button>
                                <a href="/quan-ly-bi-mat-dunghoet/delete?key={{ k }}" class="btn-action btn-del" onclick="return confirm('Xóa key này?')">Xóa</a>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <div id="tab-users" class="tab-content">
            <div class="table-responsive">
                <table>
                    <tr>
                        <th>User ID</th>
                        <th>Cấp Độ</th>
                        <th>Tổng Ván</th>
                        <th>Trạng Thái</th>
                        <th>Thao Tác</th>
                    </tr>
                    {% for uid, uinfo in users.items() %}
                    <tr>
                        <td><code>{{ uid }}</code></td>
                        <td>{% if uinfo.is_vip %}<b style="color:#eab308">VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                        <td><b>{{ uinfo.total_bets }} ván</b></td>
                        <td>
                            {% if uinfo.is_banned %}
                                <b style="color: #ef4444;">Đang Bị Khóa</b>
                            {% else %}
                                <b style="color: #22c55e;">Bình thường</b>
                            {% endif %}
                        </td>
                        <td>
                            {% if uinfo.is_banned %}
                                <button class="btn-action btn-add-time" onclick="banUserAction('{{ uid }}', 'unban')">Mở Khóa</button>
                            {% else %}
                                <button class="btn-action btn-del" onclick="banUserAction('{{ uid }}', 'perm')">Khóa VV</button>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <div id="tab-system" class="tab-content">
            <div style="background: #0b0f19; padding: 15px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 15px;">
                <h3 style="font-size: 13px; color: #f87171; margin-bottom: 10px;"><i class="fa-solid fa-triangle-exclamation"></i> Chế Độ Bảo Trì</h3>
                <textarea id="maintNotice" rows="3" style="width: 100%; background: #1e293b; color: #fff; border: 1px solid #475569; border-radius: 6px; padding: 8px; font-size: 12px; margin-bottom: 8px;">{{ maint.notice or "⚠️ Hệ thống đang bảo trì định kỳ!" }}</textarea>
                <button class="btn-add" onclick="updateMaintenance(true)">Bật Bảo Trì</button>
                <button class="btn-vip" onclick="updateMaintenance(false)">Tắt Bảo Trì</button>
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
    function showToast(msg) {
        const t = document.getElementById("toastMsg");
        t.innerText = msg; t.style.display = "block";
        setTimeout(() => { t.style.display = "none"; }, 2500);
    }
    function switchTab(tabId) {
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        document.getElementById("btn-" + tabId).classList.add('active');
        toggleSidebar();
    }
    function copyThisKey(code) {
        navigator.clipboard.writeText(code).then(() => { showToast("✅ Đã sao chép!"); });
    }
    function createCustomKey(isVip) {
        let hours = document.getElementById("customHours").value;
        let qty = document.getElementById("customQty").value;
        let maxUses = document.getElementById("maxUses").value;
        fetch("/quan-ly-bi-mat-dunghoet/create_custom_key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hours: hours, quantity: qty, max_uses: maxUses, is_vip: isVip })
        }).then(res => res.json()).then(data => { if(data.success) { location.reload(); } else { alert("Lỗi: " + data.msg); } });
    }
    function modifyKeyTime(key, mode) {
        let hours = document.getElementById("time_" + key).value;
        fetch("/quan-ly-bi-mat-dunghoet/modify_key_time", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: key, hours: hours, mode: mode })
        }).then(res => res.json()).then(data => {
            if(data.success) { showToast("✅ Đã cập nhật giờ!"); setTimeout(() => { location.reload(); }, 800); } else { alert("Lỗi: " + data.msg); }
        });
    }
    function banUserAction(uid, banType) {
        fetch("/quan-ly-bi-mat-dunghoet/ban_user_advanced", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: uid, ban_type: banType, minutes: 0 })
        }).then(res => res.json()).then(data => { if(data.success) { showToast("✅ Đã cập nhật!"); setTimeout(() => { location.reload(); }, 800); } });
    }
    function updateMaintenance(active) {
        let notice = document.getElementById("maintNotice").value;
        fetch("/quan-ly-bi-mat-dunghoet/update_maintenance", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active: active, notice: notice })
        }).then(res => res.json()).then(data => { if(data.success) { showToast("✅ Đã cập nhật bảo trì!"); setTimeout(() => { location.reload(); }, 1000); } });
    }
    </script>
    </body></html>
    """
    return render_template_string(html, keys=keys_db, users=users_list, maint=maint, now=now, total_keys_count=total_keys_count, used_keys_count=used_keys_count, unused_keys_count=unused_keys_count)

@app.route('/quan-ly-bi-mat-dunghoet/create_custom_key', methods=['POST'])
def admin_create_custom_key():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        hours = float(req_data.get("hours", 24))
        quantity = int(req_data.get("quantity", 1))
        max_uses = int(req_data.get("max_uses", 1))
        is_vip = bool(req_data.get("is_vip", False))
        prefix = "VIP-" if is_vip else "ADMIN-"
        
        db = load_system_db()
        if "keys" not in db: db["keys"] = {}
        for _ in range(quantity):
            new_key = prefix + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
            db["keys"][new_key] = {"status": "chua_dung", "used_by": [], "created_at": time.time(), "expire_at": None, "duration_hours": hours, "is_vip": is_vip, "max_uses": max_uses, "total_bets_count": 0}
            
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/quan-ly-bi-mat-dunghoet/modify_key_time', methods=['POST'])
def admin_modify_key_time():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        key_code = req_data.get("key")
        hours = float(req_data.get("hours", 0))
        mode = req_data.get("mode", "add")
        db = load_system_db()
        if key_code not in db["keys"]: return jsonify({"success": False, "msg": "Key không tồn tại!"})
        k_data = db["keys"][key_code]
        now = time.time()
        current_expire = k_data.get("expire_at") or now
        if current_expire < now: current_expire = now
        seconds_change = hours * 3600
        if mode == "add":
            new_expire = current_expire + seconds_change
            k_data["duration_hours"] = k_data.get("duration_hours", 24) + hours
        else:
            new_expire = current_expire - seconds_change
            k_data["duration_hours"] = max(0, k_data.get("duration_hours", 24) - hours)
        k_data["expire_at"] = new_expire
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/quan-ly-bi-mat-dunghoet/ban_user_advanced', methods=['POST'])
def admin_ban_user_advanced():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        uid = str(req_data.get("user_id"))
        ban_type = req_data.get("ban_type")
        db = load_system_db()
        if "banned_users" not in db or isinstance(db["banned_users"], list): db["banned_users"] = {}
            
        if ban_type == "unban":
            if uid in db["banned_users"]: del db["banned_users"][uid]
        elif ban_type == "perm":
            db["banned_users"][uid] = {"type": "perm", "until": 0}
            
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/quan-ly-bi-mat-dunghoet/update_maintenance', methods=['POST'])
def admin_update_maintenance():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        db = load_system_db()
        db["maintenance"] = {"active": bool(req_data.get("active")), "notice": req_data.get("notice", "")}
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/quan-ly-bi-mat-dunghoet/delete')
def admin_delete():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    k = request.args.get('key')
    if k: delete_key_from_cloud(k)
    return redirect(url_for('admin_dashboard'))

@app.route('/quan-ly-bi-mat-dunghoet/delete_all')
def admin_delete_all():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    db["keys"] = {}
    save_system_db(db)
    return redirect(url_for('admin_dashboard'))

@app.route('/quan-ly-bi-mat-dunghoet/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))

# ---------------------------------------------------------
# KHỞI CHẠY HỆ THỐNG WEB
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
