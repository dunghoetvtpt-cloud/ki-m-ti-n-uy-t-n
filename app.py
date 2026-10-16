import telebot
from telebot import types
import json
import time
import random
import requests
import os
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask

TELEGRAM_BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

@app.route('/')
def home():
    return "XWorld Multi-Game Bot 24/7 is running!"

user_data = {}
data_lock = Lock()

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None,
                "waiting_for_link": None,
                "waiting_for_bet": None,
                "escape": {
                    "accounts": {},
                    "global_running": False,
                    "asset_type": "BUILD",
                    "base_bet": 10.0,
                },
                "sprint": {
                    "accounts": {},
                    "global_running": False,
                    "asset_type": "BUILD",
                    "bet_amount_total": "1",
                    "lose_limit": 3,
                    "rest_rounds": 1,
                    "lose_multiplier": "1.0"
                }
            }
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {
            "total_profit": Decimal("0"),
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "streak_loss": 0,
            "current_build": Decimal("1"),
            "history_winners": [], # Lưu lịch sử các con vô địch gần nhất để phân tích
            "random_stop": Event()
        }
    return account_threads[key]

# --- MENU CHÍNH CHỌN GAME ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    
    msg_text = (
        "🎮 *XWORLD MULTI-GAME BOT*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📌 Vui lòng chọn tựa game bạn muốn auto:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    bot.answer_callback_query(call.id)
    show_game_menu(chat_id, call.message.message_id, game_type)

def show_game_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    g_cfg = cfg[game_type]
    game_name = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    status_str = "🟢 Đang chạy" if g_cfg["global_running"] else "🔴 Đang dừng"
    total_accs = len(g_cfg["accounts"])
    current_bet_display = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    
    msg_text = (
        f"🎮 *GAME: {game_name.upper()}*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Trạng thái:* {status_str}\n"
        f"👥 *Số nick:* `{total_accs}`\n"
        f"🪙 *Coin:* `{g_cfg['asset_type']}` | 💵 *Cược:* `{current_bet_display}` (Mỗi con)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Chọn thao tác bên dưới:*"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link Nick", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🚀 Bật Auto" if not g_cfg["global_running"] else "⏹️ Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Đổi Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Nhập Số Tiền Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton("👥 Danh sách Nick", callback_data=f"game_{game_type}_list"),
        types.InlineKeyboardButton("📊 Thống kê", callback_data=f"game_{game_type}_status"),
        types.InlineKeyboardButton("🔙 Quay lại chọn Game", callback_data="back_to_main")
    )
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    bot.answer_callback_query(call.id)
    
    msg_text = (
        "🎮 *XWORLD MULTI-GAME BOT*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📌 Vui lòng chọn tựa game bạn muốn auto:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    try:
        bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    parts = call.data.split("_")
    game_type = parts[1]
    action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    
    if action == "setup_link":
        cfg["waiting_for_link"] = game_type
        cfg["waiting_for_bet"] = None
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"📥 **Vui lòng dán link game [ {game_name_vi} ] vào đây!**")
        
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type
        cfg["waiting_for_link"] = None
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"✏️ **Vui lòng nhập số tiền cược cố định cho [ {game_name_vi} ] (Mỗi con):**\n*(Ví dụ: 1, 5, 10.5)*")
        
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào cho game này!", show_alert=True)
            return
        if not g_cfg["global_running"]:
            g_cfg["global_running"] = True
            for uid, skey in g_cfg["accounts"].items():
                st = get_account_state(game_type, uid)
                st["random_stop"].clear()
                if game_type == "escape":
                    Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                else:
                    Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
            bot.answer_callback_query(call.id, f"🚀 Đã bật auto {game_name_vi} cho {len(g_cfg['accounts'])} nick!")
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]:
                acc_st = get_account_state(game_type, uid)
                acc_st["random_stop"].set()
            bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
        show_game_menu(chat_id, call.message.message_id, game_type)
        
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(call.id, f"Đổi sang {g_cfg['asset_type']}")
        show_game_menu(chat_id, call.message.message_id, game_type)
        
    elif action == "list":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "Chưa có nick nào!", show_alert=True)
            return
        msg = f"👥 *DANH SÁCH NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1):
            msg += f"{idx}. `{uid}`\n"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
        
    elif action == "status":
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]
            tot_wins += st["wins"]
            tot_losses += st["losses"]
            tot_profit += st["total_profit"]
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0
        msg = (
            f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n"
            f"Trạng thái: {'🟢 Đang chạy' if g_cfg['global_running'] else '🔴 Đang dừng'}\n"
            f"Tổng ván: `{tot_bets}` | Thắng/Thua: `{tot_wins}`/`{tot_losses}` ({wr:.1f}%)\n"
            f"Tổng lời: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        if "userId=" in text and "secretKey=" in text:
            try:
                parsed_url = urlparse(text)
                query_params = parse_qs(parsed_url.query)
                uid_str = query_params.get("userId", [None])[0]
                skey = query_params.get("secretKey", [None])[0]
                if uid_str and skey:
                    uid = int(uid_str)
                    cfg[game_target_link]["accounts"][uid] = skey
                    cfg["waiting_for_link"] = None
                    g_cfg = cfg[game_target_link]
                    if g_cfg["global_running"]:
                        if game_target_link == "escape":
                            Thread(target=run_escape_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                        else:
                            Thread(target=run_sprint_bot_engine, args=(chat_id, uid, skey), daemon=True).start()
                    bot.reply_to(message, f"✅ **Đã thêm nick thành công!**\nGõ `/start` để quay lại quản lý.")
                    return
            except:
                pass
        bot.reply_to(message, "⚠️ Link không hợp lệ! Hãy dán đúng link game XWorld.")
        return

    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try:
            val = float(text)
            if val <= 0:
                raise ValueError()
            
            g_cfg = cfg[game_target_bet]
            if game_target_bet == "sprint":
                g_cfg["bet_amount_total"] = str(val)
                for uid in g_cfg["accounts"]:
                    st = get_account_state("sprint", uid)
                    st["current_build"] = Decimal(str(val))
            else:
                g_cfg["base_bet"] = val
                
            cfg["waiting_for_bet"] = None
            bot.reply_to(message, f"✅ **Đã cập nhật mức cược cố định:** `{val}` (Mỗi con)\nGõ `/start` để mở lại menu.")
            return
        except ValueError:
            bot.reply_to(message, "⚠️ Số tiền không hợp lệ! Vui lòng nhập một số dương (ví dụ: `1` hoặc `5.5`).")
            return

    if not text.startswith("/"):
        bot.reply_to(message, "💡 Gõ `/start` để mở bảng chọn game.")

# ==========================================
# ENGINE 1: VUA THOÁT HIỂM
# ==========================================
def run_escape_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["escape"]
    acc_st = get_account_state("escape", uid)
    
    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            url = "https://api.escapemaster.net/escape_game/my_joined"
            resp = requests.get(url, params={"asset": cfg["asset_type"], "page": 1, "page_size": 10},
                                headers={"user-id": str(uid), "user-secret-key": skey}, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                if items:
                    latest_issue = str(items[0].get("issue_id"))
                    if acc_st.get("current_issue") != latest_issue:
                        acc_st["current_issue"] = latest_issue
                        acc_st["total_bets"] += 1
                        room = random.randint(1, 8)
                        
                        requests.post("https://api.escapemaster.net/escape_game/enter_room",
                                      json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room},
                                      headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
                        time.sleep(0.1)
                        requests.post("https://api.escapemaster.net/escape_game/bet",
                                      json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room, "bet_amount": cfg["base_bet"]},
                                      headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
        except:
            pass
        time.sleep(3)

# ==========================================
# ENGINE 2: ĐUA TỐC ĐỘ (CÓ PHÂN TÍCH LỊCH SỬ VÀ CỐ ĐỊNH VỐN)
# ==========================================
def run_sprint_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["sprint"]
    acc_st = get_account_state("sprint", uid)
    base_api = "https://api.sprintrun.win"
    
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://sprintrun.win",
        "referer": "https://sprintrun.win/",
        "user-agent": "Mozilla/5.0",
        "user-id": str(uid),
        "user-login": "login_v2",
        "user-secret-key": skey
    }

    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            base_build = Decimal(str(cfg["bet_amount_total"]))
            acc_st["current_build"] = base_build

            r = requests.get(f"{base_api}/sprint/home?asset={cfg['asset_type']}", headers=headers, timeout=10)
            if r.status_code != 200:
                time.sleep(3)
                continue
            
            res_data = r.json().get("data", {})
            issue_id = res_data.get("issue_id")
            expire = res_data.get("expire_seconds", 50)
            athletes = res_data.get("athlete_list", [])

            if len(athletes) < 3:
                time.sleep(3)
                continue

            # --- CHIẾN THUẬT PHÂN TÍCH LỊCH SỬ ---
            # Ưu tiên chọn các con có xu hướng ra hoặc pha trộn dựa trên lịch sử gần đây (history_winners)
            history = acc_st["history_winners"]
            if history:
                # Sắp xếp các vận động viên ưu tiên con nào xuất hiện ít trong lịch sử gần đây (bắt nhịp cầu lót)
                # hoặc kết hợp ngẫu nhiên có lọc lịch sử để tối ưu tỉ lệ thắng
                athletes_sorted = sorted(athletes, key=lambda a: history.count(a["id"]))
                # Lấy một nửa từ nhóm ít ra và một nửa ngẫu nhiên để tạo sự cân bằng thông minh
                chosen_athletes = random.sample(athletes_sorted[:4], min(3, len(athletes_sorted)))
            else:
                # Nếu chưa có lịch sử thì xáo trộn ngẫu nhiên bình thường
                random.shuffle(athletes)
                chosen_athletes = random.sample(athletes, 3)

            chosen = [a["id"] for a in chosen_athletes]

            each_bet = acc_st["current_build"].quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            total_bet_amount = each_bet * Decimal(len(chosen))

            for aid in chosen:
                payload = {
                    "issue_id": issue_id,
                    "bet_group": "winner",
                    "asset_type": cfg["asset_type"],
                    "athlete_id": aid,
                    "bet_amount": float(each_bet)
                }
                requests.post(f"{base_api}/sprint/bet", json=payload, headers=headers, timeout=10)
                time.sleep(0.2)

            acc_st["total_bets"] += 1

            wait_time = int(expire) if isinstance(expire, (int, float)) else 50
            for _ in range(wait_time):
                if not cfg["global_running"] or acc_st["random_stop"].is_set(): break
                time.sleep(1)

            winner = None
            for _ in range(30):
                res_r = requests.get(f"{base_api}/sprint/issue_result?issue={issue_id}&asset={cfg['asset_type']}", headers=headers, timeout=10)
                if res_r.status_code == 200:
                    rank = res_r.json().get("data", {}).get("athlete_rank", [])
                    if rank:
                        winner = rank[0]
                        # Cập nhật lịch sử quán quân (giữ tối đa 10 ván gần nhất)
                        acc_st["history_winners"].append(winner)
                        if len(acc_st["history_winners"]) > 10:
                            acc_st["history_winners"].pop(0)
                        break
                time.sleep(1)

            if winner in chosen:
                profit = (each_bet * 5) - total_bet_amount
                acc_st["total_profit"] += profit
                acc_st["wins"] += 1
            else:
                acc_st["total_profit"] -= total_bet_amount
                acc_st["losses"] += 1

        except:
            pass
        time.sleep(2)

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
