import os
import json
import time
import random
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, render_template_string, request, redirect, url_for, session
import telebot
from telebot import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)
app.secret_key = "dung_license_secret_key_1612012"

KEYS_DB_FILE = "keys_db.json"
ADMIN_PASSWORD = "dung1612012"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

def load_keys():
    if os.path.exists(KEYS_DB_FILE):
        try:
            with open(KEYS_DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_keys(keys_data):
    with open(KEYS_DB_FILE, "w") as f:
        json.dump(keys_data, f, indent=4)

@app.route('/')
def home():
    new_key = request.args.get("key", "")
    error = request.args.get("error", "")
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWORLD LICENSE GATEWAY</title>
        <style>
            body { background: linear-gradient(135deg, #0f172a, #1e293b); color: #fff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .card { background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(10px); padding: 35px; border-radius: 24px; width: 90%; max-width: 400px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6); border: 1px solid rgba(56, 189, 248, 0.2); }
            .icon { font-size: 60px; margin-bottom: 10px; }
            .badge { background: linear-gradient(90deg, #0284c7, #38bdf8); color: #fff; padding: 6px 16px; border-radius: 20px; font-size: 11px; font-weight: bold; text-transform: uppercase; }
            h2 { color: #38bdf8; margin: 20px 0 10px; font-size: 22px; }
            p { color: #94a3b8; font-size: 13px; line-height: 1.6; margin-bottom: 25px; }
            .btn { display: block; background: linear-gradient(90deg, #0284c7, #6366f1); color: #fff; text-decoration: none; padding: 15px; border-radius: 14px; font-weight: bold; font-size: 15px; box-shadow: 0 8px 20px rgba(2, 132, 199, 0.4); }
            .btn-admin { display: block; background: rgba(51, 65, 85, 0.6); color: #94a3b8; text-decoration: none; padding: 12px; border-radius: 12px; font-size: 13px; margin-top: 15px; }
            .key-box { background: #0b0f19; border: 2px dashed #38bdf8; padding: 14px; border-radius: 12px; margin-top: 15px; font-family: monospace; font-size: 16px; color: #4ade80; word-break: break-all; }
            .error { background: rgba(248, 113, 113, 0.1); border: 1px solid #f87171; color: #f87171; padding: 10px; border-radius: 10px; font-size: 13px; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">🔑</div>
            <span class="badge">Hệ thống tự động 24/7</span>
            <h2>XWORLD GATEWAY</h2>
            <p>Vượt link Link4m an toàn và nhanh chóng để nhận mã bản quyền sử dụng trong 24 giờ.</p>
            {% if new_key %}
                <div class="key-box"><b>{{ new_key }}</b></div>
                <p style="color: #4ade80; margin-top: 12px; font-weight: bold;">👉 Sao chép mã trên dán vào Bot Telegram!</p>
            {% else %}
                <a href="/get_link4m" class="btn">🚀 TIẾN HÀNH LẤY KEY</a>
            {% endif %}
            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}
            <a href="/admin" class="btn-admin">⚙️ Đăng nhập Quản trị viên</a>
        </div>
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
        if result.get("status") == "success":
            return redirect(result.get("shortenedUrl"))
        else:
            return redirect(url_for('home', error=result.get("message", "Lỗi tạo link")))
    except:
        return redirect(url_for('home', error="Không thể kết nối Link4m API"))

@app.route('/claim_key')
def claim_key():
    keys_db = load_keys()
    new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    keys_db[new_key] = {"status": "chua_dung", "used_by": None, "created_at": time.time(), "expire_at": None}
    save_keys(keys_db)
    return redirect(url_for('home', key=new_key))

@app.route('/api/verify_key')
def api_verify_key():
    key_code = request.args.get('key', '').strip()
    user_id = request.args.get('user_id', '').strip()
    keys_db = load_keys()
    if key_code not in keys_db:
        return {"status": "error", "msg": "Key không tồn tại!"}
    k_data = keys_db[key_code]
    if k_data["status"] == "da_dung":
        if k_data["used_by"] == user_id and time.time() < k_data["expire_at"]:
            return {"status": "success", "msg": "Key vẫn còn hiệu lực 24h!"}
        return {"status": "error", "msg": "Key đã được sử dụng hoặc hết hạn!"}
    k_data["status"] = "da_dung"
    k_data["used_by"] = user_id
    k_data["expire_at"] = time.time() + (24 * 3600)
    save_keys(keys_db)
    return {"status": "success", "msg": "Kích hoạt thành công 24 giờ!"}

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Mật khẩu bảo mật không chính xác!"
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập Quản Trị</title>
    <style>
        body { background: #0f172a; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #1e293b; padding: 30px; border-radius: 20px; width: 90%; max-width: 350px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h2 { color: #38bdf8; margin-bottom: 20px; font-size: 18px; }
        input { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; margin-bottom: 15px; }
        .btn { width: 100%; background: #0284c7; color: #fff; border: none; padding: 12px; border-radius: 10px; font-weight: bold; cursor: pointer; }
        .error { color: #f87171; font-size: 13px; margin-bottom: 10px; }
        .back { display: block; margin-top: 15px; color: #94a3b8; font-size: 13px; text-decoration: none; }
    </style></head>
    <body><div class="card">
        <h2>🔒 Quản Trị Hệ Thống</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST"><input type="password" name="password" placeholder="Mật khẩu admin..." required><button type="submit" class="btn">Đăng Nhập</button></form>
        <a href="/" class="back">← Quay lại trang chủ</a>
    </div></body></html>
    """
    return render_template_string(html, error=error)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    keys_db = load_keys()
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Quản Lý Key</title>
    <style>
        body { background: #0f172a; color: #fff; font-family: sans-serif; padding: 20px; margin: 0; }
        .container { max-width: 650px; margin: 0 auto; background: #1e293b; padding: 20px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h2 { color: #38bdf8; margin-top: 0; font-size: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }
        th, td { padding: 10px; border-bottom: 1px solid #334155; text-align: left; }
        th { color: #94a3b8; }
        .btn-del { background: #ef4444; color: #fff; border: none; padding: 6px 10px; border-radius: 6px; cursor: pointer; text-decoration: none; }
        .btn-add { background: #22c55e; color: #fff; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 15px; }
        .logout { float: right; color: #94a3b8; text-decoration: none; font-size: 14px; }
        .status-used { color: #f87171; } .status-new { color: #4ade80; }
    </style></head>
    <body><div class="container">
        <a href="/admin/logout" class="logout">Đăng xuất</a>
        <h2>⚙️ Quản Lý Key Bản Quyền</h2>
        <a href="/claim_key" class="btn-add">➕ Tạo Key Mới</a>
        <table><tr><th>Mã Key</th><th>Trạng Thái & User</th><th>Còn Lại</th><th>Xóa</th></tr>
        {% for k, info in keys.items() %}
        <tr><td><code>{{ k }}</code></td>
        <td>{% if info.status == 'da_dung' %}<span class="status-used">Đã dùng (ID: {{ info.used_by }})</span>{% else %}<span class="status-new">Chưa dùng</span>{% endif %}</td>
        <td>{% if info.expire_at and now < info.expire_at %}{{ ((info.expire_at - now) | int // 3600) }}h nữa{% else %}Hết hạn{% endif %}</td>
        <td><a href="/admin/delete?key={{ k }}" class="btn-del" onclick="return confirm('Xóa key này?')">Xóa</a></td></tr>
        {% endfor %}</table></div></body></html>
    """
    return render_template_string(html, keys=keys_db, now=time.time())

@app.route('/admin/delete')
def admin_delete():
    if not session.get('admin_logged'): return redirect(url_for('admin_login'))
    k = request.args.get('key')
    keys_db = load_keys()
    if k in keys_db: del keys_db[k]; save_keys(keys_db)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))
user_data = {}
data_lock = Lock()

ROOM_NAMES = {
    1: "Nhà Kho", 2: "Phòng trò chuyện", 3: "Phòng tài vụ", 4: "Phòng họp",
    5: "Phòng giám sát", 6: "Phòng nhân sự", 7: "Phòng giám đốc", 8: "Văn phòng"
}

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None, "waiting_for_link": None, "waiting_for_bet": None,
                "waiting_for_key": False, "has_valid_key": False, "prompt_msg_id": None,
                "escape": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "base_bet": 1.0, "killer_stats": {i: 0 for i in range(1, 9)}},
                "sprint": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "bet_amount_total": "1", "lose_limit": 3, "rest_rounds": 1, "lose_multiplier": "1.0"}
            }
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {
            "total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0,
            "streak_loss": 0, "current_build": Decimal("1"), "random_stop": Event()
        }
    return account_threads[key]

def verify_key_with_server(key_code, user_id):
    try:
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:5000")
        url = f"{web_url}/api/verify_key?key={key_code}&user_id={user_id}"
        res = requests.get(url, timeout=3)
        return res.json()
    except:
        return {"status": "error", "msg": "Không thể kết nối máy chủ xác thực key!"}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None; cfg["waiting_for_bet"] = None
    if not cfg["has_valid_key"]:
        cfg["waiting_for_key"] = True
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = f"🔐 *YÊU CẦU KEY BẢN QUYỀN*\n━━━━━━━━━━━━━━━━━━━\n🌐 Lấy Key tại Web: {web_url}\n🔑 Vui lòng nhập mã Key của bạn vào ô chat bên dưới:"
        try:
            sent = bot.send_message(chat_id, msg_text, parse_mode="Markdown")
            cfg["prompt_msg_id"] = sent.message_id
        except: pass
        return
    show_main_menu(chat_id, message.message_id, is_new=True)

def show_main_menu(chat_id, message_id, is_new=False):
    msg_text = "🎮 *XWORLD BOT* | Chọn game:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    try:
        if is_new: bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        else: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try: bot.answer_callback_query(call.id, "⚠️ Cần nhập Key bản quyền trước!", show_alert=True)
        except: pass
        return
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)

def show_game_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    g_cfg = cfg[game_type]
    game_name = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
    total_accs = len(g_cfg["accounts"])
    bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    msg_text = f"🎮 *{game_name.upper()}*\nTrạng thái: {status_str} | Nick: `{total_accs}` | Cược: `{bet_disp}`"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Sửa Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton("👥 DS Nick", callback_data=f"game_{game_type}_list"),
        types.InlineKeyboardButton("📊 Thống Kê", callback_data=f"game_{game_type}_status"),
        types.InlineKeyboardButton("🔙 Quay lại", callback_data="back_to_main")
    )
    try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        try: bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None; cfg["waiting_for_bet"] = None
    try: bot.answer_callback_query(call.id)
    except: pass
    show_main_menu(chat_id, call.message.message_id, is_new=False)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try: bot.answer_callback_query(call.id, "⚠️ Hết hạn Key!", show_alert=True)
        except: pass
        return
    parts = call.data.split("_")
    game_type = parts[1]; action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    markup_back = types.InlineKeyboardMarkup()
    markup_back.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}"))

    if action == "setup_link":
        cfg["waiting_for_link"] = game_type; cfg["waiting_for_bet"] = None; cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"📥 **Dán link [ {game_name_vi} ] vào ô chat:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type; cfg["waiting_for_link"] = None; cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "toggle_bot":
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
                else: Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
            try: bot.answer_callback_query(call.id, f"🚀 Đã bật auto!")
            except: pass
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]: get_account_state(game_type, uid)["random_stop"].set()
            try: bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
            except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        try: bot.answer_callback_query(call.id, f"Đổi sang {g_cfg['asset_type']}")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "list":
        if not g_cfg["accounts"]:
            try: bot.answer_callback_query(call.id, "Chưa có nick nào!", show_alert=True)
            except: pass
            return
        msg = f"👥 *DS NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1): msg += f"{idx}. `{uid}`\n"
        try: bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "status":
        try: bot.answer_callback_query(call.id, "🔄 Cập nhật!")
        except: pass
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]; tot_wins += st["wins"]; tot_losses += st["losses"]; tot_profit += st["total_profit"]
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0.0
        msg = f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n━━━━━━━━━━━━━━━━━━━\n📌 Trạng thái: {'🟢 Chạy' if g_cfg['global_running'] else '🔴 Dừng'}\n🎲 Tổng cược: `{tot_bets}`\n🏆 Thắng/Thua: `{tot_wins}` / `{tot_losses}`\n📈 Tỷ lệ thắng: `{wr:.1f}%`\n💵 Tổng Lời/Lỗ: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
        if game_type == "escape":
            k_stats = g_cfg.get("killer_stats", {}); total_k = sum(k_stats.values())
            msg += f"\n━━━━━━━━━━━━━━━━━━━\n👹 *SÁT THỦ:* (Tổng: `{total_k}` lần)\n"
            for rid in range(1, 9):
                cnt = k_stats.get(rid, 0); pct = (cnt / total_k * 100) if total_k > 0 else 0.0
                msg += f"🚪 {ROOM_NAMES.get(rid)}: `{cnt}` (`{pct:.1f}%`)\n"
        markup_stat = types.InlineKeyboardMarkup(row_width=2)
        markup_stat.add(
            types.InlineKeyboardButton("🔄 Cập nhật", callback_data=f"game_{game_type}_status"),
            types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}")
        )
        try: bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_stat, parse_mode="Markdown")
        except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_game_"))
def callback_back_game(call):
    chat_id = call.message.chat.id; game_type = call.data.split("_")[3]
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)
    
