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

# --- KHỞI TẠO DATABASE SQLITE NGAY TRÊN RENDER ---
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

# --- PHẦN 1: WEB GATEWAY CHẠY TRÊN RENDER (THAY THẾ INFINITYFREE) ---
@app.route('/')
def home():
    # Tự động dọn dẹp key hết hạn hoặc quá 30 phút chưa dùng
    db = get_db()
    db.execute("DELETE FROM license_keys WHERE is_used = 0 AND created_at < datetime('now', '-30 minute')")
    db.commit()
    db.close()

    html_template = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWorld License Gateway</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
            body {
                background: #090d16;
                background-image: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #090d16 70%);
                color: #f8fafc;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }
            .container {
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 24px;
                width: 100%;
                max-width: 420px;
                text-align: center;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            }
            .logo-icon { font-size: 48px; margin-bottom: 15px; }
            h1 {
                font-size: 22px;
                font-weight: 800;
                margin-bottom: 10px;
                background: linear-gradient(to right, #38bdf8, #818cf8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
            .badge {
                display: inline-block;
                background: rgba(56, 189, 248, 0.1);
                color: #38bdf8;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 20px;
                margin-bottom: 20px;
                border: 1px solid rgba(56, 189, 248, 0.2);
            }
            .btn {
                display: block;
                width: 100%;
                background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
                color: #fff;
                padding: 14px;
                font-size: 15px;
                font-weight: 700;
                text-decoration: none;
                border-radius: 12px;
                box-shadow: 0 10px 20px rgba(99, 102, 241, 0.3);
                transition: all 0.3s ease;
            }
            .btn:hover { transform: translateY(-2px); opacity: 0.9; }
            .footer-note { margin-top: 25px; font-size: 12px; color: #64748b; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo-icon">🔑</div>
            <div class="badge">Hệ thống tự động 24/7</div>
            <h1>XWORLD LICENSE GATEWAY</h1>
            <p>Bấm nút bên dưới để vượt link Link4m nhận mã bản quyền có hiệu lực trong 24 giờ.</p>
            <a href="/generate" class="btn">🚀 TIẾN HÀNH LẤY KEY</a>
            <div class="footer-note">Key chưa dùng quá 30 phút sẽ tự động bị xóa</div>
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
    
    # Lấy domain hiện tại của Render
    base_url = request.host_url.rstrip('/')
    raw_destination = f"{base_url}/get_key_page?key={license_key}"
    
    # Tích hợp Link4m
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
    html = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head><meta charset="UTF-8"><title>Key Của Bạn</title></head>
    <body style="background:#090d16; color:#fff; text-align:center; padding-top:50px; font-family:sans-serif;">
        <h2>🎉 Vượt link thành công!</h2>
        <p>Mã bản quyền của bạn là:</p>
        <h1 style="color:#38bdf8; background:#1e293b; display:inline-block; padding:15px 30px; border-radius:10px;">{key}</h1>
        <p>Hãy copy mã này và dán vào Bot Telegram để kích hoạt!</p>
    </body>
    </html>
    """
    return html

# API kiểm tra key nội bộ (Không bao giờ bị chặn)
@app.route('/check_key')
def check_key():
    key = request.args.get('key', '').strip()
    telegram_id = request.args.get('telegram_id', '').strip()
    
    if not key or not telegram_id:
        return jsonify({"status": "error", "message": "Thiếu thông tin key hoặc telegram_id"})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM license_keys WHERE license_key = ?", (key,))
    row = cursor.fetchone()
    
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "❌ Key không tồn tại hoặc đã bị xóa!"})
    
    # Kiểm tra hạn 24h
    if row['expires_at'] and row['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        db.close()
        return jsonify({"status": "error", "message": "❌ Key này đã hết hạn sử dụng (quá 24h)!"})
    
    if row['is_used'] == 1:
        if row['used_by'] == str(telegram_id):
            db.close()
            return jsonify({"status": "success", "message": "✅ Key hợp lệ (Bạn đã kích hoạt trước đó)!"})
        else:
            db.close()
            return jsonify({"status": "error", "message": "❌ Key này đã được kích hoạt bởi tài khoản khác!"})
    
    # Cập nhật đã dùng
    cursor.execute("UPDATE license_keys SET is_used = 1, used_by = ? WHERE license_key = ?", (str(telegram_id), key))
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "🎉 Kích hoạt key thành công! Dùng bot trong 24 giờ."})


# --- PHẦN 2: TELEGRAM BOT LOGIC ---
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
                "escape": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "base_bet": 10.0},
                "sprint": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "bet_amount_total": "1"}
            }
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {
            "total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0,
            "current_build": Decimal("1"), "random_stop": Event()
        }
    return account_threads[key]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in verified_users:
        # Tự động lấy domain render hiện tại để gắn vào nút bấm
        render_domain = request.host_url.rstrip('/') if 'request' in globals() else "https://ten-app.onrender.com"
        msg_text = (
            "🔒 *XWORLD LICENSE GATEWAY*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Bạn cần có Key bản quyền để sử dụng bot.\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        # Link web chạy trực tiếp trên Render
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=render_domain),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="prompt_enter_key")
        )
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        return
    show_main_game_menu(chat_id)

def show_main_game_menu(chat_id, message_id=None):
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    msg_text = "🎮 *XWORLD MULTI-GAME BOT*\n━━━━━━━━━━━━━━━━━━━\n📌 Vui lòng chọn tựa game bạn muốn auto:"
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
        f"🎮 *GAME: {game_name.upper()}*\n━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n👥 *Số nick:* `{total_accs}`\n"
        f"🪙 *Coin:* `{g_cfg['asset_type']}` | 💵 *Cược:* `{current_bet_display}` (Mỗi con)\n"
        "━━━━━━━━━━━━━━━━━━━\n👇 *Chọn thao tác bên dưới:*"
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
        bot.send_message(chat_id, f"✏️ **Vui lòng nhập số tiền cược cố định cho [ {game_name_vi} ]:**")
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào!", show_alert=True)
            return
        g_cfg["global_running"] = not g_cfg["global_running"]
        bot.answer_callback_query(call.id, "Trạng thái bot đã thay đổi!")
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "list":
        msg = f"👥 *NICK ({game_name_vi.upper()}):*\n" + "\n".join([f"- `{uid}`" for uid in g_cfg["accounts"]])
        bot.send_message(chat_id, msg or "Chưa có nick nào!", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    # 1. Xử lý nhập key trực tiếp gọi API nội bộ trên Render
    if chat_id in waiting_for_key_users:
        waiting_for_key_users.remove(chat_id)
        # Gọi thẳng vào API nội bộ của Render, không qua bên thứ 3 nên không bao giờ lỗi
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

    # 2. Xử lý link game
    if cfg.get("waiting_for_link"):
        game_type = cfg["waiting_for_link"]
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text)
                query_params = parse_qs(parsed_url.query)
                uid = int(query_params.get("userId", [None])[0])
                skey = query_params.get("secretKey", [None])[0]
                if uid and skey:
                    cfg[game_type]["accounts"][uid] = skey
                    cfg["waiting_for_link"] = None
                    bot.reply_to(message, f"✅ **Thêm nick thành công!** Gõ `/start` để quản lý.")
                    return
            except:
                pass
        bot.reply_to(message, "⚠️ Link không hợp lệ!")
        return

    if not text.startswith("/"):
        bot.reply_to(message, "💡 Gõ `/start` để mở bảng chọn game.")

def run_telebot_polling():
    try:
        bot.remove_webhook()
    except:
        pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    Thread(target=run_telebot_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
