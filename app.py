import telebot
from telebot import types
import time
import random
import requests
import os
import sqlite3
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, request, redirect, jsonify, render_template_string

TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

# --- KHỞI TẠO DATABASE SQLITE ---
def init_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE,
            is_used INTEGER DEFAULT 0,
            used_by TEXT,
            expires_at DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- WEB GATEWAY ---
@app.route('/')
def home():
    db = get_db()
    db.execute("DELETE FROM license_keys WHERE is_used = 0")
    db.commit()
    db.close()

    html_template = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWorld License Gateway</title>
        <style>
            body { background: #090d16; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .box { background: #1e293b; padding: 30px; border-radius: 16px; text-align: center; max-width: 400px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            .btn { display: block; background: #0ea5e9; color: #fff; padding: 12px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 20px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>XWORLD LICENSE GATEWAY</h2>
            <p>Bấm nút bên dưới để lấy mã bản quyền (Key 24h).</p>
            <a href="/generate" class="btn">LẤY KEY NGAY</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/generate')
def generate_key():
    random_string = ''.join(random.choices('0123456789ABCDEF', k=8))
    license_key = "XW-" + random_string
    
    db = get_db()
    db.execute("INSERT INTO license_keys (license_key, is_used, expires_at) VALUES (?, 0, datetime('now', '+1 day'))", (license_key,))
    db.commit()
    db.close()
    
    base_url = request.host_url.rstrip('/')
    raw_destination = f"{base_url}/get_key_page?key={license_key}"
    
    long_url = requests.utils.quote(raw_destination)
    api_token = '68a76c1354de3f0da567ca17'
    api_url = f"https://link4m.co/api-shorten/v2?api={api_token}&url={long_url}"
    
    try:
        res = requests.get(api_url, timeout=5).json()
        if res.get("status") == 'success':
            return redirect(res["shortenedUrl"])
    except:
        pass
    
    return redirect(raw_destination)

@app.route('/get_key_page')
def get_key_page():
    key = request.args.get('key', '')
    return f"""
    <body style="background:#090d16; color:#fff; text-align:center; padding-top:50px; font-family:sans-serif;">
        <h2>🎉 Lấy Key thành công!</h2>
        <p>Mã bản quyền của bạn:</p>
        <h1 style="color:#38bdf8; background:#1e293b; display:inline-block; padding:15px 30px; border-radius:10px;">{key}</h1>
        <p>Copy mã này dán vào Bot Telegram để kích hoạt.</p>
    </body>
    """

@app.route('/check_key')
def check_key():
    key = request.args.get('key', '').strip()
    telegram_id = request.args.get('telegram_id', '').strip()
    
    if not key or not telegram_id:
        return jsonify({"status": "error", "message": "Thiếu thông tin"})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM license_keys WHERE license_key = ?", (key,))
    row = cursor.fetchone()
    
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "❌ Key không tồn tại!"})
    
    if row['is_used'] == 1:
        if row['used_by'] == str(telegram_id):
            db.close()
            return jsonify({"status": "success", "message": "✅ Key hợp lệ!"})
        else:
            db.close()
            return jsonify({"status": "error", "message": "❌ Key đã được dùng bởi tài khoản khác!"})
    
    cursor.execute("UPDATE license_keys SET is_used = 1, used_by = ? WHERE license_key = ?", (str(telegram_id), key))
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "🎉 Kích hoạt thành công!"})


# --- TELEGRAM BOT & GAME LOGIC ---
user_data = {}
data_lock = Lock()
waiting_for_key_users = set()
verified_users = set()

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None,
                "waiting_for_link": None,
                "waiting_for_bet": None,
                "escape": {
                    "accounts": {},
                    "global_running": False,
                    "asset_type": "BUILD",
                    "base_bet": 10.0,
                },
                "sprint": {
                    "accounts": {},
                    "global_running": False,
                    "asset_type": "BUILD",
                    "bet_amount_total": "1",
                }
            }
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {
            "total_profit": Decimal("0"),
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "current_build": Decimal("1"),
            "random_stop": Event()
        }
    return account_threads[key]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in verified_users:
        render_domain = os.environ.get("RENDER_EXTERNAL_URL", "https://bot-tool-golike.onrender.com")
        generate_url = f"{render_domain}/generate"
        msg_text = (
            "🔒 *XWORLD LICENSE GATEWAY*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Bạn cần có Key bản quyền để sử dụng bot.\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=generate_url),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="prompt_enter_key")
        )
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        return
    show_main_game_menu(chat_id)

