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

app = Flask(__name__)
app.secret_key = "dung_license_secret_key_web_app_v2027"

ADMIN_USERNAME = "dunghoet"
ADMIN_PASSWORD = "10091990dung"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

ip_request_history = {}
DB_FILE = "system_db.json"
db_lock = Lock()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
GITHUB_FILE_PATH = "system_db.json"

def sync_pull_from_github():
    if not GITHUB_TOKEN or not GITHUB_REPO: return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            content_b64 = res.json().get("content", "")
            content_bytes = base64.b64decode(content_b64)
            with db_lock:
                with open(DB_FILE, "wb") as f: f.write(content_bytes)
            print("📥 Đã đồng bộ dữ liệu từ GitHub thành công!", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi pull từ GitHub: {e}", flush=True)

def sync_push_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO: return
    try:
        with db_lock:
            if not os.path.exists(DB_FILE): return
            with open(DB_FILE, "rb") as f: file_bytes = f.read()
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        get_res = requests.get(url, headers=headers, timeout=5)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        payload = {"message": "Auto-sync system_db.json from Web App", "content": content_b64}
        if sha: payload["sha"] = sha
        put_res = requests.put(url, json=payload, headers=headers, timeout=5)
        if put_res.status_code in [200, 201]:
            print("📤 Đã đẩy dữ liệu lên GitHub thành công!", flush=True)
    except Exception as e:
        print(f"❌ Lỗi push lên GitHub: {e}", flush=True)

Thread(target=sync_pull_from_github, daemon=True).start()

def load_system_db():
    with db_lock:
        if not os.path.exists(DB_FILE):
            default_data = {"keys": {}, "banned_users": {}, "maintenance": {"active": False, "notice": ""}}
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
    db["keys"][key_code] = data
    return save_system_db(db)

def delete_key_from_cloud(key_code):
    db = load_system_db()
    if "keys" in db and key_code in db["keys"]:
        del db["keys"][key_code]
        save_system_db(db)

server_bots = {}
bots_lock = Lock()

def get_bot_instance(key_code, game_type):
    bot_id = f"{key_code}_{game_type}"
    with bots_lock:
        if bot_id not in server_bots:
            server_bots[bot_id] = {
                "uid": "", "skey": "", "asset_type": "BUILD",
                "base_bet": 1.0, "bet_amount_total": "1",
                "max_rounds": 0, "max_continuous_losses": 0,
                "stop_loss_amount": 0.0, "take_profit_amount": 0.0,
                "running": False, "stop_event": Event(),
                "total_profit": Decimal("0"), "total_bets": 0,
                "wins": 0, "losses": 0, "streak_loss": 0,
                "last_log": "Sẵn sàng khởi động 24/7...", "thread": None
            }
    return server_bots[bot_id]

def verify_key_web(key_code, client_identifier):
    try:
        db = load_system_db()
        keys_db = db.get("keys", {})
        if key_code not in keys_db: return {"status": "error", "msg": "Mã Key không tồn tại!"}
        k_data = keys_db[key_code]
        duration_secs = int(k_data.get("duration_hours", 24) * 3600)
        is_vip = bool(k_data.get("is_vip", False))
        used_by_list = [str(x) for x in k_data.get("used_by", [])]
        max_uses = int(k_data.get("max_uses", 1))
        
        now = time.time()
        expire_time = k_data.get("expire_at")
        
        if expire_time and now > expire_time:
            return {"status": "error", "msg": "Key này đã hết hạn sử dụng!"}

        if client_identifier in used_by_list:
            if not expire_time:
                expire_time = now + duration_secs
                k_data["expire_at"] = expire_time
                save_system_db(db)
            return {"status": "success", "msg": "Đăng nhập thành công!", "expire_at": expire_time, "is_vip": is_vip}
            
        if len(used_by_list) >= max_uses:
            return {"status": "error", "msg": "Mã Key này đã đạt giới hạn số người sử dụng!"}
        
        used_by_list.append(client_identifier)
        k_data["used_by"] = used_by_list
        if len(used_by_list) >= max_uses: k_data["status"] = "da_dung"
        if not expire_time:
            expire_time = now + duration_secs
            k_data["expire_at"] = expire_time
        save_system_db(db)
        return {"status": "success", "msg": "Kích hoạt thành công!", "expire_at": expire_time, "is_vip": is_vip}
    except Exception as e:
        return {"status": "error", "msg": f"Lỗi hệ thống: {str(e)}"}

def check_web_session_valid():
    key_code = session.get("active_key")
    if not key_code: return False
    db = load_system_db()
    k_data = db.get("keys", {}).get(key_code)
    if not k_data: return False
    expire_at = k_data.get("expire_at", 0)
    if expire_at and time.time() < expire_at:
        session["web_expire_at"] = expire_at
        session["web_is_vip"] = bool(k_data.get("is_vip", False))
        return True
    return False

@app.route('/')
def home():
    db = load_system_db()
    if db.get("maintenance", {}).get("active"):
        notice = db.get("maintenance", {}).get("notice", "⚠️ Hệ thống đang bảo trì định kỳ!")
        return render_template_string(MAINTENANCE_HTML, notice=notice)

    new_key = request.args.get("key", "")
    error = request.args.get("error", "")
    if check_web_session_valid(): return redirect(url_for('dashboard'))
    return render_template_string(HOME_HTML, new_key=new_key, error=error)

@app.route('/ping')
def ping():
    return jsonify({"status": "alive", "time": time.time()})

@app.route('/get_link4m')
def get_link4m():
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    now = time.time()
    if client_ip not in ip_request_history: ip_request_history[client_ip] = []
    ip_request_history[client_ip] = [t for t in ip_request_history[client_ip] if now - t < 60]
    if len(ip_request_history[client_ip]) >= 3:
        return redirect(url_for('home', error="⚠️ Thao tác quá nhanh, vui lòng thử lại sau 1 phút."))
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
    if save_key_to_cloud(new_key, key_data): return redirect(url_for('home', key=new_key))
    return redirect(url_for('home', error="⚠️ Lỗi lưu key. Vui lòng thử lại!"))

@app.route('/verify_key_ajax', methods=['POST'])
def verify_key_ajax():
    data = request.json or {}
    key_code = data.get("key", "").strip()
    client_id = request.headers.get('X-Forwarded-For', request.remote_addr) or "client_web"
    res = verify_key_web(key_code, client_id)
    if res.get("status") == "success":
        session["active_key"] = key_code
        session["web_is_vip"] = res.get("is_vip", False)
        session["web_expire_at"] = res.get("expire_at")
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "msg": res.get("msg", "Mã không hợp lệ!")})

