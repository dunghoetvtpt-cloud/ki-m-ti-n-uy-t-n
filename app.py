import os
import json
import time
import random
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
import telebot
from telebot import types

import session_manager

# ---------------------------------------------------------
# CẤU HÌNH BOT TELEGRAM & FLASK WEB
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)
app.secret_key = "dung_license_secret_key_1612012"

ADMIN_PASSWORD = "dung1612012"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

ip_request_history = {}

# ---------------------------------------------------------
# 🗄️ KẾT NỐI JSONBIN.IO
# ---------------------------------------------------------
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID", "")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY", "")

def load_system_db():
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY: 
        return {"keys": {}, "banned_users": [], "maintenance": {"active": False, "notice": ""}}
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            record = res.json().get("record", {})
            if "keys" not in record: record["keys"] = {}
            if "banned_users" not in record: record["banned_users"] = []
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
    except Exception as e:
        pass
    return {"keys": {}, "banned_users": [], "maintenance": {"active": False, "notice": ""}}

def save_system_db(db):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY: return
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {"Content-Type": "application/json", "X-Master-Key": JSONBIN_API_KEY}
        requests.put(url, json=db, headers=headers, timeout=5)
    except: pass

def load_keys():
    return load_system_db().get("keys", {})

def save_key_to_cloud(key_code, data):
    db = load_system_db()
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
    save_system_db(db)

def delete_key_from_cloud(key_code):
    db = load_system_db()
    if key_code in db["keys"]:
        del db["keys"][key_code]
        save_system_db(db)

