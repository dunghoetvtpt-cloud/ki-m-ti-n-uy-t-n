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

import session_manager

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
            return {"status": "success", "msg": "Key vẫn còn hiệu lực 24h!", "expire_at": k_data["expire_at"]}
        return {"status": "error", "msg": "Key đã được sử dụng hoặc hết hạn!"}
    k_data["status"] = "da_dung"
    k_data["used_by"] = user_id
    expire_time = time.time() + (24 * 3600)
    k_data["expire_at"] = expire_time
    save_keys(keys_db)
    return {"status": "success", "msg": "Kích hoạt thành công 24 giờ!", "expire_at": expire_time}

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

GAME_NAMES_VI = {
    "escape": "Vua Thoát Hiểm",
    "sprint": "Đua Tốc Độ"
}

def get_user_config(chat_id):
    with data_lock:
        is_valid, expire_time = session_manager.check_session_valid(chat_id)

        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None, "waiting_for_link": None, "waiting_for_bet": None,
                "waiting_for_rounds": None, "waiting_for_key": False, "waiting_for_uids": None,
                "has_valid_key": is_valid, "key_expire_at": expire_time, "prompt_msg_id": None,
                "escape": {
                    "accounts": {}, "global_running": False, "asset_type": "BUILD", 
                    "base_bet": 1.0, "max_rounds": 0, "killer_stats": {i: 0 for i in range(1, 9)},
                    "selected_uids": []
                },
                "sprint": {
                    "accounts": {}, "global_running": False, "asset_type": "BUILD", 
                    "bet_amount_total": "1", "max_rounds": 0, "lose_limit": 3, 
                    "rest_rounds": 1, "lose_multiplier": "2.5",
                    "selected_uids": []
                }
            }
        else:
            user_data[chat_id]["has_valid_key"] = is_valid
            user_data[chat_id]["key_expire_at"] = expire_time
            
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

def check_key_validity(chat_id):
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        return False
    if time.time() >= cfg.get("key_expire_at", 0):
        cfg["has_valid_key"] = False
        cfg["escape"]["global_running"] = False
        cfg["sprint"]["global_running"] = False
        return False
    return True

def reset_user_wait_flags(cfg):
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    cfg["waiting_for_rounds"] = None
    cfg["waiting_for_uids"] = None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    
    if not check_key_validity(chat_id):
        cfg["waiting_for_key"] = True
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = (
            "📜 **XWORLD LICENSE GATEWAY**\n"
            "───────────────────\n"
            "⚠️ **Key của bạn đã hết hạn hoặc chưa kích hoạt.**\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=web_url),
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
    
    text = "🔑 **Vui lòng nhập mã Key của bạn vào đây**\n*(Ví dụ: `KEY-XW-XXXXXXXX`):*"
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
    msg_text = (
        "📜 **XWORLD LICENSE GATEWAY**\n"
        "───────────────────\n"
        "⚠️ **Bạn cần có Key bản quyền để sử dụng bot.**\n\n"
        "👉 Vui lòng chọn thao tác bên dưới:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=web_url),
        types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="btn_nhap_key")
    )
    try: bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except: pass

