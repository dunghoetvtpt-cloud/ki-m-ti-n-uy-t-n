#!/usr/bin/env python3
"""
ESCAPE MASTER AUTO BET BOT - WEB DASHBOARD FOR RENDER
=====================================================
- Giao diện Web Dashboard điều khiển trực tiếp trên trình duyệt
- Console Real-time hiển thị nhật ký cược
- WebSocket Worker chạy ngầm 24/7
"""

import websocket
import json
import time
import random
import requests
import os
from datetime import datetime
from threading import Thread, Lock
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Global State & Locks
state_lock = Lock()
bot_running = False
log_messages = []

# Cấu hình bot mặc định
config = {
    "user_id": "",
    "user_secret_key": "",
    "telegram_token": "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE",
    "chat_id": "",
    "asset_type": "BUILD",
    "base_bet": 1.0,
    "loss_threshold": 2,
    "skip_rounds": 3,
    "multiplier": 2.0
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36",
    "Origin": "https://escapemaster.net",
    "Accept": "application/json",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": "https://escapemaster.net/",
})

def add_log(msg):
    global log_messages
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    with state_lock:
        log_messages.append(formatted_msg)
        if len(log_messages) > 100:
            log_messages.pop(0)

def send_telegram(message):
    token = config.get("telegram_token")
    chat_id = config.get("chat_id")
    if not chat_id or not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def get_headers():
    return {
        "Content-Type": "application/json",
        "user-id": str(config.get("user_id")),
        "user-login": "login_v2",
        "user-secret-key": str(config.get("user_secret_key")),
        "Accept": "application/json",
        "xb-language": "vi-VN"
    }

def get_balance():
    try:
        resp = session.post(
            "https://api.escapemaster.net/escape_game/get_user_asset",
            json={"asset_type": config.get("asset_type"), "user_id": int(config.get("user_id"))},
            headers=get_headers(),
            timeout=10
        )
        data = resp.json()
        if data and data.get("code") == 0:
            return float(data.get("data", {}).get("balance", 0))
    except:
        pass
    return 0.0

def enter_room(room_id):
    try:
        resp = session.post(
            "https://api.escapemaster.net/escape_game/enter_room",
            json={"asset_type": config.get("asset_type"), "user_id": int(config.get("user_id")), "room_id": room_id},
            headers=get_headers(),
            timeout=5
        )
        return resp.json().get("code") == 0
    except:
        return False

def place_bet(room_id, amount):
    try:
        resp = session.post(
            "https://api.escapemaster.net/escape_game/bet",
            json={"asset_type": config.get("asset_type"), "user_id": int(config.get("user_id")), "room_id": room_id, "bet_amount": amount},
            headers=get_headers(),
            timeout=5
        )
        return resp.json().get("code") == 0
    except:
        return False

class BotEngine:
    def __init__(self):
        self.current_bet = 1.0
        self.consecutive_losses = 0
        self.total_profit = 0.0
        self.total_bets = 0
        self.wins = 0
        self.losses = 0
        self.skips_left = 0
        self.current_issue = None
        self.has_bet = False
        self.ws = None

    def reset(self):
        self.current_bet = float(config.get("base_bet", 1.0))
        self.consecutive_losses = 0
        self.total_profit = 0.0
        self.total_bets = 0
        self.wins = 0
        self.losses = 0
        self.skips_left = 0
        self.current_issue = None
        self.has_bet = False

    def process_result(self, issue_id, is_killed, award, bet, killed_room, my_room):
        profit = award - bet
        self.total_bets += 1
        status_text = "THẮNG 🟢" if not is_killed else "THUA 🔴"
        
        if not is_killed:
            self.wins += 1
            self.consecutive_losses = 0
            self.current_bet = float(config.get("base_bet", 1.0))
            self.skips_left = 0
        else:
            self.losses += 1
            self.consecutive_losses += 1
            if self.consecutive_losses >= int(config.get("loss_threshold", 2)):
                self.skips_left = int(config.get("skip_rounds", 3))
            else:
                self.current_bet *= float(config.get("multiplier", 2.0))
        
        self.total_profit += profit
        wr = (self.wins / self.total_bets * 100) if self.total_bets > 0 else 0
        
        add_log(f"🏁 Phiên #{issue_id} | {status_text} | Lời: {profit:+.4f} | Tổng lời: {self.total_profit:+.4f}")
        
        balance = get_balance()
        msg = (
            f"*ESCAPE MASTER CLOUD* - #{issue_id}\n"
            f"Trạng thái: *{status_text}*\n"
            f"Phòng chọn: `{my_room}` | Phòng bẫy: `{killed_room}`\n"
            f"Tiền cược: `{bet:.4f}` | Thưởng: `{award:.4f}`\n"
            f"Lợi nhuận: `{profit:+.4f}` {config.get('asset_type')}\n"
            f"Tổng lời: `{self.total_profit:+.4f}` (WR: {wr:.1f}%)\n"
            f"Số dư ví: `{balance:.4f}` {config.get('asset_type')}"
        )
        Thread(target=send_telegram, args=(msg,), daemon=True).start()

    def should_skip(self):
        if self.skips_left > 0:
            self.skips_left -= 1
            return True
        return False

