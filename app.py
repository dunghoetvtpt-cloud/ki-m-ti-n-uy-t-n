import os
import random
import string
import requests
from flask import Flask, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- CẤU HÌNH TOKEN ---
TELEGRAM_BOT_TOKEN = "8880267204:AAG4JJRziEY5e66yzI2pas305ZX3rQCHEh8"
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"
RENDER_DOMAIN = "https://bot-link-vuot.onrender.com" # Nhớ thay link Render của bạn vào đây

VALID_KEYS = set()

app = Flask(__name__)

# --- GIAO DIỆN WEB SIÊU ĐẸP (HTML/CSS) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xác Nhận Vượt Link - Premium Config</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #0f172a, #1e1b4b); 
            color: #f8fafc; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 100vh; 
        }
        .container { 
            background: rgba(30, 41, 59, 0.7); 
            backdrop-filter: blur(10px);
            border: 1px solid rgba(56, 189, 248, 0.2);
            padding: 40px 30px; 
            border-radius: 20px; 
            text-align: center; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); 
            max-width: 400px;
            width: 90%;
        }
        h2 { color: #38bdf8; margin-bottom: 10px; font-size: 24px; }
        p { color: #94a3b8; font-size: 14px; margin-bottom: 20px; line-height: 1.5; }
        .key-box { 
            background: #0f172a; 
            border: 2px dashed #38bdf8; 
            padding: 15px; 
            font-size: 24px; 
            font-family: monospace;
            font-weight: bold; 
            color: #4ade80; 
            margin: 20px 0; 
            border-radius: 12px; 
            letter-spacing: 2px;
            user-select: all;
        }
        .footer-note { font-size: 12px; color: #64748b; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🎉 Vượt Link Thành Công!</h2>
        <p>Tuyệt vời! Bạn đã hoàn thành bước xác thực. Hãy sao chép mã Key bên dưới:</p>
        <div class="key-box">{{ key }}</div>
        <p>Dán mã này vào khung chat của Bot Telegram để nhận file config ngay lập tức nhé.</p>
        <div class="footer-note">⚡ Powered by Telegram Bot Security System</div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    VALID_KEYS.add(key)
    return render_template_string(HTML_TEMPLATE, key=key)

# --- HÀM RÚT GỌN LINK ---
def create_link4m_link(target_url):
    try:
        api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={target_url}"
        response = requests.get(api_url, timeout=10)
        result = response.json()
        
        if result.get("status") == 'success':
            return result.get("shortenedUrl")
    except Exception as e:
        print(f"Lỗi Link4m: {e}")
    return target_url

# --- GIAO DIỆN TELEGRAM BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "✨ **CHÀO MỪNG BẠN ĐẾN VỚI HỆ THỐNG CONFIG VIP** ✨\n\n"
        "Để nhận file config tốc độ cao mới nhất, bạn vui lòng hoàn thành bước xác thực ngắn gọn bên dưới nhé 👇"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Lấy File Config (Vượt Link)", callback_data="get_link")],
        [InlineKeyboardButton("📖 Hướng Dẫn Sử Dụng", callback_data="guide")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Gửi kèm ảnh banner trực quan (hoặc chỉ gửi text nếu không dùng ảnh)
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "get_link":
        short_url = create_link4m_link(RENDER_DOMAIN)

        keyboard = [
            [InlineKeyboardButton("🌐 Mở Link Xác Thực", url=short_url)],
            [InlineKeyboardButton("🔑 Nhập Key Đã Lấy", callback_data="input_key")],
            [InlineKeyboardButton("« Quay lại", callback_data="back_home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="🔗 **LIÊN KẾT XÁC THỰC ĐÃ SẴN SÀNG**\n\n"
                 "1️⃣ Bấm nút **'Mở Link Xác Thực'** ở dưới.\n"
                 "2️⃣ Hoàn thành vượt link và lấy mã **Key**.\n"
                 "3️⃣ Quay lại đây bấm **'Nhập Key Đã Lấy'** để nhận file.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    elif query.data == "input_key":
        await query.edit_message_text(
            text="⌨️ **HÃY GỬI MÃ KEY**\n\n"
                 "Vui lòng nhập hoặc dán trực tiếp mã Key 8 ký tự mà bạn vừa nhận được từ trang web vào khung chat này nhé!"
        )

    elif query.data == "guide":
        keyboard = [[InlineKeyboardButton("« Quay lại", callback_data="back_home")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="📖 **HƯỚNG DẪN NHANH**\n\n"
                 "- Mỗi Key chỉ có hiệu lực sử dụng 1 lần duy nhất.\n"
                 "- Nếu gặp lỗi, vui lòng bấm `/start` để làm lại từ đầu.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    elif query.data == "back_home":
        keyboard = [
            [InlineKeyboardButton("🚀 Lấy File Config (Vượt Link)", callback_data="get_link")],
            [InlineKeyboardButton("📖 Hướng Dẫn Sử Dụng", callback_data="guide")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="✨ **CHÀO MỪNG BẠN ĐẾN VỚI HỆ THỐNG CONFIG VIP** ✨\n\n"
                 "Vui lòng chọn một tính năng bên dưới:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    
    if user_text in VALID_KEYS:
        VALID_KEYS.remove(user_text)
        
        # Giao diện khi nhận file thành công (Có thể thay thế bằng file thật .env, .json, .txt bằng reply_document)
        success_msg = (
            "✅ **XÁC NHẬN THÀNH CÔNG!**\n\n"
            "Cảm ơn bạn đã ủng hộ. Dưới đây là thông tin file config của bạn:\n\n"
            "`vless://example-config-uuid-hight-speed@server:port...`\n\n"
            "📌 *Lưu ý: Không chia sẻ link/file này cho người khác.*"
        )
        await update.message.reply_text(success_msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❌ **Mã Key không hợp lệ hoặc đã được sử dụng!**\n\n"
            "Vui lòng bấm `/start` để tạo link và lấy Key mới.",
            parse_mode="Markdown"
        )

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def main():
    import threading
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot và Web Server đang chạy mượt mà...")
    application.run_polling()

if __name__ == "__main__":
    main()
    
