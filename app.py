import os
import json
import time
import random
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask
import telebot
from telebot import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

@app.route('/')
def home():
    return "XWorld Multi-Game Bot 24/7 is running!"

user_data = {}
data_lock = Lock()

ROOM_NAMES = {
    1: "Nhà Kho", 2: "Phòng trò chuyện", 3: "Phòng tài vụ", 4: "Phòng họp",
    5: "Phòng giám sát", 6: "Phòng nhân sự", 7: "Phòng giám đốc", 8: "Văn phòng"
}

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None, "waiting_for_link": None, "waiting_for_bet": None,
                "waiting_for_key": False, "has_valid_key": False, "prompt_msg_id": None,
                "escape": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "base_bet": 1.0, "killer_stats": {i: 0 for i in range(1, 9)}},
                "sprint": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "bet_amount_total": "1", "lose_limit": 3, "rest_rounds": 1, "lose_multiplier": "1.0"}
            }
        return user_data[chat_id]

account_threads = {}

def get_account_state(game_prefix, uid):
    key = f"{game_prefix}_{uid}"
    if key not in account_threads:
        account_threads[key] = {
            "total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0,
            "streak_loss": 0, "current_build": Decimal("1"), "random_stop": Event()
        }
    return account_threads[key]

def verify_key_with_server(key_code, user_id):
    try:
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:5000")
        url = f"{web_url}/api/verify_key?key={key_code}&user_id={user_id}"
        res = requests.get(url, timeout=3)
        return res.json()
    except:
        return {"status": "error", "msg": "Không thể kết nối máy chủ xác thực key!"}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    
    if not cfg["has_valid_key"]:
        cfg["waiting_for_key"] = True
        web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
        msg_text = (
            "🔐 *YÊU CẦU KEY BẢN QUYỀN*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Lấy Key tại Web: {web_url}\n"
            "🔑 Vui lòng nhập mã Key của bạn vào ô chat bên dưới:"
        )
        try:
            sent = bot.send_message(chat_id, msg_text, parse_mode="Markdown")
            cfg["prompt_msg_id"] = sent.message_id
        except:
            pass
        return

    show_main_menu(chat_id, message.message_id, is_new=True)

def show_main_menu(chat_id, message_id, is_new=False):
    msg_text = "🎮 *XWORLD BOT* | Chọn game:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    if is_new:
        try: bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        except: pass
    else:
        try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            try: bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
            except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try: bot.answer_callback_query(call.id, "⚠️ Cần nhập Key bản quyền trước!", show_alert=True)
        except: pass
        return
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)

def show_game_menu(chat_id, message_id, game_type):
    cfg = get_user_config(chat_id)
    g_cfg = cfg[game_type]
    game_name = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
    total_accs = len(g_cfg["accounts"])
    bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    
    msg_text = f"🎮 *{game_name.upper()}*\nTrạng thái: {status_str} | Nick: `{total_accs}` | Cược: `{bet_disp}`"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Thêm Link", callback_data=f"game_{game_type}_setup_link"),
        types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"game_{game_type}_toggle_bot"),
        types.InlineKeyboardButton(f"🪙 Coin ({g_cfg['asset_type']})", callback_data=f"game_{game_type}_toggle_asset"),
        types.InlineKeyboardButton("✏️ Sửa Cược", callback_data=f"game_{game_type}_input_bet"),
        types.InlineKeyboardButton("👥 DS Nick", callback_data=f"game_{game_type}_list"),
        types.InlineKeyboardButton("📊 Thống Kê", callback_data=f"game_{game_type}_status"),
        types.InlineKeyboardButton("🔙 Quay lại", callback_data="back_to_main")
    )
    try: bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        try: bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    try: bot.answer_callback_query(call.id)
    except: pass
    show_main_menu(chat_id, call.message.message_id, is_new=False)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try: bot.answer_callback_query(call.id, "⚠️ Hết hạn Key!", show_alert=True)
        except: pass
        return
    parts = call.data.split("_")
    game_type = parts[1]
    action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    
    markup_back = types.InlineKeyboardMarkup()
    markup_back.add(types.InlineKeyboardButton("🔙 Trở lại Menu", callback_data=f"back_to_game_{game_type}"))

    if action == "setup_link":
        cfg["waiting_for_link"] = game_type
        cfg["waiting_for_bet"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"📥 **Dán link [ {game_name_vi} ] vào ô chat bên dưới:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type
        cfg["waiting_for_link"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**\n*(VD: 1, 5, 10)*", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            try: bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào!", show_alert=True)
            except: pass
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
            try: bot.answer_callback_query(call.id, f"🚀 Đã bật auto!")
            except: pass
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]:
                acc_st = get_account_state(game_type, uid)
                acc_st["random_stop"].set()
            try: bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
            except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        try: bot.answer_callback_query(call.id, f"Đổi sang {g_cfg['asset_type']}")
        except: pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "list":
        if not g_cfg["accounts"]:
            try: bot.answer_callback_query(call.id, "Chưa có nick nào!", show_alert=True)
            except: pass
            return
        msg = f"👥 *DS NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1):
            msg += f"{idx}. `{uid}`\n"
        try: bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except: pass
    elif action == "status":
        try: bot.answer_callback_query(call.id, "🔄 Đã cập nhật thống kê!")
        except: pass
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]
            tot_wins += st["wins"]
            tot_losses += st["losses"]
            tot_profit += st["total_profit"]
        
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0.0
        msg = (
            f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Trạng thái: {'🟢 Chạy' if g_cfg['global_running'] else '🔴 Dừng'}\n"
            f"🎲 Tổng cược: `{tot_bets}`\n"
            f"🏆 Thắng/Thua: `{tot_wins}` / `{tot_losses}`\n"
            f"📈 Tỷ lệ thắng: `{wr:.1f}%`\n"
            f"💵 Tổng Lời/Lỗ: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
        )
        if game_type == "escape":
            k_stats = g_cfg.get("killer_stats", {})
            total_k = sum(k_stats.values())
            msg += f"\n━━━━━━━━━━━━━━━━━━━\n👹 *SÁT THỦ:* (Tổng: `{total_k}` lần)\n"
            for rid in range(1, 9):
                cnt = k_stats.get(rid, 0)
                pct = (cnt / total_k * 100) if total_k > 0 else 0.0
                msg += f"🚪 {ROOM_NAMES.get(rid)}: `{cnt}` (`{pct:.1f}%`)\n"
        markup_stat = types.InlineKeyboardMarkup(row_width=2)
        markup_stat.add(
            types.InlineKeyboardButton("🔄 Cập nhật", callback_data=f"game_{game_type}_status"),
            types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}")
        )
        try: bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_stat, parse_mode="Markdown")
        except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_game_"))
def callback_back_game(call):
    chat_id = call.message.chat.id
    game_type = call.data.split("_")[3]
    try: bot.answer_callback_query(call.id)
    except: pass
    show_game_menu(chat_id, call.message.message_id, game_type)
