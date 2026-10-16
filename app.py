#!/usr/bin/env python3
"""
ESCAPE MASTER AUTO BET BOT - RENDER 24/7 CLOUD WORKER
=====================================================
- Flask giữ cổng HTTP cho Render không bị sleep/đóng
- WebSocket ngầm tự động cược và bắn thông báo Telegram 24/7
"""
import websocket
import json
import time
import random
import requests
import os
from threading import Thread, Lock
from flask import Flask

# --- CẤU HÌNH WEB SERVER CHO RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Escape Master Bot is running 24/7 on Render!"

# --- CẤU HÌNH TÀI KHOẢN VÀ BOT ---
ASSET_TYPE = "BUILD"
BASE_BET = 1.0
LOSS_THRESHOLD = 2
SKIP_ROUNDS = 3
MULTIPLIER = 2.0
WS_URL = "wss://api.escapemaster.net/escape_game/ws"

# ⚠️ Thay thông tin của ông vào đây
USER_ID = 123456789                  
USER_SECRET_KEY = "SECRET_KEY_CỦA_ÔNG" 
TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
CHAT_ID = "CHAT_ID_CỦA_ÔNG"            

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36",
    "Origin": "https://escapemaster.net",
    "Accept": "application/json",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": "https://escapemaster.net/",
})

def get_headers():
    return {
        "Content-Type": "application/json",
        "user-id": str(USER_ID),
        "user-login": "login_v2",
        "user-secret-key": USER_SECRET_KEY,
        "Accept": "application/json",
        "xb-language": "vi-VN"
    }

def send_telegram(message):
    if not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def get_balance():
    try:
        resp = session.post("https://api.escapemaster.net/escape_game/get_user_asset",
                            json={"asset_type": ASSET_TYPE, "user_id": USER_ID}, headers=get_headers(), timeout=10)
        data = resp.json()
        if data and data.get("code") == 0:
            return float(data.get("data", {}).get("balance", 0))
    except:
        pass
    return 0.0

def enter_room(room_id):
    try:
        resp = session.post("https://api.escapemaster.net/escape_game/enter_room",
                            json={"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id}, headers=get_headers(), timeout=5)
        return resp.json().get("code") == 0
    except:
        return False

def place_bet(room_id, amount):
    try:
        resp = session.post("https://api.escapemaster.net/escape_game/bet",
                            json={"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id, "bet_amount": amount}, headers=get_headers(), timeout=5)
        return resp.json().get("code") == 0
    except:
        return False

class BotStrategy:
    def __init__(self):
        self.current_bet = BASE_BET
        self.consecutive_losses = 0
        self.total_profit = 0.0
        self.total_bets = 0
        self.wins = 0
        self.losses = 0
        self.skips_left = 0
        self.lock = Lock()

    def process_result(self, issue_id, is_killed, award, bet, killed_room, my_room):
        with self.lock:
            profit = award - bet
            self.total_bets += 1
            status_text = "THẮNG" if not is_killed else "THUA"
            
            if not is_killed:
                self.wins += 1
                self.consecutive_losses = 0
                self.current_bet = BASE_BET
                self.skips_left = 0
            else:
                self.losses += 1
                self.consecutive_losses += 1
                if self.consecutive_losses >= LOSS_THRESHOLD:
                    self.skips_left = SKIP_ROUNDS
                else:
                    self.current_bet *= MULTIPLIER
            
            self.total_profit += profit
            wr = self.wins / self.total_bets * 100 if self.total_bets > 0 else 0
            
            print(f"🏁 Phiên #{issue_id} | {status_text} | Lời: {profit:+.4f} | Tổng: {self.total_profit:+.4f}")
            
            # Bắn tin nhắn về Telegram
            balance = get_balance()
            msg = (
                f"*ESCAPE MASTER CLOUD* - #{issue_id}\n"
                f"Trạng thái: *{status_text}*\n"
                f"Phòng cược: {my_room} | Phòng chết: {killed_room}\n"
                f"Cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
                f"Lợi nhuận trận: `{profit:+.4f}` BUILD\n"
                f"Tổng lời: `{self.total_profit:+.4f}` (WR: {wr:.1f}%)\n"
                f"Số dư ví: `{balance:.4f}` BUILD"
            )
            Thread(target=send_telegram, args=(msg,), daemon=True).start()

    def should_skip(self):
        with self.lock:
            if self.skips_left > 0:
                self.skips_left -= 1
                return True
            return False

bot_strategy = BotStrategy()
current_betting_issue = None
has_bet_current = False

def on_message(ws, message):
    global current_betting_issue, has_bet_current
    try:
        data = json.loads(message)
        msg_type = data.get("msg_type", "")
        
        if msg_type == "notify_count_down":
            issue_id = data.get("issue_id")
            count_down = data.get("count_down", 0)
            
            if current_betting_issue != issue_id:
                current_betting_issue = issue_id
                has_bet_current = False
                
                print(f"▶️ Phiên mới #{issue_id} | Đếm ngược: {count_down}s")
                
                if not bot_strategy.should_skip():
                    room = random.randint(1, 8)
                    amount = bot_strategy.current_bet
                    
                    if enter_room(room):
                        time.sleep(0.3)
                        if place_bet(room, amount):
                            has_bet_current = True
                            print(f"✅ Đã cược {amount} BUILD vào phòng {room}")
                        else:
                            print(f"❌ Đặt cược thất bại phòng {room}")
                    else:
                        print(f"❌ Không vào được phòng {room}")
                else:
                    print(f"⏸️ Bỏ qua trận này theo chiến thuật.")

        elif msg_type == "notify_result":
            issue_id = data.get("issue_id")
            if has_bet_current and issue_id == current_betting_issue:
                award = float(data.get("award_amount", 0))
                bet = float(data.get("bet_amount", 0))
                is_killed = not (award > bet)
                killed_room = data.get("killed_room", "?")
                my_room = data.get("room_id", "?")
                
                bot_strategy.process_result(issue_id, is_killed, award, bet, killed_room, my_room)
                has_bet_current = False

        elif msg_type == "notify_heartbeat":
            ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
    except Exception as e:
        print(f"Lỗi xử lý message: {e}")

def on_error(ws, error):
    print(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket đóng, kết nối lại sau 3s...")
    time.sleep(3)
    run_bot_worker()

def on_open(ws):
    print("✅ Đã kết nối WebSocket Escape Master thành công trên Render!")
    ws.send(json.dumps({
        "msg_type": "handle_enter_game",
        "asset_type": ASSET_TYPE,
        "user_id": USER_ID,
        "user_secret_key": USER_SECRET_KEY
    }))
    balance = get_balance()
    print(f"💰 Số dư hiện tại: {balance:.4f} BUILD")
    send_telegram(f"🚀 *Bot Cloud đã khởi động thành công!*\n💰 Số dư ví: `{balance:.4f}` BUILD")

def run_bot_worker():
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                header={"Origin": "https://escapemaster.net", "User-Agent": "Mozilla/5.0"},
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=15, ping_timeout=10)
        except Exception as e:
            print(f"Lỗi kết nối worker: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Khởi chạy bot ngầm ở luồng riêng
    Thread(target=run_bot_worker, daemon=True).start()
    
    # Khởi chạy Flask Web Server ở luồng chính để giữ server Render sống 24/7
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
