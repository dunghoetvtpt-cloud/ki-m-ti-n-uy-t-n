import os
import json
import time
import random
import base64
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

import session_manager

# ---------------------------------------------------------
# CẤU HÌNH FLASK WEB (CHẠY TRỰC TIẾP TRÊN WEB - KHÔNG DÙNG BOT TELEGRAM)
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
# ENGINE GAME CHẠY TRỰC TIẾP TRÊN WEB (DÙNG THREAD NỀN)
# ---------------------------------------------------------
web_user_threads = {}
web_threads_lock = Lock()
GAME_NAMES_VI = {"escape": "Vua Thoát Hiểm", "sprint": "Đua Tốc Độ"}

def get_web_account_state(game_prefix, uid):
    key = f"web_{game_prefix}_{uid}"
    with web_threads_lock:
        if key not in web_user_threads:
            web_user_threads[key] = {
                "total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0, 
                "streak_loss": 0, "random_stop": Event(), "running": False, "thread": None
            }
    return web_user_threads[key]

def verify_key_web(key_code, client_identifier):
    try:
        db = load_system_db()
        keys_db = db.get("keys", {})
        if key_code not in keys_db: return {"status": "error", "msg": "Mã hoặc Key không tồn tại!"}
        k_data = keys_db[key_code]
        duration_secs = int(k_data.get("duration_hours", 24) * 3600)
        is_vip = bool(k_data.get("is_vip", False))
        used_by_list = [str(x) for x in k_data.get("used_by", [])]
        max_uses = int(k_data.get("max_uses", 1))
        
        if client_identifier in used_by_list:
            expire_time = k_data.get("expire_at") or (time.time() + duration_secs)
            return {"status": "success", "msg": "Kích hoạt lại thành công!", "expire_at": expire_time, "is_vip": is_vip}
        if len(used_by_list) >= max_uses: return {"status": "error", "msg": "Mã này đã đạt giới hạn số người sử dụng!"}
        
        used_by_list.append(client_identifier)
        k_data["used_by"] = used_by_list
        if len(used_by_list) >= max_uses: k_data["status"] = "da_dung"
        expire_time = time.time() + duration_secs
        k_data["expire_at"] = expire_time
        save_system_db(db)
        return {"status": "success", "msg": "Kích hoạt thành công!", "expire_at": expire_time, "is_vip": is_vip}
    except Exception as e: return {"status": "error", "msg": f"Lỗi: {str(e)}"}

def check_web_session_valid():
    expire_at = session.get("web_expire_at", 0)
    if time.time() < expire_at:
        return True
    return False

# ---------------------------------------------------------
# FLASK WEB ROUTES & ADMIN DASHBOARD
# ---------------------------------------------------------
@app.route('/')
def home():
    db = load_system_db()
    if db.get("maintenance", {}).get("active"):
        notice = db.get("maintenance", {}).get("notice", "⚠️ Hệ thống đang bảo trì định kỳ!")
        return render_template_string(MAINTENANCE_HTML, notice=notice)

    new_key = request.args.get("key", "")
    error = request.args.get("error", "")
    is_authenticated = check_web_session_valid()

    if is_authenticated:
        return redirect(url_for('dashboard'))

    return render_template_string(HOME_HTML, new_key=new_key, error=error)

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

@app.route('/verify_key_ajax', methods=['POST'])
def verify_key_ajax():
    data = request.json or {}
    key_code = data.get("key", "").strip()
    client_id = request.remote_addr or "client_web"
    
    res = verify_key_web(key_code, client_id)
    if res.get("status") == "success":
        session["web_authenticated"] = True
        session["web_is_vip"] = res.get("is_vip", False)
        session["web_expire_at"] = res.get("expire_at")
        session["client_id"] = client_id
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "msg": res.get("msg", "Mã không hợp lệ!")})

@app.route('/dashboard')
def dashboard():
    if not check_web_session_valid():
        return redirect(url_for('home'))
    
    expire_at = session.get("web_expire_at", 0)
    remaining_sec = max(0, int(expire_at - time.time()))
    h = remaining_sec // 3600
    m = (remaining_sec % 3600) // 60
    is_vip = session.get("web_is_vip", False)

    return render_template_string(DASHBOARD_HTML, h=h, m=m, is_vip=is_vip)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---------------------------------------------------------
# QUẢN TRỊ ADMIN (BẤM 10 LẦN TIA SÉT Ở TRANG CHỦ HOẶC ĐƯỜNG DẪN)
# ---------------------------------------------------------
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
    return render_template_string(ADMIN_LOGIN_HTML, error=error)

