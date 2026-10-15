import os
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from pymongo import MongoClient
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

# --- CẤU HÌNH HỆ THỐNG ---
TELEGRAM_BOT_TOKEN = "ĐIỀN_TOKEN_BOT_TELEGRAM_VÀO_ĐÂY"
ADMIN_CHAT_ID = ĐIỀN_CHAT_ID_CỦA_ÔNG_VÀO_ĐÂY  # Dạng số, ví dụ: 12345678
MONGO_URI = "ĐIỀN_MONGO_DB_URI_VÀO_ĐÂY"
SHORTLINK_API_URL = "https://link1s.com/api?api=API_KEY_CỦA_TRANG_RÚT_GỌN&url=" # Thay API rút gọn của ông vào

app = Flask(__name__)
client = MongoClient(MONGO_URI)
db = client["key_system_db"]
keys_collection = db["keys"]

# --- HÀM TẠO KEY AN TOÀN ---
def generate_random_key(length=10):
    letters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

# --- WEB SERVER (XỬ LÝ LẤY VÀ CHECK KEY) ---

# 1. Trang tạo Key (Gửi link này qua Telegram cho user vượt link rút gọn)
@app.route('/getkey', methods=['GET'])
def get_key():
    telegram_id = request.args.get('id')
    if not telegram_id:
        return "Thiếu ID người dùng!", 400
    
    # Tạo key ngẫu nhiên mới
    raw_key = f"ESCAPE-{generate_random_key(8)}"
    expires_at = datetime.utcnow() + timedelta(hours=24) # Key sống trong 24 giờ
    
    # Lưu vào MongoDB với trạng thái "unused" (chưa dùng)
    keys_collection.update_one(
        {"telegram_id": telegram_id},
        {
            "$set": {
                "key": raw_key,
                "status": "unused",
                "expires_at": expires_at,
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    
    # Link đích sau khi user vượt qua rút gọn (trang chứa key hiển thị cho user copy)
    redirect_success_url = f"https://{request.host}/verify?key={raw_key}"
    
    # Gọi api trang rút gọn link (Ví dụ Link1s / Traffic123)
    final_short_link = f"{SHORTLINK_API_URL}{redirect_success_url}"
    
    # Chuyển hướng user thẳng sang trang rút gọn link kiếm tiền
    return f"""
    <html>
        <head><title>Đang chuyển hướng...</title></head>
        <body onload="window.location.href = '{final_short_link}';">
            <center><h2>Đang chuyển hướng đến trang vượt link lấy key...</h2></center>
        </body>
    </html>
    """

# 2. Trang hiển thị Key sau khi vượt link thành công
@app.route('/verify', methods=['GET'])
def verify_page():
    user_key = request.args.get('key', '').strip()
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Lấy Key Thành Công</title>
        <style>
            body { font-family: Arial; background: #121212; color: #fff; text-align: center; padding-top: 50px; }
            .box { background: #1e1e1e; padding: 20px; border-radius: 10px; display: inline-block; width: 300px; }
            input { width: 90%; padding: 10px; font-size: 16px; text-align: center; background: #333; color: #00ffcc; border: none; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>🎉 Key Của Bạn Đây</h2>
            <input type="text" value="{{ key }}" id="myKey" readonly>
            <p style="font-size: 12px; color: #888;">Hãy copy key này dán vào bot hoặc tool!</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template, key=user_key)

# 3. API Check Key dành cho Bot/Tool gọi sang (Chống lỗi chuẩn xác 100%)
@app.route('/api/check-key', methods=['POST'])
def api_check_key():
    data = request.json or {}
    input_key = data.get('key', '').strip() # .strip() để loại bỏ khoảng trắng thừa chống lỗi
    
    if not input_key:
        return jsonify({"status": "error", "message": "Key không được để trống!"}), 400
        
    # Tìm key trong Database
    key_doc = keys_collection.find_one({"key": input_key})
    
    if not key_doc:
        return jsonify({"status": "error", "message": "Key không tồn tại hoặc sai!"}), 400
        
    # Kiểm tra xem key đã bị dùng chưa (Nếu muốn key dùng 1 lần)
    if key_doc.get("status") == "used":
        return jsonify({"status": "error", "message": "Key này đã được sử dụng rồi!"}), 400
        
    # Kiểm tra hạn sử dụng
    if datetime.utcnow() > key_doc.get("expires_at"):
        return jsonify({"status": "error", "message": "Key đã hết hạn sử dụng!"}), 400
        
    # ĐÁNH DẤU KEY ĐÃ DÙNG (Để chống việc nhập lại lần 2 báo đúng)
    keys_collection.update_one({"key": input_key}, {"$set": {"status": "used"}})
    
    return jsonify({"status": "success", "message": "Key hợp lệ!", "telegram_id": key_doc.get("telegram_id")})


# --- TELEGRAM BOT LOGIC ---

def start(update, context):
    user_id = update.effective_user.id
    # Tạo link lấy key riêng biệt cho từng user
    # (Lưu ý: Thay domain render của ông vào sau khi deploy lên Render)
    domain = "ten-app-cua-ong.onrender.com" 
    get_key_link = f"https://{domain}/getkey?id={user_id}"
    
    keyboard = [[InlineKeyboardButton("🔗 Lấy Key Ngay", url=get_key_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🤖 *HỆ THỐNG LẤY KEY ESCAPE MASTER*\n\n"
        "Bấm vào nút bên dưới để vượt link rút gọn và nhận Key sử dụng trong 24 giờ:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def run_telegram_bot():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    updater.start_polling()

# --- CHẠY SONG SONG WEB (FLASK) VÀ TELEGRAM BOT ---
if __name__ == '__main__':
    import threading
    # Chạy Telegram bot ở một luồng riêng phụ trợ
    t = threading.Thread(target=run_telegram_bot)
    t.daemon = True
    t.start()
    
    # Chạy Flask Web Server trên cổng Render chỉ định
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
