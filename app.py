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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

app = Flask(__name__)

@app.route('/')
def home():
    return "XWorld Multi-Game Bot 24/7 is running!"

user_data = {}
data_lock = Lock()

ROOM_NAMES = {
    1: "Nhà Kho",
    2: "Phòng trò chuyện",
    3: "Phòng tài vụ",
    4: "Phòng họp",
    5: "Phòng giám sát",
    6: "Phòng nhân sự",
    7: "Phòng giám đốc",
    8: "Văn phòng"
}

def get_user_config(chat_id):
    with data_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {
                "active_game": None,
                "waiting_for_link": None,
                "waiting_for_bet": None,
                "prompt_msg_id": None,
                "escape": {
                    "accounts": {},
                    "global_running": False,
                    "asset_type": "BUILD",
                    "base_bet": 1.0,
                    "killer_stats": {i: 0 for i in range(1, 9)}
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
            "random_stop": Event()
        }
    return account_threads[key]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    
    msg_text = "🎮 *XWORLD BOT* | Chọn game:"
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
    status_str = "🟢 Chạy" if g_cfg["global_running"] else "🔴 Dừng"
    total_accs = len(g_cfg["accounts"])
    bet_disp = g_cfg.get('bet_amount_total') if game_type == 'sprint' else g_cfg.get('base_bet')
    
    msg_text = (
        f"🎮 *{game_name.upper()}*\n"
        f"Trạng thái: {status_str} | Nick: `{total_accs}` | Cược: `{bet_disp}`"
    )
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
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    bot.answer_callback_query(call.id)
    
    msg_text = "🎮 *XWORLD BOT* | Chọn game:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="select_game_escape"),
        types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="select_game_sprint")
    )
    try:
        bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception:
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
    
    markup_back = types.InlineKeyboardMarkup()
    markup_back.add(types.InlineKeyboardButton("🔙 Trở lại Menu", callback_data=f"back_to_game_{game_type}"))

    if action == "setup_link":
        cfg["waiting_for_link"] = game_type
        cfg["waiting_for_bet"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        bot.answer_callback_query(call.id)
        msg_text = f"📥 **Dán link [ {game_name_vi} ] vào ô chat bên dưới:**"
        bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type
        cfg["waiting_for_link"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        bot.answer_callback_query(call.id)
        msg_text = f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**\n*(VD: 1, 5, 10)*"
        bot.edit_message_text(msg_text, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào!", show_alert=True)
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
            bot.answer_callback_query(call.id, f"🚀 Đã bật auto!")
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
        msg = f"👥 *DS NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1):
            msg += f"{idx}. `{uid}`\n"
        bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        
    elif action == "status":
        bot.answer_callback_query(call.id, "🔄 Đã cập nhật thống kê!")
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
            total_killer_appearances = sum(k_stats.values())
            
            msg += "\n━━━━━━━━━━━━━━━━━━━\n"
            msg += f"👹 *SÁT THỦ:* (Tổng: `{total_killer_appearances}` lần)\n"
            
            for room_id in range(1, 9):
                count = k_stats.get(room_id, 0)
                room_name = ROOM_NAMES.get(room_id, f"P{room_id}")
                pct = (count / total_killer_appearances * 100) if total_killer_appearances > 0 else 0.0
                msg += f"🚪 {room_name}: `{count}` (`{pct:.1f}%`)\n"

        markup_stat = types.InlineKeyboardMarkup(row_width=2)
        markup_stat.add(
            types.InlineKeyboardButton("🔄 Cập nhật", callback_data=f"game_{game_type}_status"),
            types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}")
        )
        try:
            bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_stat, parse_mode="Markdown")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_game_"))
def callback_back_game(call):
    chat_id = call.message.chat.id
    game_type = call.data.split("_")[3]
    bot.answer_callback_query(call.id)
    show_game_menu(chat_id, call.message.message_id, game_type)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_link}"))

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
                    
                    if prompt_id:
                        try:
                            bot.edit_message_text(f"✅ **Đã thêm nick thành công!** (`{uid}`)", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                        except Exception:
                            pass
                    return
            except Exception:
                pass
        
        if prompt_id:
            try:
                bot.edit_message_text("⚠️ **Link không hợp lệ!** Thử lại:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass
        return

    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        prompt_id = cfg.get("prompt_msg_id")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_target_bet}"))

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
            if prompt_id:
                try:
                    bot.edit_message_text(f"✅ **Đã cập nhật mức cược:** `{val}`", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except Exception:
                    pass
            return
        except ValueError:
            if prompt_id:
                try:
                    bot.edit_message_text("⚠️ **Số tiền không hợp lệ!** Nhập lại số:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except Exception:
                    pass
            return

    if not text.startswith("/"):
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass
