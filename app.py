import os
import time
import random
import requests
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
import telebot
from telebot import types

from bot_engines import (
    get_user_config, get_account_state, 
    run_escape_bot_engine, run_sprint_bot_engine, ROOM_NAMES
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")

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
        try:
            bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        except:
            pass
    else:
        try:
            bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            try:
                bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
            except:
                pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_game_"))
def callback_select_game(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try:
            bot.answer_callback_query(call.id, "⚠️ Cần nhập Key bản quyền trước!", show_alert=True)
        except:
            pass
        return
    game_type = call.data.split("_")[2]
    cfg["active_game"] = game_type
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
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
    try:
        bot.edit_message_text(msg_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        try:
            bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="Markdown")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def callback_back_main(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    cfg["waiting_for_link"] = None
    cfg["waiting_for_bet"] = None
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    show_main_menu(chat_id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def callback_game_actions(call):
    chat_id = call.message.chat.id
    cfg = get_user_config(chat_id)
    if not cfg["has_valid_key"]:
        try:
            bot.answer_callback_query(call.id, "⚠️ Hết hạn Key!", show_alert=True)
        except:
            pass
        return
    parts = call.data.split("_")
    game_type = parts[1]
    action = "_".join(parts[2:])
    g_cfg = cfg[game_type]
    game_name_vi = "Vua Thoát Hiểm" if game_type == "escape" else "Đua Tốc Độ"
    
    markup_back = types.InlineKeyboardMarkup()
    markup_back.add(types.InlineKeyboardButton("🔙 Trở lại", callback_data=f"back_to_game_{game_type}"))

    if action == "setup_link":
        cfg["waiting_for_link"] = game_type
        cfg["waiting_for_bet"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"📥 **Dán link [ {game_name_vi} ] vào ô chat:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except:
            pass
    elif action == "input_bet":
        cfg["waiting_for_bet"] = game_type
        cfg["waiting_for_link"] = None
        cfg["prompt_msg_id"] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"✏️ **Nhập số tiền cược cho [ {game_name_vi} ]:**", chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except:
            pass
    elif action == "toggle_bot":
        if not g_cfg["accounts"]:
            try:
                bot.answer_callback_query(call.id, "⚠️ Chưa có nick nào!", show_alert=True)
            except:
                pass
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
            try:
                bot.answer_callback_query(call.id, f"🚀 Đã bật auto!")
            except:
                pass
        else:
            g_cfg["global_running"] = False
            for uid in g_cfg["accounts"]:
                get_account_state(game_type, uid)["random_stop"].set()
            try:
                bot.answer_callback_query(call.id, "⏹️ Đã dừng bot!")
            except:
                pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "toggle_asset":
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        try:
            bot.answer_callback_query(call.id, f"Đổi sang {g_cfg['asset_type']}")
        except:
            pass
        show_game_menu(chat_id, call.message.message_id, game_type)
    elif action == "list":
        if not g_cfg["accounts"]:
            try:
                bot.answer_callback_query(call.id, "Chưa có nick nào!", show_alert=True)
            except:
                pass
            return
        msg = f"👥 *DS NICK ({game_name_vi.upper()}):*\n"
        for idx, uid in enumerate(g_cfg["accounts"].keys(), 1):
            msg += f"{idx}. `{uid}`\n"
        try:
            bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_back, parse_mode="Markdown")
        except:
            pass
    elif action == "status":
        try:
            bot.answer_callback_query(call.id, "🔄 Cập nhật!")
        except:
            pass
        tot_bets, tot_wins, tot_losses, tot_profit = 0, 0, 0, Decimal("0")
        for uid in g_cfg["accounts"]:
            st = get_account_state(game_type, uid)
            tot_bets += st["total_bets"]
            tot_wins += st["wins"]
            tot_losses += st["losses"]
            tot_profit += st["total_profit"]
        wr = (tot_wins / tot_bets * 100) if tot_bets > 0 else 0.0
        msg = f"📊 *THỐNG KÊ {game_name_vi.upper()}*\n━━━━━━━━━━━━━━━━━━━\n📌 Trạng thái: {'🟢 Chạy' if g_cfg['global_running'] else '🔴 Dừng'}\n🎲 Tổng cược: `{tot_bets}`\n🏆 Thắng/Thua: `{tot_wins}` / `{tot_losses}`\n📈 Tỷ lệ thắng: `{wr:.1f}%`\n💵 Tổng Lời/Lỗ: `{tot_profit:+.4f} {g_cfg['asset_type']}`"
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
        try:
            bot.edit_message_text(msg, chat_id, call.message.message_id, reply_markup=markup_stat, parse_mode="Markdown")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_game_"))
def callback_back_game(call):
    chat_id = call.message.chat.id
    game_type = call.data.split("_")[3]
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    show_game_menu(chat_id, call.message.message_id, game_type)
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip()
    cfg = get_user_config(chat_id)
    
    if cfg.get("waiting_for_key"):
        try:
            bot.delete_message(chat_id, message.message_id)
        except:
            pass
        
        prompt_id = cfg.get("prompt_msg_id")
        res = verify_key_with_server(text, str(chat_id))
        
        if res.get("status") == "success":
            cfg["has_valid_key"] = True
            cfg["waiting_for_key"] = False
            if prompt_id:
                try:
                    show_main_menu(chat_id, prompt_id, is_new=False)
                except:
                    pass
        else:
            if prompt_id:
                markup = types.InlineKeyboardMarkup()
                web_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ung-dung-cua-ong.onrender.com")
                markup.add(types.InlineKeyboardButton("🌐 Lấy Key Mới", url=web_url))
                try:
                    bot.edit_message_text("⚠️ **Key không hợp lệ hoặc đã hết hạn!** Thử lại:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except:
                    pass
        return

    game_target_link = cfg.get("waiting_for_link")
    if game_target_link:
        try:
            bot.delete_message(chat_id, message.message_id)
        except:
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
                            bot.edit_message_text(f"✅ **Thêm nick thành công!** (`{uid}`)", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                        except:
                            pass
                    return
            except:
                pass
        if prompt_id:
            try:
                bot.edit_message_text("⚠️ **Link lỗi!** Thử lại:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
            except:
                pass
        return

    game_target_bet = cfg.get("waiting_for_bet")
    if game_target_bet:
        try:
            bot.delete_message(chat_id, message.message_id)
        except:
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
                    get_account_state("sprint", uid)["current_build"] = Decimal(str(val))
            else:
                g_cfg["base_bet"] = val
            cfg["waiting_for_bet"] = None
            if prompt_id:
                try:
                    bot.edit_message_text(f"✅ **Đã cập nhật cược:** `{val}`", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except:
                    pass
            return
        except:
            if prompt_id:
                try:
                    bot.edit_message_text("⚠️ **Số tiền lỗi!** Nhập lại số:", chat_id, prompt_id, reply_markup=markup, parse_mode="Markdown")
                except:
                    pass
            return

    if not text.startswith("/"):
        try:
            bot.delete_message(chat_id, message.message_id)
        except:
            pass

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
                               