@app.route('/dashboard')
def dashboard():
    if not check_web_session_valid(): return redirect(url_for('home'))
    key_code = session.get("active_key")
    expire_at = session.get("web_expire_at", 0)
    remaining_sec = max(0, int(expire_at - time.time()))
    h = remaining_sec // 3600
    m = (remaining_sec % 3600) // 60
    is_vip = session.get("web_is_vip", False)

    esc_bot = get_bot_instance(key_code, "escape")
    spr_bot = get_bot_instance(key_code, "sprint")
    return render_template_string(DASHBOARD_HTML, h=h, m=m, is_vip=is_vip, key_code=key_code, esc=esc_bot, spr=spr_bot)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

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

@app.route('/api/game_action', methods=['POST'])
def api_game_action():
    if not check_web_session_valid():
        return jsonify({"success": False, "msg": "Key đã hết hạn hoặc phiên đăng nhập không hợp lệ!"})
    
    data = request.json or {}
    game_type = data.get("game_type")
    action = data.get("action")
    key_code = session.get("active_key")
    is_vip = session.get("web_is_vip", False)
    
    if game_type not in ["escape", "sprint"]:
        return jsonify({"success": False, "msg": "Game không hợp lệ!"})
    
    bot_inst = get_bot_instance(key_code, game_type)

    if action == "save_link":
        link_str = data.get("link", "").strip()
        try:
            parsed_url = urlparse(link_str)
            query_params = parse_qs(parsed_url.query)
            uid_str = query_params.get("userId", [None])[0]
            skey = query_params.get("secretKey", [None])[0]
            if uid_str and skey:
                bot_inst["uid"] = uid_str
                bot_inst["skey"] = skey
                bot_inst["last_log"] = f"Đã kết nối nick UID: {uid_str}"
                return jsonify({"success": True, "msg": f"Lưu thành công! UID: {uid_str}", "uid": uid_str})
        except Exception as e: pass
        return jsonify({"success": False, "msg": "Link không hợp lệ! Vui lòng kiểm tra lại userId và secretKey."})

    elif action == "toggle_bot":
        bot_inst["asset_type"] = data.get("asset_type", "BUILD")
        try:
            bet_val = str(data.get("bet", "1")).replace(",", ".")
            if game_type == "sprint": bot_inst["bet_amount_total"] = bet_val
            else: bot_inst["base_bet"] = float(bet_val)
        except: return jsonify({"success": False, "msg": "Số tiền cược không hợp lệ!"})

        try:
            mr = int(data.get("max_rounds", 0))
            bot_inst["max_rounds"] = mr if is_vip else (mr if mr > 0 else 0)
        except: bot_inst["max_rounds"] = 0

        if is_vip:
            try:
                bot_inst["max_continuous_losses"] = int(data.get("max_losses", 0))
                bot_inst["stop_loss_amount"] = float(str(data.get("stop_loss", 0)).replace(",", "."))
                bot_inst["take_profit_amount"] = float(str(data.get("take_profit", 0)).replace(",", "."))
            except: pass

        if not bot_inst["uid"] or not bot_inst["skey"]:
            return jsonify({"success": False, "msg": "Vui lòng dán Link và bấm Lưu Nick trước khi bật Bot!"})
        
        if not bot_inst["running"]:
            bot_inst["running"] = True
            bot_inst["stop_event"].clear()
            bot_inst["last_log"] = "🚀 Đang khởi động luồng chạy tự động 24/7..."
            if game_type == "escape":
                t = Thread(target=run_eternal_escape_engine, args=(key_code, bot_inst), daemon=True)
            else:
                t = Thread(target=run_eternal_sprint_engine, args=(key_code, bot_inst), daemon=True)
            bot_inst["thread"] = t
            t.start()
            return jsonify({"success": True, "running": True, "msg": "Đã BẬT Bot chạy tự động vĩnh viễn!"})
        else:
            bot_inst["running"] = False
            bot_inst["stop_event"].set()
            bot_inst["last_log"] = "⏹️ Đã dừng Bot theo yêu cầu."
            return jsonify({"success": True, "running": False, "msg": "Đã DỪNG Bot!"})

    elif action == "get_status":
        tot_bets = bot_inst["total_bets"]
        wins = bot_inst["wins"]
        losses = bot_inst["losses"]
        profit = float(bot_inst["total_profit"])
        wr = (wins / tot_bets * 100) if tot_bets > 0 else 0.0
        return jsonify({
            "success": True, "running": bot_inst["running"], "uid": bot_inst["uid"],
            "total_bets": tot_bets, "wins": wins, "losses": losses,
            "win_rate": f"{wr:.1f}%", "total_profit": f"{profit:+.4f}",
            "asset": bot_inst["asset_type"], "last_log": bot_inst["last_log"]
        })

    elif action == "reset_stats":
        bot_inst["total_profit"] = Decimal("0")
        bot_inst["total_bets"] = 0
        bot_inst["wins"] = 0
        bot_inst["losses"] = 0
        bot_inst["streak_loss"] = 0
        bot_inst["last_log"] = "🔄 Đã làm mới thống kê về 0."
        return jsonify({"success": True, "msg": "Đã reset thống kê về 0!"})

    return jsonify({"success": False, "msg": "Thao tác không hợp lệ!"})

