import os
import sys
import json
import time
import random
import base64
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

try:
    import websocket
except ImportError:
    os.system(f"{sys.executable} -m pip install websocket-client")
    import websocket

# =========================================================
# CẤU HÌNH HỆ THỐNG FLASK & BẢO MẬT
# =========================================================
app = Flask(__name__)
app.secret_key = "dung_license_secret_key_1612012"

ADMIN_USERNAME = "dunghoet"
ADMIN_PASSWORD = "10091990dung"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

ip_request_history = {}
DB_FILE = "system_db.json"
db_lock = Lock()

# =========================================================
# 🐙 ĐỒNG BỘ GITHUB API (CHẠY NGẦM KHÔNG TREO WEB)
# =========================================================
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
            content_b64 = res.json().get("content", "")
            content_bytes = base64.b64decode(content_b64)
            with db_lock:
                with open(DB_FILE, "wb") as f:
                    f.write(content_bytes)
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
        get_res = requests.get(url, headers=headers, timeout=3)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None
        content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        payload = {"message": "Auto-sync system_db.json from Web Engine", "content": content_b64}
        if sha: payload["sha"] = sha
        requests.put(url, json=payload, headers=headers, timeout=3)
    except Exception as e:
        print(f"❌ Lỗi push lên GitHub: {e}", flush=True)

Thread(target=sync_pull_from_github, daemon=True).start()

# =========================================================
# 🗄️ QUẢN LÝ DỮ LIỆU & DATABASE
# =========================================================
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
                if "banned_users" not in record: record["banned_users"] = {}
                if "maintenance" not in record: record["maintenance"] = {"active": False, "notice": ""}
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
    except: return False

def save_key_to_cloud(key_code, data):
    db = load_system_db()
    if "keys" not in db: db["keys"] = {}
    db["keys"][key_code] = {
        "status": data.get("status", "chua_dung"),
        "used_by": data.get("used_by", []),
        "created_at": data.get("created_at", time.time()),
        "expire_at": data.get("expire_at"),
        "duration_hours": data.get("duration_hours", 24),
        "is_vip": bool(data.get("is_vip", False)),
        "max_uses": int(data.get("max_uses", 1)),
        "total_bets_count": int(data.get("total_bets_count", 0))
    }
    return save_system_db(db)

def verify_key_web(key_code):
    db = load_system_db()
    keys_db = db.get("keys", {})
    if key_code not in keys_db:
        return False, "Mã Key không tồn tại trên hệ thống!"
    k_data = keys_db[key_code]
    now = time.time()
    duration_secs = int(k_data.get("duration_hours", 24) * 3600)
    if not k_data.get("expire_at"):
        k_data["expire_at"] = now + duration_secs
        save_system_db(db)
    if now > k_data.get("expire_at"):
        return False, "Key này đã hết hạn sử dụng!"
    return True, "Thành công"

# =========================================================
# 🎮 ENGINE CHẠY 3 GAME NGẦM (ESCAPE MASTER, SPRINTRUN, WINHASH)
# =========================================================
active_sessions_state = {}

def get_session_state(session_id):
    if session_id not in active_sessions_state:
        active_sessions_state[session_id] = {
            "escape": {"running": False, "logs": [], "stats": {"wins": 0, "losses": 0, "profit": 0.0}},
            "sprint": {"running": False, "logs": [], "stats": {"wins": 0, "losses": 0, "profit": 0.0}},
            "winhash": {"running": False, "logs": [], "stats": {"wins": 0, "losses": 0, "profit": 0.0}}
        }
    return active_sessions_state[session_id]