def show_main_game_menu(chat_id, message_id=None):
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    
    msg_text = (
        "🎮 *XWORLD MULTI-GAME BOT*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📌 Vui lòng chọn tựa game bạn muốn auto:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
            return
        except:
            pass
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "prompt_enter_key")
def callback_prompt_key(call):
    chat_id = call.message.chat.id
    waiting_for_key_users.add(chat_id)
    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, "🔑 **Vui lòng nhập mã Key của bạn vào đây (Ví dụ: `XW-A1B2C3D4`):**", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    bot.answer_callback_query(call.id)
    show_game_menu(chat_id, call.message.message_id, game_type)

def show_game_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    g_cfg = cfg[game_type]
    game_name = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    status_str = "🟢 Đang chạy" if g_cfg["global_running"] else "🔴 Đang dừng"
    total_accs = len(g_cfg["accounts"])
    current_bet_display = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    
    msg_text = (
        f"🎮 *GAME: {game_name.upper()}*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👥 *Số nick:* `{total_accs}`\n"
        f"🪙 *Coin:* `{g_cfg['asset_type']}` | 💵 *Cược:* `{current_bet_display}` (Mỗi con)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Chọn thao tác bên dưới:*"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link Nick", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🚀 Bật Auto" if not g_cfg["global_running"] else "⏹️ Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Đổi Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Nhập Số Tiền Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton("👥 Danh sách Nick", callback_data=f"game_{game_type}_list"),
        types.InlineKeyboardButton("📊 Thống kê", callback_data=f"game_{game_type}_status"),
        types.InlineKeyboardButton("🔙 Quay lại chọn Game", callback_data="back_to_main")
    )
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    show_main_game_menu(chat_id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    parts = call.data.split("_")
    game_type = parts[1]
    action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    
    if action == "setup_link":
        cfg["waiting_for_link"] = game_type
        cfg["waiting_for_bet"] = None
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"📥 **Vui lòng dán link game [ {game_name_vi} ] vào đây!**")
        
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type
        cfg["waiting_for_link"] = None
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"✏️ **Vui lòng nhập số tiền cược cố định cho [ {game_name_vi} ] (Mỗi con):**")
        
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào cho game này!", show_alert=True)
            return
        if not g_cfg["global_running"]:
            g_cfg["global_running"] = True
            for uid, skey in g_cfg["accounts"].items():
                st = get_account_state(game_type, uid)
                st["random_stop"].clear()
                if game_type == "escape":
                    Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                else:
                    Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
            bot.answer_callback_query(call.id, f"🚀 Đã bật auto {game_name_vi}!")
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]:
                acc_st = get_account_state(game_type, uid)
                acc_st["random_stop"].set()
            bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
        show_game_menu(chat_id, call.message.message_id, game_type)
        
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(call.id, f"Đổi sang {g_cfg['asset_type']}")
        show_game_menu(chat_id, call.message.message_id, game_type)
        
    elif action == "list":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "Chưa có nick nào!", show_alert=True)
            return
        msg = f"👥 *DANH SÁCH NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1):
            msg += f"{idx}. `{uid}`\n"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    elif action == "status":
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]
            tot_wins += st["wins"]
            tot_losses += st["losses"]
            tot_profit += st["total_profit"]
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n"
            f"Trạng thái: {'🟢 Đang chạy' if g_cfg['global_running'] else '🔴 Đang dừng'}\n"
            f"Tổng ván: `{tot_bets}` | Thắng/Thua: `{tot_wins}`/`{tot_losses}` ({wr:.1f}%)\n"
            f"Tổng lời: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    # 1. Xử lý nhập key
    if chat_id in waiting_for_key_users:
        waiting_for_key_users.remove(chat_id)
        local_api_url = f"http://127.0.0.1:{os.environ.get('PORT', 5000)}/check_key?key={text}&telegram_id={chat_id}"
        try:
            res = requests.get(local_api_url, timeout=5).json()
            if res.get("status") == "success":
                verified_users.add(chat_id)
                bot.reply_to(message, f"🎉 {res.get('message')}\n\n👉 Bấm `/start` để mở giao diện quản lý game!", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"{res.get('message', '❌ Key không hợp lệ!')}\n👉 Bấm `/start` để thử lại.")
        except Exception as e:
            bot.reply_to(message, f"❌ Lỗi xác thực: `{str(e)}`", parse_mode="Markdown")
        return

    # 2. Xử lý dán link game
    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text)
                query_params = parse_qs(parsed_url.query)
                uid_str = query_params.get("userId", [None])[0]
                skey = query_params.get("secretKey", [None])[0]
                if uid_str and skey:
                    uid = int(uid_str)
                    cfg[game_target_link]["accounts"][uid] = skey
                    cfg["waiting_for_link"] = None
                    g_cfg = cfg[game_target_link]
                    if g_cfg["global_running"]:
                        if game_target_link == "escape":
                            Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                        else:
                            Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                    bot.reply_to(message, f"✅ **Đã thêm nick thành công!**\nGõ `/start` để quay lại quản lý.")
                    return
            except:
                pass
        bot.reply_to(message, "⚠️ Link không hợp lệ! Hãy dán đúng link game XWorld.")
        return

    # 3. Xử lý nhập tiền cược
    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try:
            val = float(text)
            if val <= 0:
                raise ValueError()
            g_cfg = cfg[game_target_bet]
            if game_target_bet == "sprint":
                g_cfg["bet_amount_total"] = str(val)
                for uid in g_cfg["accounts"]:
                    st = get_account_state("sprint", uid)
                    st["current_build"] = Decimal(str(val))
            else:
                g_cfg["base_bet"] = val
            cfg["waiting_for_bet"] = None
            bot.reply_to(message, f"✅ **Đã cập nhật mức cược:** `{val}`\nGõ `/start` để mở lại menu.")
            return
        except ValueError:
            bot.reply_to(message, "⚠️ Số tiền không hợp lệ! Vui lòng nhập số dương.")
            return

    if not text.startswith("/"):
        bot.reply_to(message, "💡 Gõ `/start` để mở bảng chọn game.")