def run_eternal_escape_engine(key_code, bot_inst):
    session_req = requests.Session()
    while bot_inst["running"] and not bot_inst["stop_event"].is_set():
        try:
            if bot_inst["max_continuous_losses"] > 0 and bot_inst["streak_loss"] >= bot_inst["max_continuous_losses"]:
                bot_inst["running"] = False; bot_inst["last_log"] = "🛑 Dừng tự động: Thua liên tiếp."; break
            if bot_inst["stop_loss_amount"] > 0 and bot_inst["total_profit"] <= -Decimal(str(bot_inst["stop_loss_amount"])):
                bot_inst["running"] = False; bot_inst["last_log"] = "📉 Dừng tự động: Chạm ngưỡng cắt lỗ."; break
            if bot_inst["take_profit_amount"] > 0 and bot_inst["total_profit"] >= Decimal(str(bot_inst["take_profit_amount"])):
                bot_inst["running"] = False; bot_inst["last_log"] = "🎯 Dừng tự động: Đạt mục tiêu chốt lời!"; break
            if bot_inst["max_rounds"] > 0 and bot_inst["total_bets"] >= bot_inst["max_rounds"]:
                bot_inst["running"] = False; bot_inst["last_log"] = f"🏁 Hoàn thành {bot_inst['max_rounds']} ván cược."; break

            uid = bot_inst["uid"]; skey = bot_inst["skey"]; asset = bot_inst["asset_type"]; amount = float(bot_inst["base_bet"])
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
                "Origin": "https://escapemaster.net", "Referer": f"https://escapemaster.net/battleroyale/?userId={uid}&secretKey={skey}&language=vi-VN",
                "Content-Type": "application/json", "User-Id": str(uid), "User-Login": "login_v2", "User-Secret-Key": skey, "Accept": "application/json"
            }
            room_id = random.choice([1, 2, 3, 4, 5, 6, 7, 8])
            bot_inst["last_log"] = f"⏳ Đang vào phòng #{room_id} và đặt cược {amount} {asset}..."
            
            session_req.post("https://api.escapemaster.net/escape_game/enter_room",
                             json={"asset_type": asset, "user_id": int(uid), "room_id": int(room_id)}, headers=headers, timeout=5)
            res = session_req.post("https://api.escapemaster.net/escape_game/bet",
                                   json={"asset_type": asset, "user_id": int(uid), "room_id": int(room_id), "bet_amount": amount}, headers=headers, timeout=5)
            if res.status_code == 200:
                res_data = res.json()
                if res_data.get("code") == 0:
                    bot_inst["total_bets"] += 1; bot_inst["wins"] += 1; bot_inst["streak_loss"] = 0
                    bet_dec = Decimal(str(amount))
                    bot_inst["total_profit"] += (bet_dec * Decimal("0.5"))
                    bot_inst["last_log"] = f"✅ Cược thành công phòng #{room_id} (+{bet_dec * Decimal('0.5'):.4f} {asset})"
                else:
                    bot_inst["last_log"] = f"⚠️ Phản hồi game: {res_data.get('msg', 'Đang chờ...')}"
            else:
                bot_inst["last_log"] = f"⚠️ Máy chủ bận (HTTP {res.status_code}), đang thử lại..."
        except Exception:
            bot_inst["last_log"] = "🔄 Mất kết nối tạm thời, đang tự động kết nối lại..."

        for _ in range(45):
            if not bot_inst["running"] or bot_inst["stop_event"].is_set(): break
            time.sleep(1)

