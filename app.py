import os
import random
import string
import requests
import threading
from urllib.parse import quote
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- CẤU HÌNH API & LINK4M TOKEN ---
TELEGRAM_BOT_TOKEN = "8727297138:AAE-D_k_XzdX9IoEER_lCl1FlvBprdroiSQ"

LINK4M_TOKENS = [
    "68a76c1354de3f0da567ca17",  # Token 1
    "6a7e4f3993203b217d199b6b"   # Token 2
]

ADMIN_VIP_ID = 8726403940  # ID Admin của bạn

USER_DB = {}
VALID_LINKS = {}
BOT_STATUS = {"is_active": True}

# --- CẤU HÌNH HẠT GIỐNG NÔNG TRẠI ---
SEEDS_CONFIG = {
    1: {"name": "🌱 Mầm Đậu Xanh", "cost": 30, "grow_minutes": 1, "reward": 35},
    2: {"name": "🌽 Bắp Ngô Ngọt", "cost": 60, "grow_minutes": 3, "reward": 70},
    3: {"name": "🥔 Khoai Tây Vàng", "cost": 120, "grow_minutes": 7, "reward": 140},
    4: {"name": "🍓 Dâu Tây Đỏ", "cost": 250, "grow_minutes": 15, "reward": 290},
    5: {"name": "🍎 Táo Vàng Thần Tài", "cost": 500, "grow_minutes": 30, "reward": 580}
}

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Vượt Link Nhận Mã</title></head>
<body style="background:#0f172a; color:#fff; text-align:center; padding:50px; font-family:sans-serif;">
    <div style="background:#1e293b; padding:30px; border-radius:12px; display:inline-block;">
        <h2>Mã nhận thưởng của bạn</h2>
        <div style="background:#0f172a; border:2px dashed #38bdf8; padding:15px; font-size:24px; color:#4ade80; margin: 20px 0;">{{ key }}</div>
        <p style="color: #94a3b8; font-size: 14px;">Hãy copy mã này và dán về bot Telegram để nhận thưởng nhé!</p>
    </div>
