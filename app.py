#!/usr/bin/env python3
"""
ESCAPE MASTER MULTI-ACCOUNT TELEGRAM BOT - RENDER 24/7
======================================================
- Hỗ trợ đa luồng: Chạy song song nhiều tài khoản độc lập cùng lúc.
- Cấu hình mốc cược: 3.8 (vô hạn), 10 (giới hạn 3 lần), 100, 1000, 10000 (vô hạn).
- Tích hợp Watchdog 360s và Random phòng 0.2s mượt mà.
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
    return "Escape Master Multi-Account Bot is running 24/7!"

# Quản lý danh sách tài khoản theo từng Chat ID và User ID riêng biệt
# Cấu trúc: multi_accounts[chat_id][user_id] = { session_data }
multi_accounts = {}
manager_lock = Lock()

def get_account_session(chat_id, user_id):
    with manager_lock:
        if chat_id not in multi_accounts:
            multi_accounts[chat_id] = {}
        if user_id not in multi_accounts[chat_id]:
            multi_accounts[chat_id][user_id] = {
                "user_id": user_id,
                "secret_key": "",
                "asset_type": "BUILD",
                "base_bet": 3.8,
                "bet_index": 0,
                "count_10_used": 0,
                "loss_threshold": 2,
                "skip_rounds": 3,
                "multiplier": 2.0,
                "running": False,
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
        return multi_accounts[chat_id][user_id]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    
    msg_text = (
        f"🎮 *XWORLD ESCAPE MASTER - MULTI-ACCOUNT BOT*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Hệ thống đa luồng độc lập*\n"
        f"👉 Hãy **dán Link game** bất kỳ vào đây để thêm và quản lý tài khoản chạy song song!"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_list = types.InlineKeyboardButton("📋 Danh sách tài khoản đang quản lý", callback_data="btn_list_acc")
    markup.add(btn_list)
    
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

# Xử lý khi người dùng dán link game trực tiếp để thêm tài khoản
@bot.message_handler(func=lambda message: True)
def handle_link_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    if "userId=" in text and "secretKey=" in text:
        try:
            parsed_url = urlparse(text)
            query_params = parse_qs(parsed_url.query)
            uid_str = query_params.get("userId", [None])[0]
            skey = query_params.get("secretKey", [None])[0]
            
            if uid_str and skey:
                uid = int(uid_str)
                sess = get_account_session(chat_id, uid)
                sess["secret_key"] = skey
                
                bot.reply_to(message, f"✅ **Đã thêm/cập nhật tài khoản thành công!**\n• User ID: `{uid}`\n\nBấm vào danh sách bên dưới để bật/tắt cược cho tài khoản này.")
                show_account_management(chat_id, message.message_id, uid)
                return
        except:
            pass
            
    if not text.startswith("/"):
        bot.reply_to(message, "⚠️ Vui lòng dán đúng **Link game XWorld** chứa `userId` và `secretKey` để thêm tài khoản mới.")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if data == "btn_list_acc":
        show_accounts_list(chat_id, call.message.message_id)
        
    elif data.startswith("acc_"):
        # Format: acc_UID_action
        parts = data.split("_")
        uid = int(parts[1])
        action = parts[2]
        sess = get_account_session(chat_id, uid)
        
        if action == "toggle":
            if not sess["running"]:
                if not sess["secret_key"]:
                    bot.answer_callback_query(call.id, "⚠️ Tài khoản chưa có Secret Key hợp lệ!", show_alert=True)
                    return
                sess["running"] = True
                Thread(target=run_bot_engine, args=(chat_id, uid), daemon=True).start()
                bot.answer_callback_query(call.id, f"🚀 Đã bật luồng cho nick {uid}!")
            else:
                sess["running"] = False
                sess["random_stop"].set()
                if sess["ws_app"]:
                    try: sess["ws_app"].close()
                    except: pass
                bot.answer_callback_query(call.id, f"⏹️ Đã dừng luồng nick {uid}!")
            show_account_management(chat_id, call.message.message_id, uid)
            
        elif action == "asset":
            sess["asset_type"] = "USDT" if sess["asset_type"] == "BUILD" else "BUILD"
            bot.answer_callback_query(call.id, f"Đổi coin sang {sess['asset_type']}")
            show_account_management(chat_id, call.message.message_id, uid)
            
        elif action == "bet":
            allowed_bets = [3.8, 10.0, 100.0, 1000.0, 10000.0]
            sess["bet_index"] = (sess["bet_index"] + 1) % len(allowed_bets)
            chosen_bet = allowed_bets[sess["bet_index"]]
            if chosen_bet == 10.0:
                if sess["count_10_used"] >= 3:
                    sess["bet_index"] = (sess["bet_index"] + 1) % len(allowed_bets)
                    chosen_bet = allowed_bets[sess["bet_index"]]
                else:
                    sess["count_10_used"] += 1
            sess["base_bet"] = chosen_bet
            bot.answer_callback_query(call.id, f"Đổi cược thành {sess['base_bet']}")
            show_account_management(chat_id, call.message.message_id, uid)
            
        elif action == "status":
            bal = get_balance(sess)
            wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
            msg = (
                f"📊 *THỐNG KÊ NICK `{uid}`*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
                f"Số dư ví: `{bal:.4f} {sess['asset_type']}`\n"
                f"Tổng ván: `{sess['total_bets']}` | Thắng: `{sess['wins']}` | Thua: `{sess['losses']}` (WR: `{wr:.1f}%`)\n"
                f"Tổng lời: `{sess['total_profit']:+.4f} {sess['asset_type']}`"
            )
            bot.send_message(chat_id, msg, parse_mode="Markdown")

def show_accounts_list(chat_id, message_id):
    with manager_lock:
        accs = multi_accounts.get(chat_id, {})
        
    if not accs:
        bot.answer_callback_query(message_id, "Chưa có tài khoản nào được thêm!", show_alert=True)
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, sess in accs.items():
        status = "🟢" if sess["running"] else "🔴"
        btn = types.InlineKeyboardButton(f"{status} Tài khoản: {uid} ({sess['asset_type']})", callback_data=f"acc_{uid}_status_menu")
        markup.add(btn)
        
    try:
        bot.edit_message_text("📋 *DANH SÁCH TÀI KHOẢN ĐANG QUẢN LÝ*\nChọn tài khoản bên dưới để cấu hình:", chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

def show_account_management(chat_id, message_id, uid):
    sess = get_account_session(chat_id, uid)
    status_str = "🟢 Đang chạy ngầm" if sess["running"] else "🔴 Đang dừng"
    
    msg_text = (
        f"🎮 *QUẢN LÝ TÀI KHOẢN: `{uid}`*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái luồng:* {status_str}\n"
        f"🪙 *Đồng cược:* `{sess['asset_type']}`\n"
        f"💵 *Mức cược hiện tại:* `{sess['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{sess['multiplier']}`\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Luồng" if not sess["running"] else "⏹️ Tắt Luồng", callback_data=f"acc_{uid}_toggle")
    btn_asset = types.InlineKeyboardButton(f"🪙 Coin: {sess['asset_type']}", callback_data=f"acc_{uid}_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Cược: {sess['base_bet']}", callback_data=f"acc_{uid}_bet")
    btn_status = types.InlineKeyboardButton("📊 Thống kê", callback_data=f"acc_{uid}_status")
    btn_back = types.InlineKeyboardButton("⬅️ Quay lại danh sách", callback_data="btn_list_acc")
    
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_status)
    markup.add(btn_back)
    
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

# API xử lý cho từng session độc lập
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

def start_random_rooms(sess):
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

def process_game_result(chat_id, sess, issue_id, is_killed, award, bet, killed_room, my_room):
    stop_random_rooms(sess)
    profit = award - bet
    sess["total_bets"] += 1
    
    status_text = "THẮNG 🟢" if not is_killed else "THUA 🔴"
    
    if not is_killed:
        sess["wins"] += 1
        sess["consecutive_losses"] = 0
        sess["skips_left"] = 0
    else:
        sess["losses"] += 1
        sess["consecutive_losses"] += 1
        if sess["consecutive_losses"] >= sess["loss_threshold"]:
            sess["skips_left"] = sess["skip_rounds"]
            sess["consecutive_losses"] = 0
            
    sess["total_profit"] += profit
    bal = get_balance(sess)
    wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
    
    msg = (
        f"🏁 *[NICK `{sess['user_id']}`] KẾT QUẢ PHIÊN #{issue_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Trạng thái: *{status_text}*\n"
        f"Phòng bẫy: `{killed_room}` | Chọn: `{my_room}`\n"
        f"Cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
        f"Lời trận: `{profit:+.4f}` | Tổng lời: `{sess['total_profit']:+.4f}` (WR: {wr:.1f}%)\n"
        f"💰 Số dư ví: `{bal:.4f} {sess['asset_type']}`"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    sess["has_bet"] = False
    sess["betting_issue"] = None

# Động cơ luồng độc lập cho từng tài khoản
def run_bot_engine(chat_id, user_id):
    sess = get_account_session(chat_id, user_id)
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
                            sess["watchdog_last_time"] = time.time()
                            
                            start_random_rooms(sess)
                            
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