def show_main_menu(chat_id, message_id, is_new=False):
    cfg = get_user_config(chat_id)
    reset_user_wait_flags(cfg)
    remaining_sec = int(cfg.get("key_expire_at", 0) - time.time())
    h = max(0, remaining_sec // 3600)
    m = max(0, (remaining_sec % 3600) // 60)
    
    msg_text = f"🎮 *XWORLD BOT* | Key còn hạn: `{h}h {m}p`\nChọn game:"
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
    reset_user_wait_flags(cfg)
    if not check_key_validity(chat_id):
        cfg["waiting_for_key"] = True
        cfg["prompt_msg_id"] = call.message.message_id
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = (
            "📜 **XWORLD LICENSE GATEWAY**\n"
            "───────────────────\n"
            "⚠️ **Key của bạn đã hết hạn!**\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=web_url),
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
    reset_user_wait_flags(cfg)
    g_cfg = cfg[game_type]
    game_name = GAME_NAMES_VI.get(game_type, "Game")
    status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
    total_accs = len(g_cfg["accounts"])
    selected_count = len(g_cfg.get("selected_uids", []))
    selected_str = f"{selected_count} nick" if selected_count > 0 else f"Tất cả ({total_accs})"
    
    bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    rounds_disp = g_cfg.get('max_rounds', 0)
    rounds_str = f"{rounds_disp} ván" if rounds_disp > 0 else "Vô hạn"
    
    remaining_sec = int(cfg.get("key_expire_at", 0) - time.time())
    h = max(0, remaining_sec // 3600)
    m = max(0, (remaining_sec % 3600) // 60)
    
    msg_text = f"🎮 *{game_name.upper()}* | Key: `{h}h {m}p`\nTrạng thái: {status_str} | Chạy: `{selected_str}` / Tổng: `{total_accs}/1`\nCược: `{bet_disp}` | Giới hạn: `{rounds_str}`"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🗑️ Xóa Nick", callback_data=f"game_{game_type}_delete_acc"),
        types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Sửa Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton("🔢 Sửa Số Ván", callback_data=f"game_{game_type}_input_rounds"),
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
        msg_text = (
            "📜 **XWORLD LICENSE GATEWAY**\n"
            "───────────────────\n"
            "⚠️ **Key của bạn đã hết hạn!**\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=web_url),
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

    if action == "setup_link":
        if len(g_cfg["accounts"]) >= 1:
            try: bot.answer_callback_query(call.id, "⚠️ Đã có nick! Hãy xóa nick cũ trước khi thêm nick mới.", show_alert=True)
            except: pass
            return
        reset_user_wait_flags(cfg)
        cfg["waiting_for_link"] = game_type
        cfg["prompt_msg_id"] = call.message.message_id
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
        for uid in list(g_cfg["accounts"].keys()):
            get_account_state(game_type, uid)["random_stop"].set()
        
        g_cfg["accounts"].clear()
        g_cfg["selected_uids"].clear()
        try:
            bot.answer_callback_query(call.id, "🗑️ Đã xóa nick thành công!")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "input_bet":
        reset_user_wait_flags(cfg)
        cfg["waiting_for_bet"] = game_type
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "input_rounds":
        reset_user_wait_flags(cfg)
        cfg["waiting_for_rounds"] = game_type
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"🔢 **Nhập số ván muốn cược (Nhập `0` nếu muốn chạy vô hạn):**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
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
                st["total_bets"] = 0
                st["random_stop"].clear()
                if game_type == "escape": 
                    Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                elif game_type == "sprint": 
                    Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                        
            try: bot.answer_callback_query(call.id, "🚀 Đã bật auto thành công!")
            except: pass
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]: 
                get_account_state(game_type, uid)["random_stop"].set()
            try: bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
            except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        current_asset = g_cfg["asset_type"]
        if current_asset == "BUILD":
            g_cfg["asset_type"] = "WORLD"
        elif current_asset == "WORLD":
            g_cfg["asset_type"] = "USDT"
        else:
            g_cfg["asset_type"] = "BUILD"

        if game_type == "sprint":
            if not g_cfg.get("bet_amount_total"):
                g_cfg["bet_amount_total"] = "1"
            for uid in g_cfg["accounts"]:
                get_account_state("sprint", uid)["current_build"] = Decimal(str(g_cfg["bet_amount_total"]))
        else:
            if not g_cfg.get("base_bet"):
                g_cfg["base_bet"] = 1.0

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
    cfg = get_user_config(chat_id)
    
    if cfg.get("waiting_for_key"):
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        if prompt_id:
            try: bot.delete_message(chat_id, prompt_id)
            except: pass

        res = verify_key_with_server(text, str(chat_id))
        if res.get("status") == "success":
            cfg["has_valid_key"] = True
            cfg["waiting_for_key"] = False
            cfg["key_expire_at"] = res.get("expire_at", time.time() + 86400)
            
            session_manager.save_session_to_file(chat_id, cfg["key_expire_at"])
            
            bot.send_message(
                chat_id,
                "✅ **Kích hoạt Key thành công!** Sử dụng trong 24 giờ.",
                parse_mode="Markdown"
            )
            show_main_menu(chat_id, message.message_id, is_new=True)
        else:
            web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("🌐 Lấy Key Mới", url=web_url),
                types.InlineKeyboardButton("🔑 Nhập Lại Key", callback_data="btn_nhap_key")
            )
            bot.send_message(
                chat_id,
                f"❌ **Không thể xác thực!**\nKey `{text}` không hợp lệ hoặc đã hết hạn.",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        return

    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_link}"))
        
        g_cfg = cfg[game_target_link]
        if len(g_cfg["accounts"]) >= 1:
            if prompt_id:
                try: bot.edit_message_text("⚠️ **Đã có nick!** Vui lòng xóa nick cũ trước.", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            cfg["waiting_for_link"] = None
            return

        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text); query_params = parse_qs(parsed_url.query)
                uid_str = query_params.get("userId", [None])[0]; skey = query_params.get("secretKey", [None])[0]
                if uid_str and skey:
                    uid = int(uid_str); g_cfg["accounts"][uid] = skey; cfg["waiting_for_link"] = None
                    if g_cfg["global_running"] and check_key_validity(chat_id):
                        if game_target_link == "escape": Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                        elif game_target_link == "sprint": Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                    if prompt_id:
                        try: bot.edit_message_text(f"✅ **Thêm nick thành công!** (`{uid}`)", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                        except: pass
                    return
            except: pass
        if prompt_id:
            try: bot.edit_message_text("⚠️ **Link lỗi!** Thử lại:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
            except: pass
        return

    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_bet}"))
        try:
            val = float(text)
            if val <= 0: raise ValueError()
            g_cfg = cfg[game_target_bet]
            if game_target_bet == "sprint":
                g_cfg["bet_amount_total"] = str(val)
                for uid in g_cfg["accounts"]: get_account_state("sprint", uid)["current_build"] = Decimal(str(val))
            else: g_cfg["base_bet"] = val
            cfg["waiting_for_bet"] = None
            if prompt_id:
                try: bot.edit_message_text(f"✅ **Đã cập nhật cược:** `{val}`", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            return
        except:
            if prompt_id:
                try: bot.edit_message_text("⚠️ **Số tiền lỗi!** Nhập lại số:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            return

    game_target_rounds = cfg.get("waiting_for_rounds")
    if game_target_rounds:
        try: bot.delete_message(chat_id, message.message_id)
        except: pass
        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_rounds}"))
        try:
            val = int(text)
            if val < 0: raise ValueError()
            g_cfg = cfg[game_target_rounds]
            g_cfg["max_rounds"] = val
            cfg["waiting_for_rounds"] = None
            rounds_desc = f"{val} ván" if val > 0 else "Vô hạn"
            if prompt_id:
                try: bot.edit_message_text(f"✅ **Đã cập nhật số ván cược:** `{rounds_desc}`", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            return
        except:
            if prompt_id:
                try: bot.edit_message_text("⚠️ **Số ván lỗi!** Nhập lại số nguyên dương:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            return

    if not text.startswith("/"):
        try: bot.delete_message(chat_id, message.message_id)
        except: pass

# ==========================================================
# 🎮 LOGIC ĐẶT CƯỢC ĐƯỢC TÍCH HỢP TỪ 2 FILE MẪU
# ==========================================================

def run_escape_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)
    escape_cfg = cfg["escape"]
    acc_st = get_account_state("escape", uid)
    headers = {"Content-Type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey, "Accept": "application/json", "xb-language": "vi-VN"}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36",
        "Origin": "https://escapemaster.net",
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": "https://escapemaster.net/",
    })

    def enter_room(r_id):
        try:
            resp = session.post("https://api.escapemaster.net/escape_game/enter_room", json={"asset_type": escape_cfg["asset_type"], "user_id": int(uid), "room_id": int(r_id)}, headers=headers, timeout=5)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except: return False

    def place_bet(r_id, amt):
        try:
            resp = session.post("https://api.escapemaster.net/escape_game/bet", json={"asset_type": escape_cfg["asset_type"], "user_id": int(uid), "room_id": int(r_id), "bet_amount": float(amt)}, headers=headers, timeout=5)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except: return False

    def get_game_home():
        try:
            resp = session.get("https://api.escapemaster.net/escape_game/home", params={"asset_type": escape_cfg["asset_type"]}, headers=headers, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except: pass
        return {}

    def get_my_joined():
        try:
            resp = session.get("https://api.escapemaster.net/escape_game/my_joined", params={"asset": escape_cfg["asset_type"], "page": 1, "page_size": 10}, headers=headers, timeout=5)
            if resp.status_code == 200: return resp.json().get("data", {}).get("items", [])
        except: pass
        return []

    # Logic chiến lược từ XWVuaThoatHiem_2.py
    current_bet = float(escape_cfg["base_bet"])
    consecutive_losses = 0
    loss_threshold = 2
    skip_rounds = 3
    multiplier = 2.0
    skips_left = 0

    while escape_cfg["global_running"] and not acc_st["random_stop"].is_set():
        if not check_key_validity(chat_id):
            escape_cfg["global_running"] = False
            acc_st["random_stop"].set()
            try: bot.send_message(chat_id, "⚠️ **Key đã hết hạn!** Bot Vua Thoát Hiểm đã tự động tắt.", parse_mode="Markdown")
            except: pass
            break
        if escape_cfg.get("max_rounds", 0) > 0 and acc_st["total_bets"] >= escape_cfg["max_rounds"]:
            acc_st["random_stop"].set()
            break
        try:
            home_data = get_game_home()
            latest_issue = str(home_data.get("issue_id") or home_data.get("current_issue") or "")
            count_down = home_data.get("count_down", 50)
            if not latest_issue:
                items = get_my_joined()
                if items:
                    latest_issue = str(items[0].get("issue_id"))

            if latest_issue and acc_st.get("current_issue") != latest_issue:
                acc_st["current_issue"] = latest_issue
                
                if skips_left > 0:
                    skips_left -= 1
                    time.sleep(3)
                    continue

                acc_st["total_bets"] += 1
                room = random.randint(1, 8)
                bet_amt = current_bet
                
                # Random phòng mượt mà trước khi cược theo XWVuaThoatHiem_2.py
                def random_rooms_loop():
                    rooms = [1, 2, 3, 4, 5, 6, 7, 8]
                    while not acc_st["random_stop"].is_set():
                        r_id = random.choice(rooms)
                        try:
                            session.post("https://api.escapemaster.net/escape_game/enter_room",
                                         json={"asset_type": escape_cfg["asset_type"], "user_id": int(uid), "room_id": int(r_id)}, headers=headers, timeout=2)
                        except: pass
                        time.sleep(0.2)
                
                r_thread = Thread(target=random_rooms_loop, daemon=True)
                r_thread.start()

                if enter_room(room):
                    time.sleep(0.3)
                    if place_bet(room, bet_amt):
                        time.sleep(max(15, count_down + 2))
                        for _ in range(12):
                            history_items = get_my_joined()
                            matched = [it for it in history_items if str(it.get("issue_id")) == latest_issue]
                            if matched:
                                item_res = matched[0]
                                award = float(item_res.get("award_amount", 0))
                                bet_val = float(item_res.get("bet_amount", bet_amt))
                                is_killed = not (award > bet_val)
                                killer_room = (
                                    item_res.get("killed_room_id") or 
                                    item_res.get("killer_room") or 
                                    item_res.get("killer") or 
                                    item_res.get("room_id")
                                )
                                if killer_room is not None:
                                    try:
                                        k_int = int(killer_room)
                                        if 1 <= k_int <= 8:
                                            escape_cfg["killer_stats"][k_int] += 1
                                        
                                        profit = award - bet_val
                                        if is_killed: 
                                            acc_st["losses"] += 1
                                            consecutive_losses += 1
                                            acc_st["total_profit"] -= Decimal(str(bet_val))
                                            if consecutive_losses >= loss_threshold:
                                                skips_left = skip_rounds
                                                consecutive_losses = 0
                                                current_bet = float(escape_cfg["base_bet"])
                                            else:
                                                current_bet *= multiplier
                                        else: 
                                            acc_st["wins"] += 1
                                            consecutive_losses = 0
                                            current_bet = float(escape_cfg["base_bet"])
                                            skips_left = 0
                                            acc_st["total_profit"] += Decimal(str(profit))
                                        break
                                    except: pass
                            time.sleep(2)
                acc_st["random_stop"].set()
        except: pass
        time.sleep(3)

def run_sprint_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)
    sprint_cfg = cfg["sprint"]
    acc_st = get_account_state("sprint", uid)
    base_api = "https://api.sprintrun.win"
    headers = {"accept": "*/*", "content-type": "application/json", "origin": "https://sprintrun.win", "referer": "https://sprintrun.win/", "user-agent": "Mozilla/5.0", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    session = requests.Session()

    def api_home():
        try:
            r = session.get(f"{base_api}/sprint/home?asset={sprint_cfg['asset_type']}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json()
        except: pass
        return {}

    def api_bet(payload):
        try:
            r = session.post(f"{base_api}/sprint/bet", json=payload, headers=headers, timeout=10)
            if r.status_code == 200: return r.json()
        except: pass
        return {}

    def api_result(issue):
        try:
            r = session.get(f"{base_api}/sprint/issue_result?issue={issue}&asset={sprint_cfg['asset_type']}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json()
        except: pass
        return {}

    # Logic cấu hình chuẩn từ XWCDTD_2.py
    base_build = Decimal(str(sprint_cfg["bet_amount_total"]))
    current_build = base_build
    lose_limit = int(sprint_cfg.get("lose_limit", 3))
    rest_rounds = int(sprint_cfg.get("rest_rounds", 1))
    lose_multiplier = Decimal(str(sprint_cfg.get("lose_multiplier", "2.5")))
    streak_loss = 0

    while sprint_cfg["global_running"] and not acc_st["random_stop"].is_set():
        if not check_key_validity(chat_id):
            sprint_cfg["global_running"] = False
            acc_st["random_stop"].set()
            try: bot.send_message(chat_id, "⚠️ **Key đã hết hạn!** Bot Đua Tốc Độ đã tự động tắt.", parse_mode="Markdown")
            except: pass
            break
        if sprint_cfg.get("max_rounds", 0) > 0 and acc_st["total_bets"] >= sprint_cfg["max_rounds"]:
            acc_st["random_stop"].set()
            break
        try:
            # Kiểm tra chế độ nghỉ khi chạm giới hạn thua theo XWCDTD_2.py
            if streak_loss >= lose_limit:
                for _ in range(rest_rounds):
                    if not sprint_cfg["global_running"] or acc_st["random_stop"].is_set():
                        break
                    code, rest_data = api_home()
                    rest_expire = rest_data.get("data", {}).get("expire_seconds", 50)
                    time.sleep(int(rest_expire) if isinstance(rest_expire, (int, float)) else 50)
                streak_loss = 0
                continue
            
            home_data = api_home()
            res_data = home_data.get("data", {})
            issue_id = res_data.get("issue_id")
            expire = res_data.get("expire_seconds", 50)
            athletes = res_data.get("athlete_list", [])
            
            if not issue_id or len(athletes) < 3: 
                time.sleep(3)
                continue
            
            # Chọn ngẫu nhiên 3 vận động viên theo XWCDTD_2.py
            chosen_athletes = random.sample(athletes, 3)
            chosen = [a["id"] for a in chosen_athletes]
            
            each_bet = (current_build / Decimal(len(chosen))).quantize(
                Decimal("0.000001"), rounding=ROUND_DOWN
            )
            total_bet_amount = each_bet * Decimal(len(chosen))
            
            for aid in chosen:
                api_bet({
                    "issue_id": issue_id, 
                    "bet_group": "winner", 
                    "asset_type": sprint_cfg["asset_type"], 
                    "athlete_id": aid, 
                    "bet_amount": float(each_bet)
                })
                time.sleep(0.2)
            
            acc_st["total_bets"] += 1
            
            for _ in range(int(expire) if isinstance(expire, (int, float)) else 50):
                if not sprint_cfg["global_running"] or acc_st["random_stop"].is_set(): 
                    break
                time.sleep(1)
            
            winner = None
            for _ in range(30):
                res_json = api_result(issue_id)
                rank = res_json.get("data", {}).get("athlete_rank", [])
                if rank: 
                    winner = rank[0]
                    break
                time.sleep(1)
            
            # Tính toán lời/lỗ chính xác theo yêu cầu hệ thống
            if winner in chosen:
                profit = (each_bet * Decimal("5")) - total_bet_amount
                acc_st["total_profit"] += profit
                acc_st["wins"] += 1
                streak_loss = 0
                current_build = base_build
            else:
                acc_st["total_profit"] -= total_bet_amount
                acc_st["losses"] += 1
                streak_loss += 1
                # Nhân hệ số ngay lập tức khi thua
                current_build = (current_build * lose_multiplier).quantize(
                    Decimal("0.000001"), rounding=ROUND_DOWN
                )
        except: 
            pass
        time.sleep(2)

def run_telebot_polling():
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except:
            time.sleep(5)

if __name__ == "__main__":
    Thread(target=run_telebot_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