bot_engine = BotEngine()

def on_message(ws, message):
    global bot_running
    if not bot_running:
        ws.close()
        return

    try:
        data = json.loads(message)
        msg_type = data.get("msg_type", "")
        
        if msg_type == "notify_count_down":
            issue_id = data.get("issue_id")
            count_down = data.get("count_down", 0)
            
            if bot_engine.current_issue != issue_id:
                bot_engine.current_issue = issue_id
                bot_engine.has_bet = False
                
                add_log(f"▶️ Phiên #{issue_id} bắt đầu | Đếm ngược: {count_down}s")
                
                if not bot_engine.should_skip():
                    room = random.randint(1, 8)
                    amount = bot_engine.current_bet
                    
                    if enter_room(room):
                        time.sleep(0.2)
                        if place_bet(room, amount):
                            bot_engine.has_bet = True
                            add_log(f"✅ Cược thành công: {amount} {config.get('asset_type')} vào Phòng [{room}]")
                        else:
                            add_log(f"❌ Đặt cược thất bại Phòng [{room}]")
                    else:
                        add_log(f"❌ Không thể vào Phòng [{room}]")
                else:
                    add_log(f"⏸️ Bỏ qua phiên này theo cài đặt chiến thuật.")

        elif msg_type == "notify_result":
            issue_id = data.get("issue_id")
            if bot_engine.has_bet and issue_id == bot_engine.current_issue:
                award = float(data.get("award_amount", 0))
                bet = float(data.get("bet_amount", 0))
                is_killed = not (award > bet)
                killed_room = data.get("killed_room", "?")
                my_room = data.get("room_id", "?")
                
                bot_engine.process_result(issue_id, is_killed, award, bet, killed_room, my_room)
                bot_engine.has_bet = False

        elif msg_type == "notify_heartbeat":
            ws.send(json.dumps({"msg_type": "heartbeat_ack"}))
    except Exception as e:
        add_log(f"⚠️ Lỗi tin nhắn WebSocket: {e}")

