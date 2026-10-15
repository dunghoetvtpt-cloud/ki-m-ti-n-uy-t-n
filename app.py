#!/usr/bin/env python3
"""
ESCAPE MASTER AUTO BET BOT - STABLE FINAL + AUTO CONFIG + TELEGRAM NOTIFY
======================================================================
- 🔥 Tự động lưu & đọc cấu hình (USER_ID, SECRET_KEY, CHAT_ID) từ config.json
- 📱 Tự động gửi thông báo kết quả cược về Telegram
- 🎲 Random phòng mượt mà, watchdog ổn định
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
WS_URL = "wss://api.escapemaster.net/escape_master/ws"

# === TELEGRAM CONFIG ===
TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
CHAT_ID = None  # Sẽ được lưu tự động trong config.json

# === WATCHDOG CONFIG ===
WATCHDOG_TIMEOUT = 360  # 360 giây (6 phút)

ws_app = None
ws_connected = False

# === BIẾN HIỂN THỊ TẬP TRUNG ===
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

# === BIẾN WATCHDOG ===
watchdog_last_bet_time = time.time()
watchdog_lock = Lock()

CONFIG_FILE = "config.json"

def load_account():
    """Tự động đọc cấu hình từ file config.json, nếu chưa có thì hỏi và lưu lại"""
    global CHAT_ID
    user_id = None
    secret_key = None
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                user_id = config.get("user_id")
                secret_key = config.get("secret_key")
                CHAT_ID = config.get("chat_id")
                if user_id and secret_key:
                    print(f"{Color.GREEN}✅ Đã tải thông tin tài khoản từ {CONFIG_FILE} thành công!{Color.RESET}")
                    print(f"  📱 USER_ID: {user_id}")
                    print(f"  💬 CHAT_ID: {CHAT_ID}\n")
                    return int(user_id), secret_key
        except Exception as e:
            print(f"{Color.YELLOW}⚠️  Lỗi đọc config.json, vui lòng nhập lại: {e}{Color.RESET}")

    # Nếu chưa có file config hoặc config lỗi, tiến hành hỏi người dùng
    print(f"{Color.YELLOW}{'='*60}{Color.RESET}")
    print(f"{Color.BOLD}  🔐 THIẾT LẬP TÀI KHOẢN LẦN ĐẦU{Color.RESET}")
    print(f"{Color.YELLOW}{'='*60}{Color.RESET}")
    
    while True:
        user_id_input = input(f"  {Color.GREEN}📱 Nhập USER_ID: {Color.RESET}").strip()
        if user_id_input.isdigit():
            user_id = int(user_id_input)
            break
        else:
            print(f"  {Color.RED}❌ USER_ID phải là số!{Color.RESET}")
    
    secret_key = input(f"  {Color.GREEN}🔑 Nhập USER_SECRET_KEY: {Color.RESET}").strip()
    while not secret_key:
        print(f"  {Color.RED}❌ Không được để trống SECRET_KEY!{Color.RESET}")
        secret_key = input(f"  {Color.GREEN}🔑 Nhập USER_SECRET_KEY: {Color.RESET}").strip()

    chat_id_input = input(f"  {Color.GREEN}💬 Nhập Telegram Chat ID (để nhận tin báo kết quả): {Color.RESET}").strip()
    if chat_id_input:
        CHAT_ID = chat_id_input

    # Lưu lại vào file config.json để các lần sau tự động dùng
    config_data = {
        "user_id": user_id,
        "secret_key": secret_key,
        "chat_id": CHAT_ID
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        print(f"{Color.GREEN}💾 Đã lưu cấu hình vào {CONFIG_FILE} thành công!{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}❌ Không thể lưu file config: {e}{Color.RESET}")
        
    print(f"{Color.YELLOW}{'='*60}{Color.RESET}\n")
    return int(user_id), secret_key

USER_ID = None
USER_SECRET_KEY = None

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

# ============ WATCHDOG THREAD ============
def watchdog_loop():
    global g_need_restart
    while True:
        time.sleep(2)
        if g_need_restart:
            continue
        remaining = get_watchdog_remaining()
        with display_lock:
            display_data["watchdog_remaining"] = remaining
            display_data["show_watchdog"] = True
        if remaining <= 0:
            log(f"⏰ WATCHDOG: {WATCHDOG_TIMEOUT}s không đặt cược -> Auto restart WebSocket!", Color.RED)
            restart_websocket()
            time.sleep(5)

# ============ THREAD HIỂN THỊ DUY NHẤT ============
def display_loop():
    global display_data
    last_render = ""
    frame_delay = 1.0 / 60
    while True:
        with display_lock:
            log_msg = display_data.get("log_msg")
            log_color = display_data.get("log_color", Color.RESET)
            room = display_data.get("room", 0)
            countdown = display_data.get("countdown", 0)
            show_timer = display_data.get("show_timer", False)
            random_active = display_data.get("random_active", False)
            watchdog_remaining = display_data.get("watchdog_remaining", WATCHDOG_TIMEOUT)
            show_watchdog = display_data.get("show_watchdog", False)
            if log_msg:
                display_data["log_msg"] = None
        
        if log_msg:
            sys.stdout.write(f"\r\033[K{log_color}{log_msg}{Color.RESET}\n")
            sys.stdout.flush()
            last_render = ""
        
        if random_active or show_timer or show_watchdog:
            timer_part = ""
            if show_timer and countdown > 0:
                bar_len = 25
                filled = int(bar_len * countdown / 60)
                bar = "█" * filled + "░" * (bar_len - filled)
                c = Color.GREEN if countdown > 15 else (Color.YELLOW if countdown > 7 else Color.RED)
                timer_part = f"{c}⏱ [{bar}] {countdown:2d}s{Color.RESET}  "
            
            room_part = f"{Color.MAGENTA}🚪 Phòng: {Color.BOLD}{room}{Color.RESET}" if random_active and room > 0 else ""
            
            watchdog_part = ""
            if show_watchdog and watchdog_remaining > 0:
                w_color = Color.GREEN if watchdog_remaining > 240 else (Color.CYAN if watchdog_remaining > 120 else (Color.YELLOW if watchdog_remaining > 60 else Color.RED))
                watchdog_part = f"  {w_color}🔔 WD: {watchdog_remaining}s{Color.RESET}"
            
            new_render = f"\r\033[K  {timer_part}{room_part}{watchdog_part}     " if (timer_part or room_part or watchdog_part) else f"\r\033[K"
            
            if new_render != last_render:
                sys.stdout.write(new_render)
                sys.stdout.flush()
                last_render = new_render
        
        time.sleep(frame_delay)

def start_random_rooms(bet_room_id, count_down):
    global display_data, random_stop
    random_stop.clear()
    with display_lock:
        display_data["random_active"] = True
        display_data["room"] = 0
    
    log(f"🎰 BẮT ĐẦU RANDOM PHÒNG ({count_down}s)...", Color.MAGENTA)
    
    def api_loop():
        rooms = [1, 2, 3, 4, 5, 6, 7, 8]
        while not random_stop.is_set():
            room_id = random.choice(rooms)
            with display_lock:
                display_data["room"] = room_id
            def call_api():
                try:
                    headers = get_headers()
                    payload = {"asset_type": ASSET_TYPE, "user_id": USER_ID, "room_id": room_id}
                    session.post("https://api.escapemaster.net/escape_game/enter_room", json=payload, headers=headers, timeout=2)
                except:
                    pass
            Thread(target=call_api, daemon=True).start()
            time.sleep(0.2)
            
    Thread(target=api_loop, daemon=True).start()
    
    def auto_stop():
        time.sleep(count_down + 1)
        stop_random_rooms()
    Thread(target=auto_stop, daemon=True).start()

def stop_random_rooms():
    global display_data, random_stop
    random_stop.set()
    with display_lock:
        display_data["random_active"] = False
        display_data["room"] = 0

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
        
        stop_random_rooms()
        stop_timer_display()
        
        with self.lock:
            profit = award - bet
            self.total_bets += 1
            
            print(f"\n{Color.BOLD}{'='*70}{Color.RESET}")
            print(f"{Color.BOLD}  🏁 KẾT QUẢ PHIÊN #{issue_id}{Color.RESET}")
            print(f"  {'─'*50}")
            print(f"  📍 Phòng chết: {Color.RED if is_killed else Color.GREEN}{killed_room}{Color.RESET} | Phòng của bạn: {Color.CYAN}{my_room}{Color.RESET}")
            print(f"  💰 Tiền cược: {Color.YELLOW}{bet:.6f}{Color.RESET} BUILD")
            print(f"  🎁 Tiền thưởng: {Color.GREEN}{award:.6f}{Color.RESET} BUILD")
            
            status_text = ""
            if not is_killed:
                self.wins += 1
                self.consecutive_losses = 0
                self.current_bet = BASE_BET
                self.skips_left = 0
                status_text = "🎉 THẮNG!"
                print(f"  {Color.GREEN}{status_text} +{profit:.6f} BUILD{Color.RESET}")
                print(f"  {Color.GREEN}↩️  Reset cược: {BASE_BET:.2f}{Color.RESET}")
            else:
                self.losses += 1
                self.consecutive_losses += 1
                status_text = "💀 THUA!"
                print(f"  {Color.RED}{status_text} {profit:+.6f} BUILD{Color.RESET}")
                print(f"  {Color.RED}⚠️  Thua liên tiếp: {self.consecutive_losses}/{LOSS_THRESHOLD}{Color.RESET}")
                if self.consecutive_losses >= LOSS_THRESHOLD:
                    self.skips_left = SKIP_ROUNDS
                    print(f"  {Color.YELLOW}⏸️  ĐẠT NGƯỠNG! Nghỉ {SKIP_ROUNDS} trận{Color.RESET}")
                else:
                    self.current_bet *= MULTIPLIER
                    print(f"  {Color.YELLOW}📈 Nhân cược: {bet:.2f} × {MULTIPLIER} = {self.current_bet:.2f}{Color.RESET}")
            
            self.total_profit += profit
            wr = self.wins/self.total_bets*100 if self.total_bets>0 else 0
            print(f"  {'─'*50}")
            print(f"  {Color.BOLD}📊 THỐNG KÊ{Color.RESET}")
            print(f"  Tổng: {self.total_bets} | Thắng: {Color.GREEN}{self.wins}{Color.RESET} | Thua: {Color.RED}{self.losses}{Color.RESET} | WR: {wr:.1f}%")
            print(f"  Lời: {Color.GREEN if self.total_profit>0 else Color.RED}{self.total_profit:+.6f}{Color.RESET} BUILD | Cược HT: {Color.YELLOW}{self.current_bet:.2f}{Color.RESET}")
            print(f"  {'='*70}\n")
            
            # 📱 GỬI THÔNG BÁO VỀ TELEGRAM
            current_balance = get_balance()
            tele_msg = (
                f"*escape master result* - #{issue_id}\n"
                f"Status: {status_text}\n"
                f"Phòng cược: {my_room} | Phòng chết: {killed_room}\n"
                f"Cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
                f"Lợi nhuận trận: `{profit:+.4f}` BUILD\n"
                f"Tổng lời: `{self.total_profit:+.4f}` BUILD (WR: {wr:.1f}%)\n"
                f"Số dư ví: `{current_balance:.4f}` BUILD"
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

def stop_timer_display():
    global display_data
    with display_lock:
        display_data["show_timer"] = False
        display_data["countdown"] = 0

def restart_websocket():
    global ws_app, g_countdown_active, g_need_restart
    g_countdown_active = False
    g_need_restart = True
    stop_random_rooms()
    stop_timer_display()
    log("🔄 Restart WebSocket để bắt phiên mới...", Color.YELLOW)
    if ws_app:
        try:
            ws_app.close()
        except:
            pass

def countdown_timer():
    global display_data, g_countdown_active, g_need_restart
    while True:
        if g_need_restart:
            time.sleep(0.1)
            continue
        if g_countdown_active:
            with display_lock:
                cd = display_data.get("countdown", 0)
                if cd > 0:
                    display_data["countdown"] = cd - 1
                    display_data["show_timer"] = True
            time.sleep(1)
        else:
            with display_lock:
                display_data["show_timer"] = False
            time.sleep(0.1)

def do_bet(issue_id, count_down):
    global g_betting_issue_id, g_has_bet, g_countdown_active, g_current_issue_id, g_need_restart, display_data
    if g_need_restart: return
    if g_current_issue_id is not None and g_current_issue_id != issue_id: return
    
    g_current_issue_id = issue_id
    if g_betting_issue_id == issue_id or g_has_bet: return
    
    g_betting_issue_id = issue_id
    g_has_bet = False
    g_countdown_active = True
    
    with display_lock:
        display_data["countdown"] = count_down
    
    log(f"▶️  PHIÊN MỚI #{issue_id} | Đếm ngược: {count_down}s", Color.CYAN)
    
    if not strategy.should_skip():
        room = random.randint(1, 8)
        amount = strategy.current_bet
        
        log(f"   🎲 Đang cược {amount:.6f} BUILD vào Phòng {room}...", Color.WHITE)
        if enter_room(room):
            time.sleep(0.3)
            if place_bet(room, amount):
                g_has_bet = True
                log(f"   ✅ ĐÃ CƯỢC THÀNH CÔNG! Phòng {room} | {amount:.6f} BUILD", Color.GREEN)
                reset_watchdog()
                log(f"   🔔 Watchdog reset -> {WATCHDOG_TIMEOUT}s", Color.CYAN)
                start_random_rooms(room, count_down)
                
                def check_api_backup():
                    time.sleep(count_down + 5)
                    global g_has_bet, g_betting_issue_id, g_countdown_active, g_need_restart
                    if g_need_restart: return
                    if g_has_bet and g_betting_issue_id == issue_id:
                        log(f"🔍 Check API backup cho phiên #{issue_id}...", Color.YELLOW)
                        data = get_my_joined(1)
                        items = data.get("items", [])
                        for item in items:
                        