# ==========================================
# ENGINE 1: VUA THOÁT HIỂM
# ==========================================
def run_escape_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["escape"]
    acc_st = get_account_state("escape", uid)
    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            url = "https://api.escapemaster.net/escape_game/my_joined"
            resp = requests.get(url, params={"asset": cfg["asset_type"], "page": 1, "page_size": 10},
                                headers={"user-id": str(uid), "user-secret-key": skey}, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                if items:
                    latest_issue = str(items[0].get("issue_id"))
                    if acc_st.get("current_issue") != latest_issue:
                        acc_st["current_issue"] = latest_issue
                        acc_st["total_bets"] += 1
                        room = random.randint(1, 8)
                        requests.post("https://api.escapemaster.net/escape_game/enter_room",
                                      json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room},
                                      headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
                        time.sleep(0.1)
                        requests.post("https://api.escapemaster.net/escape_game/bet",
                                      json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room, "bet_amount": cfg["base_bet"]},
                                      headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
        except:
            pass
        time.sleep(3)

# ==========================================
# ENGINE 2: ĐUA TỐC ĐỘ
# ==========================================
def run_sprint_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["sprint"]
    acc_st = get_account_state("sprint", uid)
    base_api = "https://api.sprintrun.win"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://sprintrun.win",
        "referer": "https://sprintrun.win/",
        "user-agent": "Mozilla/5.0",
        "user-id": str(uid),
        "user-login": "login_v2",
        "user-secret-key": skey
    }
    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            base_build = Decimal(str(cfg["bet_amount_total"]))
            acc_st["current_build"] = base_build

    
