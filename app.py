#!/usr/bin/env python3
"""
ESCAPE MASTER AUTO BET BOT - RENDER 24/7 VERSION
==============================================
- Chạy trực tiếp trên Server không cần hỏi input
- Tự động cược và bắn thông báo về Telegram qua Bot
"""
import websocket
import json
import time
import random
import requests
import sys
import os
from datetime import datetime
from threading import Lock, Thread, Event

class Color:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"

ASSET_TYPE = "BUILD"
BASE_BET = 1.0
LOSS_THRESHOLD = 2
SKIP_ROUNDS = 3
MULTIPLIER = 2.0
WS_URL = "wss://api.escapemaster.net/escape_game/ws"

# === CẤU HÌNH TÀI KHOẢN VÀ TELEGRAM CHO SERVER ===
USER_ID = 123456789          # ⚠️ Thay ID game Escape Master của ông vào đây
USER_SECRET_KEY = "TOKEN_HOẶC_SECRET_KEY_CỦA_ÔNG" # ⚠️ Thay Secret Key của ông vào đây
TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
CHAT_ID = "ID_CHAT_TELEGRAM_CỦA_ÔNG" # ⚠️ Thay ID chat Telegram của ông vào đây (lấy từ @userinfobot)

# === WATCHDOG CONFIG ===
WATCHDOG_TIMEOUT = 360  # 360 giây (6 phút)

ws_app = None
ws_connected = False

display_data = {
    "room": 0,
    "countdown": 0,
    "show_timer": False,
    "random_active": False,
    "log_msg": None,
    "log_color": Color.RESET,
    "watchdog_remaining": WATCHDOG_TIMEOUT,
    "show_watchdog": False,
}
display_lock = Lock()
random_stop = Event()

watchdog_last_bet_time = time.time()
watchdog_lock = Lock()

def send_telegram_notification(message):
    """Gửi tin nhắn thông báo về Telegram"""
    if not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def log(msg, color=Color.RESET):
    global display_data
    with display_lock:
        display_data["log_msg"] = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        display_data["log_color"] = color

def reset_watchdog():
    global watchdog_last_bet_time
    with watchdog_lock:
        watchdog_last_bet_time = time.time()
    with display_lock:
        display_data["watchdog_remaining"] = WATCHDOG_TIMEOUT
        display_data["show_watchdog"] = True

def get_watchdog_remaining():
    with watchdog_lock:
        elapsed = time.time() - watchdog_last_bet_time
        remaining = max(0, WATCHDOG_TIMEOUT - elapsed)
    return int(remaining)

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

def api_call(method, url, **kwargs):
    try:
        resp = session.request(method, url, headers=get_headers(), timeout=15, **kwargs)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}

def get_balance_from_wallet():
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
        "user-id": str(USER_ID),
        "user-secret-key": USER_SECRET_KEY,
        "xb-language": "vi-VN"
    }
    payload = {"user_id": USER_ID, "filter": {"top_n": {"n": 10}}, "refresh": 0}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                result = data.get("data")
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict) and item.get("symbol") == "BUILD":
                            return float(item.get("balance", 0))
                elif isinstance(result, dict):
                    items = result.get("items", [])
                    for item in items:
                        if isinstance(item, dict) and item.get("symbol") == "BUILD":
                            return float(item.get("balance", 0))
    except:
        pass
    return 0.0

def get_balance_old():
    data = api_call("POST", "https://api.escapemaster.net/escape_game/get_user_asset",
                    json={"asset_type": ASSET_TYPE, "user_id": USER_ID})
    if data and data.get("code") == 0:
        return float(data.get("data", {}).get("balance", 0))
    return 0.0

def get_balance():
    bal = get_balance_from_wallet()
    return bal if bal > 0 else get_balance_old()