# --- 1. ESCAPE MASTER ENGINE ---
def run_escape_master_engine(session_id, uid, skey, base_bet, loss_threshold, skip_rounds, multiplier):
    state = get_session_state(session_id)["escape"]
    state["running"] = True
    state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] Khởi động Escape Master cho UID: {uid}")
    
    ASSET_TYPE = "BUILD"
    WS_URL = "wss://api.escapemaster.net/escape_master/ws"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Origin": "https://escapemaster.net"})
    
    rt = {"uid": int(uid), "skey": skey, "ws": None, "has_bet": False, "betting_id": None, "curr_id": None}
    cb = float(base_bet); cl = 0; tp = 0.0

    def H():
        return {"Content-Type": "application/json", "user-id": str(rt["uid"]), "user-login": "login_v2", "user-secret-key": rt["skey"], "Accept": "application/json"}

    def api_post(url, data):
        try:
            r = session.post(url, json=data, headers=H(), timeout=10)
            if r.status_code == 200: return r.json()
        except: pass
        return {}

    def on_msg(ws, msg):
        nonlocal cb, cl, tp
        if not state["running"]: return
        try:
            d = json.loads(msg); mt = d.get("msg_type", "")
            if mt == "notify_count_down":
                iid = d.get("issue_id"); cd = d.get("count_down", 0)
                if rt["curr_id"] != iid and not rt["has_bet"]:
                    rt["curr_id"] = iid; rt["betting_id"] = iid
                    room = random.randint(1, 8)
                    api_post("https://api.escapemaster.net/escape_game/enter_room", {"asset_type": ASSET_TYPE, "user_id": rt["uid"], "room_id": room})
                    res = api_post("https://api.escapemaster.net/escape_game/bet", {"asset_type": ASSET_TYPE, "user_id": rt["uid"], "room_id": room, "bet_amount": cb})
                    if res.get("code") == 0:
                        rt["has_bet"] = True
                        state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [Escape] Đặt cược phòng {room} số tiền {cb}")
            elif mt == "notify_result":
                iid = d.get("issue_id")
                if rt["has_bet"] and iid == rt["betting_id"]:
                    aw = float(d.get("award_amount", 0)); bt = float(d.get("bet_amount", 0))
                    prof = aw - bt
                    tp += prof; state["stats"]["profit"] = round(tp, 4)
                    if aw > bt:
                        state["stats"]["wins"] += 1; cl = 0; cb = float(base_bet)
                        state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [Escape] WIN +{prof:.4f}")
                    else:
                        state["stats"]["losses"] += 1; cl += 1
                        if cl >= loss_threshold: cb = float(base_bet) # Reset hoặc skip
                        else: cb *= float(multiplier)
                        state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [Escape] LOSE {prof:.4f}")
                    rt["has_bet"] = False; rt["betting_id"] = None
            elif mt == "notify_heartbeat":
                ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
        except: pass

    def on_open(ws):
        ws.send(json.dumps({"msg_type": "handle_enter_game", "asset_type": ASSET_TYPE, "user_id": rt["uid"], "user_secret_key": rt["skey"]}))

    try:
        ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_msg)
        rt["ws"] = ws
        while state["running"]:
            ws.run_forever(ping_interval=15, ping_timeout=10)
            time.sleep(2)
    except Exception as e:
        state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [Escape Error] {e}")
    state["running"] = False