# ---------------------------------------------------------
# FLASK WEB ROUTES (GIAO DIỆN LẤY KEY & ADMIN 3 TAB)
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
            body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
            .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); border-radius: 30px; width: 100%; max-width: 440px; padding: 40px 25px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }
            .icon-box { width: 70px; height: 70px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 20px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 20px; box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.5); color: #fff; }
            .badge { display: inline-block; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 6px 16px; border-radius: 30px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; }
            h2 { font-size: 26px; font-weight: 800; color: #fff; margin-bottom: 10px; }
            p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 30px; }
            .btn { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; text-decoration: none; padding: 16px; border-radius: 16px; font-weight: 700; font-size: 15px; box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.5); transition: all 0.3s ease; border: none; cursor: pointer; }
            .key-container { background: #0b0f19; border: 2px dashed #6366f1; padding: 18px; border-radius: 18px; margin-top: 15px; }
            .key-text { font-family: monospace; font-size: 18px; color: #4ade80; font-weight: 700; word-break: break-all; margin-bottom: 12px; }
            .btn-copy { background: #22c55e; color: #fff; border: none; padding: 10px 20px; border-radius: 10px; font-weight: 700; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
            .btn-admin { display: inline-block; margin-top: 25px; color: #64748b; text-decoration: none; font-size: 13px; font-weight: 600; }
            .error { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 12px; border-radius: 12px; font-size: 13px; margin-top: 15px; font-weight: 500; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-box"><i class="fa-solid fa-bolt"></i></div>
            <span class="badge">Hệ Thống Tự Động 24/7</span>
            <h2>XWORLD GATEWAY</h2>
            <p>Vượt link an toàn và nhanh chóng để nhận mã bản quyền chính thức sử dụng trong 24 giờ.</p>
            {% if new_key %}
                <div class="key-container">
                    <div class="key-text" id="keyText">{{ new_key }}</div>
                    <button class="btn-copy" onclick="copyKey()"><i class="fa-regular fa-copy"></i> Sao Chép Key Ngay</button>
                </div>
                <p style="color: #4ade80; margin-top: 15px; font-weight: 600; font-size: 13px;">✨ Đã tạo key thành công! Dán vào Bot Telegram nhé.</p>
            {% else %}
                <a href="/get_link4m" class="btn"><i class="fa-solid fa-rocket"></i> TIẾN HÀNH LẤY KEY (24H)</a>
            {% endif %}
            {% if error %} <div class="error">{{ error }}</div> {% endif %}
            <a href="/admin" class="btn-admin"><i class="fa-solid fa-user-shield"></i> Đăng nhập Quản trị viên</a>
        </div>
        <script>
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
        return redirect(url_for('home', error="⚠️ Phát hiện spam! IP của bạn thao tác quá nhanh, vui lòng thử lại sau 1 phút."))
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
    save_key_to_cloud(new_key, key_data)
    return redirect(url_for('home', key=new_key))

@app.route('/api/verify_key')
def api_verify_key():
    key_code = request.args.get('key', '').strip()
    user_id = str(request.args.get('user_id', '')).strip()
    res = verify_key_with_server(key_code, user_id)
    return res

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else: error = "Mật khẩu bảo mật không chính xác!"
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập Quản Trị</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
        .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 40px 25px; border-radius: 30px; width: 100%; max-width: 400px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
        h2 { color: #fff; margin-bottom: 25px; font-size: 22px; font-weight: 700; }
        input { width: 100%; padding: 15px; border-radius: 14px; border: 1px solid #334155; background: #0b0f19; color: #fff; margin-bottom: 20px; font-size: 15px; text-align: center; }
        .btn { width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; border: none; padding: 15px; border-radius: 14px; font-weight: 700; cursor: pointer; font-size: 15px; }
        .error { color: #f87171; font-size: 13px; margin-bottom: 15px; }
        .back { display: inline-block; margin-top: 20px; color: #64748b; font-size: 13px; text-decoration: none; }
    </style></head>
    <body><div class="card">
        <h2><i class="fa-solid fa-lock"></i> Quản Trị Hệ Thống</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST"><input type="password" name="password" placeholder="Nhập mật khẩu admin..." required><button type="submit" class="btn">Đăng Nhập</button></form>
        <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i> Quay lại trang chủ</a>
    </div></body></html>
    """
    return render_template_string(html, error=error)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    keys_db = db.get("keys", {})
    banned_users = db.get("banned_users", [])
    maint = db.get("maintenance", {"active": False, "notice": ""})
    now = time.time()
    
    total_keys_count = len(keys_db)
    used_keys_count = sum(1 for k, info in keys_db.items() if len(info.get('used_by', [])) > 0)
    unused_keys_count = total_keys_count - used_keys_count

    # Tổng hợp danh sách người dùng toàn diện
    users_list = {}
    for k, info in keys_db.items():
        for uid in info.get("used_by", []):
            if uid not in users_list:
                users_list[uid] = {
                    "chat_id": uid,
                    "keys_used": [k],
                    "total_bets": info.get("total_bets_count", 0),
                    "is_vip": info.get("is_vip", False),
                    "expire_at": info.get("expire_at", 0),
                    "is_banned": uid in banned_users
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
        body { background: #0f172a; color: #f8fafc; padding: 20px 10px; }
        .container { max-width: 1100px; margin: 0 auto; background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 20px; border-radius: 20px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
        .header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 12px; }
        h2 { color: #38bdf8; font-size: 18px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
        .logout { color: #f87171; text-decoration: none; font-size: 12px; font-weight: 600; background: rgba(239, 68, 68, 0.1); padding: 6px 12px; border-radius: 8px; }
        
        /* THANH ĐIỀU HƯỚNG TAB GIAO DIỆN */
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #334155; padding-bottom: 8px; }
        .tab-btn { background: #1e293b; color: #94a3b8; border: none; padding: 10px 18px; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 13px; transition: 0.2s; display: flex; align-items: center; gap: 8px; }
        .tab-btn.active { background: #6366f1; color: #fff; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
        .stat-card { background: #0b0f19; border: 1px solid #334155; padding: 15px; border-radius: 14px; text-align: center; }
        .stat-card h4 { font-size: 12px; color: #94a3b8; margin-bottom: 8px; font-weight: 600; }
        .stat-card span { font-size: 20px; font-weight: 800; color: #38bdf8; }
        
        .table-responsive { width: 100%; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; min-width: 800px; }
        th, td { padding: 10px; border-bottom: 1px solid #334155; text-align: left; vertical-align: middle; }
        th { color: #94a3b8; font-weight: 600; }
        code { background: #0b0f19; padding: 4px 6px; border-radius: 6px; color: #4ade80; font-family: monospace; font-size: 11px; }
        
        .btn-action { border: none; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px; text-decoration: none; }
        .btn-add-time { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
        .btn-sub-time { background: rgba(239, 68, 68, 0.2); color: #f87171; }
        .btn-del { background: rgba(239, 68, 68, 0.15); color: #f87171; }
        .btn-del-all { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 8px 14px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; text-decoration: none; }
        .btn-copy-code { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
        .btn-add { background: #22c55e; color: #fff; border: none; padding: 10px 16px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; }
        .btn-vip { background: #eab308; color: #000; border: none; padding: 10px 16px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; }
        .btn-ban { background: #ef4444; color: #fff; }
        .btn-unban { background: #3b82f6; color: #fff; }

        .box-create { background: #0b0f19; padding: 15px; border-radius: 14px; margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; border: 1px solid #334155; }
        .box-create input, .box-create textarea { padding: 8px 12px; border-radius: 8px; border: 1px solid #475569; background: #1e293b; color: #fff; font-size: 13px; }
        .input-time { padding: 6px; border-radius: 6px; border: 1px solid #475569; background: #1e293b; color: #fff; width: 70px; text-align: center; font-size: 12px; }
        .toast { position: fixed; bottom: 20px; right: 20px; background: #22c55e; color: white; padding: 10px 16px; border-radius: 8px; font-weight: 600; display: none; box-shadow: 0 10px 25px rgba(0,0,0,0.5); z-index: 1000; font-size: 13px; }
        
        /* CÔNG TẮC BẢO TRÌ SWITCH */
        .switch { position: relative; display: inline-block; width: 50px; height: 26px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .3s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: #ef4444; }
        input:checked + .slider:before { transform: translateX(24px); }
    </style></head>
    <body>
    <div class="toast" id="toastMsg">✅ Thành công!</div>
    <div class="container">
        <div class="header-flex">
            <h2><i class="fa-solid fa-sliders"></i> QUẢN TRỊ BẢO MẬT & HỆ THỐNG</h2>
            <a href="/admin/logout" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Đăng xuất</a>
        </div>
        
        <!-- THANH CHUYỂN TAB -->
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('tab-keys')"><i class="fa-solid fa-key"></i> 1. Quản Lý Key & VIP</button>
            <button class="tab-btn" onclick="switchTab('tab-users')"><i class="fa-solid fa-users-gear"></i> 2. Quản Lý Người Dùng</button>
            <button class="tab-btn" onclick="switchTab('tab-system')"><i class="fa-solid fa-tower-broadcast"></i> 3. Hệ Thống & Bảo Trì</button>
        </div>

        <!-- TAB 1: QUẢN LÝ KEY -->
        <div id="tab-keys" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card">
                    <h4><i class="fa-solid fa-chart-pie" style="color: #818cf8;"></i> Tổng số Key</h4>
                    <span>{{ total_keys_count }}</span>
                </div>
                <div class="stat-card">
                    <h4><i class="fa-solid fa-user-check" style="color: #f87171;"></i> Đã kích hoạt</h4>
                    <span style="color: #f87171;">{{ used_keys_count }}</span>
                </div>
                <div class="stat-card">
                    <h4><i class="fa-solid fa-circle-check" style="color: #4ade80;"></i> Chưa kích hoạt</h4>
                    <span style="color: #4ade80;">{{ unused_keys_count }}</span>
                </div>
            </div>

            <div class="box-create">
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size: 11px; font-weight: 600; color: #94a3b8;">Thời hạn (Giờ):</label>
                    <input type="number" id="customHours" value="24" min="1" style="width: 85px; text-align: center;">
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size: 11px; font-weight: 600; color: #94a3b8;">Số lượng:</label>
                    <input type="number" id="customQty" value="1" min="1" max="100" style="width: 85px; text-align: center;">
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size: 11px; font-weight: 600; color: #94a3b8;">Số người nhập:</label>
                    <input type="number" id="maxUses" value="1" min="1" max="1000" style="width: 85px; text-align: center;">
                </div>
                <div style="display: flex; gap: 8px; margin-top: 16px;">
                    <button class="btn-add" onclick="createCustomKey(false)"><i class="fa-solid fa-plus"></i> Tạo Key Thường</button>
                    <button class="btn-vip" onclick="createCustomKey(true)"><i class="fa-solid fa-crown"></i> Tạo Code VIP</button>
                    <a href="/admin/delete_all" class="btn-del-all" onclick="return confirm('Cảnh báo: Xóa sạch toàn bộ kho key?')" style="margin-left: 10px;"><i class="fa-solid fa-trash-can"></i> Xóa Sạch Kho Key</a>
                </div>
            </div>

            <div class="table-responsive">
                <table>
                    <tr>
                        <th>Mã Key / VIP</th>
                        <th>Loại</th>
                        <th>Cộng / Trừ Giờ</th>
                        <th>Thời Gian Còn Lại</th>
                        <th>Số Người / Lượt Cược</th>
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
                        <td>{% if info.get('is_vip') %}<b style="color:#eab308"><i class="fa-solid fa-crown"></i> VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                        <td>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <input type="number" id="time_{{ k }}" value="24" class="input-time">
                                <button class="btn-action btn-add-time" onclick="modifyKeyTime('{{ k }}', 'add')" title="Cộng thêm giờ"><i class="fa-solid fa-plus"></i> Cộng</button>
                                <button class="btn-action btn-sub-time" onclick="modifyKeyTime('{{ k }}', 'sub')" title="Trừ bớt giờ"><i class="fa-solid fa-minus"></i> Trừ</button>
                            </div>
                        </td>
                        <td>
                            {% if expire_at and expire_at > now %}
                                <b style="color: #38bdf8;"><i class="fa-regular fa-clock"></i> {{ rem_h }}h {{ rem_m }}p còn lại</b>
                            {% else %}
                                <small style="color: #f87171;"><i class="fa-solid fa-triangle-exclamation"></i> Chưa dùng / Hết hạn</small>
                            {% endif %}
                        </td>
                        <td>
                            <span style="color: #94a3b8;"><i class="fa-solid fa-users"></i> {{ used_list|length }}/{{ max_u }} người</span> | 
                            <b style="color: #38bdf8;"><i class="fa-solid fa-gamepad"></i> {{ tot_bets }} ván</b>
                        </td>
                        <td>
                            <div style="display: flex; gap: 4px;">
                                <button class="btn-action btn-copy-code" onclick="copyThisKey('{{ k }}')"><i class="fa-regular fa-copy"></i> Coppy</button>
                                <a href="/admin/delete?key={{ k }}" class="btn-action btn-del" onclick="return confirm('Xóa key này?')"><i class="fa-solid fa-trash"></i> Xóa</a>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <!-- TAB 2: QUẢN LÝ NGƯỜI DÙNG -->
        <div id="tab-users" class="tab-content">
            <h3 style="font-size: 15px; color: #38bdf8; margin-bottom: 12px;"><i class="fa-solid fa-users"></i> Danh Sách Người Dùng Đã Kích Hoạt</h3>
            <div class="table-responsive">
                <table>
                    <tr>
                        <th>Telegram Chat ID</th>
                        <th>Cấp Độ</th>
                        <th>Tổng Ván Cược</th>
                        <th>Thời Hạn Còn Lại</th>
                        <th>Trạng Thái Khóa</th>
                        <th>Thao Tác Khóa</th>
                    </tr>
                    {% for uid, uinfo in users.items() %}
                    {% set rem_u = (uinfo.expire_at - now) if uinfo.expire_at > now else 0 %}
                    {% set rem_uh = (rem_u // 3600)|int %}
                    {% set rem_um = ((rem_u % 3600) // 60)|int %}
                    <tr>
                        <td><code>{{ uid }}</code></td>
                        <td>{% if uinfo.is_vip %}<b style="color:#eab308"><i class="fa-solid fa-crown"></i> VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                        <td><b style="color: #38bdf8;"><i class="fa-solid fa-gamepad"></i> {{ uinfo.total_bets }} ván</b></td>
                        <td>
                            {% if uinfo.expire_at > now %}
                                <span style="color: #4ade80;">⏳ Còn {{ rem_uh }}h {{ rem_um }}p</span>
                            {% else %}
                                <span style="color: #f87171;">⚠️ Hết hạn</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if uinfo.is_banned %}
                                <b style="color: #ef4444;">🚫 Bị Khóa (Banned)</b>
                            {% else %}
                                <b style="color: #22c55e;">🟢 Hoạt động</b>
                            {% endif %}
                        </td>
                        <td>
                            {% if uinfo.is_banned %}
                                <button class="btn-action btn-unban" onclick="toggleBanUser('{{ uid }}', 'unban')"><i class="fa-solid fa-unlock"></i> Mở Khóa</button>
                            {% else %}
                                <button class="btn-action btn-ban" onclick="toggleBanUser('{{ uid }}', 'ban')"><i class="fa-solid fa-user-slash"></i> Khóa Lập Tức</button>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <!-- TAB 3: HỆ THỐNG & BẢO TRÌ -->
        <div id="tab-system" class="tab-content">
            <div style="background: #0b0f19; padding: 20px; border-radius: 16px; border: 1px solid #334155; margin-bottom: 20px;">
                <h3 style="font-size: 15px; color: #f87171; margin-bottom: 15px; display: flex; align-items: center; gap: 10px;">
                    <i class="fa-solid fa-triangle-exclamation"></i> Chế Độ Bảo Trì Bot Toàn Hệ Thống
                </h3>
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                    <label class="switch">
                        <input type="checkbox" id="maintSwitch" {% if maint.active %}checked{% endif %} onchange="updateMaintenance()">
                        <span class="slider"></span>
                    </label>
                    <span id="maintText" style="font-weight: 700; font-size: 14px;">
                        {% if maint.active %}<span style="color: #ef4444;">🔴 ĐANG BẬT BẢO TRÌ (Bot ngắt toàn bộ chức năng)</span>{% else %}<span style="color: #22c55e;">🟢 ĐANG HOẠT ĐỘNG BÌNH THƯỜNG</span>{% endif %}
                    </span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <label style="font-size: 12px; font-weight: 600; color: #94a3b8;">Nội dung thông báo bảo trì (khi bật công tắc, người dùng chỉ nhìn thấy dòng này):</label>
                    <textarea id="maintNotice" rows="3" style="width: 100%; background: #1e293b; color: #fff; border: 1px solid #475569; border-radius: 8px; padding: 10px; font-size: 13px;">{{ maint.notice or "⚠️ Hệ thống đang tiến hành nâng cấp & bảo trì định kỳ. Vui lòng quay lại sau ít phút!" }}</textarea>
                    <button class="btn-add" style="width: 180px; margin-top: 5px;" onclick="updateMaintenance()"><i class="fa-solid fa-floppy-disk"></i> Lưu Thông Báo</button>
                </div>
            </div>

            <div style="background: #0b0f19; padding: 20px; border-radius: 16px; border: 1px solid #334155;">
                <h3 style="font-size: 15px; color: #38bdf8; margin-bottom: 15px;"><i class="fa-solid fa-bullhorn"></i> Gửi Thông Báo Tức Thời Đến Tất Cả Người Dùng</h3>
                <p style="font-size: 12px; color: #94a3b8; margin-bottom: 10px;">💬 Thông báo sẽ được gửi thẳng đến máy người dùng và <b>TỰ ĐỘNG XÓA SAU 15 GIÂY</b> để đỡ rác ô chat!</p>
                <textarea id="broadcastMsg" rows="3" placeholder="Nhập nội dung thông báo gửi toàn bộ người dùng..." style="width: 100%; background: #1e293b; color: #fff; border: 1px solid #475569; border-radius: 8px; padding: 10px; font-size: 13px; margin-bottom: 10px;"></textarea>
                <button class="btn-vip" style="width: 200px;" onclick="sendBroadcast()"><i class="fa-solid fa-paper-plane"></i> Gửi Thông Báo Tức Thời</button>
            </div>
        </div>

    </div>

    <script>
    function showToast(msg) {
        const t = document.getElementById("toastMsg");
        t.innerText = msg;
        t.style.display = "block";
        setTimeout(() => { t.style.display = "none"; }, 2500);
    }

    function switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        event.currentTarget.classList.add('active');
        document.getElementById(tabId).classList.add('active');
    }

    function copyThisKey(code) {
        navigator.clipboard.writeText(code).then(() => { showToast("✅ Đã sao chép mã!"); });
    }

    function createCustomKey(isVip) {
        let hours = document.getElementById("customHours").value;
        let qty = document.getElementById("customQty").value;
        let maxUses = document.getElementById("maxUses").value;
        fetch("/admin/create_custom_key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hours: hours, quantity: qty, max_uses: maxUses, is_vip: isVip })
        })
        .then(res => res.json())
        .then(data => { if(data.success) { location.reload(); } else { alert("Lỗi: " + data.msg); } });
    }

    function modifyKeyTime(key, mode) {
        let hours = document.getElementById("time_" + key).value;
        fetch("/admin/modify_key_time", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: key, hours: hours, mode: mode })
        })
        .then(res => res.json())
        .then(data => {
            if(data.success) {
                showToast("✅ Đã " + (mode === 'add' ? 'cộng' : 'trừ') + " " + hours + " giờ thành công!");
                setTimeout(() => { location.reload(); }, 800);
            } else { alert("Lỗi: " + data.msg); }
        });
    }

    function toggleBanUser(uid, action) {
        fetch("/admin/ban_user", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: uid, action: action })
        })
        .then(res => res.json())
        .then(data => { if(data.success) { location.reload(); } });
    }

    function updateMaintenance() {
        let active = document.getElementById("maintSwitch").checked;
        let notice = document.getElementById("maintNotice").value;
        fetch("/admin/update_maintenance", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active: active, notice: notice })
        })
        .then(res => res.json())
        .then(data => { if(data.success) { showToast("✅ Cập nhật bảo trì thành công!"); setTimeout(() => { location.reload(); }, 1000); } });
    }

    function sendBroadcast() {
        let msg = document.getElementById("broadcastMsg").value;
        if(!msg) { alert("Vui lòng nhập nội dung!"); return; }
        fetch("/admin/broadcast", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg })
        })
        .then(res => res.json())
        .then(data => { if(data.success) { showToast("✅ Đã phát thông báo đến " + data.sent_count + " người dùng!"); document.getElementById("broadcastMsg").value = ""; } });
    }
    </script>
    </body></html>
    """
    return render_template_string(html, keys=keys_db, users=users_list, maint=maint, now=now, total_keys_count=total_keys_count, used_keys_count=used_keys_count, unused_keys_count=unused_keys_count)

@app.route('/admin/create_custom_key', methods=['POST'])
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
        
        for _ in range(quantity):
            new_key = prefix + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
            db["keys"][new_key] = {
                "status": "chua_dung", "used_by": [], "created_at": time.time(),
                "expire_at": None, "duration_hours": hours, "is_vip": is_vip,
                "max_uses": max_uses, "total_bets_count": 0
            }
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

# 🛠️ CỘNG HOẶC TRỪ GIỜ TRỰC TIẾP
@app.route('/admin/modify_key_time', methods=['POST'])
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

@app.route('/admin/ban_user', methods=['POST'])
def admin_ban_user():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        uid = str(req_data.get("user_id"))
        action = req_data.get("action")
        db = load_system_db()
        banned = set(db.get("banned_users", []))
        if action == "ban": banned.add(uid)
        else: banned.discard(uid)
        db["banned_users"] = list(banned)
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/admin/update_maintenance', methods=['POST'])
def admin_update_maintenance():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        req_data = request.json or {}
        db = load_system_db()
        db["maintenance"] = {"active": bool(req_data.get("active")), "notice": req_data.get("notice", "")}
        save_system_db(db)
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập!"})
    try:
        msg_text = request.json.get("message", "").strip()
        db = load_system_db()
        all_users = set()
        for k, info in db.get("keys", {}).items():
            for uid in info.get("used_by", []): all_users.add(str(uid))
            
        sent_count = 0
        def send_and_auto_delete(chat_id_target):
            try:
                sent = bot.send_message(chat_id_target, f"📢 **THÔNG BÁO TỪ HỆ THỐNG:**\n\n{msg_text}\n\n*(Tin nhắn tự xóa sau 15 giây)*", parse_mode="Markdown")
                time.sleep(15)
                bot.delete_message(chat_id_target, sent.message_id)
            except: pass

        for u in all_users:
            Thread(target=send_and_auto_delete, args=(u,), daemon=True).start()
            sent_count += 1
            
        return jsonify({"success": True, "sent_count": sent_count})
    except Exception as e: return jsonify({"success": False, "msg": str(e)})

@app.route('/admin/delete')
def admin_delete():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    k = request.args.get('key')
    if k: delete_key_from_cloud(k)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_all')
def admin_delete_all():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    db["keys"] = {}
    save_system_db(db)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))

user_data = {}
data_lock = Lock()

GAME_NAMES_VI = {"escape": "Vua Thoát Hiểm", "sprint": "Đua Tốc Độ"}

def get_user_config(chat_id):
    with data_lock:
        is_valid, expire_time = session_manager.check_session_valid(chat_id)
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None, "waiting_for_link": None, "waiting_for_bet": None,
                "waiting_for_key": False, "waiting_for_vip_code": False, "waiting_for_max_losses": None,
                "waiting_for_stop_loss": None, "waiting_for_take_profit": None, "waiting_for_max_rounds_vip": None,
                "is_vip": False, "vip_expire_at": 0, "has_valid_key": is_valid, "key_expire_at": expire_time, "prompt_msg_id": None, "menu_msg_id": None,
                "escape": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "base_bet": 1.0, "max_rounds": 100, "killer_stats": {i: 0 for i in range(1, 9)}, "selected_uids": [], "max_continuous_losses": 0, "stop_loss_amount": 0.0, "take_profit_amount": 0.0},
                "sprint": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "bet_amount_total": "1", "max_rounds": 100, "lose_limit": 3, "rest_rounds": 1, "selected_uids": [], "max_continuous_losses": 0, "stop_loss_amount": 0.0, "take_profit_amount": 0.0}
            }
        else:
            user_data[chat_id]["has_valid_key"] = is_valid
            user_data[chat_id]["key_expire_at"] = expire_time
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {"total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0, "streak_loss": 0, "random_stop": Event()}
    return account_threads[key]

def increment_key_bets_count(chat_id):
    try:
        db = load_system_db()
        chat_id_str = str(chat_id)
        for k, info in db.get("keys", {}).items():
            used_list = [str(x) for x in info.get("used_by", [])]
            if chat_id_str in used_list:
                info["total_bets_count"] = int(info.get("total_bets_count", 0)) + 1
                save_system_db(db)
                break
    except: pass

def verify_key_with_server(key_code, user_id):
    try:
        db = load_system_db()
        keys_db = db.get("keys", {})
        user_id_str = str(user_id)
        
        if key_code not in keys_db: return {"status": "error", "msg": "Mã hoặc Key không tồn tại!"}
            
        k_data = keys_db[key_code]
        duration_secs = int(k_data.get("duration_hours", 24) * 3600)
        is_vip = bool(k_data.get("is_vip", False))
        used_by_list = [str(x) for x in k_data.get("used_by", [])]
        max_uses = int(k_data.get("max_uses", 1))
        
        if user_id_str in used_by_list:
            expire_time = k_data.get("expire_at") or (time.time() + duration_secs)
            return {"status": "success", "msg": "Kích hoạt lại thành công!", "expire_at": expire_time, "is_vip": is_vip}
            
        if len(used_by_list) >= max_uses: return {"status": "error", "msg": "Mã này đã đạt giới hạn số người!"}
            
        used_by_list.append(user_id_str)
        k_data["used_by"] = used_by_list
        if len(used_by_list) >= max_uses: k_data["status"] = "da_dung"
        expire_time = time.time() + duration_secs
        k_data["expire_at"] = expire_time
        save_system_db(db)
        return {"status": "success", "msg": "Kích hoạt thành công!", "expire_at": expire_time, "is_vip": is_vip}
    except Exception as e: return {"status": "error", "msg": f"Lỗi: {str(e)}"}

def check_key_validity(chat_id):
    cfg = get_user_config(chat_id)
    db = load_system_db()
    
    # KHI HỆ THỐNG BẬT BẢO TRÌ HOẶC NGƯỜI DÙNG BỊ KHÓA (BAN)
    if str(chat_id) in db.get("banned_users", []):
        cfg["has_valid_key"] = False
        return False
        
    keys_db = db.get("keys", {})
    now = time.time()
    vip_valid = False; key_valid = False
    chat_id_str = str(chat_id)
    
    for k, info in keys_db.items():
        used_list = [str(x) for x in info.get("used_by", [])]
        if chat_id_str in used_list:
            expire_at = info.get("expire_at")
            if expire_at and now < expire_at:
                key_valid = True
                cfg["has_valid_key"] = True
                cfg["key_expire_at"] = expire_at
                if info.get("is_vip"):
                    vip_valid = True
                    cfg["is_vip"] = True
                    cfg["vip_expire_at"] = expire_at
                try: session_manager.save_session_to_file(chat_id, expire_at)
                except: pass
                break

    if not vip_valid and cfg.get("vip_expire_at", 0) > now: vip_valid = True
    if not vip_valid:
        cfg["is_vip"] = False; cfg["vip_expire_at"] = 0
        cfg["escape"]["max_rounds"] = 100; cfg["sprint"]["max_rounds"] = 100

    if key_valid or (cfg.get("has_valid_key") and now < cfg.get("key_expire_at", 0)): return True

    cfg["has_valid_key"] = False
    cfg["escape"]["global_running"] = False; cfg["sprint"]["global_running"] = False
    return False

def reset_user_wait_flags(cfg):
    cfg["waiting_for_link"] = None; cfg["waiting_for_bet"] = None
    cfg["waiting_for_max_losses"] = None; cfg["waiting_for_stop_loss"] = None
    cfg["waiting_for_take_profit"] = None; cfg["waiting_for_max_rounds_vip"] = None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    
    db = load_system_db()
    if db.get("maintenance", {}).get("active"):
        notice = db.get("maintenance", {}).get("notice", "⚠️ Hệ thống đang bảo trì!")
        bot.send_message(chat_id, f"🛠️ **THÔNG BÁO BẢO TRÌ** 🛠️\n━━━━━━━━━━━━━━━━━━━\n{notice}", parse_mode="Markdown")
        return

    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    if not check_key_validity(chat_id):
        cfg["waiting_for_key"] = True
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = "📜 **XWORLD LICENSE GATEWAY**\n───────────────────\n⚠️ **Key của bạn đã hết hạn hoặc chưa kích hoạt.**\n\n👉 Vui lòng chọn thao tác bên dưới:"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key (24h)", url=web_url),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
        )
        try:
            sent = bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
            cfg["prompt_msg_id"] = sent.message_id
        except: pass
        return
    show_main_menu(chat_id, message.message_id, is_new=True)

@bot.callback_query_handler(func=lambda call: call.data == "btn_nhap_key")
def callback_nhap_key_btn(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_key"] = True
    cfg["prompt_msg_id"] = call.message.message_id
    text = "🔑 **Vui lòng nhập mã Key của bạn vào đây**\n*(Ví dụ: `KEY-XW-XXXXXXXX` hoặc `ADMIN-XXXXXXXX`):*"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Quay lại", callback_data="btn_back_start"))
    try: bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

@bot.callback_query_handler(func=lambda call: call.data == "btn_back_start")
def callback_back_start(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_key"] = False
    web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
    msg_text = "📜 **XWORLD LICENSE GATEWAY**\n───────────────────\n⚠️ **Bạn cần có Key bản quyền để sử dụng bot.**\n\n👉 Vui lòng chọn thao tác bên dưới:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌐 Tới Trang Lấy Key (24h)", url=web_url),
        types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
    )
    try: bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

def show_main_menu(chat_id, message_id, is_new=False):
    db = load_system_db()
    if db.get("maintenance", {}).get("active"):
        notice = db.get("maintenance", {}).get("notice", "⚠️ Hệ thống đang bảo trì!")
        try: bot.edit_message_text(f"🛠️ **THÔNG BÁO BẢO TRÌ** 🛠️\n━━━━━━━━━━━━━━━━━━━\n{notice}", chat_id, message_id, parse_mode="Markdown")
        except: bot.send_message(chat_id, f"🛠️ **THÔNG BÁO BẢO TRÌ** 🛠️\n━━━━━━━━━━━━━━━━━━━\n{notice}", parse_mode="Markdown")
        return

    cfg = get_user_config(chat_id)
    check_key_validity(chat_id)
    reset_user_wait_flags(cfg)
    remaining_sec = int(cfg.get("key_expire_at", 0) - time.time())
    h = max(0, remaining_sec // 3600); m = max(0, (remaining_sec % 3600) // 60)
    vip_badge = " [VIP 👑]" if cfg.get("is_vip") else ""
    msg_text = f"🎮 *XWORLD BOT*{vip_badge} | Key còn: `{h}h {m}p`\nChọn game:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    try:
        if is_new:
            sent = bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
            cfg["menu_msg_id"] = sent.message_id
        else:
            bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
            cfg["menu_msg_id"] = message_id
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    if not check_key_validity(chat_id):
        cfg["waiting_for_key"] = True
        cfg["prompt_msg_id"] = call.message.message_id
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = "📜 **XWORLD LICENSE GATEWAY**\n───────────────────\n⚠️ **Key của bạn đã hết hạn!**\n\n👉 Vui lòng chọn thao tác bên dưới:"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key (24h)", url=web_url),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
        )
        try:
            bot.answer_callback_query(call.id, "⚠️ Key đã hết hạn!", show_alert=True)
            bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except: pass
        return
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)

def show_game_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    check_key_validity(chat_id)
    reset_user_wait_flags(cfg)
    g_cfg = cfg[game_type]
    game_name = GAME_NAMES_VI.get(game_type, "Game")
    status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
    total_accs = len(g_cfg["accounts"])
    selected_count = len(g_cfg.get("selected_uids", []))
    selected_str = f"{selected_count} nick" if selected_count > 0 else f"Tất cả ({total_accs})"
    bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    
    max_r = g_cfg.get('max_rounds', 100)
    tot_bets_done = sum(get_account_state(game_type, u)["total_bets"] for u in g_cfg["accounts"])
    remaining_rounds = max(0, max_r - tot_bets_done) if max_r > 0 else "Vô hạn"
    rounds_str = f"{remaining_rounds} ván (còn lại)" if max_r > 0 else "Vô hạn"
    
    vip_btn_text = "👑 Cấu Hình VIP ✨" if cfg.get("is_vip") else "👑 Tính Năng VIP 🔒"
    remaining_sec = int(cfg.get("key_expire_at", 0) - time.time())
    h = max(0, remaining_sec // 3600); m = max(0, (remaining_sec % 3600) // 60)
    
    msg_text = f"🎮 *{game_name.upper()}* | Key: `{h}h {m}p`\nTrạng thái: {status_str} | Chạy: `{selected_str}` / Tổng: `{total_accs}/1`\nCược: `{bet_disp}` | Giới hạn số ván: `{rounds_str}`"
    
    cfg["menu_msg_id"] = message_id
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🗑️ Xóa Nick", callback_data=f"game_{game_type}_delete_acc"),
        types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Sửa Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton(vip_btn_text, callback_data=f"game_{game_type}_vip_menu"),
        types.InlineKeyboardButton("📊 Thống Kê", callback_data=f"game_{game_type}_status"),
        types.InlineKeyboardButton("🔙 Quay lại", callback_data="back_to_main")
    )
    try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        try:
            sent = bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
            cfg["menu_msg_id"] = sent.message_id
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    try: bot.answer_callback_query(call.id)
    except: pass
    show_main_menu(chat_id, call.message.message_id, is_new=False)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not check_key_validity(chat_id):
        cfg["waiting_for_key"] = True
        cfg["prompt_msg_id"] = call.message.message_id
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = "📜 **XWORLD LICENSE GATEWAY**\n───────────────────\n⚠️ **Key của bạn đã hết hạn!**\n\n👉 Vui lòng chọn thao tác bên dưới:"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key (24h)", url=web_url),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
        )
        try:
            bot.answer_callback_query(call.id, "⚠️ Key đã hết hạn!", show_alert=True)
            bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except: pass
        return
    parts = call.data.split("_")
    game_type = parts[1]; action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = GAME_NAMES_VI.get(game_type, "Game")
    markup_back = types.InlineKeyboardMarkup()
    markup_back.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}"))

    if action == "reset_stats":
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            st["total_profit"] = Decimal("0"); st["total_bets"] = 0
            st["wins"] = 0; st["losses"] = 0; st["streak_loss"] = 0
        if "max_rounds" not in g_cfg: g_cfg["max_rounds"] = 100 if not cfg.get("is_vip") else 0
        try: bot.answer_callback_query(call.id, "🔄 Đã reset thống kê về 0!")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)

    elif action == "vip_menu":
        if not cfg.get("is_vip"):
            cfg["waiting_for_vip_code"] = True
            cfg["prompt_msg_id"] = call.message.message_id
            msg_vip = "👑 **TÍNH NĂNG VIP BỊ KHÓA** 🔒\n━━━━━━━━━━━━━━━━━━━\n✨ *Key Thường giới hạn cố định 100 ván.*\n✨ *Nhập Mã Code VIP để mở khóa:*\n• 🔢 Thay đổi giới hạn số ván (Vô hạn hoặc tùy chọn)\n• 🛑 Tự dừng khi thua liên tiếp X ván\n• 📉 Tự ngắt khi chạm ngưỡng Cắt Lỗ\n• 🎯 Tự ngắt khi đạt mục tiêu Chốt Lời\n\n👉 **Vui lòng nhập Mã Code VIP do Admin cấp để mở khóa:**"
            try: bot.edit_message_text(msg_vip, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
            except: pass
        else: show_vip_settings_menu(chat_id, call.message.message_id, game_type)

    elif action == "vip_set_max_rounds":
        if not cfg.get("is_vip"):
            try: bot.answer_callback_query(call.id, "⚠️ Key Thường không thể đổi số ván. Cần lên VIP!", show_alert=True)
            except: pass
            return
        cfg["waiting_for_max_rounds_vip"] = game_type
        cfg["prompt_msg_id"] = call.message.message_id
        try: bot.edit_message_text(f"🔢 **Nhập số ván muốn cược (Nhập `0` để chạy vô hạn):**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass

    elif action == "vip_set_max_losses":
        cfg["waiting_for_max_losses"] = game_type; cfg["prompt_msg_id"] = call.message.message_id
        try: bot.edit_message_text(f"🛑 **Nhập số ván THUA LIÊN TIẾP để dừng bot (Nhập `0` để tắt):**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass

    elif action == "vip_set_stop_loss":
        cfg["waiting_for_stop_loss"] = game_type; cfg["prompt_msg_id"] = call.message.message_id
        try: bot.edit_message_text(f"📉 **Nhập số tiền LỖ TỐI ĐA để ngắt bot (VD: `50` BUILD, Nhập `0` để tắt):**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass

    elif action == "vip_set_take_profit":
        cfg["waiting_for_take_profit"] = game_type; cfg["prompt_msg_id"] = call.message.message_id
        try: bot.edit_message_text(f"🎯 **Nhập số tiền LÃI MỤC TIÊU để ngắt bot (VD: `100` BUILD, Nhập `0` để tắt):**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass

    elif action == "setup_link":
        if len(g_cfg["accounts"]) >= 1:
            try: bot.answer_callback_query(call.id, "⚠️ Đã có nick! Hãy xóa nick cũ trước khi thêm nick mới.", show_alert=True)
            except: pass
            return
        reset_user_wait_flags(cfg)
        cfg["waiting_for_link"] = game_type; cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"📥 **Dán link [ {game_name_vi} ] vào ô chat:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "delete_acc":
        if not g_cfg["accounts"]:
            try: bot.answer_callback_query(call.id, "⚠️ Không có nick nào để xóa!", show_alert=True)
            except: pass
            return
        g_cfg["global_running"] = False
        for uid in list(g_cfg["accounts"].keys()): get_account_state(game_type, uid)["random_stop"].set()
        g_cfg["accounts"].clear(); g_cfg["selected_uids"].clear()
        try: bot.answer_callback_query(call.id, "🗑️ Đã xóa nick thành công!")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "input_bet":
        reset_user_wait_flags(cfg)
        cfg["waiting_for_bet"] = game_type; cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "toggle_bot":
        if not check_key_validity(chat_id):
            g_cfg["global_running"] = False
            try: bot.answer_callback_query(call.id, "⚠️ Key hết hạn, không thể bật bot!", show_alert=True)
            except: pass
            show_game_menu(chat_id, call.message.message_id, game_type)
            return

        if not g_cfg["accounts"]:
            try: bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào!", show_alert=True)
            except: pass
            return
            
        if not g_cfg["global_running"]:
            g_cfg["global_running"] = True
            for uid, skey in g_cfg["accounts"].items():
                st = get_account_state(game_type, uid)
                st["random_stop"].clear()
                if game_type == "escape": Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                elif game_type == "sprint": Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
            try: bot.answer_callback_query(call.id, "🚀 Đã bật auto thành công!")
            except: pass
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]: get_account_state(game_type, uid)["random_stop"].set()
            try: bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
            except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        current_asset = g_cfg["asset_type"]
        if current_asset == "BUILD": g_cfg["asset_type"] = "WORLD"
        elif current_asset == "WORLD": g_cfg["asset_type"] = "USDT"
        else: g_cfg["asset_type"] = "BUILD"

        if game_type == "sprint":
            if not g_cfg.get("bet_amount_total"): g_cfg["bet_amount_total"] = "1"
        else:
            if not g_cfg.get("base_bet"): g_cfg["base_bet"] = 1.0

        try: bot.answer_callback_query(call.id, f"✅ Đã đổi sang {g_cfg['asset_type']}")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "status":
        try: bot.answer_callback_query(call.id, "🔄 Cập nhật!")
        except: pass
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]; tot_wins += st["wins"]; tot_losses += st["losses"]; tot_profit += st["total_profit"]
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0.0
        msg = f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n━━━━━━━━━━━━━━━━━━━\n📌 Trạng thái: {'🟢 Chạy' if g_cfg['global_running'] else '🔴 Dừng'}\n🎲 Tổng cược: `{tot_bets}`\n🏆 Thắng/Thua: `{tot_wins}` / `{tot_losses}`\n📈 Tỷ lệ thắng: `{wr:.1f}%`\n💵 Tổng Lời/Lỗ: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
        markup_stat = types.InlineKeyboardMarkup(row_width=2)
        markup_stat.add(
            types.InlineKeyboardButton("🔄 Cập nhật", callback_data=f"game_{game_type}_status"),
            types.InlineKeyboardButton("🔄 Reset Thống Kê", callback_data=f"game_{game_type}_reset_stats"),
            types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}")
        )
        try: bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_stat, parse_mode="Markdown")
        except: pass

def show_vip_settings_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    g_cfg = cfg[game_type]
    game_name = GAME_NAMES_VI.get(game_type, "Game")
    max_rounds = g_cfg.get("max_rounds", 100)
    max_losses = g_cfg.get("max_continuous_losses", 0)
    stop_loss = g_cfg.get("stop_loss_amount", 0.0)
    take_profit = g_cfg.get("take_profit_amount", 0.0)
    
    rounds_str = f"{max_rounds} ván" if max_rounds > 0 else "Vô hạn"
    losses_str = f"{max_losses} ván" if max_losses > 0 else "Tắt"
    stop_loss_str = f"-{stop_loss} {g_cfg['asset_type']}" if stop_loss > 0 else "Tắt"
    take_profit_str = f"+{take_profit} {g_cfg['asset_type']}" if take_profit > 0 else "Tắt"
    
    msg_text = f"👑 *CẤU HÌNH QUẢN TRỊ VIP ({game_name.upper()})*\n━━━━━━━━━━━━━━━━━━━\n🔢 Giới hạn số ván: `{rounds_str}`\n🛑 Dừng khi thua liên tiếp: `{losses_str}`\n📉 Dừng khi Cắt Lỗ: `{stop_loss_str}`\n🎯 Dừng khi Chốt Lời: `{take_profit_str}`\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔢 Đổi Giới Hạn Số Ván", callback_data=f"game_{game_type}_vip_set_max_rounds"),
        types.InlineKeyboardButton("🛑 Cài Thua Liên Tiếp", callback_data=f"game_{game_type}_vip_set_max_losses"),
        types.InlineKeyboardButton("📉 Cài Giới Hạn Cắt Lỗ", callback_data=f"game_{game_type}_vip_set_stop_loss"),
        types.InlineKeyboardButton("🎯 Cài Mục Tiêu Chốt Lời", callback_data=f"game_{game_type}_vip_set_take_profit"),
        types.InlineKeyboardButton("🔙 Trở lại Game", callback_data=f"back_to_game_{game_type}")
    )
    try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_game_"))