def enter_room(room_id):
    data = api_call("POST", "https://api.escapemaster.net/escape_game/enter_room",
                    json={"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id})
    return data.get("code") == 0 if data else False

def place_bet(room_id, amount):
    data = api_call("POST", "https://api.escapemaster.net/escape_game/bet",
                    json={"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id, "bet_amount": amount})
    return data.get("code") == 0 if data else False

def get_my_joined(page=1):
    url = "https://api.escapemaster.net/escape_game/my_joined"
    params = {"asset": ASSET_TYPE, "page": page, "page_size": 10}
    try:
        resp = session.get(url, params=params, headers={
            "user-id": str(USER_ID),
            "user-login": "login_v2",
            "user-secret-key": USER_SECRET_KEY,
            "xb-language": "vi-VN",
            "Accept": "application/json"
        }, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {})
    except:
        pass
    return {}

def watchdog_loop():
    global g_need_restart
    while True:
        time.sleep(2)
        if g_need_restart: continue
        remaining = get_watchdog_remaining()
        if remaining <= 0:
            log(f"⏰ WATCHDOG: Restart WebSocket!", Color.RED)
            restart_websocket()
            time.sleep(5)

def display_loop():
    global display_data
    while True:
        with display_lock:
            log_msg = display_data.get("log_msg")
            if log_msg:
                display_data["log_msg"] = None
                print(log_msg)
        time.sleep(0.5)

def start_random_rooms(bet_room_id, count_down):
    global display_data, random_stop
    random_stop.clear()
    def api_loop():
        rooms = [1, 2, 3, 4, 5, 6, 7, 8]
        while not random_stop.is_set():
            room_id = random.choice(rooms)
            try:
                headers = get_headers()
                payload = {"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id}
                session.post("https://api.escapemaster.net/escape_game/enter_room", json=payload, headers=headers, timeout=2)
            except:
                pass
            time.sleep(0.2)
    Thread(target=api_loop, daemon=True).start()
    
    def auto_stop():
        time.sleep(count_down + 1)
        random_stop.set()
    Thread(target=auto_stop, daemon=True).start()

class Strategy:
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
        global g_has_bet, g_betting_issue_id, g_current_issue_id, g_countdown_active, g_need_restart
        random_stop.set()
        
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
            wr = self.wins/self.total_bets*100 if self.total_bets>0 else 0
            
            print(f"🏁 Phiên #{issue_id} | {status_text} | Lời trận: {profit:+.4f} | Tổng lời: {self.total_profit:+.4f}")
            
            # Gửi thông báo về Telegram
            current_balance = get_balance()
            tele_msg = (
                f"*ESCAPE MASTER* - #{issue_id}\n"
                f"Trạng thái: *{status_text}*\n"
                f"Phòng cược: {my_room} | Phòng chết: {killed_room}\n"
                f"Cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
                f"Lợi nhuận: `{profit:+.4f}` BUILD\n"
                f"Tổng lời: `{self.total_profit:+.4f}` (WR: {wr:.1f}%)\n"
                f"Số dư: `{current_balance:.4f}` BUILD"
            )
            Thread(target=send_telegram_notification, args=(tele_msg,), daemon=True).start()
        
        g_has_bet = False
        g_betting_issue_id = None
        g_current_issue_id = None
        g_countdown_active = False
        restart_websocket()
            
    def should_skip(self):
        with self.lock:
            if self.skips_left > 0:
                self.skips_left -= 1
                return True
            return False

strategy = Strategy()
g_betting_issue_id = None
g_current_issue_id = None
g_has_bet = False
g_countdown_active = False
g_need_restart = False

def restart_websocket():
    global ws_app, g_countdown_active, g_need_restart
    g_countdown_active = False
    g_need_restart = True
    random_stop.set()
    if ws_app:
        try: ws_app.close()
        except: pass

def do_bet(issue_id, count_down):
    global g_betting_issue_id, g_has_bet, g_countdown_active, g_current_issue_id, g_need_restart
    if g_need_restart: return
    if g_current_issue_id is not None and g_current_issue_id != issue_id: return
    
    g_current_issue_id = issue_id
    if g_betting_issue_id == issue_id or g_has_bet: return
    
    g_betting_issue_id = issue_id
    g_has_bet = False
    g_countdown_active = True
    
    log(f"▶️ Phiên mới #{issue_id} | Đếm ngược: {count_down}s")
    
    if not strategy.should_skip():
        room = random.randint(1, 8)
        amount = strategy.current_bet
        
        if enter_room(room):
            time.sleep(0.3)
            if place_bet(room, amount):
                g_has_bet = True
                log(f"✅ Cược thành công Phòng {room} | {amount} BUILD")
                reset_watchdog()
                start_random_rooms(room, count_down)
                
                def check_api_backup():
                    time.sleep(count_down + 5)
                    global g_has_bet, g_betting_issue_id, g_countdown_active, g_need_restart
                    if g_need_restart: return
                    if g_has_bet and g_betting_issue_id == issue_id:
                        data = get_my_joined(1)
                        for item in data.get("items", []):
                            if str(item.get("issue_id")) == str(issue_id):
                                award = float(item.get("award_amount", 0))
                                bet_amt = float(item.get("bet_amount", 0))
                                is_killed = not (award > bet_amt)
                                kr = item.get("killed_room_id", "?")
                                mr = item.get("room_id", "?")
                                g_countdown_active = False
                                strategy.process_result(issue_id, is_killed, award, bet_amt, kr, mr)
                                return
                        g_has_bet = False
                        g_betting_issue_id = None
                        g_current_issue_id = None
                        restart_websocket()
                Thread(target=check_api_backup, daemon=True).start()
            else:
                g_betting_issue_id = None
                g_has_bet = False
                g_current_issue_id = None
                restart_websocket()
        else:
            g_betting_issue_id = None
            g_has_bet = False
            g_current_issue_id = None
            restart_websocket()
    else:
        log(f"⏸️ Nghỉ trận này")
        g_betting_issue_id = issue_id
        g_current_issue_id = None
        restart_websocket()

def on_message(ws, message):
    global g_betting_issue_id, g_has_bet, g_countdown_active, g_current_issue_id, g_need_restart
    if g_need_restart: return
    try:
        data = json.loads(message)
        msg_type = data.get("msg_type", "")
        if msg_type == "notify_count_down":
            if g_need_restart: return
            issue_id = data.get("issue_id")
            count_down = data.get("count_down", 0)
            g_countdown_active = True
            if g_current_issue_id is None or g_current_issue_id != issue_id:
                do_bet(issue_id, count_down)
        elif msg_type == "notify_result":
            if g_need_restart: return
            g_countdown_active = False
            random_stop.set()
            issue_id = data.get("issue_id")
            if g_has_bet and issue_id == g_betting_issue_id:
                award = float(data.get("award_amount", 0))
                bet = float(data.get("bet_amount", 0))
                is_killed = not (award > bet)
                killed_room = data.get("killed_room", "?")
                my_room = data.get("room_id", "?")
                strategy.process_result(issue_id, is_killed, award, bet, killed_room, my_room)
        elif msg_type == "notify_heartbeat":
            try: ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
            except: pass
    except: pass

def on_error(ws, error):
    random_stop.set()
    log(f"🔌 WS Error: {error}")

def on_close(ws, close_status_code, close_msg):
    global ws_connected, g_need_restart
    ws_connected = False
    g_need_restart = False
    random_stop.set()
    time.sleep(2)
    run_websocket()

def on_open(ws):
    global g_betting_issue_id, g_has_bet, ws_connected, g_current_issue_id, g_countdown_active, g_need_restart
    g_betting_issue_id = None
    g_has_bet = False
    g_current_issue_id = None
    g_countdown_active = False
    ws_connected = True
    g_need_restart = False
    reset_watchdog()
    random_stop.set()
    
    log("✅ Bot đã kết nối WebSocket thành công!")
    ws.send(json.dumps({
        "msg_type": "handle_enter_game",
        "asset_type": ASSET_TYPE,
        "user_id": USER_ID,
        "user_secret_key": USER_SECRET_KEY
    }))
    balance = get_balance()
    log(f"💰 Số dư ví: {balance:.4f} BUILD")

def run_websocket():
    global ws_app
    ws_app = websocket.WebSocketApp(
        WS_URL,
        header={"Origin": "https://escapemaster.net", "User-Agent": "Mozilla/5.0"},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws_app.run_forever(ping_interval=15, ping_timeout=10)

if __name__ == "__main__":
    print("🚀 Khởi chạy Bot Cược trên Server...")
    Thread(target=display_loop, daemon=True).start()
    Thread(target=watchdog_loop, daemon=True).start()
    while True:
        try:
            run_websocket()
        except Exception as e:
            print(f"Lỗi: {e}, khởi động lại sau 3s...")
            time.sleep(3)
