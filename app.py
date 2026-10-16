#!/usr/bin/env python3
"""
ESCAPE MASTER FULL-FEATURED TELEGRAM BOT - RENDER 24/7
=====================================================
- Full tính năng tuỳ chỉnh: Chọn loại tiền, mức cược, hệ số nhân, số vòng nghỉ.
- Giao diện Inline Keyboard tương tác trực tiếp 100% trên Telegram.
- Tự động bóc tách Link game hoặc nhận thông tin từ người dùng.
"""
import telebot
from telebot import types
import websocket
import json
import time
import random
import requests
import os
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock
from flask import Flask

TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

@app.route('/')
def home():
    return "Escape Master Full Bot is running 24/7!"

# Lưu trữ cấu hình chi tiết cho từng người dùng (Chat ID)
user_sessions = {}
session_lock = Lock()

def get_session(chat_id):
    with session_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = {
                "user_id": "",
                "secret_key": "",
                "asset_type": "BUILD",     # BUILD hoặc USDT
                "base_bet": 1.0,           # Mức cược gốc
                "loss_threshold": 2,       # Thua liên tiếp mấy ván thì nghỉ
                "skip_rounds": 3,          # Số ván nghỉ
                "multiplier": 2.0,         # Hệ số nhân gấp thếp
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

# Menu chính
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    
    status_str = "🟢 Đang chạy" if sess["running"] else "🔴 Đang dừng"
    uid_str = sess["user_id"] if sess["user_id"] else "Chưa có (Hãy gửi Link game)"
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER - FULL TOOL*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👤 *User ID:* `{uid_str}`\n"
        f"💰 *Đồng cược:* `{sess['asset_type']}`\n"
        f"💵 *Cược gốc:* `{sess['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{sess['multiplier']}`\n"
        f"🛡️ *Ngắt khi thua:* `{sess['loss_threshold']} ván (Nghỉ {sess['skip_rounds']} ván)`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👉 *Cách dùng:* Dán trực tiếp **Link game** vào đây để nạp tài khoản, sau đó dùng các nút bên dưới để cấu hình hoặc Bật Bot!"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Bot" if not sess["running"] else "⏹️ Tắt Bot", callback_data="toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin: {sess['asset_type']}", callback_data="toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược Gốc ({sess['base_bet']})", callback_data="set_base_bet")
    btn_mult = types.InlineKeyboardButton(f"📈 Hệ số nhân (x{sess['multiplier']})", callback_data="set_mult")
    btn_status = types.InlineKeyboardButton("📊 Thống kê chi tiết", callback_data="status")
    
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_mult)
    markup.add(btn_status)
    
    bot.send_message(chat_id, msg_text, reply_markup=markup)

# Nhận link game tự động bóc tách
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    sess = get_session(chat_id)
    
    if "userId=" in text and "secretKey=" in text:
        try:
            parsed_url = urlparse(text)
            query_params = parse_qs(parsed_url.query)
            uid = query_params.get("userId", [None])[0]
            skey = query_params.get("secretKey", [None])[0]
            
            if uid and skey:
                sess["user_id"] = uid
                sess["secret_key"] = skey
                bot.reply_to(message, f"✅ **Nạp tài khoản thành công!**\n• User ID: `{uid}`\n\nGõ `/start` để mở lại Menu điều khiển đầy đủ.")
                return
        except:
            pass
            
    bot.reply_to(message, "⚠️ Tin nhắn không hợp lệ. Hãy dán **Link game** chứa `userId` và `secretKey`, hoặc gõ `/start` để mở menu.")

