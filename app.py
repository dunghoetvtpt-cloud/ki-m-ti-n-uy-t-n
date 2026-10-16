#!/usr/bin/env python3
"""
ESCAPE MASTER FULL-FEATURED TELEGRAM BOT + WATCHDOG + RANDOM ROOMS
==================================================================
- Tích hợp toàn bộ thuật toán gốc từ XWVuaThoatHiem.py
- Điều khiển, tuỳ chỉnh chiến thuật và nhận thông báo trực tiếp qua Telegram
- Tự động chạy ngầm 24/7 trên Render
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
from threading import Thread, Lock, Event
from flask import Flask

TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

@app.route('/')
def home():
    return "Escape Master Ultimate Bot is running 24/7!"

# Quản lý phiên làm việc cho từng người dùng Telegram
user_sessions = {}
session_lock = Lock()

def get_session(chat_id):
    with session_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = {
                "user_id": None,
                "secret_key": None,
                "asset_type": "BUILD",
                "base_bet": 1.0,
                "loss_threshold": 2,
                "skip_rounds": 3,
                "multiplier": 2.0,
                "running": False,
                "waiting_for_link": False,
                "ws_app": None,
                "total_profit": 0.0,
                "total_bets": 0,
                "wins": 0,
                "losses": 0,
                "consecutive_losses": 0,
                "skips_left": 0,
                "current_issue": None,
                "betting_issue": None,
                "has_bet": False,
                "watchdog_last_time": time.time(),
                "random_stop": Event()
            }
        return user_sessions[chat_id]

# Giao diện Menu chính trên Telegram
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    sess["waiting_for_link"] = False
    
    status_str = "🟢 Đang chạy ngầm 24/7" if sess["running"] else "🔴 Đang dừng"
    uid_str = sess["user_id"] if sess["user_id"] else "Chưa cài đặt"
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER - ULTIMATE BOT*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👤 *User ID:* `{uid_str}`\n"
        f"🪙 *Đồng cược:* `{sess['asset_type']}`\n"
        f"💵 *Cược gốc:* `{sess['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{sess['multiplier']}`\n"
        f"🛡️ *Ngắt thua:* `{sess['loss_threshold']} ván (Nghỉ {sess['skip_rounds']} ván)`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Chọn thao tác bên dưới:*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_link = types.InlineKeyboardButton("⚙️ Nhập Link Game", callback_data="btn_setup_link")
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Bot Cược" if not sess["running"] else "⏹️ Tắt Bot", callback_data="btn_toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin ({sess['asset_type']})", callback_data="btn_toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược ({sess['base_bet']})", callback_data="btn_change_bet")
    btn_status = types.InlineKeyboardButton("📊 Thống kê chi tiết", callback_data="btn_status")
    
    markup.add(btn_link)
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_status)
    
    bot.send_message(chat_id, msg_text, reply_markup=markup)

# Xử lý nút bấm tương tác
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    sess = get_session(chat_id)
    data = call.data
    
    if data == "btn_setup_link":
        sess["waiting_for_link"] = True
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📥 **Vui lòng dán Link game XWorld của bạn vào đây** để hệ thống tự động trích xuất User ID và Secret Key!")
        
    elif data == "btn_toggle_bot":
        if not sess["running"]:
            if not sess["user_id"] or not sess["secret_key"]:
                bot.answer_callback_query(call.id, "⚠️ Chưa có User ID! Hãy bấm Nhập Link trước.", show_alert=True)
                return
            sess["running"] = True
            Thread(target=run_bot_engine, args=(chat_id,), daemon=True).start()
            bot.answer_callback_query(call.id, "🚀 Đã kích hoạt bot chạy ngầm thành công!")
        else:
            sess["running"] = False
            sess["random_stop"].set()
            if sess["ws_app"]:
                try: sess["ws_app"].close()
                except: pass
            bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
        refresh_menu(call.message)
        
    elif data == "btn_toggle_asset":
        sess["asset_type"] = "USDT" if sess["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(call.id, f"Đã chuyển sang {sess['asset_type']}")
        refresh_menu(call.message)
        
    elif data == "btn_change_bet":
        bets = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
        next_idx = (bets.index(sess["base_bet"]) + 1) % len(bets) if sess["base_bet"] in bets else 0
        sess["base_bet"] = bets[next_idx]
        bot.answer_callback_query(call.id, f"Đã đổi cược gốc thành {sess['base_bet']}")
        refresh_menu(call.message)
        
    elif data == "btn_status":
        bal = get_balance(sess)
        wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ HOẠT ĐỘNG*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
            f"Số dư ví thực tế: `{bal:.4f} {sess['asset_type']}`\n"
            f"Tổng ván cược: `{sess['total_bets']}`\n"
            f"Thắng / Thua: `{sess['wins']}` / `{sess['losses']}` (WR: `{wr:.1f}%`)\n"
            f"Lợi nhuận tổng: `{sess['total_profit']:+.4f} {sess['asset_type']}`"
        )
        bot.send_message(chat_id, msg)

# Nhận link tự động bóc tách thông tin
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    sess = get_session(chat_id)
    
    if sess.get("waiting_for_link", False):
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text)
                query_params = parse_qs(parsed_url.query)
                uid = query_params.get("userId", [None])[0]
                skey = query_params.get("secretKey", [None])[0]
                
                if uid and skey:
                    sess["user_id"] = int(uid)
                    sess["secret_key"] = skey
                    sess["waiting_for_link"] = False
                    bot.reply_to(message, f"✅ **Cài đặt tài khoản thành công!**\n• User ID: `{uid}`\n\nGõ lệnh `/start` để mở lại menu và bấm Bật Bot Cược.")
                    return
            except:
                pass
        bot.reply_to(message, "⚠️ Link không hợp lệ! Hãy đảm bảo copy đầy đủ Link game XWorld chứa thông số `userId` và `secretKey`.")
    else:
        if text.startswith("/"):
            return
        bot.reply_to(message, "💡 Vui lòng gõ `/start` để mở bảng điều khiển quản lý bot.")

def refresh_menu(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    status_str = "🟢 Đang chạy ngầm 24/7" if sess["running"] else "🔴 Đang dừng"
    uid_str = sess["user_id"] if sess["user_id"] else "Chưa cài đặt"
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER - ULTIMATE BOT*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👤 *User ID:* `{uid_str}`\n"
        f"🪙 *Đồng cược:* `{sess['asset_type']}`\n"
        f"💵 *Cược gốc:* `{sess['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{sess['multiplier']}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Chọn thao tác bên dưới:*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_link = types.InlineKeyboardButton("⚙️ Nhập Link Game", callback_data="btn_setup_link")
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Bot Cược" if not sess["running"] else "⏹️ Tắt Bot", callback_data="btn_toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin ({sess['asset_type']})", callback_data="btn_toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược ({sess['base_bet']})", callback_data="btn_change_bet")
    btn_status = types.InlineKeyboardButton("📊 Thống kê chi tiết", callback_data="btn_status")
    
    markup.add(btn_link)
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_status)
    
    try:
        bot.edit_message_text(msg_text, chat_id, message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

# ================= CORE API & LOGIC TỪ FILE GỐC =================
def get_headers(sess):
    return {
        "Content-Type": "application/json",
        "user-id": str(sess["user_id"]),
        "user-login": "login_v2",
        "user-secret-key": sess["secret_key"],
        "Accept": "application/json",
        "xb-language": "vi-VN"
    }

def api_call(sess, method, url, **kwargs):
    try:
        session_req = requests.Session()
        resp = session_req.request(method, url, headers=get_headers(sess), timeout=15, **kwargs)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}

def get_balance(sess):
    # Lấy từ ví tổng 3games/xworld trước[span_4](start_span)[span_4](end_span)
    url = "https://wallet.3games.io/api/wallet/total_asset_in_usdt"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "country-code": "vn",
        "nonce": "dohQi",
        "origin": "https://xworld.info",
        "platform": "h5",
        "referer": "https://xworld.info/",
        "user-agent": "Mozilla/5.0",
        "user-id": str(sess["user_id"]),
        "user-secret-key": sess["secret_key"],
        "xb-language": "vi-VN"
    }
    payload = {"user_id": sess["user_id"], "filter": {"top_n": {"n": 10}}, "refresh": 0}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                result = data.get("data")
                items = result.get("items", []) if isinstance(result, dict) else result
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("symbol") == sess["asset_type"]:
                            return float(item.get("balance", 0))
    except:
        pass
    
    # Fallback lấy qua API game cũ nếu ví tổng lỗi[span_5](start_span)[span_5](end_span)
    data = api_call(sess, "POST", "https://api.escapemaster.net/escape_game/get_user_asset",
                    json={"asset_type": sess["asset_type"], "user_id": sess["user_id"]})
    if data and data.get("code") == 0:
        return float(data.get("data", {}).get("balance", 0))
    return 0.0

def enter_room(sess, room_id):
    data = api_call(sess, "POST", "https://api.escapemaster.net/escape_game/enter_room",
                    json={"asset_type": sess["asset_type"], "user_id": sess["user_id"], "room_id": room_id})
    return data.get("code") == 0 if data else False

def place_bet(sess, room_id, amount):
    data = api_call(sess, "POST", "https://api.escapemaster.net/escape_game/bet",
                    json={"asset_type": sess["asset_type"], "user_id": sess["user_id"], "room_id": room_id, "bet_amount": amount})
    return data.get("code") == 0 if data else False

def get_my_joined(sess, page=1):
    url = "https://api.escapemaster.net/escape_game/my_joined"
    params = {"asset": sess["asset_type"], "page": page, "page_size": 10}
    try:
        session_req = requests.Session()
        resp = session_req.get(url, params=params, headers=get_headers(sess), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {})
    except:
        pass
    return {}

# Thuật toán random phòng mượt mà 0.2s giống bản gốc[span_6](start_span)[span_6](end_span)
def start_random_rooms(chat_id, sess):
    sess["random_stop"].clear()
    def api_loop():
        rooms = [1, 2, 3, 4, 5, 6, 7, 8]
        while not sess["random_stop"].is_set() and sess["running"]:
            room_id = random.choice(rooms)
            try:
                session_req = requests.Session()
                session_req.post("https://api.escapemaster.net/escape_game/enter_room",
                                 json={"asset_type": sess["asset_type"], "user_id": sess["user_id"], "room_id": room_id},
                                 headers=get_headers(sess), timeout=2)
            except:
                pass
            time.sleep(0.2)
    Thread(target=api_loop, daemon=True).start()

def stop_random_rooms(sess):
    sess["random_stop"].set()

# Xử lý kết quả cược và chiến thuật gấp thếp
def process_game_result(chat_id, sess, issue_id, is_killed, award, bet, killed_room, my_room):
    stop_random_rooms(sess)
    profit = award - bet
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
        if sess["consecutive_losses"] >= sess["loss_threshold"]:
            sess["skips_left"] = sess["skip_rounds"]
            sess["consecutive_losses"] = 0
        else:
            sess["base_bet"] *= sess["multiplier"]
            
    sess["total_profit"] += profit
    bal = get_balance(sess)
    wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
    
    msg = (
        f"🏁 *KẾT QUẢ PHIÊN #{issue_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Trạng thái: *{status_text}*\n"
        f"Phòng bẫy: `{killed_room}` | Phòng chọn: `{my_room}`\n"
        f"Tiền cược: `{bet:.4f} {sess['asset_type']}`\n"
        f"Tiền thưởng: `{award:.4f} {sess['asset_type']}`\n"
        f"Lời trận này: `{profit:+.4f}`\n"
        f"Tổng lời: `{sess['total_profit']:+.4f}` (WR: {wr:.1f}%)\n"
        f"💰 Số dư ví: `{bal:.4f} {sess['asset_type']}`"
    )
    bot.send_message(chat_id, msg)
    
    sess["has_bet"] = False
    sess["betting_issue"] = None

# Luồng chạy Bot chính + Watchdog 360s[span_7](start_span)[span_7](end_span)
def run_bot_engine(chat_id):
    sess = get_session(chat_id)
    ws_url = "wss://api.escapemaster.net/escape_master/ws"
    
    def on_message(ws, message):
        if not sess["running"]:
            ws.close()
            return
        try:
            data = json.loads(message)
            msg_type = data.get("msg_type", "")
            
            if msg_type == "notify_count_down":
                issue_id = data.get("issue_id")
                count_down = data.get("count_down", 0)
                
                if sess["current_issue"] != issue_id:
                    sess["current_issue"] = issue_id
                    sess["has_bet"] = False
                    
                    if sess["skips_left"] > 0:
                        sess["skips_left"] -= 1
                        return
                        
                    room = random.randint(1, 8)
                    amount = sess["base_bet"]
                    
                    if enter_room(sess, room):
                        time.sleep(0.3)
                        if place_bet(sess, room, amount):
                            sess["has_bet"] = True
                            sess["betting_issue"] = issue_id
                            sess["watchdog_last_time"] = time.time() # Reset Watchdog[span_8](start_span)[span_8](end_span)
                            
                            start_random_rooms(chat_id, sess)
                            
                            # API Backup kiểm tra kết quả phòng hờ rớt mạng[span_9](start_span)[span_9](end_span)
                            def check_api_backup():
                                time.sleep(count_down + 5)
                                if sess["has_bet"] and sess["betting_issue"] == issue_id:
                                    res_data = get_my_joined(sess, 1)
                                    items = res_data.get("items", [])
                                    for item in items:
                                        if str(item.get("issue_id")) == str(issue_id):
                                            award = float(item.get("award_amount", 0))
                                            bet_amt = float(item.get("bet_amount", 0))
                                            is_killed = not (award > bet_amt)
                                            kr = item.get("killed_room_id", "?")
                                            mr = item.get("room_id", "?")
                                            process_game_result(chat_id, sess, issue_id, is_killed, award, bet_amt, kr, mr)
                                            return
                            Thread(target=check_api_backup, daemon=True).start()

            elif msg_type == "notify_result":
                issue_id = data.get("issue_id")
                if sess["has_bet"] and issue_id == sess["betting_issue"]:
                    award = float(data.get("award_amount", 0))
                    bet_val = float(data.get("bet_amount", 0))
                    is_killed = not (award > bet_val)
                    killed_room = data.get("killed_room", "?")
                    my_room = data.get("room_id", "?")
                    process_game_result(chat_id, sess, issue_id, is_killed, award, bet_val, killed_room, my_room)

            elif msg_type == "notify_heartbeat":
                ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
        except:
            pass

    # Watchdog giám sát 360 giây không cược -> Auto restart WebSocket[span_10](start_span)[span_10](end_span)
    def watchdog_monitor():
        while sess["running"]:
            time.sleep(5)
            if time.time() - sess["watchdog_last_time"] > 360:
                if sess["ws_app"]:
                    try: sess["ws_app"].close()
                    except: pass
                sess["watchdog_last_time"] = time.time()
    Thread(target=watchdog_monitor, daemon=True).start()

    while sess["running"]:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                header={"Origin": "https://escapemaster.net", "User-Agent": "Mozilla/5.0"},
                on_open=lambda w: w.send(json.dumps({
                    "msg_type": "handle_enter_game",
                    "asset_type": sess["asset_type"],
                    "user_id": sess["user_id"],
                    "user_secret_key": sess["secret_key"]
                })),
                on_message=on_message,
                on_error=lambda w, e: None,
                on_close=lambda w, c, m: None
            )
            sess["ws_app"] = ws
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
