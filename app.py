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
    return "Escape Master Multi-Bot 24/7 is running!"

# Cấu hình đa luồng lưu theo chat_id
user_data = {}
data_lock = Lock()

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "accounts": {},             # Danh sách nick: {uid: secret_key}
                "global_running": False,    # Trạng thái bật/tắt chung cho tất cả nick
                "waiting_for_link": False,
                "asset_type": "BUILD",
                "base_bet": 3.8,
                "bet_index": 0,
                "count_10_used": 0,
                "loss_threshold": 2,
                "skip_rounds": 3,
                "multiplier": 2.0
            }
        return user_data[chat_id]

# Data chạy ngầm cho từng nick riêng biệt
account_threads = {}

def get_account_state(uid):
    if uid not in account_threads:
        account_threads[uid] = {
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
    return account_threads[uid]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = False
    
    status_str = "🟢 Đang chạy tự động 24/7" if cfg["global_running"] else "🔴 Đang dừng"
    total_accs = len(cfg["accounts"])
    
    msg_text = (
        "🎮 *XWORLD ESCAPE MASTER - BOT MULTI AUTO*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👥 *Số tài khoản đã thêm:* `{total_accs} nick`\n"
        f"🪙 *Đồng cược:* `{cfg['asset_type']}`\n"
        f"💵 *Mức cược:* `{cfg['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{cfg['multiplier']}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Chọn thao tác bên dưới:*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_link = types.InlineKeyboardButton("⚙️ Thêm Link Game", callback_data="btn_setup_link")
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Auto Tất Cả" if not cfg["global_running"] else "⏹️ Tắt Tất Cả Bot", callback_data="btn_toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin ({cfg['asset_type']})", callback_data="btn_toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược ({cfg['base_bet']})", callback_data="btn_change_bet")
    btn_accs = types.InlineKeyboardButton("👥 Danh sách Tài Khoản", callback_data="btn_list_accounts")
    btn_status = types.InlineKeyboardButton("📊 Thống kê tổng quan", callback_data="btn_status")
    
    markup.add(btn_link)
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_accs, btn_status)
    
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    data = call.data
    
    if data == "btn_setup_link":
        cfg["waiting_for_link"] = True
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📥 **Vui lòng dán Link game XWorld của bạn vào đây!**\n(Bạn có thể dán nhiều link khác nhau để thêm nhiều tài khoản chạy song song).")
        
    elif data == "btn_toggle_bot":
        if not cfg["accounts"]:
            bot.answer_callback_query(call.id, "⚠️ Chưa có tài khoản nào! Hãy bấm Thêm Link Game trước.", show_alert=True)
            return
            
        if not cfg["global_running"]:
            cfg["global_running"] = True
            for uid, skey in cfg["accounts"].items():
                Thread(target=run_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
            bot.answer_callback_query(call.id, f"🚀 Đã bật cược TỰ ĐỘNG cho toàn bộ {len(cfg['accounts'])} tài khoản!")
        else:
            cfg["global_running"] = False
            for uid in cfg["accounts"]:
                acc_st = get_account_state(uid)
                acc_st["random_stop"].set()
                if acc_st["ws_app"]:
                    try:
                        acc_st["ws_app"].close()
                    except Exception:
                        pass
            bot.answer_callback_query(call.id, "⏹️ Đã dừng tất cả các tài khoản!")
        refresh_menu(call.message)
        
    elif data == "btn_toggle_asset":
        cfg["asset_type"] = "USDT" if cfg["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(call.id, f"Đã chuyển sang {cfg['asset_type']}")
        refresh_menu(call.message)
        
    elif data == "btn_change_bet":
        allowed_bets = [3.8, 10.0, 100.0, 1000.0, 10000.0]
        cfg["bet_index"] = (cfg["bet_index"] + 1) % len(allowed_bets)
        chosen_bet = allowed_bets[cfg["bet_index"]]
        
        if chosen_bet == 10.0:
            if cfg["count_10_used"] >= 3:
                cfg["bet_index"] = (cfg["bet_index"] + 1) % len(allowed_bets)
                chosen_bet = allowed_bets[cfg["bet_index"]]
            else:
                cfg["count_10_used"] += 1
                
        cfg["base_bet"] = chosen_bet
        bot.answer_callback_query(call.id, f"Đã đổi mức cược thành {cfg['base_bet']}")
        refresh_menu(call.message)
        
    elif data == "btn_list_accounts":
        if not cfg["accounts"]:
            bot.answer_callback_query(call.id, "Chưa có tài khoản nào được lưu!", show_alert=True)
            return
        msg = "👥 *DANH SÁCH TÀI KHOẢN ĐANG QUẢN LÝ:*\n━━━━━━━━━━━━━━━━━━━\n"
        for idx, uid in enumerate(cfg["accounts"].keys(), 1):
            msg += f"{idx}. User ID: `{uid}`\n"
        msg += "\n💡 Bấm *🚀 Bật Auto Tất Cả* ở menu chính để chạy đồng thời tất cả nick trên!"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    elif data == "btn_status":
        tot_bets = 0
        tot_wins = 0
        tot_losses = 0
        tot_profit = 0.0
        
        for uid in cfg["accounts"]:
            st = get_account_state(uid)
            tot_bets += st["total_bets"]
            tot_wins += st["wins"]
            tot_losses += st["losses"]
            tot_profit += st["total_profit"]
            
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0
        msg = (
            "📊 *THỐNG KÊ TỔNG CÁC TÀI KHOẢN*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"Trạng thái: {'🟢 Đang chạy' if cfg['global_running'] else '🔴 Đang dừng'}\n"
            f"Số tài khoản: `{len(cfg['accounts'])} nick`\n"
            f"Tổng ván cược: `{tot_bets}`\n"
            f"Thắng / Thua: `{tot_wins}` / `{tot_losses}` (WR: `{wr:.1f}%`)\n"
            f"Tổng lợi nhuận: `{tot_profit:+.4f} {cfg['asset_type']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    if cfg.get("waiting_for_link", False):
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text)
                query_params = parse_qs(parsed_url.query)
                uid_str = query_params.get("userId", [None])[0]
                skey = query_params.get("secretKey", [None])[0]
                
                if uid_str and skey:
                    uid = int(uid_str)
                    cfg["accounts"][uid] = skey
                    cfg["waiting_for_link"] = False
                    
                    # Nếu hệ thống đang bật chạy tự động, cho nick mới chạy luôn
                    if cfg["global_running"]:
                        Thread(target=run_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                        
                    bot.reply_to(message, f"✅ **Đã thêm tài khoản thành công!**\n• User ID: `{uid}`\n• Tổng số nick: `{len(cfg['accounts'])}`\n\nGõ lệnh `/start` để quay lại bảng điều khiển.")
                    return
            except Exception:
                pass
        bot.reply_to(message, "⚠️ Link không hợp lệ! Hãy dán đúng link game XWorld chứa `userId` và `secretKey`.")
    else:
        if text.startswith("/"):
            return
        bot.reply_to(message, "💡 Vui lòng gõ `/start` để mở bảng điều khiển bot.")

def refresh_menu(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    status_str = "🟢 Đang chạy tự động 24/7" if cfg["global_running"] else "🔴 Đang dừng"
    total_accs = len(cfg["accounts"])
    
    msg_text = (
        "🎮 *XWORLD ESCAPE MASTER - BOT MULTI AUTO*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👥 *Số tài khoản đã thêm:* `{total_accs} nick`\n"
        f"🪙 *Đồng cược:* `{cfg['asset_type']}`\n"
        f"💵 *Mức cược:* `{cfg['base_bet']}`\n"
        f"📈 *Hệ số nhân:* `x{cfg['multiplier']}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Chọn thao tác bên dưới:*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_link = types.InlineKeyboardButton("⚙️ Thêm Link Game", callback_data="btn_setup_link")
    btn_toggle = types.InlineKeyboardButton("🚀 Bật Auto Tất Cả" if not cfg["global_running"] else "⏹️ Tắt Tất Cả Bot", callback_data="btn_toggle_bot")
    btn_asset = types.InlineKeyboardButton(f"🪙 Đổi Coin ({cfg['asset_type']})", callback_data="btn_toggle_asset")
    btn_bet = types.InlineKeyboardButton(f"💵 Đổi Cược ({cfg['base_bet']})", callback_data="btn_change_bet")
    btn_accs = types.InlineKeyboardButton("👥 Danh sách Tài Khoản", callback_data="btn_list_accounts")
    btn_status = types.InlineKeyboardButton("📊 Thống kê tổng quan", callback_data="btn_status")
    
    markup.add(btn_link)
    markup.add(btn_toggle)
    markup.add(btn_asset, btn_bet)
    markup.add(btn_accs, btn_status)
    
    try:
        bot.edit_message_text(msg_text, chat_id, message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        pass

def get_headers(uid, skey):
    return {
        "Content-Type": "application/json",
        "user-id": str(uid),
        "user-login": "login_v2",
        "user-secret-key": skey,
        "Accept": "application/json",
        "xb-language": "vi-VN"
    }

def api_call(uid, skey, method, url, **kwargs):
    try:
        session_req = requests.Session()
        resp = session_req.request(method, url, headers=get_headers(uid, skey), timeout=15, **kwargs)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}

def get_balance(cfg, uid, skey):
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
        "user-id": str(uid),
        "user-secret-key": skey,
        "xb-language": "vi-VN"
    }
    payload = {"user_id": uid, "filter": {"top_n": {"n": 10}}, "refresh": 0}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                result = data.get("data")
                items = result.get("items", []) if isinstance(result, dict) else result
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("symbol") == cfg["asset_type"]:
                            return float(item.get("balance", 0))
    except Exception:
        pass
        
    data = api_call(uid, skey, "POST", "https://api.escapemaster.net/escape_game/get_user_asset",
                    json={"asset_type": cfg["asset_type"], "user_id": uid})
    if data and data.get("code") == 0:
        return float(data.get("data", {}).get("balance", 0))
    return 0.0

def enter_room(cfg, uid, skey, room_id):
    data = api_call(uid, skey, "POST", "https://api.escapemaster.net/escape_game/enter_room",
                    json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room_id})
    return data.get("code") == 0 if data else False

def place_bet(cfg, uid, skey, room_id, amount):
    data = api_call(uid, skey, "POST", "https://api.escapemaster.net/escape_game/bet",
                    json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room_id, "bet_amount": amount})
    return data.get("code") == 0 if data else False

def get_my_joined(uid, skey, asset_type, page=1):
    url = "https://api.escapemaster.net/escape_game/my_joined"
    params = {"asset": asset_type, "page": page, "page_size": 10}
    try:
        session_req = requests.Session()
        resp = session_req.get(url, params=params, headers=get_headers(uid, skey), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {})
    except Exception:
        pass
    return {}

def start_random_rooms(cfg, uid, skey):
    acc_st = get_account_state(uid)
    acc_st["random_stop"].clear()
    def api_loop():
        rooms = [1, 2, 3, 4, 5, 6, 7, 8]
        while not acc_st["random_stop"].is_set() and cfg["global_running"]:
            room_id = random.choice(rooms)
            try:
                session_req = requests.Session()
                session_req.post("https://api.escapemaster.net/escape_game/enter_room",
                                 json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room_id},
                                 headers=get_headers(uid, skey), timeout=2)
            except Exception:
                pass
            time.sleep(0.2)
    Thread(target=api_loop, daemon=True).start()

def stop_random_rooms(uid):
    acc_st = get_account_state(uid)
    acc_st["random_stop"].set()

def process_game_result(chat_id, cfg, uid, skey, issue_id, is_killed, award, bet, killed_room, my_room):
    stop_random_rooms(uid)
    acc_st = get_account_state(uid)
    profit = award - bet
    acc_st["total_bets"] += 1
    
    status_text = "THẮNG 🟢" if not is_killed else "THUA 🔴"
    
    if not is_killed:
        acc_st["wins"] += 1
        acc_st["consecutive_losses"] = 0
        acc_st["skips_left"] = 0
    else:
        acc_st["losses"] += 1
        acc_st["consecutive_losses"] += 1
        if acc_st["consecutive_losses"] >= cfg["loss_threshold"]:
            acc_st["skips_left"] = cfg["skip_rounds"]
            acc_st["consecutive_losses"] = 0
            
    acc_st["total_profit"] += profit
    bal = get_balance(cfg, uid, skey)
    wr = (acc_st["wins"] / acc_st["total_bets"] * 100) if acc_st["total_bets"] > 0 else 0
    
    msg = (
        f"🏁 *[NICK `{uid}`] KẾT QUẢ PHIÊN #{issue_id}*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"Trạng thái: *{status_text}*\n"
        f"Phòng bẫy: `{killed_room}` | Chọn: `{my_room}`\n"
        f"Tiền cược: `{bet:.4f} {cfg['asset_type']}`\n"
        f"Tiền thưởng: `{award:.4f} {cfg['asset_type']}`\n"
        f"Lời trận này: `{profit:+.4f}`\n"
        f"Tổng lời: `{acc_st['total_profit']:+.4f}` (WR: {wr:.1f}%)\n"
        f"💰 Số dư ví: `{bal:.4f} {cfg['asset_type']}`"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    acc_st["has_bet"] = False
    acc_st["betting_issue"] = None

def run_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)
    acc_st = get_account_state(uid)
    ws_url = "wss://api.escapemaster.net/escape_master/ws"
    
    def on_message(ws, message):
        if not cfg["global_running"]:
            ws.close()
            return
        try:
            data = json.loads(message)
            msg_type = data.get("msg_type", "")
            
            if msg_type == "notify_count_down":
                issue_id = data.get("issue_id")
                count_down = data.get("count_down", 0)
                
                if acc_st["current_issue"] != issue_id:
                    acc_st["current_issue"] = issue_id
                    acc_st["has_bet"] = False
                    
                    if acc_st["skips_left"] > 0:
                        acc_st["skips_left"] -= 1
                        return
                        
                    room = random.randint(1, 8)
                    amount = cfg["base_bet"]
                    
                    if enter_room(cfg, uid, skey, room):
                        time.sleep(0.3)
                        if place_bet(cfg, uid, skey, room, amount):
                            acc_st["has_bet"] = True
                            acc_st["betting_issue"] = issue_id
                            acc_st["watchdog_last_time"] = time.time()
                            
                            start_random_rooms(cfg, uid, skey)
                            
                            def check_api_backup():
                                time.sleep(count_down + 5)
                                if acc_st["has_bet"] and acc_st["betting_issue"] == issue_id:
                                    res_data = get_my_joined(uid, skey, cfg["asset_type"], 1)
                                    items = res_data.get("items", [])
                                    for item in items:
                                        if str(item.get("issue_id")) == str(issue_id):
                                            award = float(item.get("award_amount", 0))
                                            bet_amt = float(item.get("bet_amount", 0))
                                            is_killed = not (award > bet_amt)
                                            kr = item.get("killed_room_id", "?")
                                            mr = item.get("room_id", "?")
                                            process_game_result(chat_id, cfg, uid, skey, issue_id, is_killed, award, bet_amt, kr, mr)
                                            return
                            Thread(target=check_api_backup, daemon=True).start()

            elif msg_type == "notify_result":
                issue_id = data.get("issue_id")
                if acc_st["has_bet"] and issue_id == acc_st["betting_issue"]:
                    award = float(data.get("award_amount", 0))
                    bet_val = float(data.get("bet_amount", 0))
                    is_killed = not (award > bet_val)
                    killed_room = data.get("killed_room", "?")
                    my_room = data.get("room_id", "?")
                    process_game_result(chat_id, cfg, uid, skey, issue_id, is_killed, award, bet_val, killed_room, my_room)

            elif msg_type == "notify_heartbeat":
                ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
        except Exception:
            pass

    def watchdog_monitor():
        while cfg["global_running"]:
            time.sleep(5)
            if time.time() - acc_st["watchdog_last_time"] > 360:
                if acc_st["ws_app"]:
                    try:
                        acc_st["ws_app"].close()
                    except Exception:
                        pass
                acc_st["watchdog_last_time"] = time.time()
    Thread(target=watchdog_monitor, daemon=True).start()

    while cfg["global_running"]:
        try:
            ws =