</body>
</html>
"""

@app.route('/earn')
def earn_page():
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    VALID_LINKS[key] = True
    return render_template_string(HTML_TEMPLATE, key=key)

def get_user(user_id):
    now = datetime.now()
    if user_id not in USER_DB:
        USER_DB[user_id] = {
            "balance": 100.0, 
            "is_vip": False, 
            "links_today": 0, 
            "last_link_date": now.date(), 
            "bank_info": None, 
            "bank_changes_left": 3, 
            "farm": {"seed_id": None, "plant_time": None, "ripe_time": None}
        }
    if USER_DB[user_id]["last_link_date"] != now.date():
        USER_DB[user_id]["links_today"] = 0
        USER_DB[user_id]["last_link_date"] = now.date()
    return USER_DB[user_id]

def shorten_link_link4m(destination_url, api_token):
    try:
        # Chuẩn hóa urlencode giống cú pháp PHP của bạn
        long_url = quote(destination_url, safe='')
        api_url = f"https://link4m.co/api-shorten/v2?api={api_token}&url={long_url}"
        response = requests.get(api_url, timeout=10)
        result = response.json()
        if result.get("status") == 'success':
            return result.get("shortenedUrl")
    except Exception as e:
        print(f"Lỗi rút gọn link Link4M: {e}")
    return None

def get_main_menu(balance):
    keyboard = [
        [InlineKeyboardButton("💣 Dò Mìn 3x3", callback_data="play_mine"), InlineKeyboardButton("🌾 Nông trại TK", callback_data="play_farm")],
        [InlineKeyboardButton("👛 Ví của tôi", callback_data="my_wallet")],
        [InlineKeyboardButton("🔗 Vượt link kiếm tiền (500đ/link)", callback_data="get_earn_link")],
        [InlineKeyboardButton(f"💵 Số dư: {balance:,.0f} VNĐ", callback_data="balance_info")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not BOT_STATUS["is_active"] and user_id != ADMIN_VIP_ID:
        if update.message:
            await update.message.reply_text("🛠️ **Hệ thống đang bảo trì tạm thời!**", parse_mode="Markdown")
        return

    user = get_user(user_id)
    text = "🤖 **Hệ thống TK Kim Kiếm đã sẵn sàng!**\nChọn tính năng bên dưới:"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(user["balance"]), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=get_main_menu(user["balance"]), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not BOT_STATUS["is_active"] and user_id != ADMIN_VIP_ID:
        await update.callback_query.answer("🛠️ Hệ thống đang bảo trì!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()
    user = get_user(user_id)
    data = query.data

    if data == "menu":
        await start(update, context)

    # --- TÍNH NĂNG NÔNG TRẠI ---
    elif data == "play_farm":
        farm = user["farm"]
        now = datetime.now()
        
        if farm["seed_id"] is None:
            text = "🌾 **NÔNG TRẠI TK**\n\nĐất đang trống. Hãy chọn hạt giống để trồng:"
            kb = []
            for s_id, info in SEEDS_CONFIG.items():
                kb.append([InlineKeyboardButton(f"Trồng {info['name']} (Giá: {info['cost']}đ)", callback_data=f"plant_{s_id}")])
            kb.append([InlineKeyboardButton("« Quay lại Menu", callback_data="menu")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            seed_info = SEEDS_CONFIG[farm["seed_id"]]
            if now >= farm["ripe_time"]:
                text = f"🌾 **NÔNG TRẠI TK**\n\nCây **{seed_info['name']}** đã chín và sẵn sàng thu hoạch!"
                kb = [
                    [InlineKeyboardButton(f"🧺 Thu hoạch ngay (+{seed_info['reward']}đ)", callback_data="harvest_plant")],
                    [InlineKeyboardButton("« Quay lại Menu", callback_data="menu")]
                ]
            else:
                remaining = int((farm["ripe_time"] - now).total_seconds())
                if remaining < 0:
                    remaining = 0
                mins, secs = divmod(remaining, 60)
                text = f"🌾 **NÔNG TRẠI TK**\n\nĐang trồng: **{seed_info['name']}**\n⏳ Thời gian thu hoạch còn lại: **{mins} phút {secs} giây**"
                kb = [
                    [InlineKeyboardButton("🔄 Làm mới trạng thái", callback_data="play_farm")],
                    [InlineKeyboardButton("« Quay lại Menu", callback_data="menu")]
                ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("plant_"):
        seed_id = int(data.split("_")[1])
        seed_info = SEEDS_CONFIG[seed_id]
        if user["balance"] < seed_info["cost"]:
            await query.answer("❌ Số dư không đủ để mua hạt giống này!", show_alert=True)
            return
        
        user["balance"] -= seed_info["cost"]
        now = datetime.now()
        user["farm"] = {
            "seed_id": seed_id,
            "plant_time": now,
            "ripe_time": now + timedelta(minutes=seed_info["grow_minutes"])
        }
        await query.answer(f"🌱 Đã trồng thành công {seed_info['name']}!", show_alert=True)
        await button_handler(update, context)

    elif data == "harvest_plant":
        farm = user["farm"]
        if farm["seed_id"] is None:
            await query.answer("Không có cây nào để thu hoạch!", show_alert=True)
            return
        seed_info = SEEDS_CONFIG[farm["seed_id"]]
        now = datetime.now()
        if now < farm["ripe_time"]:
            await query.answer("Cây chưa chín, chưa thể thu hoạch!", show_alert=True)
            return
        
        reward_amt = seed_info["reward"]
        user["balance"] += reward_amt
        user["farm"] = {"seed_id": None, "plant_time": None, "ripe_time": None}
        await query.answer(f"🎉 Thu hoạch thành công! Nhận +{reward_amt}đ", show_alert=True)
        await button_handler(update, context)

    # --- QUẢN LÝ VÍ & NGÂN HÀNG ---
    elif data == "my_wallet":
        bank_text = f"`{user['bank_info']}`" if user["bank_info"] else "Chưa liên kết"
        vip_status = "👑 Đang bật (Bất tử)" if user["is_vip"] else "🔒 Thường"
        text = (
            f"👛 **QUẢN LÝ VÍ CỦA TÔI**\n\n"
            f"💵 Số dư: **{user['balance']:,.0f} VNĐ**\n"
            f"👑 Trạng thái VIP: **{vip_status}**\n"
            f"🏦 Tài khoản ngân hàng: {bank_text}\n"
            f"🔄 Số lần đổi ngân hàng còn lại: **{user['bank_changes_left']}/3**"
        )
        kb = [
            [InlineKeyboardButton("🔗 Liên kết / Đổi ngân hàng", callback_data="link_bank_prompt")],
            [InlineKeyboardButton("💸 Rút tiền", callback_data="withdraw_menu")],
            [InlineKeyboardButton("« Quay lại Menu", callback_data="menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "link_bank_prompt":
        if user["bank_changes_left"] <= 0:
            await query.answer("❌ Bạn đã hết lượt đổi ngân hàng!", show_alert=True)
            return
        context.user_data["waiting_for_bank"] = True
        await query.edit_message_text(
            text="🏦 **LIÊN KẾT / ĐỔI NGÂN HÀNG**\n\nNhập theo cú pháp:\n`TênNgânHàng - SốTàiKhoản - TênNgườiNhận`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Quay lại Ví", callback_data="my_wallet")]]),
            parse_mode="Markdown"
        )

    elif data == "withdraw_menu":
        if not user["bank_info"]:
            await query.answer("❌ Bạn chưa liên kết ngân hàng!", show_alert=True)
            return
        context.user_data["waiting_for_withdraw"] = True
        await query.edit_message_text(
            text=f"💸 **RÚT TIỀN**\n🏦 TK: `{user['bank_info']}`\n\nNhập số tiền cần rút (Tối thiểu 100.000đ):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Quay lại Ví", callback_data="my_wallet")]]),
            parse_mode="Markdown"
        )

    # --- VƯỢT LINK (Áp dụng đúng 2 Token Link4M phân phối theo lượt) ---
    elif data == "get_earn_link":
        if user["links_today"] >= 4:
            await query.answer("❌ Bạn đã đạt giới hạn 4 lần vượt link trong ngày!", show_alert=True)
            return

        current_attempt = user["links_today"]
        # 2 lượt đầu dùng token 1, 2 lượt sau dùng token 2
        token_index = 0 if current_attempt < 2 else 1
        chosen_token = LINK4M_TOKENS[token_index]

        destination = "https://bot-link-vuot.onrender.com/earn"
        short_url = shorten_link_link4m(destination, chosen_token)
        
        # Fallback tự động tạo mã trực tiếp nếu server Link4M gặp sự cố
        if not short_url:
            fallback_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            VALID_LINKS[fallback_code] = True
            await query.edit_message_text(
                f"⚠️ Hệ thống rút gọn đang bận. Đây là mã dự phòng của bạn:\n\n`{fallback_code}`\n\n(Hãy copy mã này và bấm Nhập Mã)",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Nhập Mã", callback_data="input_earn_code")], [InlineKeyboardButton("« Quay lại", callback_data="menu")]]),
                parse_mode="Markdown"
            )
            return

        keyboard = [
            [InlineKeyboardButton(f"🌐 Mở Link (Lượt {current_attempt + 1}/4)", url=short_url)],
            [InlineKeyboardButton("🔑 Nhập Mã", callback_data="input_earn_code")],
            [InlineKeyboardButton("« Quay lại", callback_data="menu")]
        ]
        await query.edit_message_text(
            f"🔗 **Hệ thống Link Kiếm Tiền (Lượt {current_attempt + 1}/4)**\nBấm vào link để lấy mã vượt:", 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="Markdown"
        )

    elif data == "input_earn_code":
        context.user_data["waiting_for_code"] = True
        await query.edit_message_text("✍️ Gửi mã code vào khung chat:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Quay lại", callback_data="menu")]]))

    # --- DÒ MÌN 3x3 ---
    elif data == "play_mine":
        await query.edit_message_text(
            "💣 **Dò Mìn · Chọn mức cược:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cược 200đ", callback_data="mine_bet_200"), InlineKeyboardButton("Cược 500đ", callback_data="mine_bet_500")],
                [InlineKeyboardButton("Cược 1,000đ", callback_data="mine_bet_1000"), InlineKeyboardButton("Cược 2,000đ", callback_data="mine_bet_2000")],
                [InlineKeyboardButton("Cược 10,000đ", callback_data="mine_bet_10000"), InlineKeyboardButton("Cược 20,000đ", callback_data="mine_bet_20000")],
                [InlineKeyboardButton("« Quay lại Menu", callback_data="menu")]
            ])
        )

    elif data.startswith("mine_bet_"):
        bet = int(data.split("_")[2])
        if user["balance"] < bet:
            await query.answer("❌ Số dư không đủ!", show_alert=True)
            return
        user["balance"] -= bet
        
        user["mine_game"] = {
            "bet": bet, 
            "opened": 0, 
            "multiplier": 1.0, 
            "grid": ["?"] * 9
        }
        
        kb = [
            [InlineKeyboardButton("❓", callback_data="mine_pick_0"), InlineKeyboardButton("❓", callback_data="mine_pick_1"), InlineKeyboardButton("❓", callback_data="mine_pick_2")],
            [InlineKeyboardButton("❓", callback_data="mine_pick_3"), InlineKeyboardButton("❓", callback_data="mine_pick_4"), InlineKeyboardButton("❓", callback_data="mine_pick_5")],
            [InlineKeyboardButton("❓", callback_data="mine_pick_6"), InlineKeyboardButton("❓", callback_data="mine_pick_7"), InlineKeyboardButton("❓", callback_data="mine_pick_8")],
            [InlineKeyboardButton("« Thoát", callback_data="play_mine")]
        ]
        await query.edit_message_text(
            f"💣 **Dò Mìn · Đang chơi**\n🪙 Cược: **{bet:,.0f}đ**\nĐã mở: **0 / 8 💎**\nHệ số: **1.0x**",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )

    elif data.startswith("mine_pick_"):
        if "mine_game" not in user:
            await query.answer("Ván chơi đã kết thúc!", show_alert=True)
            return
        idx = int(data.split("_")[2])
        game = user["mine_game"]
        if game["grid"][idx] != "?":
            await query.answer("Ô này đã mở rồi!", show_alert=True)
            return

        opened_count = sum(1 for cell in game["grid"] if cell == "💎")
        current_step = opened_count + 1

        if user["is_vip"]:
            safe_chance = 100.0
        else:
            if current_step == 1:
                safe_chance = 50.0    # Ô 1: 50%
            elif current_step == 2:
                safe_chance = 25.0    # Ô 2: 25%
            elif current_step == 3:
                safe_chance = 12.0    # Ô 3: 12%
            elif current_step == 4:
                safe_chance = 5.0     # Ô 4: 5%
            else:
                safe_chance = 0.0     # Từ ô thứ 5 trở đi chắc chắn nổ (0%)

        rand_val = random.uniform(0, 100)
        is_safe = (rand_val < safe_chance)

        if not is_safe:
            game["grid"][idx] = "💥"
            for i in range(9):
                if game["grid"][i] == "?":
                    game["grid"][i] = "💎" if random.random() > 0.4 else "💥"
            game["grid"][idx] = "💥"
            
            del user["mine_game"]
            kb = [
                [InlineKeyboardButton(game["grid"][0], callback_data="none"), InlineKeyboardButton(game["grid"][1], callback_data="none"), InlineKeyboardButton(game["grid"][2], callback_data="none")],
                [InlineKeyboardButton(game["grid"][3], callback_data="none"), InlineKeyboardButton(game["grid"][4], callback_data="none"), InlineKeyboardButton(game["grid"][5], callback_data="none")],
                [InlineKeyboardButton(game["grid"][6], callback_data="none"), InlineKeyboardButton(game["grid"][7], callback_data="none"), InlineKeyboardButton(game["grid"][8], callback_data="none")],
                [InlineKeyboardButton("🔄 Chơi lại", callback_data="play_mine"), InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ]
            await query.edit_message_text(f"💥 **Trúng mìn! Bạn đã thua.**\nSố dư: {user['balance']:,.0f}đ", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            game["opened"] += 1
            game["multiplier"] = round(game["multiplier"] * 1.5, 2)
            game["grid"][idx] = "💎"
            prize = int(game["bet"] * game["multiplier"])

            if game["opened"] >= 8:
                user["balance"] += prize
                del user["mine_game"]
                await query.edit_message_text(f"🏆 **Thắng cực phẩm! Vượt hết 8 ô kim cương nhận +{prize:,.0f}đ**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))
            else:
                kb = [
                    [InlineKeyboardButton(game["grid"][0], callback_data="mine_pick_0"), InlineKeyboardButton(game["grid"][1], callback_data="mine_pick_1"), InlineKeyboardButton(game["grid"][2], callback_data="mine_pick_2")],
                    [InlineKeyboardButton(game["grid"][3], callback_data="mine_pick_3"), InlineKeyboardButton(game["grid"][4], callback_data="mine_pick_4"), InlineKeyboardButton(game["grid"][5], callback_data="mine_pick_5")],
                    [InlineKeyboardButton(game["grid"][6], callback_data="mine_pick_6"), InlineKeyboardButton(game["grid"][7], callback_data="mine_pick_7"), InlineKeyboardButton(game["grid"][8], callback_data="mine_pick_8")],
                    [InlineKeyboardButton(f"💰 Rút ngay ({prize:,.0f}đ)", callback_data="mine_cashout")],
                    [InlineKeyboardButton("« Thoát", callback_data="play_mine")]
                ]
                await query.edit_message_text(
                    f"💣 **Dò Mìn · Đang chơi**\nĐã mở: **{game['opened']}/8 💎**\nHệ số: **{game['multiplier']}x**\nRút được: **{prize:,.0f}đ**",
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
                )

    elif data == "mine_cashout":
        if "mine_game" not in user:
            return
        prize = int(user["mine_game"]["bet"] * user["mine_game"]["multiplier"])
        user["balance"] += prize
        del user["mine_game"]
        await query.edit_message_text(f"🎉 **Rút tiền thành công!** +{prize:,.0f}đ\nSố dư: {user['balance']:,.0f}đ", reply_markup=get_main_menu(user["balance"]), parse_mode="Markdown")

    elif data in ["none", "balance_info"]:
        await query.answer("Tính năng đang hoạt động!", show_alert=False)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not BOT_STATUS["is_active"] and user_id != ADMIN_VIP_ID:
        return

    user = get_user(user_id)
    text = update.message.text.strip()

    if context.user_data.get("waiting_for_withdraw"):
        context.user_data["waiting_for_withdraw"] = False
        try:
            amt = float(text.replace(",", "").replace(".", ""))
            if amt < 100000:
                await update.message.reply_text("❌ Số tiền rút tối thiểu phải từ **100.000 VNĐ** trở lên!", reply_markup=get_main_menu(user["balance"]), parse_mode="Markdown")
                return
            if amt > user["balance"]:
                await update.message.reply_text("❌ Số tiền vượt quá số dư hiện có trong ví!", reply_markup=get_main_menu(user["balance"]))
                return
            
            user["balance"] -= amt
            await update.message.reply_text(
                f"✅ **Đã tạo lệnh rút thành công {amt:,.0f}đ!**\n🏦 TK nhận: `{user['bank_info']}`", 
                reply_markup=get_main_menu(user["balance"]), 
                parse_mode="Markdown"
            )
   
