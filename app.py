#!/usr/bin/env python3
"""
ESCAPE MASTER INTERACTIVE TELEGRAM BOT (POLLING)
================================================
- Dùng telebot Polling: gõ /start chắc chắn hiện Menu 100%
- Flask giữ cổng HTTP cho Render không bị sập
"""
import telebot
from telebot import types
import websocket
import json
import time
import random
import requests
import os
from threading import Thread, Lock
from flask import Flask

# --- CẤU HÌNH BOT TELEGRAM ---
TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

# --- FLASK SERVER GIỮ RENDER SỐNG ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Telegram Escape Master đang chạy Polling 24/7!"

# Quản lý session từng người dùng
user_sessions = {}
session_lock = Lock()

def get_session(chat_id):
    with session_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = {
                "user_id": "",
                "secret_key": "",
                "asset_type": "BUILD",
                "base_bet": 1.0,
                "running": False,
                "ws": None,
                "total_profit": 0.0,
                "total_bets": 0,
                "wins": 0,
                "losses": 0,
                "consecutive_losses": 0,
                "skips_left": 0,
                "current_issue": None,
                "has_bet": False
            }
        return user_sessions[chat_id]

# --- XỬ LÝ LỆNH TELEGRAM ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    
    status_str = "🟢 Đang hoạt động" if sess["running"] else "🔴 Đang dừng"
    uid_str = sess["user_id"] if sess["user_id"] else "Chưa cài đặt"
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER BOT*\n\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👤 *User ID:* `{uid_str}`\n"
        f"💰 *Mức cược:* `{sess['base_bet']} {sess['asset_type']}`\n\n"
        f"Bấm các nút bên dưới để điều khiển bot:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_login = types.InlineKeyboardButton("⚙️ Nhập ID & Key", callback_data="set_creds")
    btn_start = types.InlineKeyboardButton("🚀 Bật Bot", callback_data="start_bot")
    btn_stop = types.InlineKeyboardButton("⏹️ Tắt Bot", callback_data="stop_bot")
    btn_status = types.InlineKeyboardButton("📊 Số dư & Thống kê", callback_data="status")
    
    markup.add(btn_login)
    markup.add(btn_start, btn_stop)
    markup.add(btn_status)
    
    bot.send_message(chat_id, msg_text, reply_markup=markup)

@bot.message_handler(commands=['login'])
def handle_login(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    parts = message.text.split()
    
    if len(parts) >= 3:
        sess["user_id"] = parts[1].strip()
        sess["secret_key"] = parts[2].strip()
        bot.reply_to(message, f"✅ Đã lưu cấu hình thành công!\n• User ID: `{sess['user_id']}`\n\nGõ `/start` để mở lại menu.")
    else:
        bot.reply_to(message, "⚠️ Sai cú pháp!\nVui lòng gõ theo mẫu:\n`/login <User_ID> <Secret_Key>`\n\n*(Ví dụ: `/login 123456 abcxyz123`)*")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    sess = get_session(chat_id)
    
    if call.data == "set_creds":
        bot.send_message(chat_id, "💡 Hãy gửi tin nhắn theo cú pháp sau để nhập tài khoản:\n\n`/login <User_ID> <Secret_Key>`\n\n*(Ví dụ: `/login 100234988 abc123def456`)*")
    
    elif call.data == "start_bot":
        if not sess["user_id"] or not sess["secret_key"]:
            bot.send_message(chat_id, "⚠️ Bạn chưa cài đặt User ID và Secret Key!\nHãy bấm nút *⚙️ Nhập ID & Key* trước.")
            return
        if sess["running"]:
            bot.send_message(chat_id, "⚠️ Bot của bạn đang chạy rồi!")
            return
            
        sess["running"] = True
        Thread(target=run_bot_worker, args=(chat_id,), daemon=True).start()
        bot.send_message(chat_id, "🚀 *Đã bật Bot thành công!* Bot bắt đầu cược ngầm 24/7 và báo kết quả về đây.")
        
    elif call.data == "stop_bot":
        sess["running"] = False
        if sess["ws"]:
            try:
                sess["ws"].close()
            except:
                pass
        bot.send_message(chat_id, "⏹️ *Đã dừng Bot thành công.*")
        
    elif call.data == "status":
        bal = get_balance_for_session(sess)
        wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ BOT*\n\n"
            f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
            f"Số dư hiện tại: `{bal:.4f} {sess['asset_type']}`\n"
            f"Tổng số ván: `{sess['total_bets']}`\n"
            f"Thắng / Thua: `{sess['wins']}` / `{sess['losses']}` (WR: `{wr:.1f}%`)\n"
            f"Tổng lời/lỗ: `{sess['total_profit']:+.4f} {sess['asset_type']}`"
        )
        bot.send_message(chat_id, msg)

