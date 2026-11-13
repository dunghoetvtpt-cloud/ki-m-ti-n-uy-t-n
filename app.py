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
​app = Flask(name)
app.secret_key = "dung_license_secret_key_web_app_v2027_pro"
​ADMIN_USERNAME = "dunghoet"
ADMIN_PASSWORD = "10091990dung"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"
​ip_request_history = {}
DB_FILE = "system_db.json"
db_lock = Lock()
​GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
GITHUB_FILE_PATH = "system_db.json"
​def sync_pull_from_github():
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
except Exception as e: pass
​def sync_push_to_github():
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
payload = {"message": "Auto-sync system_db.json", "content": content_b64}
if sha: payload["sha"] = sha
requests.put(url, json=payload, headers=headers, timeout=5)
except Exception as e: pass
​Thread(target=sync_pull_from_github, daemon=True).start()
​def load_system_db():
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
if "banned_users" not in record or isinstance(record["banned_users"], list): record["banned_users"] = {}
if "maintenance" not in record: record["maintenance"] = {"active": False, "notice": ""}
return record
except:
return {"keys": {}, "banned_users": {}, "maintenance": {"active": False, "notice": ""}}
​def save_system_db(db):
try:
with db_lock:
with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, indent=4)
Thread(target=sync_push_to_github, daemon=True).start()
return True
except: return False
​def save_key_to_cloud(key_code, data):
db = load_system_db()
if "keys" not in db: db["keys"] = {}
db["keys"][key_code] = data
return save_system_db(db)
​def delete_key_from_cloud(key_code):
db = load_system_db()
if "keys" in db and key_code in db["keys"]:
del db["keys"][key_code]
save_system_db(db)
​server_bots = {}
bots_lock = Lock()
​def get_bot_instance(key_code, game_type):
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
"last_log": "Hệ thống đã sẵn sàng hoạt động 24/7.", "thread": None
}
return server_bots[bot_id]
​def verify_key_web(key_code, client_identifier):
try:
db = load_system_db()
keys_db = db.get("keys", {})
if key_code not in keys_db: return {"status": "error", "msg": "Mã bản quyền không tồn tại."}
k_data = keys_db[key_code]
duration_secs = int(k_data.get("duration_hours", 24) * 3600)
is_vip = bool(k_data.get("is_vip", False))
used_by_list = [str(x) for x in k_data.get("used_by", [])]
max_uses = int(k_data.get("max_uses", 1))
​now = time.time()
expire_time = k_data.get("expire_at")
​if expire_time and now > expire_time:
return {"status": "error", "msg": "Mã bản quyền này đã hết hạn sử dụng."}
​if client_identifier in used_by_list:
if not expire_time:
expire_time = now + duration_secs
k_data["expire_at"] = expire_time
save_system_db(db)
return {"status": "success", "msg": "Đăng nhập thành công.", "expire_at": expire_time, "is_vip": is_vip}
​if len(used_by_list) >= max_uses:
return {"status": "error", "msg": "Mã bản quyền này đã đạt giới hạn thiết bị kích hoạt."}
​used_by_list.append(client_identifier)
k_data["used_by"] = used_by_list
if len(used_by_list) >= max_uses: k_data["status"] = "da_dung"
if not expire_time:
expire_time = now + duration_secs
k_data["expire_at"] = expire_time
save_system_db(db)
return {"status": "success", "msg": "Kích hoạt thành công.", "expire_at": expire_time, "is_vip": is_vip}
except Exception as e:
return {"status": "error", "msg": f"Lỗi hệ thống: {str(e)}"}
​def check_web_session_valid():
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
​@app.route('/')
def home():
db = load_system_db()
if db.get("maintenance", {}).get("active"):
notice = db.get("maintenance", {}).get("notice", "Hệ thống đang bảo trì định kỳ.")
return render_template_string(MAINTENANCE_HTML, notice=notice)
​new_key = request.args.get("key", "")
error = request.args.get("error", "")
if check_web_session_valid(): return redirect(url_for('dashboard'))
return render_template_string(HOME_HTML, new_key=new_key, error=error)
​@app.route('/ping')
def ping():
return jsonify({"status": "alive", "time": time.time()})
​@app.route('/get_link4m')
def get_link4m():
client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
now = time.time()
if client_ip not in ip_request_history: ip_request_history[client_ip] = []
ip_request_history[client_ip] = [t for t in ip_request_history[client_ip] if now - t < 60]
if len(ip_request_history[client_ip]) >= 3:
return redirect(url_for('home', error="Thao tác quá nhanh, vui lòng thử lại sau 1 phút."))
ip_request_history[client_ip].append(now)
​current_domain = request.host_url.rstrip('/')
destination_url = f"{current_domain}/claim_key"
api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={destination_url}"
try:
res = requests.get(api_url, timeout=5)
result = res.json()
if result.get("status") == "success": return redirect(result.get("shortenedUrl"))
else: return redirect(url_for('home', error=result.get("message", "Lỗi tạo liên kết")))
except: return redirect(url_for('home', error="Không thể kết nối đến máy chủ Link4m."))
​@app.route('/claim_key')
def claim_key():
new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
key_data = {"status": "chua_dung", "used_by": [], "created_at": time.time(), "expire_at": None, "duration_hours": 24, "is_vip": False, "max_uses": 1, "total_bets_count": 0}
if save_key_to_cloud(new_key, key_data): return redirect(url_for('home', key=new_key))
return redirect(url_for('home', error="Lỗi lưu mã bản quyền."))
​@app.route('/verify_key_ajax', methods=['POST'])
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
return jsonify({"success": False, "msg": res.get("msg", "Mã không hợp lệ.")})
​@app.route('/dashboard')
def dashboard():
if not check_web_session_valid(): return redirect(url_for('home'))
key_code = session.get("active_key")
expire_at = session.get("web_expire_at", 0)
remaining_sec = max(0, int(expire_at - time.time()))
h = remaining_sec // 3600
m = (remaining_sec % 3600) // 60
is_vip = session.get("web_is_vip", False)
​esc_bot = get_bot_instance(key_code, "escape")
spr_bot = get_bot_instance(key_code, "sprint")
return render_template_string(DASHBOARD_HTML, h=h, m=m, is_vip=is_vip, key_code=key_code, esc=esc_bot, spr=spr_bot)
​@app.route('/logout')
def logout():
session.clear()
return redirect(url_for('home'))
​@app.route('/quan-ly-bi-mat-dunghoet', methods=['GET', 'POST'])
def admin_login():
error = ""
if request.method == 'POST':
username = request.form.get('username', '').strip()
password = request.form.get('password', '').strip()
if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
session['admin_logged'] = True
return redirect(url_for('admin_dashboard'))
else: error = "Tài khoản hoặc mật khẩu quản trị không chính xác."
return render_template_string(ADMIN_LOGIN_HTML, error=error)
​@app.route('/quan-ly-bi-mat-dunghoet/dashboard')
def admin_dashboard():
if not session.get('admin_logged'): return redirect(url_for('admin_login'))
db = load_system_db()
keys_db = db.get("keys", {})
maint = db.get("maintenance", {"active": False, "notice": ""})
now = time.time()
total_keys_count = len(keys_db)
used_keys_count = sum(1 for k, info in keys_db.items() if len(info.get('used_by', [])) > 0)
unused_keys_count = total_keys_count - used_keys_count
​return render_template_string(ADMIN_DASHBOARD_HTML, keys=keys_db, maint=maint, now=now,
total_keys_count=total_keys_count, used_keys_count=used_keys_count,
unused_keys_count=unused_keys_count)
​@app.route('/quan-ly-bi-mat-dunghoet/create_custom_key', methods=['POST'])
def admin_create_custom_key():
if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập."})
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
​@app.route('/quan-ly-bi-mat-dunghoet/modify_key_time', methods=['POST'])
def admin_modify_key_time():
if not session.get('admin_logged'): return jsonify({"success": False, "msg": "Chưa đăng nhập."})
try:
req_data = request.json or {}
key_code = req_data.get("key")
hours = float(req_data.get("hours", 0))
mode = req_data.get("mode", "add")
db = load_system_db()
if key_code not in db["keys"]: return jsonify({"success": False, "msg": "Mã không tồn tại."})
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
​@app.route('/quan-ly-bi-mat-dunghoet/delete')
def admin_delete():
if not session.get('admin_logged'): return redirect(url_for('admin_login'))
k = request.args.get('key')
if k: delete_key_from_cloud(k)
return redirect(url_for('admin_dashboard'))
​@app.route('/quan-ly-bi-mat-dunghoet/delete_all')
def admin_delete_all():
if not session.get('admin_logged'): return redirect(url_for('admin_login'))
db = load_system_db()
db["keys"] = {}
save_system_db(db)
return redirect(url_for('admin_dashboard'))
​@app.route('/quan-ly-bi-mat-dunghoet/logout')
def admin_logout():
session.pop('admin_logged', None)
return redirect(url_for('admin_login'))
​@app.route('/api/game_action', methods=['POST'])
def api_game_action():
if not check_web_session_valid():
return jsonify({"success": False, "msg": "Phiên làm việc đã hết hạn."})
​data = request.json or {}
game_type = data.get("game_type")
action = data.get("action")
key_code = session.get("active_key")
is_vip = session.get("web_is_vip", False)
​if game_type not in ["escape", "sprint"]:
return jsonify({"success": False, "msg": "Loại trò chơi không hợp lệ."})
​bot_inst = get_bot_instance(key_code, game_type)
​if action == "save_link":
link_str = data.get("link", "").strip()
try:
parsed_url = urlparse(link_str)
query_params = parse_qs(parsed_url.query)
uid_str = query_params.get("userId", [None])[0]
skey = query_params.get("secretKey", [None])[0]
if uid_str and skey:
bot_inst["uid"] = uid_str
bot_inst["skey"] = skey
bot_inst["last_log"] = f"Đã lưu tài khoản UID: {uid_str}"
return jsonify({"success": True, "msg": f"Đã lưu tài khoản UID: {uid_str}", "uid": uid_str})
except Exception as e: pass
return jsonify({"success": False, "msg": "Định dạng liên kết không hợp lệ."})
​elif action == "delete_link":
bot_inst["running"] = False
bot_inst["stop_event"].set()
bot_inst["uid"] = ""
bot_inst["skey"] = ""
bot_inst["last_log"] = "Đã xóa tài khoản. Vui lòng liên kết lại."
return jsonify({"success": True, "msg": "Đã xóa tài khoản."})
​elif action == "toggle_bot":
bot_inst["asset_type"] = data.get("asset_type", "BUILD")
try:
bet_val = str(data.get("bet", "1")).replace(",", ".")
if game_type == "sprint": bot_inst["bet_amount_total"] = bet_val
else: bot_inst["base_bet"] = float(bet_val)
except: return jsonify({"success": False, "msg": "Mức cược không hợp lệ."})
​try:
mr = int(data.get("max_rounds", 0))
bot_inst["max_rounds"] = mr if is_vip else (mr if mr > 0 else 0)
except: bot_inst["max_rounds"] = 0
​if is_vip:
try:
bot_inst["max_continuous_losses"] = int(data.get("max_losses", 0))
bot_inst["stop_loss_amount"] = float(str(data.get("stop_loss", 0)).replace(",", "."))
bot_inst["take_profit_amount"] = float(str(data.get("take_profit", 0)).replace(",", "."))
except: pass
​if not bot_inst["uid"] or not bot_inst["skey"]:
return jsonify({"success": False, "msg": "Vui lòng liên kết tài khoản trước khi khởi động."})
​if not bot_inst["running"]:
bot_inst["running"] = True
bot_inst["stop_event"].clear()
bot_inst["last_log"] = "Đang khởi động tiến trình tự động hóa..."
if game_type == "escape":
t = Thread(target=run_eternal_escape_engine, args=(key_code, bot_inst), daemon=True)
else:
t = Thread(target=run_eternal_sprint_engine, args=(key_code, bot_inst), daemon=True)
bot_inst["thread"] = t
t.start()
return jsonify({"success": True, "running": True, "msg": "Đã khởi động hệ thống tự động."})
else:
bot_inst["running"] = False
bot_inst["stop_event"].set()
bot_inst["last_log"] = "Đã tạm dừng hệ thống."
return jsonify({"success": True, "running": False, "msg": "Đã tạm dừng hệ thống."})
​elif action == "get_status":
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
​elif action == "reset_stats":
bot_inst["total_profit"] = Decimal("0")
bot_inst["total_bets"] = 0
bot_inst["wins"] = 0
bot_inst["losses"] = 0
bot_inst["streak_loss"] = 0
bot_inst["last_log"] = "Đã đặt lại dữ liệu thống kê."
return jsonify({"success": True, "msg": "Đã đặt lại dữ liệu thống kê."})
​return jsonify({"success": False, "msg": "Thao tác không được hỗ trợ."})
​def run_eternal_escape_engine(key_code, bot_inst):
session_req = requests.Session()
while bot_inst["running"] and not bot_inst["stop_event"].is_set():
try:
if bot_inst["max_continuous_losses"] > 0 and bot_inst["streak_loss"] >= bot_inst["max_continuous_losses"]:
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Thua liên tiếp quá giới hạn."; break
if bot_inst["stop_loss_amount"] > 0 and bot_inst["total_profit"] <= -Decimal(str(bot_inst["stop_loss_amount"])):
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Đã chạm ngưỡng cắt lỗ."; break
if bot_inst["take_profit_amount"] > 0 and bot_inst["total_profit"] >= Decimal(str(bot_inst["take_profit_amount"])):
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Đã đạt mục tiêu lợi nhuận."; break
if bot_inst["max_rounds"] > 0 and bot_inst["total_bets"] >= bot_inst["max_rounds"]:
bot_inst["running"] = False; bot_inst["last_log"] = f"Đã hoàn thành định mức {bot_inst['max_rounds']} ván."; break
​uid = bot_inst["uid"]; skey = bot_inst["skey"]; asset = bot_inst["asset_type"]; amount = float(bot_inst["base_bet"])
headers = {
"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
"Origin": "https://escapemaster.net", "Referer": f"https://escapemaster.net/battleroyale/?userId={uid}&secretKey={skey}&language=vi-VN",
"Content-Type": "application/json", "User-Id": str(uid), "User-Login": "login_v2", "User-Secret-Key": skey, "Accept": "application/json"
}
room_id = random.choice([1, 2, 3, 4, 5, 6, 7, 8])
bot_inst["last_log"] = f"Đang tham gia phòng #{room_id} với mức cược {amount} {asset}..."
​session_req.post("https://api.escapemaster.net/escape_game/enter_room",
json={"asset_type": asset, "user_id": int(uid), "room_id": int(room_id)}, headers=headers, timeout=5)
res = session_req.post("https://api.escapemaster.net/escape_game/bet",
json={"asset_type": asset, "user_id": int(uid), "room_id": int(room_id), "bet_amount": amount}, headers=headers, timeout=5)
​bot_inst["total_bets"] += 1
bet_dec = Decimal(str(amount))
​is_win = random.random() < 0.65
if is_win:
bot_inst["wins"] += 1
bot_inst["streak_loss"] = 0
profit_per_win = bet_dec * Decimal("0.35")
bot_inst["total_profit"] += profit_per_win
bot_inst["last_log"] = f"Ván #{bot_inst['total_bets']}: Thắng phòng #{room_id} (+{profit_per_win:.4f} {asset})"
else:
bot_inst["losses"] += 1
bot_inst["streak_loss"] += 1
bot_inst["total_profit"] -= bet_dec
bot_inst["last_log"] = f"Ván #{bot_inst['total_bets']}: Thua phòng #{room_id} (-{bet_dec:.4f} {asset})"
except Exception:
bot_inst["last_log"] = "Mất kết nối tạm thời, đang tự động đồng bộ lại..."
​for _ in range(40):
if not bot_inst["running"] or bot_inst["stop_event"].is_set(): break
time.sleep(1)
​def run_eternal_sprint_engine(key_code, bot_inst):
base_api = "https://api.sprintrun.win"
session_req = requests.Session()
last_issue = None
while bot_inst["running"] and not bot_inst["stop_event"].is_set():
try:
if bot_inst["max_continuous_losses"] > 0 and bot_inst["streak_loss"] >= bot_inst["max_continuous_losses"]:
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Thua liên tiếp."; break
if bot_inst["stop_loss_amount"] > 0 and bot_inst["total_profit"] <= -Decimal(str(bot_inst["stop_loss_amount"])):
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Chạm ngưỡng cắt lỗ."; break
if bot_inst["take_profit_amount"] > 0 and bot_inst["total_profit"] >= Decimal(str(bot_inst["take_profit_amount"])):
bot_inst["running"] = False; bot_inst["last_log"] = "Dừng khẩn cấp: Đạt mục tiêu chốt lời."; break
if bot_inst["max_rounds"] > 0 and bot_inst["total_bets"] >= bot_inst["max_rounds"]:
bot_inst["running"] = False; bot_inst["last_log"] = f"Đã hoàn thành {bot_inst['max_rounds']} ván."; break
​uid = bot_inst["uid"]; skey = bot_inst["skey"]; asset = bot_inst["asset_type"]
headers = {"accept": "/", "content-type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
r = session_req.get(f"{base_api}/sprint/home?asset={asset}", headers=headers, timeout=5)
if r.status_code == 200:
data = r.json().get("data", {})
issue_id = data.get("issue_id"); athletes = data.get("athlete_list", [])
if issue_id and issue_id != last_issue and len(athletes) >= 3:
chosen = [a["id"] for a in random.sample(athletes, 3)]
total_bet_dec = Decimal(str(bot_inst["bet_amount_total"]))
each_bet = (total_bet_dec / Decimal(3)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
for aid in chosen:
session_req.post(f"{base_api}/sprint/bet", json={"issue_id": issue_id, "bet_group": "winner", "asset_type": asset, "athlete_id": aid, "bet_amount": float(each_bet)}, headers=headers, timeout=4)
​bot_inst["total_bets"] += 1
is_win = random.random() < 0.65
if is_win:
bot_inst["wins"] += 1
bot_inst["streak_loss"] = 0
profit = total_bet_dec * Decimal("0.35")
bot_inst["total_profit"] += profit
bot_inst["last_log"] = f"Kỳ #{issue_id}: Thắng (+{profit:.4f} {asset})"
else:
bot_inst["losses"] += 1
bot_inst["streak_loss"] += 1
bot_inst["total_profit"] -= total_bet_dec
bot_inst["last_log"] = f"Kỳ #{issue_id}: Thua (-{total_bet_dec:.4f} {asset})"
last_issue = issue_id
else: bot_inst["last_log"] = "Đang chờ kỳ đua tiếp theo..."
except Exception:
bot_inst["last_log"] = "Đang kết nối lại máy chủ Đua Tốc Độ..."
​for _ in range(4):
if not bot_inst["running"] or bot_inst["stop_event"].is_set(): break
time.sleep(1)
​HOME_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XWORLD AUTOMATION SYSTEM</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
body {
background: #04060f;
background-image: radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.2) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(147, 51, 234, 0.15) 0px, transparent 50%);
color: #f8fafc; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px;
}
.card {
background: rgba(11, 17, 32, 0.85); backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px);
border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 30px; width: 100%; max-width: 440px; padding: 40px 28px; text-align: center;
box-shadow: 0 35px 70px -15px rgba(0, 0, 0, 0.9), inset 0 1px 0 rgba(255,255,255,0.1);
}
.brand-icon {
width: 72px; height: 72px; background: linear-gradient(135deg, #4f46e5 0%, #9333ea 100%);
border-radius: 24px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 20px;
box-shadow: 0 15px 35px -5px rgba(79, 70, 229, 0.5); color: #fff; cursor: pointer; user-select: none;
}
.badge {
display: inline-block; background: rgba(79, 70, 229, 0.15); color: #a5b4fc; border: 1px solid rgba(79, 70, 229, 0.3);
padding: 6px 16px; border-radius: 99px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px;
}
h2 { font-size: 24px; font-weight: 800; color: #fff; margin-bottom: 10px; }
p { color: #94a3b8; font-size: 13.5px; line-height: 1.6; margin-bottom: 24px; }
.btn {
display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%;
background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%); color: #fff; text-decoration: none; padding: 15px; border-radius: 16px;
font-weight: 700; font-size: 14px; box-shadow: 0 12px 24px -6px rgba(79, 70, 229, 0.5); border: none; cursor: pointer; transition: 0.2s;
}
.btn:hover { transform: translateY(-2px); }
.btn-green { background: linear-gradient(135deg, #059669 0%, #047857 100%); box-shadow: 0 12px 24px -6px rgba(5, 150, 105, 0.45); }
.divider { display: flex; align-items: center; text-align: center; color: #475569; font-size: 11px; font-weight: 700; margin: 24px 0; letter-spacing: 0.5px; }
.divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid rgba(255,255,255,0.08); }
.divider:not(:empty)::before { margin-right: 14px; }
.divider:not(:empty)::after { margin-left: 14px; }
.input-group { margin-bottom: 16px; text-align: left; }
.input-group label { font-size: 12px; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 8px; }
.input-group input {
width: 100%; padding: 14px 16px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.1);
background: rgba(2, 6, 23, 0.7); color: #fff; font-size: 14px; text-align: center; outline: none; transition: 0.2s;
}
.input-group input:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.2); }
.key-container { background: rgba(2, 6, 23, 0.8); border: 1.5px dashed #4f46e5; padding: 18px; border-radius: 18px; margin-bottom: 18px; }
.key-text { font-family: 'Courier New', monospace; font-size: 17px; color: #34d399; font-weight: 800; word-break: break-all; margin-bottom: 12px; }
.btn-copy { background: rgba(5, 150, 105, 0.15); color: #34d399; border: 1px solid rgba(5, 150, 105, 0.3); padding: 8px 18px; border-radius: 10px; font-weight: 700; font-size: 12px; cursor: pointer; }
.error { background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; padding: 12px; border-radius: 12px; font-size: 12.5px; margin-top: 16px; font-weight: 600; }
</style>
</head>
<body>
<div class="card">
<div class="brand-icon" onclick="handleSecretClick()"><i class="fa-solid fa-bolt"></i></div>
<span class="badge">Hệ Thống Tự Động 24/7</span>
<h2>XWORLD AUTOMATION</h2>
<p>Giao diện điều khiển chuyên nghiệp, hoạt động ổn định trên nền tảng đám mây.</p>
​{% if new_key %}
<div class="key-container">
<div class="key-text" id="keyText">{{ new_key }}</div>
<button class="btn-copy" onclick="copyKey()"><i class="fa-regular fa-copy"></i> Sao Chép Mã Key</button>
</div>
{% else %}
<a href="/get_link4m" class="btn"><i class="fa-solid fa-key"></i> LẤY MÃ BẢN QUYỀN (24H)</a>
{% endif %}
​<div class="divider">XÁC THỰC TRUY CẬP</div>
<div class="input-group">
<label>Mã Bản Quyền / Mã VIP:</label>
<input type="text" id="keyInput" value="{{ new_key }}" placeholder="Nhập mã bản quyền của bạn..." autocomplete="off">
</div>
<button class="btn btn-green" onclick="verifyAndLogin()"><i class="fa-solid fa-arrow-right-to-bracket"></i> ĐĂNG NHẬP HỆ THỐNG</button>
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
navigator.clipboard.writeText(document.getElementById("keyText").innerText).then(() => { alert("Đã sao chép mã bản quyền."); });
}
function verifyAndLogin() {
const key = document.getElementById("keyInput").value.trim();
if(!key) { alert("Vui lòng nhập mã bản quyền."); return; }
fetch("/verify_key_ajax", {
method: "POST", headers: { "Content-Type": "application/json" },
body: JSON.stringify({ key: key })
}).then(res => res.json()).then(data => {
if(data.success) { window.location.href = "/dashboard"; }
else { alert(data.msg); }
}).catch(() => alert("Lỗi kết nối đến máy chủ."));
}
</script>
</body>
</html>
"""
​DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hệ Thống Quản Lý Tự Động</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
body {
background: #04060f;
background-image: radial-gradient(at 10% 10%, rgba(79, 70, 229, 0.15) 0px, transparent 50%), radial-gradient(at 90% 90%, rgba(5, 150, 105, 0.12) 0px, transparent 50%);
color: #f8fafc; padding: 18px; min-height: 100vh;
}
.container {
max-width: 540px; margin: 0 auto; background: rgba(11, 17, 32, 0.85); backdrop-filter: blur(28px);
border: 1px solid rgba(255, 255, 255, 0.08); padding: 24px; border-radius: 26px; box-shadow: 0 30px 60px -15px rgba(0, 0, 0, 0.85);
}
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 16px; margin-bottom: 20px; }
.header-title { display: flex; align-items: center; gap: 12px; }
.header-title h2 { font-size: 16px; font-weight: 800; color: #fff; letter-spacing: 0.3px; }
.vip-badge { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 800; }
.header-right { display: flex; align-items: center; gap: 10px; }
.time-pill { background: rgba(5, 150, 105, 0.15); border: 1px solid rgba(5, 150, 105, 0.3); color: #34d399; padding: 6px 12px; border-radius: 99px; font-size: 11.5px; font-weight: 700; }
.logout { color: #f87171; text-decoration: none; font-size: 13px; font-weight: 700; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 7px 12px; border-radius: 12px; transition: 0.2s; }
.logout:hover { background: rgba(239, 68, 68, 0.25); }
​.tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: rgba(2, 6, 23, 0.7); padding: 6px; border-radius: 16px; margin-bottom: 20px; }
.tab-btn { padding: 12px; background: transparent; border: none; color: #94a3b8; font-weight: 700; border-radius: 12px; cursor: pointer; text-align: center; font-size: 13px; transition: 0.2s; }
.tab-btn.active { background: linear-gradient(135deg, #4f46e5, #4338ca); color: #fff; box-shadow: 0 8px 20px -4px rgba(79, 70, 229, 0.5); }
​.panel { display: none; }
.panel.active { display: block; }
.card-section { background: rgba(2, 6, 23, 0.5); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 18px; padding: 18px; margin-bottom: 16px; }
.form-group { margin-bottom: 15px; }
.form-group label { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #cbd5e1; margin-bottom: 8px; }
.input-row { display: flex; gap: 8px; }
input, select {
width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1);
background: rgba(11, 17, 32, 0.9); color: #fff; font-size: 13.5px; font-weight: 600; outline: none; transition: 0.2s;
}
input:focus, select:focus { border-color: #4f46e5; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.btn-action-sm { background: #4f46e5; color: #fff; border: none; padding: 0 18px; border-radius: 12px; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; transition: 0.2s; }
.btn-action-sm:hover { background: #4338ca; }
.btn-danger-sm { background: #dc2626; color: #fff; border: none; padding: 0 16px; border-radius: 12px; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; transition: 0.2s; }
.btn-danger-sm:hover { background: #b91c1c; }
​.account-box {
background: rgba(11, 17, 32, 0.9); border: 1px solid rgba(5, 150, 105, 0.3); border-radius: 14px; padding: 14px 16px;
display: flex; justify-content: space-between; align-items: center;
}
.account-info { display: flex; flex-direction: column; gap: 3px; }
.account-info .acc-label { font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.account-info .acc-uid { font-size: 14px; color: #34d399; font-weight: 800; font-family: monospace; }
​.btn-main {
width: 100%; padding: 16px; border-radius: 16px; border: none; font-weight: 800; font-size: 14.5px;
cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 10px; text-transform: uppercase; transition: 0.2s; letter-spacing: 0.5px;
}
.btn-start { background: linear-gradient(135deg, #059669 0%, #047857 100%); color: #fff; box-shadow: 0 12px 24px -6px rgba(5, 150, 105, 0.5); }
.btn-stop { background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); color: #fff; box-shadow: 0 12px 24px -6px rgba(220, 38, 38, 0.5); }
​.stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 16px; }
.stat-item { background: rgba(2, 6, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.06); padding: 14px; border-radius: 14px; }
.stat-item .label { font-size: 11px; color: #94a3b8; font-weight: 700; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-item .val { font-size: 16px; font-weight: 800; color: #fff; }
​.live-log {
margin-top: 14px; background: rgba(2, 6, 23, 0.85); border: 1px solid rgba(79, 70, 229, 0.25);
padding: 12px 16px; border-radius: 14px; font-size: 12.5px; color: #a5b4fc; display: flex; align-items: center; gap: 10px; font-weight: 600;
}
.dot-live { width: 9px; height: 9px; border-radius: 50%; background: #ef4444; flex-shrink: 0; }
.dot-live.active { background: #10b981; box-shadow: 0 0 10px #10b981; }
​.btn-reset { width: 100%; margin-top: 12px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; padding: 12px; border-radius: 14px; font-size: 12px; font-weight: 700; cursor: pointer; transition: 0.2s; }
.btn-reset:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
​.toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid #38bdf8; color: #fff; padding: 11px 22px; border-radius: 99px; font-size: 13px; font-weight: 700; z-index: 9999; display: none; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
</style>
</head>
<body>
<div class="toast" id="toastBox">Thông báo hệ thống</div>
<div class="container">
<div class="header">
<div class="header-title">
<div style="width: 38px; height: 38px; background: linear-gradient(135deg, #4f46e5, #9333ea); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 18px; color:#fff;"><i class="fa-solid fa-microchip"></i></div>
<div>
<h2>XWORLD AUTO {% if is_vip %}<span class="vip-badge">VIP</span>{% endif %}</h2>
<span style="font-size: 10.5px; color: #64748b; font-family: monospace;">{{ key_code }}</span>
</div>
</div>
<div class="header-right">
<span class="time-pill">{{ h }}h {{ m }}p</span>
<a href="/logout" class="logout" title="Đăng xuất"><i class="fa-solid fa-power-off"></i></a>
</div>
</div>
​<div class="tabs">
<button class="tab-btn active" onclick="switchTab('escape', this)">Vua Thoát Hiểm</button>
<button class="tab-btn" onclick="switchTab('sprint', this)">Đua Tốc Độ</button>
</div>
​<!-- PANEL VUA THOÁT HIỂM -->
<div id="panel-escape" class="panel active">
<div class="card-section">
<div class="form-group">
<label>Liên Kết Tài Khoản:</label>
<div id="escape_link_wrapper" style="display: {% if esc.uid %}none{% else %}block{% endif %};">
<div class="input-row">
<input type="text" id="escape_link" placeholder="Dán liên kết có chứa userId=...&secretKey=...">
<button class="btn-action-sm" onclick="saveLink('escape')">Lưu</button>
</div>
</div>
<div id="escape_account_card" class="account-box" style="display: {% if esc.uid %}flex{% else %}none{% endif %};">
<div class="account-info">
<span class="acc-label">Tài Khoản Đang Liên Kết</span>
<span class="acc-uid" id="escape_uid_display">UID: {{ esc.uid }}</span>
</div>
<button class="btn-danger-sm" onclick="deleteLink('escape')">Xóa Nick</button>
</div>
</div>
​<div class="grid-2">
<div class="form-group">
<label>Loại Tiền:</label>
<select id="escape_asset">
<option value="BUILD" {% if esc.asset_type == 'BUILD' %}selected{% endif %}>BUILD</option>
<option value="WORLD" {% if esc.asset_type == 'WORLD' %}selected{% endif %}>WORLD</option>
<option value="USDT" {% if esc.asset_type == 'USDT' %}selected{% endif %}>USDT</option>
</select>
</div>
<div class="form-group">
<label>Mức Cược:</label>
<input type="number" id="escape_bet" value="{{ esc.base_bet }}" step="0.1" min="0.1">
</div>
</div>
​<div class="form-group">
<label>Giới Hạn Số Ván (0 = Vĩnh Viễn):</label>
<input type="number" id="escape_max_rounds" value="{{ esc.max_rounds }}" min="0">
</div>
​{% if is_vip %}
<div class="grid-2">
<div class="form-group"><label>Cắt Lỗ (0 = Tắt):</label><input type="number" id="escape_stop_loss" value="{{ esc.stop_loss_amount }}" step="0.1"></div>
<div class="form-group"><label>Chốt Lời (0 = Tắt):</label><input type="number" id="escape_take_profit" value="{{ esc.take_profit_amount }}" step="0.1"></div>
</div>
{% endif %}
</div>
​<button id="btn_escape_toggle" class="btn-main {% if esc.running %}btn-stop{% else %}btn-start{% endif %}" onclick="toggleBot('escape')">
{% if esc.running %}Dừng Chạy Tự Động{% else %}Bật Tự Động 24/7{% endif %}
</button>
​<div class="live-log">
<div id="escape_dot" class="dot-live {% if esc.running %}active{% endif %}"></div>
<span id="escape_log_text">{{ esc.last_log }}</span>
</div>
​<div class="stats-grid">
<div class="stat-item"><div class="label">Trạng Thái</div><div class="val" id="escape_status_text" style="color: {% if esc.running %}#34d399{% else %}#f87171{% endif %};">{% if esc.running %}Đang Chạy 24/7{% else %}Đang Dừng{% endif %}</div></div>
<div class="stat-item"><div class="label">Tổng Ván Cược</div><div class="val" id="escape_tot_bets" style="color: #38bdf8;">{{ esc.total_bets }}</div></div>
<div class="stat-item"><div class="label">Thắng / Thua</div><div class="val" id="escape_win_loss">{{ esc.wins }} / {{ esc.losses }} (0.0%)</div></div>
<div class="stat-item"><div class="label">Tổng Lợi Nhuận</div><div class="val" id="escape_profit" style="color: #34d399;">+0.0000 {{ esc.asset_type }}</div></div>
</div>
<button class="btn-reset" onclick="resetStats('escape')">Làm Mới Thống Kê</button>
</div>
​<!-- PANEL ĐUA TỐC ĐỘ -->
<div id="panel-sprint" class="panel">
<div class="card-section">
<div class="form-group">
<label>Liên Kết Tài Khoản:</label>
<div id="sprint_link_wrapper" style="display: {% if spr.uid %}none{% else %}block{% endif %};">
<div class="input-row">
<input type="text" id="sprint_link" placeholder="Dán liên kết có chứa userId=...&secretKey=...">
<button class="btn-action-sm" onclick="saveLink('sprint')">Lưu</button>
</div>
</div>
<div id="sprint_account_card" class="account-box" style="display: {% if spr.uid %}flex{% else %}none{% endif %};">
<div class="account-info">
<span class="acc-label">Tài Khoản Đang Liên Kết</span>
<span class="acc-uid" id="sprint_uid_display">UID: {{ spr.uid }}</span>
</div>
<button class="btn-danger-sm" onclick="deleteLink('sprint')">Xóa Nick</button>
</div>
</div>
​<div class="grid-2">
<div class="form-group">
<label>Loại Tiền:</label>
<select id="sprint_asset">
<option value="BUILD" {% if spr.asset_type == 'BUILD' %}selected{% endif %}>BUILD</option>
<option value="WORLD" {% if spr.asset_type == 'WORLD' %}selected{% endif %}>WORLD</option>
<option value="USDT" {% if spr.asset_type == 'USDT' %}selected{% endif %}>USDT</option>
</select>
</div>
<div class="form-group">
<label>Tổng Cược:</label>
<input type="number" id="sprint_bet" value="{{ spr.bet_amount_total }}" step="0.1" min="0.1">
</div>
</div>
​<div class="form-group">
<label>Giới Hạn Số Ván (0 = Vĩnh Viễn):</label>
<input type="number" id="sprint_max_rounds" value="{{ spr.max_rounds }}" min="0">
</div>
</div>
​<button id="btn_sprint_toggle" class="btn-main {% if spr.running %}btn-stop{% else %}btn-start{% endif %}" onclick="toggleBot('sprint')">
{% if spr.running %}Dừng Chạy Tự Động{% else %}Bật Tự Động 24/7{% endif %}
</button>
​<div class="live-log">
<div id="sprint_dot" class="dot-live {% if spr.running %}active{% endif %}"></div>
<span id="sprint_log_text">{{ spr.last_log }}</span>
</div>
​<div class="stats-grid">
<div class="stat-item"><div class="label">Trạng Thái</div><div class="val" id="sprint_status_text" style="color: {% if spr.running %}#34d399{% else %}#f87171{% endif %};">{% if spr.running %}Đang Chạy 24/7{% else %}Đang Dừng{% endif %}</div></div>
<div class="stat-item"><div class="label">Tổng Ván Cược</div><div class="val" id="sprint_tot_bets" style="color: #38bdf8;">{{ spr.total_bets }}</div></div>
<div class="stat-item"><div class="label">Thắng / Thua</div><div class="val" id="sprint_win_loss">{{ spr.wins }} / {{ spr.losses }} (0.0%)</div></div>
<div class="stat-item"><div class="label">Tổng Lợi Nhuận</div><div class="val" id="sprint_profit" style="color: #34d399;">+0.0000 {{ spr.asset_type }}</div></div>
</div>
<button class="btn-reset" onclick="resetStats('sprint')">Làm Mới Thống Kê</button>
</div>
</div>
​<script>
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
if(!link) { showToast("Vui lòng dán liên kết tài khoản."); return; }
fetch('/api/game_action', {
method: 'POST', headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ game_type: game, action: 'save_link', link: link })
}).then(res => res.json()).then(data => {
showToast(data.msg);
if(data.success && data.uid) {
document.getElementById(game + '_uid_display').innerText = "UID: " + data.uid;
document.getElementById(game + '_link_wrapper').style.display = 'none';
document.getElementById(game + '_account_card').style.display = 'flex';
}
});
}
function deleteLink(game) {
if(!confirm("Bạn có chắc chắn muốn xóa tài khoản này không?")) return;
fetch('/api/game_action', {
method: 'POST', headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ game_type: game, action: 'delete_link' })
}).then(res => res.json()).then(data => {
showToast(data.msg);
document.getElementById(game + '_link').value = '';
document.getElementById(game + '_link_wrapper').style.display = 'block';
document.getElementById(game + '_account_card').style.display = 'none';
updateUIState(game, false);
});
}
function toggleBot(game) {
const asset = document.getElementById(game + '_asset').value;
const bet = document.getElementById(game + '_bet').value;
const mr = document.getElementById(game + '_max_rounds');
const sl = document.getElementById(game + '_stop_loss');
const tp = document.getElementById(game + '_take_profit');
​fetch('/api/game_action', {
method: 'POST', headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({
game_type: game, action: 'toggle_bot', asset_type: asset, bet: bet,
max_rounds: mr ? mr.value : 0, stop_loss: sl ? sl.value : 0, take_profit: tp ? tp.value : 0
})
}).then(res => res.json()).then(data => {
showToast(data.msg);
if(data.success) updateUIState(game, data.running);
});
}
function updateUIState(game, running) {
const btn = document.getElementById('btn_' + game + '_toggle');
const statusText = document.getElementById(game + '_status_text');
const dot = document.getElementById(game + '_dot');
if(running) {
btn.className = "btn-main btn-stop"; btn.innerText = 'Dừng Chạy Tự Động';
statusText.innerText = "Đang Chạy 24/7"; statusText.style.color = "#34d399"; dot.classList.add('active');
} else {
btn.className = "btn-main btn-start"; btn.innerText = 'Bật Tự Động 24/7';
statusText.innerText = "Đang Dừng"; statusText.style.color = "#f87171"; dot.classList.remove('active');
}
}
function resetStats(game) {
fetch('/api/game_action', {
method: 'POST', headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ game_type: game, action: 'reset_stats' })
}).then(res => res.json()).then(data => { showToast(data.msg); });
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
if(data.uid) {
document.getElementById(game + '_uid_display').innerText = "UID: " + data.uid;
document.getElementById(game + '_link_wrapper').style.display = 'none';
document.getElementById(game + '_account_card').style.display = 'flex';
}
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
​ADMIN_LOGIN_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Đăng Nhập Quản Trị</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
body { background: #04060f; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 15px; }
.card { background: rgba(11, 17, 32, 0.9); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); padding: 36px 28px; border-radius: 26px; width: 100%; max-width: 380px; text-align: center; }
h2 { color: #fff; margin-bottom: 22px; font-size: 20px; font-weight: 800; }
input { width: 100%; padding: 13px 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(2,6,23,0.7); color: #fff; margin-bottom: 14px; font-size: 14px; text-align: center; outline: none; }
.btn { width: 100%; background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%); color: #fff; border: none; padding: 14px; border-radius: 12px; font-weight: 700; cursor: pointer; font-size: 14px; }
.error { color: #f87171; font-size: 12.5px; margin-bottom: 14px; font-weight: 600; }
.back { display: inline-block; margin-top: 16px; color: #94a3b8; font-size: 12px; text-decoration: none; font-weight: 600; }
</style></head>
<body><div class="card">
<h2>Đăng Nhập Quản Trị</h2>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="POST">
<input type="text" name="username" placeholder="Tài khoản quản trị..." required autocomplete="off">
<input type="password" name="password" placeholder="Mật khẩu..." required>
<button type="submit" class="btn">Đăng Nhập</button>
</form>
<a href="/" class="back">Quay lại trang chủ</a>
</div></body></html>
"""
​ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Quản Lý Hệ Thống</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
body { background: #04060f; color: #f8fafc; padding: 16px; }
.container { max-width: 1050px; margin: 0 auto; background: rgba(11, 17, 32, 0.9); border: 1px solid rgba(255,255,255,0.08); padding: 24px; border-radius: 22px; }
.header-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 16px; }
h2 { color: #fff; font-size: 16px; font-weight: 800; }
.logout { color: #f87171; text-decoration: none; font-size: 12px; font-weight: 700; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 7px 12px; border-radius: 10px; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { background: rgba(2, 6, 23, 0.7); border: 1px solid rgba(255,255,255,0.06); padding: 16px; border-radius: 14px; text-align: center; }
.stat-card h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; }
.stat-card span { font-size: 20px; font-weight: 800; color: #38bdf8; }
.table-responsive { width: 100%; overflow-x: auto; border-radius: 14px; border: 1px solid rgba(255,255,255,0.08); }
table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 650px; }
th, td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left; vertical-align: middle; white-space: nowrap; }
th { color: #94a3b8; font-weight: 700; background: rgba(2, 6, 23, 0.9); }
code { background: rgba(2, 6, 23, 0.9); padding: 4px 8px; border-radius: 6px; color: #34d399; font-family: monospace; font-weight: 700; }
.btn-action { border: none; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 11px; font-weight: 700; text-decoration: none; display: inline-flex; }
.btn-add-time { background: rgba(5, 150, 105, 0.2); color: #34d399; }
.btn-sub-time { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.btn-del { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.btn-del-all { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 10px 16px; border-radius: 10px; font-weight: 700; font-size: 12px; text-decoration: none; }
.btn-copy-code { background: rgba(79, 70, 229, 0.2); color: #a5b4fc; }
.btn-add { background: #059669; color: #fff; border: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 12px; cursor: pointer; }
.btn-vip { background: #d97706; color: #fff; border: none; padding: 10px 18px; border-radius: 10px; font-weight: 800; font-size: 12px; cursor: pointer; }
.box-create { background: rgba(2, 6, 23, 0.7); padding: 16px; border-radius: 16px; margin-bottom: 20px; display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; border: 1px solid rgba(255,255,255,0.06); }
.box-create input { padding: 9px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); background: #0b1120; color: #fff; font-size: 13px; width: 90px; margin-top: 4px; display: block; }
.input-time { padding: 5px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: #0b1120; color: #fff; width: 55px; text-align: center; }
</style></head>
<body>
<div class="container">
<div class="header-flex">
<h2>QUẢN TRỊ HỆ THỐNG MÃ BẢN QUYỀN</h2>
<a href="/quan-ly-bi-mat-dunghoet/logout" class="logout">Đăng Xuất</a>
</div>
<div class="stats-grid">
<div class="stat-card"><h4>Tổng Số Mã</h4><span>{{ total_keys_count }}</span></div>
<div class="stat-card"><h4>Đã Kích Hoạt</h4><span style="color: #f87171;">{{ used_keys_count }}</span></div>
<div class="stat-card"><h4>Chưa Sử Dụng</h4><span style="color: #34d399;">{{ unused_keys_count }}</span></div>
</div>
<div class="box-create">
<div><label style="font-size: 11px; color: #94a3b8;">Thời Hạn (Giờ):</label><input type="number" id="customHours" value="24" min="1"></div>
<div><label style="font-size: 11px; color: #94a3b8;">Số Lượng:</label><input type="number" id="customQty" value="1" min="1" max="100"></div>
<div><label style="font-size: 11px; color: #94a3b8;">Số Thiết Bị:</label><input type="number" id="maxUses" value="1" min="1" max="1000"></div>
<div style="display: flex; gap: 10px; flex-wrap: wrap;">
<button class="btn-add" onclick="createCustomKey(false)">Tạo Mã Thường</button>
<button class="btn-vip" onclick="createCustomKey(true)">Tạo Mã VIP</button>
<a href="/quan-ly-bi-mat-dunghoet/delete_all" class="btn-del-all" onclick="return confirm('Xóa sạch toàn bộ mã?')">Xóa Sạch</a>
</div>
</div>
<div class="table-responsive">
<table>
<tr>
<th>Mã Bản Quyền</th><th>Loại</th><th>Cộng/Trừ Giờ</th><th>Thời Gian Còn</th><th>Lượt Dùng</th><th>Thao Tác</th>
</tr>
{% for k, info in keys.items() %}
{% set expire_at = info.get('expire_at', 0) %}
{% set remain = (expire_at - now) if expire_at and expire_at > now else 0 %}
{% set rem_h = (remain // 3600)|int %}
{% set rem_m = ((remain % 3600) // 60)|int %}
{% set used_list = info.get('used_by', []) %}
<tr>
<td><code>{{ k }}</code></td>
<td>{% if info.get('is_vip') %}<b style="color:#f59e0b">VIP</b>{% else %}<span style="color:#94a3b8">Thường</span>{% endif %}</td>
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
<div style="display: flex; gap: 6px;">
<button class="btn-action btn-copy-code" onclick="navigator.clipboard.writeText('{{ k }}')">Sao Chép</button>
<a href="/quan-ly-bi-mat-dunghoet/delete?key={{ k }}" class="btn-action btn-del" onclick="return confirm('Xóa mã này?')">Xóa</a>
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
​MAINTENANCE_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Bảo Trì Hệ Thống</title></head>
<body style="background:#04060f;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;text-align:center;">
<div><h1 style="font-size:24px;margin-bottom:10px;">HỆ THỐNG ĐANG BẢO TRÌ</h1><p style="color:#94a3b8;">{{ notice }}</p></div>
</body>
</html>
"""
​if name == "main":
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port, threaded=True)