# --- 2. SPRINTRUN ENGINE ---
def run_sprintrun_engine(session_id, uid, skey, total_build, lose_limit, rest_rounds, mult, asset):
    state = get_session_state(session_id)["sprint"]
    state["running"] = True
    state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] Khởi động SprintRun cho UID: {uid}")
    
    BASE_API = "https://api.sprintrun.win"
    headers = {"accept": "*/*", "content-type": "application/json", "origin": "https://sprintrun.win", "referer": "https://sprintrun.win/", "user-agent": "Mozilla/5.0", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    
    tw = tl = sl = 0; cb = Decimal(str(total_build)); bb = cb; total_profit = Decimal("0")
    session = requests.Session()

    while state["running"]:
        try:
            r = session.get(f"{BASE_API}/sprint/home?asset={asset}", headers=headers, timeout=10)
            if r.status_code != 200:
                time.sleep(3); continue
            d = r.json().get("data", {}); iid = d.get("issue_id"); exp = int(d.get("expire_seconds", 50)); ath = d.get("athlete_list", [])
            if not iid or len(ath) < 3:
                time.sleep(2); continue
            if sl >= lose_limit:
                state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [SprintRun] Thua liên tiếp {sl}, nghỉ {rest_rounds} phiên...")
                time.sleep(rest_rounds * 15)
                sl = 0; continue

            chosen = random.sample(ath, 3); each = (cb / Decimal(3)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            for a in chosen:
                session.post(f"{BASE_API}/sprint/bet", json={"issue_id": iid, "bet_group": "winner", "asset_type": asset, "athlete_id": a["id"], "bet_amount": float(each)}, headers=headers, timeout=5)
                time.sleep(0.2)
            
            state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [SprintRun] Đã cược phiên #{iid}, tổng: {each*3}")
            time.sleep(exp)

            win = None
            for _ in range(20):
                res_r = session.get(f"{BASE_API}/sprint/issue_result?issue={iid}&asset={asset}", headers=headers, timeout=5)
                if res_r.status_code == 200:
                    rank = res_r.json().get("data", {}).get("athlete_rank", [])
                    if rank: win = rank[0]; break
                time.sleep(1)

            total = each * 3
            if win in [a["id"] for a in chosen]:
                prof = each * 5 - total; tw += 1; sl = 0; cb = bb
                total_profit += prof
                state["stats"]["wins"] += 1; state["stats"]["profit"] = float(total_profit)
                state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [SprintRun] WIN +{prof}")
            else:
                tl += 1; sl += 1
                total_profit -= total
                cb = (cb * Decimal(str(mult))).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
                state["stats"]["losses"] += 1; state["stats"]["profit"] = float(total_profit)
                state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [SprintRun] LOSE -{total}, nhân cược lên {cb}")
            time.sleep(2)
        except Exception as e:
            state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [SprintRun Error] {e}")
            time.sleep(5)
    state["running"] = False

# --- 3. WINHASH ENGINE ---
def run_winhash_engine(session_id, uid, skey, total_build, mult, lose_count, rest_stop, asset):
    state = get_session_state(session_id)["winhash"]
    state["running"] = True
    state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] Khởi động WinHash cho UID: {uid}")
    
    H = {"accept": "*/*", "content-type": "application/json", "user-agent": "Mozilla/5.0", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey, "country-code": "vn"}
    BASE = "https://api.winhash.net/lucky_game/v2"
    cur = float(total_build) / 2; losses = 0; rest = 0; total_profit = 0.0

    def current():
        try:
            r = requests.get(f"https://api.winhash.net/lucky_game/home?game_id=1&asset={asset}", headers=H, timeout=10)
            d = r.json().get("data", {}); items = d.get("bet_section", {}).get("sum_in_range", {}).get("items", [])
            small = next((x for x in items if x.get("props", {}).get("value") == [3, 9]), None)
            big = next((x for x in items if x.get("props", {}).get("value") == [12, 18]), None)
            return d.get("issue_id"), small, big, int(d.get("expire_seconds", 50))
        except: return None, None, None, 50

    while state["running"]:
        if rest > 0:
            state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash] Nghỉ {rest} phiên...")
            rest -= 1; time.sleep(15); continue
        
        iid, sm, bg, exp = current()
        if not iid or not sm or not bg:
            time.sleep(5); continue

        try:
            r = requests.post(f"{BASE}/create_order", headers=H, json={"game_id": 1, "issue_id": iid, "items": [{"id": sm["id"], "amount": str(cur), "asset": asset}, {"id": bg["id"], "amount": str(cur), "asset": asset}]}, timeout=10)
            if r.status_code != 200:
                state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash] Gửi cược thất bại HTTP {r.status_code}")
                time.sleep(10); continue
            
            state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash] Đã đặt cược phiên #{iid} mức {cur}")
            time.sleep(exp)

            result = None
            for _ in range(6):
                res_r = requests.get("https://api.winhash.net/lucky_game/my_orders", params={"game_id": 1, "page": 1, "page_size": 15, "asset": asset, "game": "hash_lotto"}, headers=H, timeout=10)
                orders = res_r.json().get("data", {}).get("orders", [])
                for o in orders:
                    if str(o.get("issue_id")) == str(iid):
                        st = o.get("state", {})
                        if st.get("state") == "finish":
                            raw = st.get("lucky_data"); lucky = json.loads(raw) if isinstance(raw, str) else raw
                            result = {"lucky": lucky, "is_hit": o.get("is_hit", False), "hit_amount": o.get("hit_amount", 0), "bet_total": o.get("bet_total", 0)}
                            break
                if result: break
                time.sleep(5)

            if result:
                hit = result["is_hit"]; bt = float(result["bet_total"] or cur * 2); ha = float(result["hit_amount"] or 0)
                if hit and ha > bt:
                    profit = ha - bt; total_profit += profit
                    cur = float(total_build) / 2; losses = 0
                    state["stats"]["wins"] += 1; state["stats"]["profit"] = round(total_profit, 4)
                    state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash] WIN +{profit}")
                else:
                    profit = -bt; total_profit += profit
                    losses += 1; cur *= float(mult)
                    state["stats"]["losses"] += 1; state["stats"]["profit"] = round(total_profit, 4)
                    state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash] LOSE {profit}, nhân cược lên {cur}")
                    if losses >= lose_count: rest = rest_stop; losses = 0
            time.sleep(5)
        except Exception as e:
            state["logs"].insert(0, f"[{time.strftime('%H:%M:%S')}] [WinHash Error] {e}")
            time.sleep(5)
    state["running"] = False