def run_eternal_sprint_engine(key_code, bot_inst):
    base_api = "https://api.sprintrun.win"
    session_req = requests.Session()
    last_issue = None
    while bot_inst["running"] and not bot_inst["stop_event"].is_set():
        try:
            if bot_inst["max_continuous_losses"] > 0 and bot_inst["streak_loss"] >= bot_inst["max_continuous_losses"]:
                bot_inst["running"] = False; bot_inst["last_log"] = "🛑 Dừng tự động: Thua liên tiếp."; break
            if bot_inst["stop_loss_amount"] > 0 and bot_inst["total_profit"] <= -Decimal(str(bot_inst["stop_loss_amount"])):
                bot_inst["running"] = False; bot_inst["last_log"] = "📉 Dừng tự động: Chạm cắt lỗ."; break
            if bot_inst["take_profit_amount"] > 0 and bot_inst["total_profit"] >= Decimal(str(bot_inst["take_profit_amount"])):
                bot_inst["running"] = False; bot_inst["last_log"] = "🎯 Dừng tự động: Đạt chốt lời!"; break
            if bot_inst["max_rounds"] > 0 and bot_inst["total_bets"] >= bot_inst["max_rounds"]:
                bot_inst["running"] = False; bot_inst["last_log"] = f"🏁 Hoàn thành {bot_inst['max_rounds']} ván cược."; break

            uid = bot_inst["uid"]; skey = bot_inst["skey"]; asset = bot_inst["asset_type"]
            headers = {"accept": "*/*", "content-type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
            r = session_req.get(f"{base_api}/sprint/home?asset={asset}", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get("data", {})
                issue_id = data.get("issue_id"); athletes = data.get("athlete_list", [])
                if issue_id and issue_id != last_issue and len(athletes) >= 3:
                    chosen = [a["id"] for a in random.sample(athletes, 3)]
                    each_bet = (Decimal(str(bot_inst["bet_amount_total"])) / Decimal(3)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
                    for aid in chosen:
                        session_req.post(f"{base_api}/sprint/bet", json={"issue_id": issue_id, "bet_group": "winner", "asset_type": asset, "athlete_id": aid, "bet_amount": float(each_bet)}, headers=headers, timeout=4)
                    bot_inst["total_bets"] += 1; bot_inst["wins"] += 1; last_issue = issue_id
                    bot_inst["last_log"] = f"✅ Đã cược kỳ #{issue_id} ({bot_inst['bet_amount_total']} {asset})"
                else: bot_inst["last_log"] = "⏳ Đang đợi kỳ đua mới..."
        except Exception:
            bot_inst["last_log"] = "🔄 Đang kết nối lại máy chủ Đua Tốc Độ..."

        for _ in range(4):
            if not bot_inst["running"] or bot_inst["stop_event"].is_set(): break
            time.sleep(1)

HOME_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XWORLD VIP AUTOMATION</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body {
            background: #060913;
            background-image: radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.25) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.2) 0px, transparent 50%);
            color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px;
        }
        .card {
            background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 28px; width: 100%; max-width: 440px; padding: 36px 26px; text-align: center;
            box-shadow: 0 30px 60px -15px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255,255,255,0.1);
        }
        .icon-box {
            width: 68px; height: 68px; background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            border-radius: 22px; display: flex; align-items: center; justify-content: center; font-size: 30px; margin: 0 auto 18px;
            box-shadow: 0 15px 30px -5px rgba(99, 102, 241, 0.5); color: #fff; cursor: pointer; user-select: none;
        }
        .badge {
            display: inline-block; background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.3);
            padding: 6px 16px; border-radius: 99px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 14px;
        }
        h2 { font-size: 24px; font-weight: 800; background: linear-gradient(to right, #fff, #cbd5e1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
        p { color: #94a3b8; font-size: 13.5px; line-height: 1.6; margin-bottom: 24px; }
        .btn {
            display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%;
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; text-decoration: none; padding: 15px; border-radius: 16px;
            font-weight: 700; font-size: 14px; box-shadow: 0 12px 24px -6px rgba(79, 70, 229, 0.5); border: none; cursor: pointer; transition: 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn-green { background: linear-gradient(135deg, #10b981 0%, #059669 100%); box-shadow: 0 12px 24px -6px rgba(16, 185, 129, 0.45); }
        .divider { display: flex; align-items: center; text-align: center; color: #475569; font-size: 11px; font-weight: 600; margin: 22px 0; }
        .divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid rgba(255,255,255,0.08); }
        .divider:not(:empty)::before { margin-right: 12px; }
        .divider:not(:empty)::after { margin-left: 12px; }
        .input-group { margin-bottom: 16px; text-align: left; }
        .input-group label { font-size: 11.5px; font-weight: 700; color: #94a3b8; display: block; margin-bottom: 8px; }
        .input-group input {
            width: 100%; padding: 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.1);
            background: rgba(2, 6, 23, 0.6); color: #fff; font-size: 14px; text-align: center; outline: none;
        }
        .key-container { background: rgba(2, 6, 23, 0.7); border: 1.5px dashed #6366f1; padding: 16px; border-radius: 18px; margin-bottom: 16px; }
        .key-text { font-family: 'Courier New', monospace; font-size: 17px; color: #34d399; font-weight: 800; word-break: break-all; margin-bottom: 12px; }
        .btn-copy { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 8px 18px; border-radius: 10px; font-weight: 700; font-size: 12px; cursor: pointer; }
        .error { background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; padding: 12px; border-radius: 12px; font-size: 12.5px; margin-top: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-box" onclick="handleSecretClick()"><i class="fa-solid fa-bolt"></i></div>
        <span class="badge"><i class="fa-solid fa-server"></i> Web App 24/7 Không Dùng Telegram</span>
        <h2>XWORLD AUTOMATION</h2>
        <p>Hệ thống chạy tự động vĩnh viễn trên Web Cloud tốc độ cao.</p>
        
        {% if new_key %}
            <div class="key-container">
                <div class="key-text" id="keyText">{{ new_key }}</div>
                <button class="btn-copy" onclick="copyKey()"><i class="fa-regular fa-copy"></i> Sao Chép Mã Key</button>
            </div>
        {% else %}
            <a href="/get_link4m" class="btn"><i class="fa-solid fa-gift"></i> NHẬN KEY MIỄN PHÍ (24H)</a>
        {% endif %}

        <div class="divider">HOẶC ĐĂNG NHẬP</div>
        <div class="input-group">
            <label><i class="fa-solid fa-key" style="color: #818cf8;"></i> NHẬP MÃ BẢN QUYỀN / CODE VIP:</label>
            <input type="text" id="keyInput" value="{{ new_key }}" placeholder="VD: KEY-XW-XXXXXXXX hoặc VIP-..." autocomplete="off">
        </div>
        <button class="btn btn-green" onclick="verifyAndLogin()"><i class="fa-solid fa-right-to-bracket"></i> KÍCH HOẠT & VÀO TOOL</button>
        {% if error %} <div class="error"><i class="fa-solid fa-circle-exclamation"></i> {{ error }}</div> {% endif %}
    </div>
    <script>
        let clickCount = 0;
        function handleSecretClick() {
            clickCount++;
            if (clickCount >= 10) { window.location.href = "/quan-ly-bi-mat-dunghoet"; }
            setTimeout(() => { clickCount = 0; }, 3000);
        }
        function copyKey() {
            navigator.clipboard.writeText(document.getElementById("keyText").innerText).then(() => { alert("Đã sao chép key!"); });
        }
        function verifyAndLogin() {
            const key = document.getElementById("keyInput").value.trim();
            if(!key) { alert("Vui lòng nhập mã key!"); return; }
            fetch("/verify_key_ajax", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ key: key })
            }).then(res => res.json()).then(data => {
                if(data.success) { window.location.href = "/dashboard"; }
                else { alert("⚠️ " + data.msg); }
            }).catch(() => alert("Lỗi kết nối máy chủ!"));
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
    <title>Bảng Điều Khiển Auto - XWorld</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body {
            background: #060913;
            background-image: radial-gradient(at 15% 10%, rgba(99, 102, 241, 0.18) 0px, transparent 50%), radial-gradient(at 85% 90%, rgba(16, 185, 129, 0.15) 0px, transparent 50%);
            color: #f8fafc; padding: 16px; min-height: 100vh;
        }
        .container {
            max-width: 560px; margin: 0 auto; background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(24px);
            border: 1px solid rgba(255, 255, 255, 0.08); padding: 22px; border-radius: 24px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.8);
        }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 16px; margin-bottom: 20px; }
        .header-title { display: flex; align-items: center; gap: 10px; }
        .header-title h2 { font-size: 16px; font-weight: 800; color: #fff; }
        .vip-badge { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 800; }
        .header-right { display: flex; align-items: center; gap: 8px; }
        .time-pill { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; padding: 5px 10px; border-radius: 99px; font-size: 11px; font-weight: 700; }
        .logout { color: #f87171; text-decoration: none; font-size: 12px; font-weight: 700; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 6px 10px; border-radius: 10px; }
        
        .tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: rgba(2, 6, 23, 0.6); padding: 6px; border-radius: 16px; margin-bottom: 20px; }
        .tab-btn { padding: 12px; background: transparent; border: none; color: #94a3b8; font-weight: 700; border-radius: 12px; cursor: pointer; text-align: center; font-size: 13px; transition: 0.25s; }
        .tab-btn.active { background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; box-shadow: 0 8px 16px -4px rgba(99, 102, 241, 0.5); }
        
        .panel { display: none; }
        .panel.active { display: block; }
        .card-section { background: rgba(2, 6, 23, 0.45); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 18px; padding: 16px; margin-bottom: 16px; }
        .form-group { margin-bottom: 14px; }
        .form-group label { display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 7px; }
        .input-row { display: flex; gap: 8px; }
        input, select {
            width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(15, 23, 42, 0.9); color: #fff; font-size: 13.5px; font-weight: 600; outline: none;
        }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .btn-save { background: #3b82f6; color: #fff; border: none; padding: 0 18px; border-radius: 12px; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; }
        .btn-main {
            width: 100%; padding: 16px; border-radius: 16px; border: none; font-weight: 800; font-size: 14.5px;
            cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 10px; text-transform: uppercase; transition: 0.2s;
        }
        .btn-start { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #fff; box-shadow: 0 12px 24px -6px rgba(16, 185, 129, 0.5); }
        .btn-stop { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: #fff; box-shadow: 0 12px 24px -6px rgba(239, 68, 68, 0.5); }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 16px; }
        .stat-item { background: rgba(2, 6, 23, 0.65); border: 1px solid rgba(255, 255, 255, 0.06); padding: 12px 14px; border-radius: 14px; }
        .stat-item .label { font-size: 11px; color: #94a3b8; font-weight: 600; margin-bottom: 4px; }
        .stat-item .val { font-size: 16px; font-weight: 800; color: #fff; }
        .live-log {
            margin-top: 14px; background: rgba(2, 6, 23, 0.8); border: 1px solid rgba(99, 102, 241, 0.25);
            padding: 11px 14px; border-radius: 12px; font-size: 12px; color: #a5b4fc; display: flex; align-items: center; gap: 8px; font-weight: 500;
        }
        .dot-live { width: 8px; height: 8px; border-radius: 50%; background: #ef4444; flex-shrink: 0; }
        .dot-live.active { background: #10b981; box-shadow: 0 0 8px #10b981; }
        .btn-reset { width: 100%; margin-top: 12px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1; padding: 10px; border-radius: 12px; font-size: 12px; font-weight: 700; cursor: pointer; }
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid #38bdf8; color: #fff; padding: 10px 20px; border-radius: 99px; font-size: 13px; font-weight: 700; z-index: 9999; display: none; }
    </style>
</head>
<body>
    <div class="toast" id="toastBox">Thông báo</div>
    <div class="container">
        <div class="header">
            <div class="header-title">
                <div style="width: 36px; height: 36px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;"><i class="fa-solid fa-robot"></i></div>
                <div>
                    <h2>XWORLD AUTO {% if is_vip %}<span class="vip-badge">VIP</span>{% endif %}</h2>
                    <span style="font-size: 10.5px; color: #64748b; font-family: monospace;">{{ key_code }}</span>
                </div>
            </div>
            <div class="header-right">
                <span class="time-pill"><i class="fa-regular fa-clock"></i> {{ h }}h {{ m }}p</span>
                <a href="/logout" class="logout" title="Đăng xuất"><i class="fa-solid fa-power-off"></i></a>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('escape', this)">🕹️ Vua Thoát Hiểm</button>
            <button class="tab-btn" onclick="switchTab('sprint', this)">🏃 Đua Tốc Độ</button>
        </div>

        <!-- PANEL VUA THOÁT HIỂM -->
        <div id="panel-escape" class="panel active">
            <div class="card-section">
                <div class="form-group">
                    <label>
                        <span><i class="fa-solid fa-user-check" style="color:#38bdf8"></i> Link Game Tài Khoản:</span>
                        <span id="escape_uid_badge" style="color: #34d399;">{% if esc.uid %}UID: {{ esc.uid }}{% else %}Chưa lưu nick{% endif %}</span>
                    </label>
                    <div class="input-row">
                        <input type="text" id="escape_link" placeholder="Dán link có userId=...&secretKey=...">
                        <button class="btn-save" onclick="saveLink('escape')"><i class="fa-solid fa-floppy-disk"></i> Lưu</button>
                    </div>
                </div>

                <div class="grid-2">
                    <div class="form-group">
                        <label>Loại Tiền Cược:</label>
                        <select id="escape_asset">
                            <option value="BUILD" {% if esc.asset_type == 'BUILD' %}selected{% endif %}>BUILD</option>
                            <option value="WORLD" {% if esc.asset_type == 'WORLD' %}selected{% endif %}>WORLD</option>
                            <option value="USDT" {% if esc.asset_type == 'USDT' %}selected{% endif %}>USDT</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Tiền Cược / Ván:</label>
                        <input type="number" id="escape_bet" value="{{ esc.base_bet }}" step="0.1" min="0.1">
                    </div>
                </div>

                <div class="form-group">
                    <label>Giới Hạn Số Ván (0 = Vĩnh Viễn):</label>
                    <input type="number" id="escape_max_rounds" value="{{ esc.max_rounds }}" min="0">
                </div>

                {% if is_vip %}
                <div class="grid-2">
                    <div class="form-group"><label>Cắt Lỗ (0 = Tắt):</label><input type="number" id="escape_stop_loss" value="{{ esc.stop_loss_amount }}" step="0.1"></div>
                    <div class="form-group"><label>Chốt Lời (0 = Tắt):</label><input type="number" id="escape_take_profit" value="{{ esc.take_profit_amount }}" step="0.1"></div>
                </div>
                {% endif %}
            </div>

            <button id="btn_escape_toggle" class="btn-main {% if esc.running %}btn-stop{% else %}btn-start{% endif %}" onclick="toggleBot('escape')">
                {% if esc.running %}<i class="fa-solid fa-stop"></i> DỪNG CHẠY TỰ ĐỘNG{% else %}<i class="fa-solid fa-play"></i> BẬT AUTO VĨNH VIỄN{% endif %}
            </button>

            <div class="live-log">
                <div id="escape_dot" class="dot-live {% if esc.running %}active{% endif %}"></div>
                <span id="escape_log_text">{{ esc.last_log }}</span>
            </div>

            <div class="stats-grid">
                <div class="stat-item"><div class="label">Trạng Thái</div><div class="val" id="escape_status_text" style="color: {% if esc.running %}#34d399{% else %}#f87171{% endif %};">{% if esc.running %}Đang Chạy 24/7{% else %}Đang Dừng{% endif %}</div></div>
                <div class="stat-item"><div class="label">Tổng Ván Cược</div><div class="val" id="escape_tot_bets" style="color: #38bdf8;">{{ esc.total_bets }}</div></div>
                <div class="stat-item"><div class="label">Thắng / Thua</div><div class="val" id="escape_win_loss">{{ esc.wins }} / {{ esc.losses }}</div></div>
                <div class="stat-item"><div class="label">Tổng Lợi Nhuận</div><div class="val" id="escape_profit" style="color: #34d399;">+0.0000 {{ esc.asset_type }}</div></div>
            </div>
            <button class="btn-reset" onclick="resetStats('escape')"><i class="fa-solid fa-rotate-right"></i> Làm Mới Thống Kê</button>
        </div>

        <!-- PANEL ĐUA TỐC ĐỘ -->
        <div id="panel-sprint" class="panel">
            <div class="card-section">
                <div class="form-group">
                    <label>
                        <span><i class="fa-solid fa-user-check" style="color:#38bdf8"></i> Link Game Tài Khoản:</span>
                        <span id="sprint_uid_badge" style="color: #34d399;">{% if spr.uid %}UID: {{ spr.uid }}{% else %}Chưa lưu nick{% endif %}</span>
                    </label>
                    <div class="input-row">
                        <input type="text" id="sprint_link" placeholder="Dán link có userId=...&secretKey=...">
                        <button class="btn-save" onclick="saveLink('sprint')"><i class="fa-solid fa-floppy-disk"></i> Lưu</button>
                    </div>
                </div>

                <div class="grid-2">
                    <div class="form-group">
                        <label>Loại Tiền Cược:</label>
                        <select id="sprint_asset">
                            <option value="BUILD" {% if spr.asset_type == 'BUILD' %}selected{% endif %}>BUILD</option>
                            <option value="WORLD" {% if spr.asset_type == 'WORLD' %}selected{% endif %}>WORLD</option>
                            <option value="USDT" {% if spr.asset_type == 'USDT' %}selected{% endif %}>USDT</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Tổng Cược / Ván:</label>
                        <input type="number" id="sprint_bet" value="{{ spr.bet_amount_total }}" step="0.1" min="0.1">
                    </div>
                </div>

                <div class="form-group">
                    <label>Giới Hạn Số Ván (0 = Vĩnh Viễn):</label>
                    <input type="number" id="sprint_max_rounds" value="{{ spr.max_rounds }}" min="0">
                </div>
            </div>

            <button id="btn_sprint_toggle" class="btn-main {% if spr.running %}btn-stop{% else %}btn-start{% endif %}" onclick="toggleBot('sprint')">
                {% if spr.running %}<i class="fa-solid fa-stop"></i> DỪNG CHẠY TỰ ĐỘNG{% else %}<i class="fa-solid fa-play"></i> BẬT AUTO VĨNH VIỄN{% endif %}
            </button>

            <div class="live-log">
                <div id="sprint_dot" class="dot-live {% if spr.running %}active{% endif %}"></div>
                <span id="sprint_log_text">{{ spr.last_log }}</span>
            </div>

            <div class="stats-grid">
                <div class="stat-item"><div class="label">Trạng Thái</div><div class="val" id="sprint_status_text" style="color: {% if spr.running %}#34d399{% else %}#f87171{% endif %};">{% if spr.running %}Đang Chạy 24/7{% else %}Đang Dừng{% endif %}</div></div>
                <div class="stat-item"><div class="label">Tổng Ván Cược</div><div class="val" id="sprint_tot_bets" style="color: #38bdf8;">{{ spr.total_bets }}</div></div>
                <div class="stat-item"><div class="label">Thắng / Thua</div><div class="val" id="sprint_win_loss">{{ spr.wins }} / {{ spr.losses }}</div></div>
                <div class="stat-item"><div class="label">Tổng Lợi Nhuận</div><div class="val" id="sprint_profit" style="color: #34d399;">+0.0000 {{ spr.asset_type }}</div></div>
            </div>
            <button class="btn-reset" onclick="resetStats('sprint')"><i class="fa-solid fa-rotate-right"></i> Làm Mới Thống Kê</button>
        </div>
    </div>

    <script>
        function showToast(msg) {
            const box = document.getElementById('toastBox');
            box.innerText = msg; box.style.display = 'block';
            setTimeout(() => { box.style.display = 'none'; }, 2800);
        }
        function switchTab(game, btnEl) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('panel-' + game).classList.add('active');
            btnEl.classList.add('active');
        }
        function saveLink(game) {
            const link = document.getElementById(game + '_link').value.trim();
            if(!link) { showToast("⚠️ Vui lòng dán link trước!"); return; }
            fetch('/api/game_action', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_type: game, action: 'save_link', link: link })
            }).then(res => res.json()).then(data => {
                showToast(data.success ? "✅ " + data.msg : "❌ " + data.msg);
                if(data.success && data.uid) { document.getElementById(game + '_uid_badge').innerText = "UID: " + data.uid; }
            });
        }
        function toggleBot(game) {
            const asset = document.getElementById(game + '_asset').value;
            const bet = document.getElementById(game + '_bet').value;
            const mr = document.getElementById(game + '_max_rounds');
            const sl = document.getElementById(game + '_stop_loss');
            const tp = document.getElementById(game + '_take_profit');

            fetch('/api/game_action', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    game_type: game, action: 'toggle_bot', asset_type: asset, bet: bet,
                    max_rounds: mr ? mr.value : 0, stop_loss: sl ? sl.value : 0, take_profit: tp ? tp.value : 0
                })
            }).then(res => res.json()).then(data => {
                showToast(data.success ? "🚀 " + data.msg : "⚠️ " + data.msg);
                if(data.success) updateUIState(game, data.running);
            });
        }
        function updateUIState(game, running) {
            const btn = document.getElementById('btn_' + game + '_toggle');
            const statusText = document.getElementById(game + '_status_text');
            const dot = document.getElementById(game + '_dot');
            if(running) {
                btn.className = "btn-main btn-stop"; btn.innerHTML = '<i class="fa-solid fa-stop"></i> DỪNG CHẠY TỰ ĐỘNG';
                statusText.innerText = "Đang Chạy 24/7"; statusText.style.color = "#34d399"; dot.classList.add('active');
            } else {
                btn.className = "btn-main btn-start"; btn.innerHTML = '<i class="fa-solid fa-play"></i> BẬT AUTO VĨNH VIỄN';
                statusText.innerText = "Đang Dừng"; statusText.style.color = "#f87171"; dot.classList.remove('active');
            }
        }
        function resetStats(game) {
            fetch('/api/game_action', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_type: game, action: 'reset_stats' })
            }).then(res => res.json()).then(data => { showToast("🔄 " + data.msg); });
        }
        setInterval(() => {
            ['escape', 'sprint'].forEach(game => {
                fetch('/api/game_action', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ game_type: game, action: 'get_status' })
                }).then(res => res.json()).then(data => {
                    if(data.success) {
                        document.getElementById(game + '_tot_bets').innerText = data.total_bets;
                        document.getElementById(game + '_win_loss').innerText = data.wins + " / " + data.losses + " (" + data.win_rate + ")";
                        document.getElementById(game + '_profit').innerText = data.total_profit + " " + data.asset;
                        document.getElementById(game + '_log_text').innerText = data.last_log;
                        if(data.uid) document.getElementById(game + '_uid_badge').innerText = "UID: " + data.uid;
                        updateUIState(game, data.running);
                    }
                }).catch(() => {});
            });
        }, 1500);
        setInterval(() => { fetch('/ping').catch(() => {}); }, 25000);
    </script>
</body>
</html>
"""

ADMIN_LOGIN_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Đăng Nhập Quản Trị</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body { background: #060913; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 15px; }
    .card { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); padding: 32px 24px; border-radius: 24px; width: 100%; max-width: 380px; text-align: center; }
    h2 { color: #fff; margin-bottom: 22px; font-size: 20px; font-weight: 800; }
    input { width: 100%; padding: 13px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(2,6,23,0.7); color: #fff; margin-bottom: 14px; font-size: 14px; text-align: center; outline: none; }
    .btn { width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; border: none; padding: 14px; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 14px; }
    .error { color: #f87171; font-size: 12.5px; margin-bottom: 14px; }
    .back { display: inline-block; margin-top: 16px; color: #64748b; font-size: 12px; text-decoration: none; }
</style></head>
<body><div class="card">
    <h2><i class="fa-solid fa-shield-halved" style="color:#6366f1"></i> Quản Trị Hệ Thống</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="text" name="username" placeholder="Tài khoản..." required autocomplete="off">
        <input type="password" name="password" placeholder="Mật khẩu..." required>
        <button type="submit" class="btn">Đăng Nhập</button>
    </form>
    <a href="/" class="back"><i class="fa-solid fa-arrow-left"></i> Quay lại trang chủ</a>
</div></body></html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Quản Lý Hệ Thống VIP</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body { background: #060913; color: #f8fafc; padding: 14px; }
    .container { max-width: 1050px; margin: 0 auto; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(255,255,255,0.08); padding: 20px; border-radius: 20px; }
    .header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 14px; }
    h2 { color: #fff; font-size: 16px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
    .logout { color: #f87171; text-decoration: none; font-size: 12px; font-weight: 700; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 7px 12px; border-radius: 10px; }
    .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 18px; }
    .stat-card { background: rgba(2, 6, 23, 0.6); border: 1px solid rgba(255,255,255,0.06); padding: 14px; border-radius: 14px; text-align: center; }
    .stat-card h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; }
    .stat-card span { font-size: 20px; font-weight: 800; color: #38bdf8; }
    .table-responsive { width: 100%; overflow-x: auto; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); }
    table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 650px; }
    th, td { padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left; vertical-align: middle; white-space: nowrap; }
    th { color: #94a3b8; font-weight: 700; background: rgba(2, 6, 23, 0.8); }
    code { background: rgba(2, 6, 23, 0.8); padding: 4px 8px; border-radius: 6px; color: #34d399; font-family: monospace; font-weight: 700; }
    .btn-action { border: none; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 11px; font-weight: 700; text-decoration: none; display: inline-flex; }
    .btn-add-time { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .btn-sub-time { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .btn-del { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .btn-del-all { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 9px 14px; border-radius: 10px; font-weight: 700; font-size: 12px; text-decoration: none; }
    .btn-copy-code { background: rgba(99, 102, 241, 0.2); color: #a5b4fc; }
    .btn-add { background: #10b981; color: #fff; border: none; padding: 9px 16px; border-radius: 10px; font-weight: 700; font-size: 12px; cursor: pointer; }
    .btn-vip { background: #f59e0b; color: #000; border: none; padding: 9px 16px; border-radius: 10px; font-weight: 800; font-size: 12px; cursor: pointer; }
    .box-create { background: rgba(2, 6, 23, 0.6); padding: 14px; border-radius: 14px; margin-bottom: 18px; display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; border: 1px solid rgba(255,255,255,0.06); }
    .box-create input { padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); background: #0f172a; color: #fff; font-size: 13px; width: 85px; margin-top: 4px; display: block; }
    .input-time { padding: 5px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: #0f172a; color: #fff; width: 55px; text-align: center; }
    .toast { position: fixed; bottom: 20px; right: 20px; background: #10b981; color: white; padding: 10px 18px; border-radius: 10px; font-weight: 700; display: none; z-index: 1000; font-size: 13px; }
</style></head>
<body>
    <div class="toast" id="toastMsg">✅ Thành công!</div>
    <div class="container">
        <div class="header-flex">
            <h2><i class="fa-solid fa-crown" style="color:#f59e0b"></i> QUẢN TRỊ KEY & HỆ THỐNG</h2>
            <a href="/quan-ly-bi-mat-dunghoet/logout" class="logout"><i class="fa-solid fa-right-from-bracket"></i> Thoát</a>
        </div>
        <div class="stats-grid">
            <div class="stat-card"><h4>Tổng số Key</h4><span>{{ total_keys_count }}</span></div>
            <div class="stat-card"><h4>Đã kích hoạt</h4><span style="color: #f87171;">{{ used_keys_count }}</span></div>
            <div class="stat-card"><h4>Chưa dùng</h4><span style="color: #34d399;">{{ unused_keys_count }}</span></div>
        </div>
        <div class="box-create">
            <div><label style="font-size: 11px; color: #94a3b8;">Thời hạn (Giờ):</label><input type="number" id="customHours" value="24" min="1"></div>
            <div><label style="font-size: 11px; color: #94a3b8;">Số lượng:</label><input type="number" id="customQty" value="1" min="1" max="100"></div>
            <div><label style="font-size: 11px; color: #94a3b8;">Số máy dùng:</label><input type="number" id="maxUses" value="1" min="1" max="1000"></div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="btn-add" onclick="createCustomKey(false)"><i class="fa-solid fa-plus"></i> Tạo Key Thường</button>
                <button class="btn-vip" onclick="createCustomKey(true)"><i class="fa-solid fa-crown"></i> Tạo Code VIP</button>
                <a href="/quan-ly-bi-mat-dunghoet/delete_all" class="btn-del-all" onclick="return confirm('Xóa sạch kho key?')">Xóa Sạch</a>
            </div>
        </div>
        <div class="table-responsive">
            <table>
                <tr>
                    <th>Mã Key / VIP</th><th>Cấp Độ</th><th>Cộng/Trừ Giờ</th><th>Thời Gian Còn</th><th>Lượt Dùng</th><th>Thao Tác</th>
                </tr>
                {% for k, info in keys.items() %}
                {% set expire_at = info.get('expire_at', 0) %}
                {% set remain = (expire_at - now) if expire_at and expire_at > now else 0 %}
                {% set rem_h = (remain // 3600)|int %}
                {% set rem_m = ((remain % 3600) // 60)|int %}
                {% set used_list = info.get('used_by', []) %}
                <tr>
                    <td><code>{{ k }}</code></td>
                    <td>{% if info.get('is_vip') %}<b style="color:#f59e0b">VIP 👑</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
                    <td>
                        <div style="display: flex; gap: 4px;">
                            <input type="number" id="time_{{ k }}" value="24" class="input-time">
                            <button class="btn-action btn-add-time" onclick="modifyKeyTime('{{ k }}', 'add')">+</button>
                            <button class="btn-action btn-sub-time" onclick="modifyKeyTime('{{ k }}', 'sub')">-</button>
                        </div>
                    </td>
                    <td>{% if expire_at and expire_at > now %}<b style="color: #38bdf8;">{{ rem_h }}h {{ rem_m }}p</b>{% else %}<small style="color: #94a3b8;">Chưa kích hoạt</small>{% endif %}</td>
                    <td><span>{{ used_list|length }}/{{ info.get('max_uses', 1) }}</span></td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn-action btn-copy-code" onclick="navigator.clipboard.writeText('{{ k }}')">Copy</button>
                            <a href="/quan-ly-bi-mat-dunghoet/delete?key={{ k }}" class="btn-action btn-del" onclick="return confirm('Xóa key này?')">Xóa</a>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
    <script>
    function createCustomKey(isVip) {
        let hours = document.getElementById("customHours").value;
        let qty = document.getElementById("customQty").value;
        let maxUses = document.getElementById("maxUses").value;
        fetch("/quan-ly-bi-mat-dunghoet/create_custom_key", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hours: hours, quantity: qty, max_uses: maxUses, is_vip: isVip })
        }).then(res => res.json()).then(data => { if(data.success) { location.reload(); } });
    }
    function modifyKeyTime(key, mode) {
        let hours = document.getElementById("time_" + key).value;
        fetch("/quan-ly-bi-mat-dunghoet/modify_key_time", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: key, hours: hours, mode: mode })
        }).then(res => res.json()).then(data => { if(data.success) { location.reload(); } });
    }
    </script>
</body></html>
"""

MAINTENANCE_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Bảo Trì</title></head>
<body style="background:#060913;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;text-align:center;">
    <div><h1>🛠️ HỆ THỐNG BẢO TRÌ</h1><p>{{ notice }}</p></div>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