def callback_back_game(call):
    chat_id = call.message.chat.id
    game_type = call.data.split("_")[3]
    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    db = load_system_db()
    if db.get("maintenance", {}).get("active"):
        notice = db.get("maintenance", {}).get("notice", "⚠️ Hệ thống đang bảo trì!")
        bot.send_message(chat_id, f"🛠️ **THÔNG BÁO BẢO TRÌ** 🛠️\n━━━━━━━━━━━━━━━━━━━\n{notice}", parse_mode="Markdown")
        return

    cfg = get_user_config(chat_id)

    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        try:
            val = float(text)
            if val <= 0: raise ValueError()
            g_cfg = cfg[game_target_bet]
            if game_target_bet == "sprint": g_cfg["bet_amount_total"] = str(val)
            else: g_cfg["base_bet"] = val
            cfg["waiting_for_bet"] = None
            show_game_menu(chat_id, prompt_id, game_target_bet)
            return
        except:
            bot.send_message(chat_id, "⚠️ Vui lòng chỉ nhập số tiền cược hợp lệ!")
            return

    game_max_rounds_vip = cfg.get("waiting_for_max_rounds_vip")
    if game_max_rounds_vip:
        try: bot.delete_message(chat_id, message.message_id); val = int(text)
        except: val = 100
        cfg[game_max_rounds_vip]["max_rounds"] = val
        cfg["waiting_for_max_rounds_vip"] = None
        show_vip_settings_menu(chat_id, cfg.get("prompt_msg_id"), game_max_rounds_vip)
        return

    if cfg.get("waiting_for_vip_code"):
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        res = verify_key_with_server(text, str(chat_id))
        if res.get("status") == "success":
            if not res.get("is_vip", False): err_msg = "Mã này là Key Thường, không phải Code VIP!"
            else:
                cfg["is_vip"] = True; cfg["vip_expire_at"] = res.get("expire_at", time.time() + 86400)
                cfg["has_valid_key"] = True; cfg["key_expire_at"] = cfg["vip_expire_at"]
                cfg["waiting_for_vip_code"] = False
                prompt_id = cfg.get("prompt_msg_id")
                if prompt_id:
                    try: bot.delete_message(chat_id, prompt_id)
                    except: pass
                active_g = cfg.get("active_game", "escape")
                show_game_menu(chat_id, cfg.get("menu_msg_id"), active_g)
                return
        else: err_msg = res.get("msg", "Mã Code VIP không chính xác hoặc đã bị xóa!")

        def send_and_auto_delete_err():
            try:
                msg = bot.send_message(chat_id, f"❌ **{err_msg}**", parse_mode="Markdown")
                time.sleep(3)
                bot.delete_message(chat_id, msg.message_id)
            except: pass
        Thread(target=send_and_auto_delete_err, daemon=True).start()
        return

    game_max_loss = cfg.get("waiting_for_max_losses")
    if game_max_loss:
        try: bot.delete_message(chat_id, message.message_id); val = int(text)
        except: val = 0
        cfg[game_max_loss]["max_continuous_losses"] = val
        cfg["waiting_for_max_losses"] = None
        show_vip_settings_menu(chat_id, cfg.get("prompt_msg_id"), game_max_loss)
        return

    game_stop_loss = cfg.get("waiting_for_stop_loss")
    if game_stop_loss:
        try: bot.delete_message(chat_id, message.message_id); val = float(text)
        except: val = 0.0
        cfg[game_stop_loss]["stop_loss_amount"] = val
        cfg["waiting_for_stop_loss"] = None
        show_vip_settings_menu(chat_id, cfg.get("prompt_msg_id"), game_stop_loss)
        return

    game_take_profit = cfg.get("waiting_for_take_profit")
    if game_take_profit:
        try: bot.delete_message(chat_id, message.message_id); val = float(text)
        except: val = 0.0
        cfg[game_take_profit]["take_profit_amount"] = val
        cfg["waiting_for_take_profit"] = None
        show_vip_settings_menu(chat_id, cfg.get("prompt_msg_id"), game_take_profit)
        return

    if cfg.get("waiting_for_key"):
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        res = verify_key_with_server(text, str(chat_id))
        if res.get("status") == "success":
            cfg["has_valid_key"] = True; cfg["waiting_for_key"] = False
            cfg["is_vip"] = res.get("is_vip", False)
            cfg["key_expire_at"] = res.get("expire_at", time.time() + 86400)
            session_manager.save_session_to_file(chat_id, cfg["key_expire_at"])
            prompt_id = cfg.get("prompt_msg_id")
            if prompt_id:
                try: bot.delete_message(chat_id, prompt_id)
                except: pass
            show_main_menu(chat_id, message.message_id, is_new=True)
        else:
            err_msg = res.get("msg", "Key không hợp lệ hoặc đã được sử dụng!")
            web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("🌐 Lấy Key Mới (24h)", url=web_url),
                types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
            )
            bot.send_message(chat_id, f"❌ **{err_msg}**", reply_markup=markup, parse_mode="Markdown")
        return

    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_link}"))
        g_cfg = cfg[game_target_link]
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text); query_params = parse_qs(parsed_url.query)
                uid_str = query_params.get("userId", [None])[0]; skey = query_params.get("secretKey", [None])[0]
                if uid_str and skey:
                    uid = int(uid_str); g_cfg["accounts"][uid] = skey; cfg["waiting_for_link"] = None
                    if prompt_id:
                        try: bot.edit_message_text(f"✅ **Thêm nick thành công!** (`{uid}`)", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                        except: pass
                    return
            except: pass
        return

    if not text.startswith("/"):
        try: bot.delete_message(chat_id, message.message_id)
        except: pass

def update_menu_live(chat_id, game_type):
    cfg = get_user_config(chat_id)
    check_key_validity(chat_id)
    menu_msg_id = cfg.get("menu_msg_id")
    if not menu_msg_id: return
    try:
        g_cfg = cfg[game_type]
        game_name = GAME_NAMES_VI.get(game_type, "Game")
        status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
        total_accs = len(g_cfg["accounts"])
        selected_count = len(g_cfg.get("selected_uids", []))
        selected_str = f"{selected_count} nick" if selected_count > 0 else f"Tất cả ({total_accs})"
        bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
        
        max_r = g_cfg.get('max_rounds', 100)
        tot_bets_done = sum(get_account_state(game_type, u)["total_bets"] for u in g_cfg["accounts"])
        remaining_rounds = max(0, max_r - tot_bets_done) if max_r > 0 else "Vô hạn"
        rounds_str = f"{remaining_rounds} ván (còn lại)" if max_r > 0 else "Vô hạn"
        
        vip_btn_text = "👑 Cấu Hình VIP ✨" if cfg.get("is_vip") else "👑 Tính Năng VIP 🔒"
        remaining_sec = int(cfg.get("key_expire_at", 0) - time.time())
        h = max(0, remaining_sec // 3600); m = max(0, (remaining_sec % 3600) // 60)
        
        msg_text = f"🎮 *{game_name.upper()}* | Key: `{h}h {m}p`\nTrạng thái: {status_str} | Chạy: `{selected_str}` / Tổng: `{total_accs}/1`\nCược: `{bet_disp}` | Giới hạn số ván: `{rounds_str}`"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⚙️ Thêm Link", callback_data=f"game_{game_type}_setup_link"),
            types.InlineKeyboardButton("🗑️ Xóa Nick", callback_data=f"game_{game_type}_delete_acc"),
            types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
            types.InlineKeyboardButton(f"🪙 Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
            types.InlineKeyboardButton("✏️ Sửa Cược", callback_data=f"game_{game_type}_input_bet"),
            types.InlineKeyboardButton(vip_btn_text, callback_data=f"game_{game_type}_vip_menu"),
            types.InlineKeyboardButton("📊 Thống Kê", callback_data=f"game_{game_type}_status"),
            types.InlineKeyboardButton("🔙 Quay lại", callback_data="back_to_main")
        )
        bot.edit_message_text(msg_text, chat_id, menu_msg_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

def run_escape_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)
    escape_cfg = cfg["escape"]
    acc_st = get_account_state("escape", uid)
    
    session_req = requests.Session()
    session_req.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
        "Origin": "https://escapemaster.net",
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": f"https://escapemaster.net/battleroyale/?userId={uid}&secretKey={skey}&language=vi-VN",
    })

    def get_headers():
        return {
            "Content-Type": "application/json",
            "User-Id": str(uid), "User-Login": "login_v2",
            "User-Secret-Key": skey, "Accept": "application/json"
        }

    while escape_cfg["global_running"] and not acc_st["random_stop"].is_set():
        if escape_cfg.get("max_continuous_losses", 0) > 0 and acc_st["streak_loss"] >= escape_cfg["max_continuous_losses"]:
            escape_cfg["global_running"] = False
            bot.send_message(chat_id, f"🛑 **VIP Auto Stop:** Đã thua {acc_st['streak_loss']} ván liên tiếp!", parse_mode="Markdown")
            update_menu_live(chat_id, "escape"); break

        if escape_cfg.get("stop_loss_amount", 0.0) > 0 and acc_st["total_profit"] <= -Decimal(str(escape_cfg["stop_loss_amount"])):
            escape_cfg["global_running"] = False
            bot.send_message(chat_id, f"📉 **VIP Auto Stop:** Cắt Lỗ ({acc_st['total_profit']} {escape_cfg['asset_type']})!", parse_mode="Markdown")
            update_menu_live(chat_id, "escape"); break

        if escape_cfg.get("take_profit_amount", 0.0) > 0 and acc_st["total_profit"] >= Decimal(str(escape_cfg["take_profit_amount"])):
            escape_cfg["global_running"] = False
            bot.send_message(chat_id, f"🎯 **VIP Auto Stop:** Chốt Lời (+{acc_st['total_profit']} {escape_cfg['asset_type']})!", parse_mode="Markdown")
            update_menu_live(chat_id, "escape"); break

        if not check_key_validity(chat_id): break
        
        max_r = escape_cfg.get("max_rounds", 100)
        if max_r > 0 and acc_st["total_bets"] >= max_r:
            escape_cfg["global_running"] = False
            bot.send_message(chat_id, f"🏁 **Đã hoàn thành định mức {max_r} ván cược. Bot tự động dừng!**", parse_mode="Markdown")
            update_menu_live(chat_id, "escape"); break

        try:
            rooms = [1, 2, 3, 4, 5, 6, 7, 8]
            room_id = random.choice(rooms)
            
            session_req.post("https://api.escapemaster.net/escape_game/enter_room",
                             json={"asset_type": escape_cfg["asset_type"], "user_id": int(uid), "room_id": int(room_id)},
                             headers=get_headers(), timeout=3)
            
            amount = float(escape_cfg["base_bet"])
            res = session_req.post("https://api.escapemaster.net/escape_game/bet",
                                   json={"asset_type": escape_cfg["asset_type"], "user_id": int(uid), "room_id": int(room_id), "bet_amount": amount},
                                   headers=get_headers(), timeout=3)
            
            if res.status_code == 200:
                res_data = res.json()
                if res_data.get("code") == 0:
                    acc_st["total_bets"] += 1
                    increment_key_bets_count(chat_id)
                    acc_st["wins"] += 1
                    bet_dec = Decimal(str(amount))
                    acc_st["total_profit"] += (bet_dec * Decimal("0.5"))
                    update_menu_live(chat_id, "escape")
        except: pass
        
        for _ in range(60):
            if not escape_cfg["global_running"] or acc_st["random_stop"].is_set(): break
            time.sleep(1)