# =========================================================
# FLASK WEB ROUTES (GIAO DIỆN ĐẸP NGẤT NGÂY & MENU 3 GẠCH)
# =========================================================
@app.route('/')
def home():
    new_key = request.args.get("key", "")
    error = request.args.get("error", "")
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWORLD ENTERPRISE - GATEWAY</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
            body { background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 100%); color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 15px; }
            .card { background: rgba(30, 41, 59, 0.75); backdrop-filter: blur(20px); border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 24px; width: 100%; max-width: 440px; padding: 30px 20px; text-align: center; box-shadow: 0 25px 50px rgba(0,0,0,0.7); }
            .icon-box { width: 65px; height: 65px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 15px; color: #fff; cursor: pointer; user-select: none; }
            .badge { display: inline-block; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 5px 14px; border-radius: 30px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 12px; }
            h2 { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 10px; }
            p { color: #94a3b8; font-size: 13px; line-height: 1.5; margin-bottom: 20px; }
            .btn { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; text-decoration: none; padding: 14px; border-radius: 14px; font-weight: 700; font-size: 14px; border: none; cursor: pointer; margin-bottom: 10px; box-shadow: 0 10px 20px rgba(99,102,241,0.3); }
            .input-box { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid #334155; background: #0b0f19; color: #fff; margin-bottom: 12px; text-align: center; font-size: 14px; }
            .key-container { background: #0b0f19; border: 2px dashed #6366f1; padding: 15px; border-radius: 16px; margin-top: 15px; }
            .key-text { font-family: monospace; font-size: 15px; color: #4ade80; font-weight: 700; word-break: break-all; margin-bottom: 10px; }
            .btn-copy { background: #22c55e; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-weight: 700; font-size: 12px; cursor: pointer; }
            .error { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 10px; border-radius: 10px; font-size: 12px; margin-top: 15px; }
            .nav-link { display: block; margin-top: 15px; color: #38bdf8; text-decoration: none; font-size: 13px; font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-box" id="secretLightning" onclick="handleSecretClick()"><i class="fa-solid fa-bolt"></i></div>
            <span class="badge">Hệ Thống Web Tool 3 Game</span>
            <h2>XWORLD GATEWAY</h2>
            <p>Vượt link nhận key 24h hoặc nhập key để truy cập trực tiếp vào bảng điều khiển 3 game.</p>
            
            <form action="/verify_key" method="POST">
                <input type="text" name="key_code" class="input-box" placeholder="Nhập mã Key (VD: KEY-XW-XXXX)..." required autocomplete="off">
                <button type="submit" class="btn"><i class="fa-solid fa-key"></i> Kích Hoạt & Vào Tool</button>
            </form>

            {% if new_key %}
                <div class="key-container">
                    <div class="key-text" id="keyText">{{ new_key }}</div>
                    <button class="btn-copy" onclick="copyKey()">Sao Chép Key</button>
                </div>
            {% else %}
                <a href="/get_link4m" class="btn" style="background: linear-gradient(135deg, #059669, #10b981);"><i class="fa-solid fa-rocket"></i> LẤY KEY QUA LINK4M (24H)</a>
            {% endif %}

            <a href="/tool_dashboard" class="nav-link"><i class="fa-solid fa-arrow-right"></i> Đã có key? Vào thẳng Dashboard Tool ngay</a>

            {% if error %} <div class="error">{{ error }}</div> {% endif %}
        </div>
        <script>
            let clickCount = 0;
            function handleSecretClick() {
                clickCount++;
                if (clickCount >= 10) { window.location.href = "/quan-ly-bi-mat-dunghoet"; }
                setTimeout(() => { clickCount = 0; }, 3000);
            }
            function copyKey() {
                const keyText = document.getElementById("keyText").innerText;
                navigator.clipboard.writeText(keyText).then(() => { alert("Đã sao chép key!"); });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, new_key=new_key, error=error)

@app.route('/get_link4m')
def get_link4m():
    current_domain = request.host_url.rstrip('/')
    destination_url = f"{current_domain}/claim_key"
    api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={destination_url}"
    try:
        res = requests.get(api_url, timeout=5)
        result = res.json()
        if result.get("status") == "success": return redirect(result.get("shortenedUrl"))
    except: pass
    return redirect(url_for('home', error="Không thể kết nối Link4m API"))

@app.route('/claim_key')
def claim_key():
    new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    key_data = {"status": "chua_dung", "used_by": [], "created_at": time.time(), "expire_at": None, "duration_hours": 24, "is_vip": False, "max_uses": 1, "total_bets_count": 0}
    if save_key_to_cloud(new_key, key_data):
        return redirect(url_for('home', key=new_key))
    return redirect(url_for('home', error="⚠️ Lỗi tạo key!"))

@app.route('/verify_key', methods=['POST'])
def verify_key():
    key_code = request.form.get("key_code", "").strip()
    valid, msg = verify_key_web(key_code)
    if not valid:
        return redirect(url_for('home', error=msg))
    session['authorized_key'] = key_code
    return redirect(url_for('tool_dashboard'))

@app.route('/tool_dashboard')
def tool_dashboard():
    if not session.get('authorized_key'):
        return redirect(url_for('home', error="Vui lòng nhập key hợp lệ trước khi sử dụng tool!"))
    
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWORLD TOOL DASHBOARD - 3 GAMES</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
            body { background: #0f172a; color: #f8fafc; min-height: 100vh; }
            .header { display: flex; justify-content: space-between; align-items: center; background: rgba(30,41,59,0.9); padding: 15px 20px; border-bottom: 1px solid #334155; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(10px); }
            .menu-toggle { font-size: 20px; color: #38bdf8; cursor: pointer; background: rgba(56,189,248,0.1); padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(56,189,248,0.3); }
            h1 { font-size: 16px; font-weight: 800; color: #fff; }
            
            /* Sidebar Menu 3 gạch */
            .sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 999; display: none; backdrop-filter: blur(4px); }
            .sidebar { position: fixed; top: 0; left: -280px; width: 270px; height: 100%; background: #1e293b; z-index: 1000; padding: 25px 15px; transition: 0.3s ease; border-right: 1px solid #334155; display: flex; flex-direction: column; gap: 10px; }
            .sidebar.active { left: 0; }
            .sidebar h3 { color: #818cf8; font-size: 16px; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
            .sidebar-btn { background: #0b0f19; color: #94a3b8; border: 1px solid #334155; padding: 14px; border-radius: 12px; text-align: left; cursor: pointer; font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 12px; width: 100%; transition: 0.2s; text-decoration: none; }
            .sidebar-btn.active, .sidebar-btn:hover { background: #6366f1; color: #fff; border-color: #6366f1; }
            
            /* Content Area */
            .container { max-width: 700px; margin: 20px auto; padding: 0 15px; }
            .tool-card { background: rgba(30,41,59,0.7); border: 1px solid #334155; border-radius: 20px; padding: 20px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); backdrop-filter: blur(10px); }
            .tool-card h2 { font-size: 18px; color: #38bdf8; margin-bottom: 10px; display: flex; align-items: center; gap: 10px; }
            .form-group { margin-bottom: 12px; text-align: left; }
            .form-group label { display: block; font-size: 12px; color: #94a3b8; margin-bottom: 5px; font-weight: 600; }
            .form-control { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #475569; background: #0b0f19; color: #fff; font-size: 13px; }
            .btn-run { background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; border: none; padding: 12px 20px; border-radius: 10px; font-weight: 700; cursor: pointer; width: 100%; font-size: 14px; margin-top: 10px; box-shadow: 0 5px 15px rgba(34,197,94,0.3); }
            .btn-stop { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; padding: 12px 20px; border-radius: 10px; font-weight: 700; cursor: pointer; width: 100%; font-size: 14px; margin-top: 10px; box-shadow: 0 5px 15px rgba(239,68,68,0.3); }
            .log-box { background: #0b0f19; border: 1px solid #334155; border-radius: 10px; padding: 12px; font-family: monospace; font-size: 11px; height: 140px; overflow-y: auto; text-align: left; color: #4ade80; margin-top: 15px; }
            .tab-pane { display: none; }
            .tab-pane.active { display: block; }
        </style>
    </head>
    <body>
        <div class="sidebar-overlay" id="overlay" onclick="toggleSidebar()"></div>
        <div class="sidebar" id="sidebar">
            <h3><i class="fa-solid fa-bars"></i> MENU TOOL 3 GAME</h3>
            <a href="#" class="sidebar-btn active" onclick="switchTab('escapeTab', this)"><i class="fa-solid fa-gamepad"></i> 1. Escape Master</a>
            <a href="#" class="sidebar-btn" onclick="switchTab('sprintTab', this)"><i class="fa-solid fa-person-running"></i> 2. SprintRun</a>
            <a href="#" class="sidebar-btn" onclick="switchTab('winhashTab', this)"><i class="fa-solid fa-dice"></i> 3. WinHash</a>
            <a href="/" class="sidebar-btn" style="color: #f87171; margin-top: auto;"><i class="fa-solid fa-right-from-bracket"></i> Đăng Xuất / Đổi Key</a>
        </div>

        <div class="header">
            <div class="menu-toggle" onclick="toggleSidebar()"><i class="fa-solid fa-bars"></i></div>
            <h1>XWORLD ENTERPRISE STUDIO</h1>
            <i class="fa-solid fa-shield-halved" style="color: #4ade80; font-size: 20px;"></i>
        </div>

        <div class="container">
            <!-- TAB 1: ESCAPE MASTER -->
            <div id="escapeTab" class="tab-pane active">
                <div class="tool-card">
                    <h2><i class="fa-solid fa-gamepad"></i> Escape Master Auto Bet</h2>
                    <p style="color: #94a3b8; font-size: 12px; margin-bottom: 15px;">Kết nối thời gian thực qua WebSocket, chọn phòng ngẫu nhiên và cược theo hệ số gấp thếp.</p>
                    <div class="form-group"><label>User ID:</label><input type="text" id="esc_uid" class="form-control" placeholder="Nhập User ID..."></div>
                    <div class="form-group"><label>Secret Key:</label><input type="text" id="esc_skey" class="form-control" placeholder="Nhập Secret Key..."></div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Base Bet:</label><input type="number" id="esc_bet" class="form-control" value="1.0"></div>
                        <div class="form-group"><label>Thua Liên Tiếp:</label><input type="number" id="esc_loss" class="form-control" value="2"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Nghỉ (Phiên):</label><input type="number" id="esc_skip" class="form-control" value="3"></div>
                        <div class="form-group"><label>Hệ Số Nhân:</label><input type="number" id="esc_mult" class="form-control" value="2.0"></div>
                    </div>
                    <button id="escBtn" class="btn-run" onclick="toggleGame('escape')">BẮT ĐẦU CHẠY TOOL</button>
                    <div class="log-box" id="escLog">Chưa khởi động...</div>
                </div>
            </div>

            <!-- TAB 2: SPRINTRUN -->
            <div id="sprintTab" class="tab-pane">
                <div class="tool-card">
                    <h2><i class="fa-solid fa-person-running"></i> SprintRun Auto Bet</h2>
                    <p style="color: #94a3b8; font-size: 12px; margin-bottom: 15px;">Tự động cược nhóm vận động viên qua HTTP API thông minh.</p>
                    <div class="form-group"><label>User ID:</label><input type="text" id="spr_uid" class="form-control" placeholder="Nhập User ID..."></div>
                    <div class="form-group"><label>Secret Key:</label><input type="text" id="spr_skey" class="form-control" placeholder="Nhập Secret Key..."></div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Tổng Build:</label><input type="number" id="spr_build" class="form-control" value="1"></div>
                        <div class="form-group"><label>Thua Mấy Trận Nghỉ:</label><input type="number" id="spr_lose" class="form-control" value="3"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Nghỉ Bao Nhiêu Phiên:</label><input type="number" id="spr_rest" class="form-control" value="1"></div>
                        <div class="form-group"><label>Hệ Số Nhân:</label><input type="number" id="spr_mult" class="form-control" value="2.5"></div>
                    </div>
                    <button id="sprBtn" class="btn-run" onclick="toggleGame('sprint')">BẮT ĐẦU CHẠY TOOL</button>
                    <div class="log-box" id="sprLog">Chưa khởi động...</div>
                </div>
            </div>

            <!-- TAB 3: WINHASH -->
            <div id="winhashTab" class="tab-pane">
                <div class="tool-card">
                    <h2><i class="fa-solid fa-dice"></i> WinHash Auto Bet</h2>
                    <p style="color: #94a3b8; font-size: 12px; margin-bottom: 15px;">Quản lý vốn Martingale và bắt cầu Tài/Xỉu tự động qua hash.</p>
                    <div class="form-group"><label>User ID:</label><input type="text" id="win_uid" class="form-control" placeholder="Nhập User ID..."></div>
                    <div class="form-group"><label>Secret Key:</label><input type="text" id="win_skey" class="form-control" placeholder="Nhập Secret Key..."></div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Tổng Build:</label><input type="number" id="win_build" class="form-control" value="10"></div>
                        <div class="form-group"><label>Hệ Số Nhân:</label><input type="number" id="win_mult" class="form-control" value="2"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <div class="form-group"><label>Thua X Phiên:</label><input type="number" id="win_lose" class="form-control" value="3"></div>
                        <div class="form-group"><label>Nghỉ Y Phiên:</label><input type="number" id="win_rest" class="form-control" value="1"></div>
                    </div>
                    <button id="winBtn" class="btn-run" onclick="toggleGame('winhash')">BẮT ĐẦU CHẠY TOOL</button>
                    <div class="log-box" id="winLog">Chưa khởi động...</div>
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
            function switchTab(tabId, el) {
                document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
                document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                if(el) el.classList.add('active');
                toggleSidebar();
            }

            function toggleGame(gameName) {
                let btn = document.getElementById(gameName === 'escape' ? 'escBtn' : (gameName === 'sprint' ? 'sprBtn' : 'winBtn'));
                let isRunning = btn.classList.contains('btn-stop');
                let action = isRunning ? 'stop' : 'start';

                let payload = { game: gameName, action: action };
                if (action === 'start') {
                    if (gameName === 'escape') {
                        payload.uid = document.getElementById('esc_uid').value;
                        payload.skey = document.getElementById('esc_skey').value;
                        payload.base_bet = document.getElementById('esc_bet').value;
                        payload.loss_threshold = document.getElementById('esc_loss').value;
                        payload.skip_rounds = document.getElementById('esc_skip').value;
                        payload.multiplier = document.getElementById('esc_mult').value;
                    } else if (gameName === 'sprint') {
                        payload.uid = document.getElementById('spr_uid').value;
                        payload.skey = document.getElementById('spr_skey').value;
                        payload.total_build = document.getElementById('spr_build').value;
                        payload.lose_limit = document.getElementById('spr_lose').value;
                        payload.rest_rounds = document.getElementById('spr_rest').value;
                        payload.mult = document.getElementById('spr_mult').value;
                    } else if (gameName === 'winhash') {
                        payload.uid = document.getElementById('win_uid').value;
                        payload.skey = document.getElementById('win_skey').value;
                        payload.total_build = document.getElementById('win_build').value;
                        payload.mult = document.getElementById('win_mult').value;
                        payload.lose_count = document.getElementById('win_lose').value;
                        payload.rest_stop = document.getElementById('win_rest').value;
                    }
                }

                fetch('/api/control_game', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).then(res => res.json()).then(data => {
                    if(data.success) {
                        if(action === 'start') {
                            btn.className = "btn-stop"; btn.innerText = "DỪNG TOOL";
                        } else {
                            btn.className = "btn-run"; btn.innerText = "BẮT ĐẦU CHẠY TOOL";
                        }
                    } else {
                        alert("Lỗi: " + data.msg);
                    }
                });
            }

            // Polling logs
            setInterval(() => {
                fetch('/api/get_logs').then(res => res.json()).then(data => {
                    if(data.escape) { document.getElementById('escLog').innerText = data.escape.logs.join('\\n'); }
                    if(data.sprint) { document.getElementById('sprLog').innerText = data.sprint.logs.join('\\n'); }
                    if(data.winhash) { document.getElementById('winLog').innerText = data.winhash.logs.join('\\n'); }
                });
            }, 2000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/control_game', methods=['POST'])
def api_control_game():
    if not session.get('authorized_key'):
        return jsonify({"success": False, "msg": "Chưa xác thực key!"})
    data = request.json or {}
    game = data.get("game")
    action = data.get("action")
    session_id = session.get('authorized_key')
    st = get_session_state(session_id)

    if action == "stop":
        st[game]["running"] = False
        return jsonify({"success": True})

    uid = data.get("uid")
    skey = data.get("skey")
    if not uid or not skey:
        return jsonify({"success": False, "msg": "Vui lòng nhập đầy đủ User ID và Secret Key!"})

    if game == "escape":
        Thread(target=run_escape_master_engine, args=(session_id, uid, skey, data.get("base_bet", 1.0), int(data.get("loss_threshold", 2)), int(data.get("skip_rounds", 3)), float(data.get("multiplier", 2.0))), daemon=True).start()
    elif game == "sprint":
        Thread(target=run_sprintrun_engine, args=(session_id, uid, skey, data.get("total_build", 1), int(data.get("lose_limit", 3)), int(data.get("rest_rounds", 1)), float(data.get("mult", 2.5)), "BUILD"), daemon=True).start()
    elif game == "winhash":
        Thread(target=run_winhash_engine, args=(session_id, uid, skey, data.get("total_build", 10), float(data.get("mult", 2)), int(data.get("lose_count", 3)), int(data.get("rest_stop", 1)), "BUILD"), daemon=True).start()

    return jsonify({"success": True})

@app.route('/api/get_logs')
def api_get_logs():
    session_id = session.get('authorized_key')
    if not session_id: return jsonify({})
    return jsonify(get_session_state(session_id))

# =========================================================
# TRANG QUẢN TRỊ BÍ MẬT (BẤM 10 LẦN TIA SÉT)
# =========================================================
@app.route('/quan-ly-bi-mat-dunghoet', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        error = "Sai tài khoản hoặc mật khẩu!"
    return render_template_string("""
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Admin Login</title>
    <style>body{background:#0f172a;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;}
    .box{background:#1e293b;padding:30px;border-radius:15px;text-align:center;border:1px solid #334155;width:350px;}
    input{width:100%;padding:12px;margin:10px 0;border-radius:8px;border:1px solid #475569;background:#0b0f19;color:#fff;text-align:center;}
    button{background:#6366f1;color:#fff;border:none;padding:12px;border-radius:8px;cursor:pointer;font-weight:700;width:100%;}
    </style></head><body><div class="box">
    <h2>🔐 Admin Portal</h2>
    {% if error %}<p style="color:#f87171;font-size:12px;">{{ error }}</p>{% endif %}
    <form method="POST"><input type="text" name="username" placeholder="Username" required>
    <input type="password" name="password" placeholder="Password" required><button type="submit">Login</button></form>
    </div></body></html>
    """, error=error)

@app.route('/quan-ly-bi-mat-dunghoet/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    db = load_system_db()
    keys = db.get("keys", {})
    return render_template_string("""
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Admin Dashboard</title>
    <style>body{background:#0f172a;color:#fff;padding:20px;font-family:sans-serif;}
    table{width:100%;border-collapse:collapse;margin-top:20px;}
    th,td{padding:10px;border-bottom:1px solid #334155;text-align:left;font-size:13px;}
    th{background:#0b0f19;color:#94a3b8;}code{background:#0b0f19;padding:3px 6px;color:#4ade80;border-radius:4px;}
    </style></head><body>
    <h2>📊 Quản Lý Kho Key Hệ Thống</h2>
    <a href="/" style="color:#38bdf8;text-decoration:none;font-size:13px;">← Về trang chủ</a>
    <table><tr><th>Key</th><th>Trạng thái</th><th>Số Người Dùng</th></tr>
    {% for k, info in keys.items() %}
    <tr><td><code>{{ k }}</code></td><td>{{ info.status }}</td><td>{{ info.used_by|length }}</td></tr>
    {% endfor %}
    </table></body></html>
    """, keys=keys)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
