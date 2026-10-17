import os
import json
import time
import random
import requests
from flask import Flask, render_template_string, request, redirect, url_for, session

license_app = Flask(__name__)
license_app.secret_key = "dung_license_secret_key_1612012"

KEYS_DB_FILE = "keys_db.json"
ADMIN_PASSWORD = "dung1612012"

# Cấu hình API Link4m của ông
LINK4M_API_TOKEN = "68a76c1354de3f0da567ca17"

def load_keys():
    if os.path.exists(KEYS_DB_FILE):
        try:
            with open(KEYS_DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_keys(keys_data):
    with open(KEYS_DB_FILE, "w") as f:
        json.dump(keys_data, f, indent=4)

# 1. TRANG CHỦ (Giao diện lấy Key giống mẫu)
@license_app.route('/')
def home():
    keys_db = load_keys()
    new_key = request.args.get("key", "")
    error = request.args.get("error", "")

    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XWORLD LICENSE GATEWAY</title>
        <style>
            body { background-color: #0f172a; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 30px; border-radius: 20px; width: 90%; max-width: 380px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            .icon { font-size: 50px; margin-bottom: 10px; }
            .badge { background: #0284c7; padding: 5px 12px; border-radius: 12px; font-size: 12px; }
            h2 { color: #38bdf8; margin: 15px 0 10px; font-size: 20px; }
            p { color: #94a3b8; font-size: 13px; line-height: 1.5; }
            .btn { display: block; background: linear-gradient(90deg, #0284c7, #6366f1); color: #fff; text-decoration: none; padding: 14px; border-radius: 12px; font-weight: bold; margin-top: 20px; text-align: center; }
            .btn-admin { display: block; background: #334155; color: #94a3b8; text-decoration: none; padding: 10px; border-radius: 10px; font-size: 13px; margin-top: 15px; text-align: center; }
            .key-box { background: #0f172a; border: 1px dashed #38bdf8; padding: 12px; border-radius: 10px; margin-top: 15px; font-family: monospace; font-size: 16px; color: #4ade80; word-break: break-all; }
            .error { color: #f87171; font-size: 13px; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">🔑</div>
            <span class="badge">Hệ thống tự động 24/7</span>
            <h2>XWORLD LICENSE GATEWAY</h2>
            <p>Bấm nút bên dưới để vượt link Link4m. Hệ thống sẽ cấp mã bản quyền có hiệu lực trong 24 giờ.</p>
            
            {% if new_key %}
                <div class="key-box"><b>{{ new_key }}</b></div>
                <p style="color: #4ade80; margin-top: 8px;">👉 Copy mã trên dán vào Bot Telegram!</p>
            {% else %}
                <a href="/get_link4m" class="btn">🚀 TIẾN HÀNH LẤY KEY</a>
            {% endif %}

            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}
            
            <p style="font-size: 11px; margin-top: 15px; color: #64748b;">Key chưa dùng quá 30 phút sẽ tự động bị xóa</p>
            
            <a href="/admin" class="btn-admin">⚙️ Đăng nhập Quản trị viên</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, new_key=new_key, error=error)

# 2. TẠO LINK RÚT GỌN QUA LINK4M API
@license_app.route('/get_link4m')
def get_link4m():
    # URL đích khi vượt link xong sẽ trỏ về trang cấp key của web mình
    current_domain = request.host_url.rstrip('/')
    destination_url = f"{current_domain}/claim_key"
    
    api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_TOKEN}&url={destination_url}"
    
    try:
        res = requests.get(api_url, timeout=5)
        result = res.json()
        if result.get("status") == "success":
            shortened_url = result.get("shortenedUrl")
            return redirect(shortened_url)
        else:
            err_msg = result.get("message", "Lỗi tạo link rút gọn")
            return redirect(url_for('home', error=err_msg))
    except Exception as e:
        return redirect(url_for('home', error="Không thể kết nối tới Link4m API"))

# 3. NHẬN KEY SAU KHI VƯỢT LINK XONG
@license_app.route('/claim_key')
def claim_key():
    keys_db = load_keys()
    # Tạo mã Key mới duy nhất
    new_key = "KEY-XW-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    
    keys_db[new_key] = {
        "status": "chua_dung",
        "used_by": None,
        "created_at": time.time(),
        "expire_at": None
    }
    save_keys(keys_db)
    return redirect(url_for('home', key=new_key))

# 4. API CHO BOT TELEGRAM KIỂM TRA KEY & KÍCH HOẠT 1 LẦN
@license_app.route('/api/verify_key')
def api_verify_key():
    key_code = request.args.get('key', '').strip()
    user_id = request.args.get('user_id', '').strip()
    
    keys_db = load_keys()
    
    if key_code not in keys_db:
        return {"status": "error", "msg": "Key không tồn tại!"}
    
    k_data = keys_db[key_code]
    
    # Kiểm tra nếu key đã được dùng rồi
    if k_data["status"] == "da_dung":
        # Kiểm tra xem có đang trong 24h của chính user đó không
        if k_data["used_by"] == user_id and time.time() < k_data["expire_at"]:
            return {"status": "success", "msg": "Key vẫn còn hiệu lực 24h!"}
        return {"status": "error", "msg": "Key này đã được sử dụng bởi người khác hoặc đã hết hạn!"}
    
    # Nếu key chưa dùng -> Kích hoạt lần đầu (Đếm ngược 24h từ đây)
    k_data["status"] = "da_dung"
    k_data["used_by"] = user_id
    k_data["expire_at"] = time.time() + (24 * 3600) # Hiệu lực đúng 24 giờ
    save_keys(keys_db)
    
    return {"status": "success", "msg": "Kích hoạt thành công 24 giờ!"}

# 5. TRANG QUẢN TRỊ ADMIN (Mật khẩu: dung1612012)
@license_app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Mật khẩu bảo mật không chính xác!"
            
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Đăng Nhập Quản Trị</title>
        <style>
            body { background-color: #0f172a; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 30px; border-radius: 20px; width: 90%; max-width: 350px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h2 { color: #38bdf8; margin-bottom: 20px; font-size: 18px; }
            input { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; margin-bottom: 15px; }
            .btn { width: 100%; background: #0284c7; color: #fff; border: none; padding: 12px; border-radius: 10px; font-weight: bold; cursor: pointer; }
            .error { color: #f87171; font-size: 13px; margin-bottom: 10px; }
            .back { display: block; margin-top: 15px; color: #94a3b8; font-size: 13px; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🔒 Đăng Nhập Quản Trị</h2>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <form method="POST">
                <input type="password" name="password" placeholder="Nhập mật khẩu admin..." required>
                <button type="submit" class="btn">Đăng Nhập</button>
            </form>
            <a href="/" class="back">← Quay lại trang chủ</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, error=error)

@license_app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
        
    keys_db = load_keys()
    
    html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Quản Lý Key</title>
        <style>
            body { background-color: #0f172a; color: #fff; font-family: sans-serif; padding: 20px; margin: 0; }
            .container { max-width: 650px; margin: 0 auto; background: #1e293b; padding: 20px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h2 { color: #38bdf8; margin-top: 0; font-size: 20px; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }
            th, td { padding: 10px; border-bottom: 1px solid #334155; text-align: left; }
            th { color: #94a3b8; }
            .btn-del { background: #ef4444; color: #fff; border: none; padding: 6px 10px; border-radius: 6px; cursor: pointer; text-decoration: none; }
            .btn-add { background: #22c55e; color: #fff; border: none; padding: 10px 15px; border-radius: 8px; cursor: pointer; text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 15px; }
            .logout { float: right; color: #94a3b8; text-decoration: none; font-size: 14px; }
            .status-used { color: #f87171; }
            .status-new { color: #4ade80; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/admin/logout" class="logout">Đăng xuất</a>
            <h2>⚙️ Bảng Quản Trị Key</h2>
            <a href="/claim_key" class="btn-add">➕ Tạo Key Thủ Công</a>
            <table>
                <tr>
                    <th>Mã Key</th>
                    <th>Trạng thái & Người dùng</th>
                    <th>Thời hạn / Đếm ngược</th>
                    <th>Xóa</th>
                </tr>
                {% for k, info in keys.items() %}
                <tr>
                    <td><code>{{ k }}</code></td>
                    <td>
                        {% if info.status == 'da_dung' %}
                            <span class="status-used">Đã dùng (ID: {{ info.used_by }})</span>
                        {% else %}
                            <span class="status-new">Chưa dùng</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if info.expire_at and now < info.expire_at %}
                            {{ ((info.expire_at - now) | int // 3600) }} giờ nữa hết hạn
                        {% else %}
                            Hết hạn / Chưa kích hoạt
                        {% endif %}
                    </td>
                    <td><a href="/admin/delete?key={{ k }}" class="btn-del" onclick="return confirm('Xóa key này?')">Xóa</a></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, keys=keys_db, now=time.time())

@license_app.route('/admin/delete')
def admin_delete():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
    k = request.args.get('key')
    keys_db = load_keys()
    if k in keys_db:
        del keys_db[k]
        save_keys(keys_db)
    return redirect(url_for('admin_dashboard'))

@license_app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))
  