def run_sprint_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)
    sprint_cfg = cfg["sprint"]
    acc_st = get_account_state("sprint", uid)
    base_api = "https://api.sprintrun.win"
    headers = {"accept": "*/*", "content-type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    session = requests.Session()
    last_issue = None

    while sprint_cfg["global_running"] and not acc_st["random_stop"].is_set():
        if sprint_cfg.get("max_continuous_losses", 0) > 0 and acc_st["streak_loss"] >= sprint_cfg["max_continuous_losses"]:
            sprint_cfg["global_running"] = False
            bot.send_message(chat_id, f"🛑 **VIP Auto Stop:** Đã thua {acc_st['streak_loss']} ván liên tiếp!", parse_mode="Markdown")
            update_menu_live(chat_id, "sprint"); break

        if sprint_cfg.get("stop_loss_amount", 0.0) > 0 and acc_st["total_profit"] <= -Decimal(str(sprint_cfg["stop_loss_amount"])):
            sprint_cfg["global_running"] = False
            bot.send_message(chat_id, f"📉 **VIP Auto Stop:** Cắt Lỗ ({acc_st['total_profit']} {sprint_cfg['asset_type']})!", parse_mode="Markdown")
            update_menu_live(chat_id, "sprint"); break

        if sprint_cfg.get("take_profit_amount", 0.0) > 0 and acc_st["total_profit"] >= Decimal(str(sprint_cfg["take_profit_amount"])):
            sprint_cfg["global_running"] = False
            bot.send_message(chat_id, f"🎯 **VIP Auto Stop:** Chốt Lời (+{acc_st['total_profit']} {sprint_cfg['asset_type']})!", parse_mode="Markdown")
            update_menu_live(chat_id, "sprint"); break

        if not check_key_validity(chat_id): sprint_cfg["global_running"] = False; break

        max_r = sprint_cfg.get("max_rounds", 100)
        if max_r > 0 and acc_st["total_bets"] >= max_r:
            sprint_cfg["global_running"] = False
            bot.send_message(chat_id, f"🏁 **Đã hoàn thành định mức {max_r} ván cược. Bot tự động dừng!**", parse_mode="Markdown")
            update_menu_live(chat_id, "sprint"); break

        try:
            r = session.get(f"{base_api}/sprint/home?asset={sprint_cfg['asset_type']}", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get("data", {})
                issue_id = data.get("issue_id"); athletes = data.get("athlete_list", [])
                if issue_id and issue_id != last_issue and len(athletes) >= 3:
                    chosen = [a["id"] for a in random.sample(athletes, 3)]
                    each_bet = (Decimal(str(sprint_cfg["bet_amount_total"])) / Decimal(3)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
                    for aid in chosen:
                        session.post(f"{base_api}/sprint/bet", json={"issue_id": issue_id, "bet_group": "winner", "asset_type": sprint_cfg["asset_type"], "athlete_id": aid, "bet_amount": float(each_bet)}, headers=headers, timeout=3)
                    acc_st["total_bets"] += 1
                    increment_key_bets_count(chat_id)
                    last_issue = issue_id
                    update_menu_live(chat_id, "sprint")
        except: pass
        time.sleep(3)

def run_telebot_polling():
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except: time.sleep(5)

if __name__ == "__main__":
    Thread(target=run_telebot_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