@app.route('/quan-ly-bi-mat-dunghoet/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    keys_db = db.get("keys", {})
    maint = db.get("maintenance", {"active": False, "notice": ""})
    now = time.time()
    
    total_keys_count = len(keys_db)
    used_keys_count = sum(1 for k, info in keys_db.items() if len(info.get('used_by', [])) > 0)
    unused_keys_count = total_keys_count - used_keys_count

    return render_template_string(ADMIN_DASHBOARD_HTML, keys=keys_db, maint=maint, now=now, 
                                  total_keys_count=total_keys_count, used_keys_count=used_keys_count, 
                                  unused_keys_count=unused_keys_count)

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

# API điều khiển Game trực tiếp trên Web
@app.route('/api/game_action', methods=['POST'])
def api_game_action():
    if not check_web_session_valid():
        return jsonify({"success": False, "msg": "Phiên làm việc hết hạn!"})
    
    data = request.json or {}
    game_type = data.get("game_type")
    action = data.get("action")
    
    if game_type not in ["escape", "sprint"]:
        return jsonify({"success": False, "msg": "Game không tồn tại!"})
    
    client_id = session.get("client_id", "web_user")
    
    if f"{game_type}_config" not in session:
        session[f"{game_type}_config"] = {
            "skey": "", "uid": "", "asset_type": "BUILD", 
            "base_bet": 1.0, "bet_amount_total": "1", 
            "max_rounds": 100 if not session.get("web_is_vip") else 0,
            "max_continuous_losses": 0, "stop_loss_amount": 0.0, "take_profit_amount": 0.0
        }
    
    g_cfg = session[f"{game_type}_config"]
    acc_st = get_web_account_state(game_type, client_id)

    if action == "save_link":
        link_str = data.get("link", "").strip()
        try:
            parsed_url = urlparse(link_str); query_params = parse_qs(parsed_url.query)
            uid_str = query_params.get("userId", [None])[0]; skey = query_params.get("secretKey", [None])[0]
            if uid_str and skey:
                g_cfg["uid"] = uid_str
                g_cfg["skey"] = skey
                session.modified = True
                return jsonify({"success": True, "msg": f"Đã lưu nick thành công! (UID: {uid_str})"})
        except: pass
        return jsonify({"success": False, "msg": "Link không hợp lệ! Thiếu userId hoặc secretKey."})

    elif action == "update_settings":
        g_cfg["asset_type"] = data.get("asset_type", "BUILD")
        if game_type == "sprint":
            g_cfg["bet_amount_total"] = str(data.get("bet", "1"))
        else:
            g_cfg["base_bet"] = float(data.get("bet", 1.0))
        
        if session.get("web_is_vip"):
            g_cfg["max_rounds"] = int(data.get("max_rounds", 0))
            g_cfg["max_continuous_losses"] = int(data.get("max_losses", 0))
            g_cfg["stop_loss_amount"] = float(data.get("stop_loss", 0.0))
            g_cfg["take_profit_amount"] = float(data.get("take_profit", 0.0))
        
        session.modified = True
        return jsonify({"success": True, "msg": "Đã cập nhật cấu hình!"})

    elif action == "toggle_bot":
        if not g_cfg["uid"] or not g_cfg["skey"]:
            return jsonify({"success": False, "msg": "Vui lòng nhập Link tài khoản trước khi bật bot!"})
        
        if not acc_st["running"]:
            acc_st["running"] = True
            acc_st["random_stop"].clear()
            if game_type == "escape":
                t = Thread(target=run_web_escape_engine, args=(client_id, g_cfg, acc_st), daemon=True)
            else:
                t = Thread(target=run_web_sprint_engine, args=(client_id, g_cfg, acc_st), daemon=True)
            acc_st["thread"] = t
            t.start()
            return jsonify({"success": True, "running": True, "msg": "Đã khởi động Bot thành công!"})
        else:
            acc_st["running"] = False
            acc_st["random_stop"].set()
            return jsonify({"success": True, "running": False, "msg": "Đã dừng Bot!"})

    elif action == "get_status":
        tot_bets = acc_st["total_bets"]
        wins = acc_st["wins"]
        losses = acc_st["losses"]
        profit = float(acc_st["total_profit"])
        wr = (wins / tot_bets * 100) if tot_bets > 0 else 0.0
        return jsonify({
            "success": True,
            "running": acc_st["running"],
            "total_bets": tot_bets,
            "wins": wins,
            "losses": losses,
            "win_rate": f"{wr:.1f}%",
            "total_profit": f"{profit:+.4f}",
            "asset": g_cfg["asset_type"]
        })

    elif action == "reset_stats":
        acc_st["total_profit"] = Decimal("0")
        acc_st["total_bets"] = 0
        acc_st["wins"] = 0
        acc_st["losses"] = 0
        acc_st["streak_loss"] = 0
        return jsonify({"success": True, "msg": "Đã reset thống kê về 0!"})

    return jsonify({"success": False, "msg": "Thao tác không hợp lệ!"})

def run_web_escape_engine(client_id, g_cfg, acc_st):
    uid = g_cfg["uid"]
    skey = g_cfg["skey"]
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

    while acc_st["running"] and not acc_st["random_stop"].is_set():
        if g_cfg.get("max_continuous_losses", 0) > 0 and acc_st["streak_loss"] >= g_cfg["max_continuous_losses"]:
            acc_st["running"] = False; break
        if g_cfg.get("stop_loss_amount", 0.0) > 0 and acc_st["total_profit"] <= -Decimal(str(g_cfg["stop_loss_amount"])):
            acc_st["running"] = False; break
        if g_cfg.get("take_profit_amount", 0.0) > 0 and acc_st["total_profit"] >= Decimal(str(g_cfg["take_profit_amount"])):
            acc_st["running"] = False; break
        
        max_r = g_cfg.get("max_rounds", 100)
        if max_r > 0 and acc_st["total_bets"] >= max_r:
            acc_st["running"] = False; break

        try:
            room_id = random.choice([1, 2, 3, 4, 5, 6, 7, 8])
            session_req.post("https://api.escapemaster.net/escape_game/enter_room",
                             json={"asset_type": g_cfg["asset_type"], "user_id": int(uid), "room_id": int(room_id)},
                             headers=get_headers(), timeout=3)
            
            amount = float(g_cfg["base_bet"])
            res = session_req.post("https://api.escapemaster.net/escape_game/bet",
                                   json={"asset_type": g_cfg["asset_type"], "user_id": int(uid), "room_id": int(room_id), "bet_amount": amount},
                                   headers=get_headers(), timeout=3)
            
            if res.status_code == 200:
                res_data = res.json()
                if res_data.get("code") == 0:
                    acc_st["total_bets"] += 1
                    acc_st["wins"] += 1
                    bet_dec = Decimal(str(amount))
                    acc_st["total_profit"] += (bet_dec * Decimal("0.5"))
        except: pass
        
        for _ in range(60):
            if not acc_st["running"] or acc_st["random_stop"].is_set(): break
            time.sleep(1)

def run_web_sprint_engine(client_id, g_cfg, acc_st):
    uid = g_cfg["uid"]
    skey = g_cfg["skey"]
    base_api = "https://api.sprintrun.win"
    headers = {"accept": "*/*", "content-type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    session = requests.Session()
    last_issue = None

    while acc_st["running"] and not acc_st["random_stop"].is_set():
        if g_cfg.get("max_continuous_losses", 0) > 0 and acc_st["streak_loss"] >= g_cfg["max_continuous_losses"]:
            acc_st["running"] = False; break
        if g_cfg.get("stop_loss_amount", 0.0) > 0 and acc_st["total_profit"] <= -Decimal(str(g_cfg["stop_loss_amount"])):
            acc_st["running"] = False; break
        if g_cfg.get("take_profit_amount", 0.0) > 0 and acc_st["total_profit"] >= Decimal(str(g_cfg["take_profit_amount"])):
            acc_st["running"] = False; break
        
        max_r = g_cfg.get("max_rounds", 100)
        if max_r > 0 and acc_st["total_bets"] >= max_r:
            acc_st["running"] = False; break

        try:
            r = session.get(f"{base_api}/sprint/home?asset={g_cfg['asset_type']}", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get("data", {})
                issue_id = data.get("issue_id"); athletes = data.get("athlete_list", [])
                if issue_id and issue_id != last_issue and len(athletes) >= 3:
                    chosen = [a["id"] for a in random.sample(athletes, 3)]
                    each_bet = (Decimal(str(g_cfg["bet_amount_total"])) / Decimal(3)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
                    for aid in chosen:
                        session.post(f"{base_api}/sprint/bet", json={"issue_id": issue_id, "bet_group": "winner", "asset_type": g_cfg["asset_type"], "athlete_id": aid, "bet_amount": float(each_bet)}, headers=headers, timeout=3)
                    acc_st["total_bets"] += 1
                    last_issue = issue_id
        except: pass
        time.sleep(3)

# ---------------------------------------------------------
# HTML TEMPLATES
# ---------------------------------------------------------
HOME_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XWORLD LICENSE GATEWAY - WEB APP</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 15px; }
        .card { background: rgba(30, 41, 59, 0.75); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); border-radius: 24px; width: 100%; max-width: 440px; padding: 30px 20px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }
        .icon-box { width: 60px; height: 60px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 15px; box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.5); color: #fff; cursor: pointer; user-select: none; }
        .badge { display: inline-block; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 5px 14px; border-radius: 30px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 12px; }
        h2 { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 10px; }
        p { color: #94a3b8; font-size: 13px; line-height: 1.5; margin-bottom: 25px; }
        .btn { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; text-decoration: none; padding: 14px; border-radius: 14px; font-weight: 700; font-size: 14px; box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.5); border: none; cursor: pointer; margin-bottom: 12px; }
        .input-group { margin-bottom: 15px; text-align: left; }
        .input-group label { font-size: 11px; font-weight: 600; color: #94a3b8; display: block; margin-bottom: 6px; }
        .input-group input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #334155; background: #0b0f19; color: #fff; font-size: 14px; text-align: center; }
        .key-container { background: #0b0f19; border: 2px dashed #6366f1; padding: 15px; border-radius: 16px; margin-top: 15px; margin-bottom: 15px; }
        .key-text { font-family: monospace; font-size: 16px; color: #4ade80; font-weight: 700; word-break: break-all; margin-bottom: 10px; }
        .btn-copy { background: #22c55e; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 700; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
        .error { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 10px; border-radius: 10px; font-size: 12px; margin-top: 15px; font-weight: 500; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-box" id="secretLightning" onclick="handleSecretClick()"><i class="fa-solid fa-bolt"></i></div>
        <span class="badge">Hệ Thống Web Trực Tiếp</span>
        <h2>XWORLD WEB GATEWAY</h2>
        <p>Vượt link an toàn để nhận mã bản quyền 24 giờ hoặc nhập trực tiếp mã key để truy cập hệ thống.</p>
        
        {% if new_key %}
            <div class="key-container">
                <div class="key-text" id="keyText">{{ new_key }}</div>
                <button class="btn-copy" onclick="copyKey()"><i class="fa-regular fa-copy"></i> Sao Chép Key</button>
            </div>
            <p style="color: #4ade80; font-weight: 600; font-size: 12px;">✨ Đã tạo key thành công! Dán vào ô bên dưới để đăng nhập.</p>
        {% else %}
            <a href="/get_link4m" class="btn"><i class="fa-solid fa-rocket"></i> LẤY KEY BẢN QUYỀN (24H)</a>
        {% endif %}

        <div class="input-group" style="margin-top: 20px;">
            <label><i class="fa-solid fa-key"></i> ĐĂNG NHẬP BẰNG MÃ KEY:</label>
            <input type="text" id="keyInput" placeholder="Nhập mã KEY-XW-... hoặc VIP-..." autocomplete="off">
        </div>
        <button class="btn" style="background: linear-gradient(135deg, #22c55e, #16a34a);" onclick="verifyAndLogin()">KÍCH HOẠT & TRUY CẬP</button>

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
                setTimeout(() => { btn.innerHTML = '<i class="fa-regular fa-copy"></i> Sao Chép Key'; }, 2000);
            });
        }

        function verifyAndLogin() {
            const key = document.getElementById("keyInput").value.trim();
            if(!key) { alert("Vui lòng nhập mã key!"); return; }
            
            fetch("/verify_key_ajax", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ key: key })
            }).then(res => res.json()).then(data => {
                if(data.success) {
                    window.location.href = "/dashboard";
                } else {
                    alert("Lỗi: " + data.msg);
                }
            });
        }
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XWorld Automation Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: #0f172a; color: #f8fafc; padding: 15px; min-height: 100vh; }
        .container { max-width: 600px; margin: 0 auto; background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 20px; border-radius: 20px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px; }
        .header h2 { font-size: 16px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
        .logout { color: #f87171; text-decoration: none; font-size: 12px; font-weight: 600; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); padding: 6px 12px; border-radius: 8px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { flex: 1; padding: 12px; background: #0b0f19; border: 1px solid #334155; color: #94a3b8; font-weight: 700; border-radius: 12px; cursor: pointer; text-align: center; font-size: 13px; }
        .tab-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }
        .panel { display: none; }
        .panel.active { display: block; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 6px; }
        .form-group input, .form-group select { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #334155; background: #0b0f19; color: #fff; font-size: 13px; }
        .btn-action { width: 100%; padding: 14px; border-radius: 12px; border: none; font-weight: 700; font-size: 14px; cursor: pointer; margin-top: 10px; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-start { background: #22c55e; color: #fff; }
        .btn-stop { background: #ef4444; color: #fff; }
        .stats-box { background: #0b0f19; border: 1px solid #334155; border-radius: 12px; padding: 15px; margin-top: 20px; }
        .stats-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }
        .stats-row span { color: #94a3b8; }
        .stats-row b { color: #38bdf8; }
        .vip-badge { background: #eab308; color: #000; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 800; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2><i class="fa-solid fa-robot"></i> XWORLD WEB APP {% if is_vip %}<span class="vip-badge">VIP</span>{% endif %}</h2>
            <div>
                <span style="font-size: 12px; color: #4ade80; margin-right: 10px;"><i class="fa-solid fa-clock"></i> {{ h }}h {{ m }}p</span>
                <a href="/logout" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Đăng Xuất</a>
            </div>
        </div>

        <div class="tabs">
            <div class="tab-btn active" onclick="switchTab('escape')">🕹️ Vua Thoát Hiểm</div>
            <div class="tab-btn" onclick="switchTab('sprint')">🏃 Đua Tốc Độ</div>
        </div>

        <!-- PANEL ESCAPE -->
        <div id="panel-escape" class="panel active">
            <div class="form-group">
                <label>Dán Link Tài Khoản (Escape Master):</label>
                <input type="text" id="escape_link" placeholder="https://escapemaster.net/battleroyale/?userId=...&secretKey=...">
                <button class="btn-action" style="background: #3b82f6; margin-top: 8px;" onclick="saveLink('escape')"><i class="fa-solid fa-link"></i> Lưu Nick</button>
            </div>
            <div class="form-group">
                <label>Loại Coin:</label>
                <select id="escape_asset">
                    <option value="BUILD">BUILD</option>
                    <option value="WORLD">WORLD</option>
                    <option value="USDT">USDT</option>
                </select>
            </div>
            <div class="form-group">
                <label>Tiền Cược Mỗi Ván:</label>
                <input type="number" id="escape_bet" value="1.0" step="0.1">
            </div>
            {% if is_vip %}
            <div class="form-group">
                <label>Giới hạn số ván (0 = Vô hạn):</label>
                <input type="number" id="escape_max_rounds" value="100">
            </div>
            <div class="form-group">
                <label>Cắt lỗ / Chốt lời:</label>
                <div style="display: flex; gap: 10px;">
                    <input type="number" id="escape_stop_loss" placeholder="Cắt lỗ" value="0">
                    <input type="number" id="escape_take_profit" placeholder="Chốt lời" value="0">
                </div>
            </div>
            {% endif %}
            
            <button id="btn_escape_toggle" class="btn-action btn-start" onclick="toggleBot('escape')"><i class="fa-solid fa-play"></i> BẬT BOT TỰ ĐỘNG</button>

            <div class="stats-box">
                <div class="stats-row"><span>Trạng thái:</span> <b id="escape_status_text" style="color: #ef4444;">Đang Dừng</b></div>
                <div class="stats-row"><span>Tổng ván cược:</span> <b id="escape_tot_bets">0</b></div>
                <div class="stats-row"><span>Thắng / Thua:</span> <b id="escape_win_loss">0 / 0</b></div>
                <div class="stats-row"><span>Tỷ lệ thắng:</span> <b id="escape_win_rate">0.0%</b></div>
                <div class="stats-row"><span>Tổng Lời/Lỗ:</span> <b id="escape_profit">0.0000</b></div>
                <button class="btn-action" style="background: #475569; padding: 8px; font-size: 11px; margin-top: 10px;" onclick="resetStats('escape')">🔄 Reset Thống Kê</button>
            </div>
        </div>

        <!-- PANEL SPRINT -->
        <div id="panel-sprint" class="panel">
            <div class="form-group">
                <label>Dán Link Tài Khoản (Sprint Run):</label>
                <input type="text" id="sprint_link" placeholder="https://.../?userId=...&secretKey=...">
                <button class="btn-action" style="background: #3b82f6; margin-top: 8px;" onclick="saveLink('sprint')"><i class="fa-solid fa-link"></i> Lưu Nick</button>
            </div>
            <div class="form-group">
                <label>Loại Coin:</label>
                <select id="sprint_asset">
                    <option value="BUILD">BUILD</option>
                    <option value="WORLD">WORLD</option>
                    <option value="USDT">USDT</option>
                </select>
            </div>
            <div class="form-group">
                <label>Tổng Tiền Cược Mỗi Ván:</label>
                <input type="text" id="sprint_bet" value="1">
            </div>
            {% if is_vip %}
            <div class="form-group">
                <label>Giới hạn số ván (0 = Vô hạn):</label>
                <input type="number" id="sprint_max_rounds" value="100">
            </div>
            {% endif %}

            <button id="btn_sprint_toggle" class="btn-action btn-start" onclick="toggleBot('sprint')"><i class="fa-solid fa-play"></i> BẬT BOT TỰ ĐỘNG</button>

            <div class="stats-box">
                <div class="stats-row"><span>Trạng thái:</span> <b id="sprint_status_text" style="color: #ef4444;">Đang Dừng</b></div>
                <div class="stats-row"><span>Tổng ván cược:</span> <b id="sprint_tot_bets">0</b></div>
                <div class="stats-row"><span>Thắng / Thua:</span> <b id="sprint_win_loss">0 / 0</b></div>
                <div class="stats-row"><span>Tỷ lệ thắng:</span> <b id="sprint_win_rate">0.0%</b></div>
                <div class="stats-row"><span>Tổng Lời/Lỗ:</span> <b id="sprint_profit">0.0000</b></div>
                <button class="btn-action" style="background: #475569; padding: 8px; font-size: 11px; margin-top: 10px;" onclick="resetStats('sprint')">🔄 Reset Thống Kê</button>
            </div>
        </div>
    </div>

    <script>
        function switchTab(game) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('panel-' + game).classList.add('active');
            event.currentTarget.classList.add('active');
        }

        function saveLink(game) {
            const link = document.getElementById(game + '_link').value.trim();
            fetch('/api/game_action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_type: game, action: 'save_link', link: link })
            }).then(res => res.json()).then(data => { alert(data.msg); });
        }

        function toggleBot(game) {
            const asset = document.getElementById(game + '_asset').value;
            const bet = document.getElementById(game + '_bet').value;
            let max_rounds = 100, max_losses = 0, stop_loss = 0, take_profit = 0;
            
            const mr = document.getElementById(game + '_max_rounds');
            if(mr) max_rounds = mr.value;
            const sl = document.getElementById(game + '_stop_loss');
            if(sl) stop_loss = sl.value;
            const tp = document.getElementById(game + '_take_profit');
            if(tp) take_profit = tp.value;

            fetch('/api/game_action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    game_type: game, action: 'update_settings',
                    asset_type: asset, bet: bet, max_rounds: max_rounds,
                    max_losses: max_losses, stop_loss: stop_loss, take_profit: take_profit
                })
            }).then(() => {
                fetch('/api/game_action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ game_type: game, action: 'toggle_bot' })
                }).then(res => res.json()).then(data => {
                    alert(data.msg);
                    updateButtonState(game, data.running);
                });
            });
        }

        function updateButtonState(game, running) {
            const btn = document.getElementById('btn_' + game + '_toggle');
            const statusText = document.getElementById(game + '_status_text');
            if(running) {
                btn.className = "btn-action btn-stop";
                btn.innerHTML = '<i class="fa-solid fa-stop"></i> DỪNG BOT';
                statusText.innerText = "Đang Chạy...";
                statusText.style.color = "#22c55e";
            } else {
                btn.className = "btn-action btn-start";
                btn.innerHTML = '<i class="fa-solid fa-play"></i> BẬT BOT TỰ ĐỘNG';
                statusText.innerText = "Đang Dừng";
                statusText.style.color = "#ef4444";
            }
        }

        function resetStats(game) {
            fetch('/api/game_action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_type: game, action: 'reset_stats' })
            }).then(res => res.json()).then(data => { alert(data.msg); });
        }

        setInterval(() => {
            ['escape', 'sprint'].forEach(game => {
                fetch('/api/game_action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ game_type: game, action: 'get_status' })
                }).then(res => res.json()).then(data => {
                    if(data.success) {
                        document.getElementById(game + '_tot_bets').innerText = data.total_bets;
                        document.getElementById(game + '_win_loss').innerText = data.wins + " / " + data.losses;
                        document.getElementById(game + '_win_rate').innerText = data.win_rate;
                        document.getElementById(game + '_profit').innerText = data.total_profit + " " + data.asset;
                        updateButtonState(game, data.running);
                    }
                }).catch(err => {});
            });
        }, 2000);
    </script>
</body>
</html>
"""

ADMIN_LOGIN_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Đăng Nhập Quản Trị</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 15px; }
    .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 30px 20px; border-radius: 24px; width: 100%; max-width: 380px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); }
    h2 { color: #fff; margin-bottom: 20px; font-size: 20px; font-weight: 700; }
    input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #334155; background: #0b0f19; color: #fff; margin-bottom: 12px; font-size: 14px; text-align: center; }
    .btn { width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; border: none; padding: 12px; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 14px; }
    .error { color: #f87171; font-size: 12px; margin-bottom: 12px; }
    .back { display: inline-block; margin-top: 15px; color: #64748b; font-size: 12px; text-decoration: none; }
</style></head>
<body><div class="card">
    <h2><i class="fa-solid fa-lock"></i> Đăng Nhập Quản Trị</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="text" name="username" placeholder="Nhập tài khoản..." required autocomplete="off">
        <input type="password" name="password" placeholder="Nhập mật khẩu..." required>
        <button type="submit" class="btn">Đăng Nhập</button>
    </form>
    <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i> Về trang chủ</a>
</div></body></html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Quản Lý Hệ Thống VIP</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body { background: #0f172a; color: #f8fafc; padding: 10px; }
    .container { max-width: 1100px; margin: 0 auto; background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.2); padding: 15px; border-radius: 16px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); width: 100%; }
    .header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 12px; }
    h2 { color: #f8fafc; font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 6px; }
    h2 i { color: #38bdf8; }
    .logout { color: #f87171; text-decoration: none; font-size: 11px; font-weight: 600; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); padding: 6px 10px; border-radius: 8px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 15px; }
    .stat-card { background: #0b0f19; border: 1px solid #334155; padding: 12px; border-radius: 12px; text-align: center; }
    .stat-card h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; }
    .stat-card span { font-size: 18px; font-weight: 800; color: #38bdf8; }
    .table-responsive { width: 100%; overflow-x: auto; border-radius: 10px; border: 1px solid #334155; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; min-width: 650px; }
    th, td { padding: 8px 10px; border-bottom: 1px solid #334155; text-align: left; vertical-align: middle; white-space: nowrap; }
    th { color: #94a3b8; font-weight: 600; background: #0b0f19; }
    code { background: #0b0f19; padding: 3px 6px; border-radius: 6px; color: #4ade80; font-family: monospace; }
    .btn-action { border: none; padding: 5px 8px; border-radius: 6px; cursor: pointer; font-size: 10px; font-weight: 600; text-decoration: none; display: inline-flex; }
    .btn-add-time { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
    .btn-sub-time { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .btn-del { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .btn-del-all { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 8px 12px; border-radius: 8px; font-weight: 700; font-size: 11px; text-decoration: none; }
    .btn-copy-code { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
    .btn-add { background: #22c55e; color: #fff; border: none; padding: 8px 14px; border-radius: 8px; font-weight: 700; font-size: 11px; cursor: pointer; }
    .btn-vip { background: #eab308; color: #000; border: none; padding: 8px 14px; border-radius: 8px; font-weight: 700; font-size: 11px; cursor: pointer; }
    .box-create { background: #0b0f19; padding: 12px; border-radius: 12px; margin-bottom: 15px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; border: 1px solid #334155; }
    .box-create input { padding: 6px 10px; border-radius: 6px; border: 1px solid #475569; background: #1e293b; color: #fff; font-size: 12px; }
    .input-time { padding: 4px; border-radius: 4px; border: 1px solid #475569; background: #1e293b; color: #fff; width: 50px; text-align: center; }
    .toast { position: fixed; bottom: 20px; right: 20px; background: #22c55e; color: white; padding: 8px 14px; border-radius: 8px; font-weight: 600; display: none; z-index: 1000; font-size: 12px; }
</style></head>
<body>
    <div class="toast" id="toastMsg">✅ Thành công!</div>
    <div class="container">
        <div class="header-flex">
            <h2><i class="fa-solid fa-shield-halved"></i> QUẢN TRỊ HỆ THỐNG WEB</h2>
            <a href="/quan-ly-bi-mat-dunghoet/logout" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Thoát</a>
        </div>

        <div class="stats-grid">
            <div class="stat-card"><h4>Tổng số Key</h4><span>{{ total_keys_count }}</span></div>
            <div class="stat-card"><h4>Đã kích hoạt</h4><span style="color: #f87171;">{{ used_keys_count }}</span></div>
            <div class="stat-card"><h4>Chưa kích hoạt</h4><span style="color: #4ade80;">{{ unused_keys_count }}</span></div>
        </div>

        <div class="box-create">
            <div>
                <label style="font-size: 10px; color: #94a3b8;">Thời hạn (H):</label>
                <input type="number" id="customHours" value="24" min="1" style="width: 70px;">
            </div>
            <div>
                <label style="font-size: 10px; color: #94a3b8;">Số lượng:</label>
                <input type="number" id="customQty" value="1" min="1" max="100" style="width: 70px;">
            </div>
            <div>
                <label style="font-size: 10px; color: #94a3b8;">Lượt dùng:</label>
                <input type="number" id="maxUses" value="1" min="1" max="1000" style="width: 70px;">
            </div>
            <div style="margin-top: 12px; display: flex; gap: 6px;">
                <button class="btn-add" onclick="createCustomKey(false)"><i class="fa-solid fa-plus"></i> Key Thường</button>
                <button class="btn-vip" onclick="createCustomKey(true)"><i class="fa-solid fa-crown"></i> Code VIP</button>
                <a href="/quan-ly-bi-mat-dunghoet/delete_all" class="btn-del-all" onclick="return confirm('Xóa sạch kho key?')">Xóa Sạch</a>
            </div>
        </div>

        <div class="table-responsive">
            <table>
                <tr>
                    <th>Mã Key / VIP</th>
                    <th>Loại</th>
                    <th>Cộng/Trừ H</th>
                    <th>Thời Gian Còn</th>
                    <th>Số Người Dùng</th>
                    <th>Thao Tác</th>
                </tr>
                {% for k, info in keys.items() %}
                {% set expire_at = info.get('expire_at', 0) %}
                {% set remain = (expire_at - now) if expire_at and expire_at > now else 0 %}
                {% set rem_h = (remain // 3600)|int %}
                {% set rem_m = ((remain % 3600) // 60)|int %}
                {% set used_list = info.get('used_by', []) %}
                <tr>
                    <td><code>{{ k }}</code></td>
                    <td>{% if info.get('is_vip') %}<b style="color:#eab308">VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                    <td>
                        <div style="display: flex; gap: 2px;">
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
                    <td><span>{{ used_list|length }}/{{ info.get('max_uses', 1) }}</span></td>
                    <td>
                        <div style="display: flex; gap: 3px;">
                            <button class="btn-action btn-copy-code" onclick="copyKey('{{ k }}')">Copy</button>
                            <a href="/quan-ly-bi-mat-dunghoet/delete?key={{ k }}" class="btn-action btn-del" onclick="return confirm('Xóa key này?')">Xóa</a>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div style="background: #0b0f19; padding: 15px; border-radius: 12px; border: 1px solid #334155; margin-top: 15px;">
            <h3 style="font-size: 13px; color: #f87171; margin-bottom: 10px;"><i class="fa-solid fa-triangle-exclamation"></i> Chế Độ Bảo Trì Web</h3>
            <textarea id="maintNotice" rows="2" style="width: 100%; background: #1e293b; color: #fff; border: 1px solid #475569; border-radius: 6px; padding: 8px; font-size: 12px; margin-bottom: 8px;">{{ maint.notice or "⚠️ Hệ thống đang bảo trì định kỳ!" }}</textarea>
            <button class="btn-add" onclick="updateMaintenance(true)">Bật Bảo Trì</button>
            <button class="btn-vip" onclick="updateMaintenance(false)">Tắt Bảo Trì</button>
        </div>
    </div>

    <script>
    function showToast(msg) {
        const t = document.getElementById("toastMsg");
        t.innerText = msg; t.style.display = "block";
        setTimeout(() => { t.style.display = "none"; }, 2500);
    }
    function copyKey(code) {
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

MAINTENANCE_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hệ Thống Đang Bảo Trì</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #fff; font-family: 'Plus Jakarta Sans', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; text-align: center; padding: 20px; }
        .box { background: rgba(30, 41, 59, 0.8); border: 1px solid #334155; padding: 30px; border-radius: 20px; max-width: 400px; width: 100%; }
        h1 { font-size: 20px; color: #f87171; margin-bottom: 15px; }
        p { font-size: 14px; color: #94a3b8; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🛠️ THÔNG BÁO BẢO TRÌ</h1>
        <p>{{ notice }}</p>
    </div>
</body>
</html>
"""

# ---------------------------------------------------------
# KHỞI CHẠY WEB SERVER
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
