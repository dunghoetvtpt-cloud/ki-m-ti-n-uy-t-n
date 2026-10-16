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


# --- TELEGRAM BOT LOGIC ---
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in verified_users:
        render_domain = "https://bot-tool-golike.onrender.com" # Hoặc domain Render của ông
        msg_text = (
            "🔒 *XWORLD LICENSE GATEWAY*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Bạn cần có Key bản quyền để sử dụng bot.\n\n"
            "👉 Vui lòng chọn thao tác bên dưới:"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=render_domain),
            types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="prompt_enter_key")
        )
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        return
    show_main_game_menu(chat_id)

def show_main_game_menu(chat_id, message_id=None):
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
    bot.send_message(chat_id, "🔑 **Vui lòng nhập mã Key của bạn vào đây:**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
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

    if not text.startswith("/"):
        bot.reply_to(message, "💡 Gõ `/start` để mở bảng chọn game.")

# --- KHỞI ĐỘNG SONG SONG FLASK VÀ BOT ---
def run_telebot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Bot polling error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    # Chạy bot ở một luồng riêng biệt cực kỳ ổn định
    bot_thread = Thread(target=run_telebot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
