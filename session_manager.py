# session_manager.py - File chuyên dụng quản lý phiên đăng nhập của khách
import os
import json
import time

USER_SESSIONS_FILE = "user_sessions.json"

def load_user_sessions():
    if os.path.exists(USER_SESSIONS_FILE):
        try:
            with open(USER_SESSIONS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_sessions(sessions_data):
    with open(USER_SESSIONS_FILE, "w") as f:
        json.dump(sessions_data, f, indent=4)

def check_session_valid(chat_id):
    """Kiểm tra xem user đã kích hoạt và còn hạn trong file riêng chưa"""
    sessions_db = load_user_sessions()
    chat_id_str = str(chat_id)
    if chat_id_str in sessions_db:
        u_info = sessions_db[chat_id_str]
        if time.time() < u_info.get("expire_at", 0):
            return True, u_info.get("expire_at", 0)
    return False, 0

def save_session_to_file(chat_id, expire_at):
    """Lưu phiên đăng nhập thẳng vào file riêng"""
    sessions_db = load_user_sessions()
    sessions_db[str(chat_id)] = {"expire_at": expire_at}
    save_user_sessions(sessions_db)
    