def on_error(ws, error):
    add_log(f"❌ WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    add_log("🔌 Kết nối WebSocket đã đóng.")

def on_open(ws):
    add_log("🚀 Kết nối WebSocket thành công!")
    ws.send(json.dumps({
        "msg_type": "handle_enter_game",
        "asset_type": config.get("asset_type"),
        "user_id": int(config.get("user_id")),
        "user_secret_key": config.get("user_secret_key")
    }))
    bal = get_balance()
    add_log(f"💰 Số dư tài khoản: {bal:.4f} {config.get('asset_type')}")
    send_telegram(f"🚀 *Bot Cloud XWorld đã khởi động!*\n💰 Số dư: `{bal:.4f}` {config.get('asset_type')}")

def worker_thread():
    global bot_running
    add_log("⚙️ Đang kết nối tới server game...")
    bot_engine.reset()
    
    while bot_running:
        try:
            ws_url = "wss://api.escapemaster.net/escape_game/ws"
            ws = websocket.WebSocketApp(
                ws_url,
                header={"Origin": "https://escapemaster.net", "User-Agent": "Mozilla/5.0"},
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            bot_engine.ws = ws
            ws.run_forever(ping_interval=15, ping_timeout=10)
        except Exception as e:
            add_log(f"⚠️ Thử kết nối lại sau 3s: {e}")
        time.sleep(3)

# HTML Web Dashboard Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XWorld Escape Master Cloud Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card { background-color: #1e1e1e; border: 1px solid #333; border-radius: 12px; margin-bottom: 20px; }
        .form-control, .form-select { background-color: #2b2b2b; border: 1px solid #444; color: #fff; }
        .form-control:focus, .form-select:focus { background-color: #333; color: #fff; border-color: #0d6efd; box-shadow: none; }
        #console { background-color: #000; color: #00ff66; font-family: monospace; height: 350px; overflow-y: auto; padding: 15px; border-radius: 8px; border: 1px solid #333; }
        .badge-status { font-size: 1rem; padding: 8px 16px; border-radius: 20px; }
    </style>
</head>
<body>
<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>🎮 XWorld Escape Master Cloud Bot</h2>
        <span id="statusBadge" class="badge bg-secondary badge-status">Đang dừng</span>
    </div>

    <div class="row">
        <!-- Panel Cấu Hình -->
        <div class="col-lg-5">
            <div class="card p-3">
                <h5 class="card-title mb-3 text-primary">⚙️ Cấu hình Tài khoản & Chiến thuật</h5>
                <form id="configForm">
                    <div class="mb-2">
                        <label class="form-label">User ID</label>
                        <input type="number" class="form-control" name="user_id" id="user_id" required placeholder="Nhập User ID">
                    </div>
                    <div class="mb-2">
                        <label class="form-label">User Secret Key</label>
                        <input type="text" class="form-control" name="user_secret_key" id="user_secret_key" required placeholder="Nhập Secret Key">
                    </div>
                    <div class="mb-2">
                        <label class="form-label">Telegram Chat ID</label>
                        <input type="text" class="form-control" name="chat_id" id="chat_id" placeholder="Nhập Telegram Chat ID">
                    </div>
                    <div class="row g-2 mb-2">
                        <div class="col-6">
                            <label class="form-label">Loại tài sản</label>
                            <select class="form-select" name="asset_type" id="asset_type">
                                <option value="BUILD">BUILD</option>
                                <option value="USDT">USDT</option>
                            </select>
                        </div>
                        <div class="col-6">
                            <label class="form-label">Mức cược cơ bản</label>
                            <input type="number" step="0.1" class="form-control" name="base_bet" id="base_bet" value="1.0">
                        </div>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-4">
                            <label class="form-label">Thua nghỉ</label>
                            <input type="number" class="form-control" name="loss_threshold" id="loss_threshold" value="2">
                        </div>
                        <div class="col-4">
                            <label class="form-label">Số trận nghỉ</label>
                            <input type="number" class="form-control" name="skip_rounds" id="skip_rounds" value="3">
                        </div>
                        <div class="col-4">
                            <label class="form-label">Hệ số nhân</label>
                            <input type="number" step="0.1" class="form-control" name="multiplier" id="multiplier" value="2.0">
                        </div>
                    </div>
                    <div class="d-grid gap-2">
                        <button type="button" id="startBtn" onclick="startBot()" class="btn btn-success fw-bold">▶️ Bắt đầu Chạy Bot</button>
                        <button type="button" id="stopBtn" onclick="stopBot()" class="btn btn-danger fw-bold" disabled>⏹️ Dừng Bot</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- Live Console Terminal -->
        <div class="col-lg-7">
            <div class="card p-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5 class="card-title text-success mb-0">📟 Live Terminal Log</h5>
                    <button class="btn btn-sm btn-outline-light" onclick="clearConsole()">Xóa màn hình</button>
                </div>
                <div id="console">--- Vui lòng nhập cấu hình và bấm Bắt đầu ---</div>
            </div>
        </div>
    </div>
</div>

<script>
    function updateLogs() {
        fetch('/get_logs')
            .then(res => res.json())
            .then(data => {
                const consoleDiv = document.getElementById('console');
                consoleDiv.innerHTML = data.logs.join('<br>');
                consoleDiv.scrollTop = consoleDiv.scrollHeight;

                const badge = document.getElementById('statusBadge');
                const startBtn = document.getElementById('startBtn');
                const stopBtn = document.getElementById('stopBtn');

                if (data.running) {
                    badge.className = 'badge bg-success badge-status';
                    badge.innerText = 'Đang hoạt động 24/7';
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                } else {
                    badge.className = 'badge bg-secondary badge-status';
                    badge.innerText = 'Đang dừng';
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                }
            });
    }

    function startBot() {
        const formData = new FormData(document.getElementById('configForm'));
        fetch('/start', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => alert(data.message));
    }

    function stopBot() {
        fetch('/stop', { method: 'POST' })
            .then(res => res.json())
            .then(data => alert(data.message));
    }

    function clearConsole() {
        fetch('/clear_logs', { method: 'POST' });
    }

    setInterval(updateLogs, 1500);
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/get_logs')
def get_logs():
    with state_lock:
        return jsonify({"logs": log_messages, "running": bot_running})

@app.route('/start', methods=['POST'])
def start_bot():
    global bot_running, config
    if bot_running:
        return jsonify({"message": "Bot đang chạy rồi!"})
    
    config["user_id"] = request.form.get("user_id", "").strip()
    config["user_secret_key"] = request.form.get("user_secret_key", "").strip()
    config["chat_id"] = request.form.get("chat_id", "").strip()
    config["asset_type"] = request.form.get("asset_type", "BUILD")
    config["base_bet"] = float(request.form.get("base_bet", 1.0))
    config["loss_threshold"] = int(request.form.get("loss_threshold", 2))
    config["skip_rounds"] = int(request.form.get("skip_rounds", 3))
    config["multiplier"] = float(request.form.get("multiplier", 2.0))

    if not config["user_id"] or not config["user_secret_key"]:
        return jsonify({"message": "Vui lòng điền đầy đủ User ID và Secret Key!"})

    bot_running = True
    add_log("▶️ Khởi động Bot Worker...")
    Thread(target=worker_thread, daemon=True).start()
    return jsonify({"message": "Đã bắt đầu chạy bot!"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    global bot_running
    bot_running = False
    add_log("⏹️ Đang dừng Bot...")
    return jsonify({"message": "Đã gửi lệnh dừng bot!"})

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    global log_messages
    with state_lock:
        log_messages = []
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
