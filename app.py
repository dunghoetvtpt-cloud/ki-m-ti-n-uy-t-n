#!/usr/bin/env python3
"""
ESCAPE MASTER TELEGRAM INTERACTIVE BOT - RENDER 24/7
===================================================
- Điều khiển toàn bộ qua Telegram (Gõ /start để mở Menu)
- Flask giữ server sống trên Render
"""
import websocket
import json
import time
import random
import requests
import os
from threading import Thread, Lock
from flask import Flask, request as flask_request

# --- CẤU HÌNH TOKEN VÀ TRẠNG THÁI ---
TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"

# Lưu trữ cấu hình và trạng thái cho từng chat_id
user_sessions = {}
session_lock = Lock()

app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Escape Master Bot is running 24/7!"

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    update = flask_request.get_json()
    if update:
        # Xử lý tin nhắn text
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "").strip()
            handle_telegram_message(chat_id, text)
        
        # Xử lý khi bấm nút inline keyboard
        elif "callback_query" in update:
            chat_id = update["callback_query"]["message"]["chat"]["id"]
            data = update["callback_query"]["data"]
            handle_telegram_callback(chat_id, data)
            
    return "OK", 200

def send_telegram_markup(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

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

def handle_telegram_message(chat_id, text):
    sess = get_session(chat_id)
    
    if text == "/start":
        menu_text = (
            f"🎮 *ESCAPE MASTER BOT MANAGER*\n\n"
            f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
            f"User ID: `{sess['user_id'] or 'Chưa cài'}`\n"
            f"Mức cược: `{sess['base_bet']} {sess['asset_type']}`\n\n"
            f"Vui lòng chọn lệnh bên dưới để cấu hình:"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "⚙️ Cài đặt ID & Key", "callback_data": "set_creds"}],
                [{"text": "🚀 Bật Bot", "callback_data": "start_bot"}, {"text": "⏹️ Tắt Bot", "callback_data": "stop_bot"}],
                [{"text": "💰 Xem số dư & Thống kê", "callback_data": "status"}]
            ]
        }
        send_telegram_markup(chat_id, menu_text, keyboard)
        
    elif text.startswith("/login"):
        # Cú pháp: /login <user_id> <secret_key>
        parts = text.split()
        if len(parts) >= 3:
            sess["user_id"] = parts[1]
            sess["secret_key"] = parts[2]
            send_telegram_markup(chat_id, f"✅ Đã lưu User ID: `{sess['user_id']}` thành công!")
        else:
            send_telegram_markup(chat_id, "⚠️ Sai cú pháp! Dùng: `/login <user_id> <secret_key>`")

def handle_telegram_callback(chat_id, data):
    sess = get_session(chat_id)
    
    if data == "set_creds":
        send_telegram_markup(chat_id, "💡 Hãy gửi cú pháp để đăng nhập:\n`/login <user_id> <secret_key>`\n\n*(Ví dụ: `/login 123456 abcxyz123`)*")
    elif data == "start_bot":
        if not sess["user_id"] or not sess["secret_key"]:
            send_telegram_markup(chat_id, "⚠️ Bạn chưa nhập User ID và Secret Key! Hãy bấm Cài đặt ID & Key trước.")
            return
        if sess["running"]:
            send_telegram_markup(chat_id, "⚠️ Bot của bạn đang chạy rồi!")
            return
        
        sess["running"] = True
        Thread(target=run_bot_worker, args=(chat_id,), daemon=True).start()
        send_telegram_markup(chat_id, "🚀 Đã khởi động bot thành công! Bot bắt đầu cược ngầm 24/7.")
        
    elif data == "stop_bot":
        sess["running"] = False
        if sess["ws"]:
            try:
                sess["ws"].close()
            except:
                pass
        send_telegram_markup(chat_id, "⏹️ Đã dừng bot thành công.")
        
    elif data == "status":
        bal = get_balance_for_session(sess)
        wr = (sess["wins"] / sess["total_bets"] * 100) if sess["total_bets"] > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ BOT*\n"
            f"Trạng thái: {'🟢 Đang chạy' if sess['running'] else '🔴 Đang dừng'}\n"
            f"Số dư ví: `{bal:.4f} {sess['asset_type']}`\n"
            f"Tổng cược: `{sess['total_bets']}` trận\n"
            f"Thắng/Thua: `{sess['wins']}` / `{sess['losses']}` (WR: `{wr:.1f}%`)\n"
            f"Tổng lợi nhuận: `{sess['total_profit']:+.4f} {sess['asset_type']}`"
        )
        send_telegram_markup(chat_id, msg)

def get_balance_for_session(sess):
    try:
        session_req = requests.Session()
        headers = {
            "Content-Type": "application/json",
            "user-id": str(sess["user_id"]),
            "user-login": "login_v2",
            "user-secret-key": str(sess["secret_key"]),
            "Accept": "application/json",
            "xb-language": "vi-VN"
        }
        resp = session_req.post(
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
                    
                    # Vào phòng
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
                    bet = float(data.get("bet_amount", 0))
                    is_killed = not (award > bet)
                    killed_room = data.get("killed_room", "?")
                    my_room = data.get("room_id", "?")
                    
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
                        f"Cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
                        f"Lời trận: `{profit:+.4f}`\n"
                        f"Tổng lời: `{sess['total_profit']:+.4f}` (WR: {wr:.1f}%)\n"
                        f"Số dư: `{bal:.4f} {sess['asset_type']}`"
                    )
                    send_telegram_markup(chat_id, msg)
                    sess["has_bet"] = False

            elif msg_type == "notify_heartbeat":
                ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
        except Exception as e:
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

# Thiết lập tự động Webhook với Telegram khi khởi động app
def setup_webhook():
    time.sleep(2)
    # Lấy domain render tự động hoặc dùng domain cố định
    render_external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_external_url:
        webhook_url = f"{render_external_url}/{TELEGRAM_BOT_TOKEN}"
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}")

if __name__ == "__main__":
    Thread(target=setup_webhook, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