def get_balance_for_session(sess):
    try:
        headers = {
            "Content-Type": "application/json",
            "user-id": str(sess["user_id"]),
            "user-login": "login_v2",
            "user-secret-key": str(sess["secret_key"]),
            "Accept": "application/json",
            "xb-language": "vi-VN"
        }
        resp = requests.post(
            "https://api.escapemaster.net/escape_game/get_user_asset",
            json={"asset_type": sess["asset_type"], "user_id": int(sess["user_id"])},
            headers=headers,
            timeout=10
        )
        data = resp.json()
        if data and data.get("code") == 0:
            return float(data.get("data", {}).get("balance", 0))
    except:
        pass
    return 0.0

def run_bot_worker(chat_id):
    sess = get_session(chat_id)
    ws_url = "wss://api.escapemaster.net/escape_game/ws"
    
    def on_message(ws, message):
        if not sess["running"]:
            ws.close()
            return
        try:
            data = json.loads(message)
            msg_type = data.get("msg_type", "")
            
            headers = {
                "Content-Type": "application/json",
                "user-id": str(sess["user_id"]),
                "user-login": "login_v2",
                "user-secret-key": str(sess["secret_key"]),
                "Accept": "application/json",
                "xb-language": "vi-VN"
            }
            
            if msg_type == "notify_count_down":
                issue_id = data.get("issue_id")
                if sess["current_issue"] != issue_id:
                    sess["current_issue"] = issue_id
                    sess["has_bet"] = False
                    
                    if sess["skips_left"] > 0:
                        sess["skips_left"] -= 1
                        return
                    
                    room = random.randint(1, 8)
                    amount = sess["base_bet"]
                    
                    r1 = requests.post("https://api.escapemaster.net/escape_game/enter_room",
                                       json={"asset_type": sess["asset_type"], "user_id": int(sess["user_id"]), "room_id": room},
                                       headers=headers, timeout=5)
                    if r1.json().get("code") == 0:
                        time.sleep(0.2)
                        r2 = requests.post("https://api.escapemaster.net/escape_game/bet",
                                           json={"asset_type": sess["asset_type"], "user_id": int(sess["user_id"]), "room_id": room, "bet_amount": amount},
                                           headers=headers, timeout=5)
                        if r2.json().get("code") == 0:
                            sess["has_bet"] = True

            elif msg_type == "notify_result":
                issue_id = data.get("issue_id")
                if sess["has_bet"] and issue_id == sess["current_issue"]:
                    award = float(data.get("award_amount", 0))
                    bet_val = float(data.get("bet_amount", 0))
                    is_killed = not (award > bet_val)
                    killed_room = data.get("killed_room", "?")
                    my_room = data.get("room_id", "?")
                    
                    profit = award - bet_val
                    sess["total_bets"] += 1
                    status_text = "THẮNG 🟢" if not is_killed else "THUA 🔴"
                    
                    if not is_killed:
                        sess["wins"] += 1
                        sess["consecutive_losses"] = 0
                        sess["base_bet"] = 1.0
                        sess["skips_left"] = 0
                    else:
                        sess["losses"] += 1
                        sess["consecutive_losses"] += 1
                        if sess["consecutive_losses"] >= 2:
                            sess["skips_left"] = 3
                        else:
                            sess["base_bet"] *= 2.0
                    
                    sess["total_profit"] += profit
                    bal = get_balance_for_session(sess)
                    wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
                    
                    msg = (
                        f"*ESCAPE MASTER* - #{issue_id}\n"
                        f"Trạng thái: *{status_text}*\n"
                        f"Phòng: `{my_room}` | Bẫy: `{killed_room}`\n"
                        f"Cược: `{bet_val:.4f}` | Thưởng: `{award:.4f}`\n"
                        f"Lời trận: `{profit:+.4f}`\n"
                        f"Tổng lời: `{sess['total_profit']:+.4f}` (WR: {wr:.1f}%)\n"
                        f"Số dư ví: `{bal:.4f} {sess['asset_type']}`"
                    )
                    bot.send_message(chat_id, msg)
                    sess["has_bet"] = False

            elif msg_type == "notify_heartbeat":
                ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
        except:
            pass

    while sess["running"]:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                header={"Origin": "https://escapemaster.net", "User-Agent": "Mozilla/5.0"},
                on_open=lambda w: w.send(json.dumps({"msg_type": "handle_enter_game", "asset_type": sess["asset_type"], "user_id": int(sess["user_id"]), "user_secret_key": sess["secret_key"]})),
                on_message=on_message,
                on_error=lambda w, e: None,
                on_close=lambda w, c, m: None
            )
            sess["ws"] = ws
            ws.run_forever(ping_interval=15, ping_timeout=10)
        except:
            pass
        time.sleep(3)

def run_telebot_polling():
    # Xóa Webhook cũ để tránh xung đột Polling
    try:
        bot.remove_webhook()
    except:
        pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    # Chạy Telegram Polling ở thread riêng
    Thread(target=run_telebot_polling, daemon=True).start()
    
    # Chạy Flask Server ở thread chính để giữ Render sống
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