# Xử lý các nút bấm tương tác
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    sess = get_session(chat_id)
    data = call.data
    
    if data == "toggle_bot":
        if not sess["running"]:
            if not sess["user_id"] or not sess["secret_key"]:
                bot.answer_callback_query(call.id, "⚠️ Chưa có User ID! Hãy dán link game trước.", show_alert=True)
                return
            sess["running"] = True
            Thread(target=run_bot_worker, args=(chat_id,), daemon=True).start()
            bot.answer_callback_query(call.id, "🚀 Đã khởi động Bot thành công!")
        else:
            sess["running"] = False
            if sess["ws"]:
                try: sess["ws"].close()
                except: pass
            bot.answer_callback_query(call.id, "⏹️ Đã dừng Bot!")
        refresh_menu(call.message)
        
    elif data == "toggle_asset":
        sess["asset_type"] = "USDT" if sess["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(call.id, f"Đã đổi đồng cược sang {sess['asset_type']}")
        refresh_menu(call.message)
        
    elif data == "set_base_bet":
        # Xoay vòng mức cược gốc: 1.0 -> 2.0 -> 5.0 -> 10.0 -> 1.0
        bets = [1.0, 2.0, 5.0, 10.0]
        next_idx = (bets.index(sess["base_bet"]) + 1) % len(bets) if sess["base_bet"] in bets else 0
        sess["base_bet"] = bets[next_idx]
        bot.answer_callback_query(call.id, f"Đã đổi mức cược thành {sess['base_bet']}")
        refresh_menu(call.message)
        
    elif data == "set_mult":
        # Xoay vòng hệ số nhân: 1.5 -> 2.0 -> 2.5 -> 3.0 -> 1.5
        mults = [1.5, 2.0, 2.5, 3.0]
        next_idx = (mults.index(sess["multiplier"]) + 1) % len(mults) if sess["multiplier"] in mults else 0
        sess["multiplier"] = mults[next_idx]
        bot.answer_callback_query(call.id, f"Đã đổi hệ số nhân thành x{sess['multiplier']}")
        refresh_menu(call.message)
        
    elif data == "status":
        bal = get_balance_for_session(sess)
        wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ CHI TIẾT*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
            f"Số dư ví: `{bal:.4f} {sess['asset_type']}`\n"
            f"Tổng ván đánh: `{sess['total_bets']}`\n"
            f"Thắng / Thua: `{sess['wins']}` / `{sess['losses']}` (WR: `{wr:.1f}%`)\n"
            f"Tổng lợi nhuận: `{sess['total_profit']:+.4f} {sess['asset_type']}`"
        )
        bot.send_message(chat_id, msg)

def refresh_menu(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    status_str = "🟢 Đang chạy" if sess["running"] else "🔴 Đang dừng"
    uid_str = sess["user_id"] if sess["user_id"] else "Chưa có (Hãy gửi Link game)"
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER - FULL TOOL*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👤 *User ID:* `{uid_str}`\n"
        f"💰 *Đồng cược:* `{sess['asset_type']}`\n"
        f"💵 *Cược gốc:* `{sess['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{sess['multiplier']}`\n"
        f"🛡️ *Ngắt khi thua:* `{sess['loss_threshold']} ván (Nghỉ {sess['skip_rounds']} ván)`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Dùng các nút bên dưới để tùy chỉnh nhanh:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Bot" if not sess["running"] else "⏹️ Tắt Bot", callback_data="toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin: {sess['asset_type']}", callback_data="toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược Gốc ({sess['base_bet']})", callback_data="set_base_bet")
    btn_mult = types.InlineKeyboardButton(f"📈 Hệ số nhân (x{sess['multiplier']})", callback_data="set_mult")
    btn_status = types.InlineKeyboardButton("📊 Thống kê chi tiết", callback_data="status")
    
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_mult)
    markup.add(btn_status)
    
    try:
        bot.edit_message_text(msg_text, chat_id, message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

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
                        sess["base_bet"] = 1.0 # Reset về mức gốc khi thắng
                        sess["skips_left"] = 0
                    else:
                        sess["losses"] += 1
                        sess["consecutive_losses"] += 1
                        if sess["consecutive_losses"] >= sess["loss_threshold"]:
                            sess["skips_left"] = sess["skip_rounds"]
                            sess["consecutive_losses"] = 0
                        else:
                            sess["base_bet"] *= sess["multiplier"]
                    
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
    try:
        bot.remove_webhook()
    except:
        pass
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    Thread(target=run_telebot_polling, daemon=True).start()
    port = int(os.environ.com("PORT", 5000)) if hasattr(os.environ, "get") else 5000
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
