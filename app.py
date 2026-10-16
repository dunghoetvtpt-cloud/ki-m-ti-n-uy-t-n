import telebot, time, random, requests, os, sqlite3
from telebot import types
from urllib.parse import urlparse, parse_qs
from threading import Thread, Lock, Event
from decimal import Decimal, ROUND_DOWN
from flask import Flask, request, redirect, jsonify, render_template_string

BOT_TOKEN = "8513825480:AAGzOtGqQpkKJv1563LWU5_PcpexOJVi3HE"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.execute('CREATE TABLE IF NOT EXISTS license_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, license_key TEXT UNIQUE, is_used INTEGER DEFAULT 0, used_by TEXT, expires_at DATETIME)')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.execute("DELETE FROM license_keys WHERE is_used = 0")
    conn.commit()
    conn.close()
    return render_template_string('<!DOCTYPE html><html><body style="background:#090d16;color:#fff;text-align:center;padding-top:50px;font-family:sans-serif;"><h2>XWORLD LICENSE GATEWAY</h2><a href="/generate" style="background:#0ea5e9;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;display:inline-block;margin-top:20px;">LẤY KEY NGAY</a></body></html>')

@app.route('/generate')
def generate():
    k = "XW-" + ''.join(random.choices('0123456789ABCDEF', k=8))
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.execute("INSERT INTO license_keys (license_key, is_used, expires_at) VALUES (?, 0, datetime('now', '+1 day'))", (k,))
    conn.commit()
    conn.close()
    dest = f"{request.host_url.rstrip('/')}/get_key_page?key={k}"
    try:
        r = requests.get(f"https://link4m.co/api-shorten/v2?api=68a76c1354de3f0da567ca17&url={requests.utils.quote(dest)}", timeout=5).json()
        if r.get("status") == 'success': return redirect(r["shortenedUrl"])
    except: pass
    return redirect(dest)

@app.route('/get_key_page')
def get_key_page():
    return f'<body style="background:#090d16;color:#fff;text-align:center;padding-top:50px;font-family:sans-serif;"><h2>🎉 Lấy Key thành công!</h2><h1 style="color:#38bdf8;background:#1e293b;display:inline-block;padding:15px 30px;border-radius:10px;">{request.args.get("key","")}</h1><p>Copy mã này dán vào Bot Telegram.</p></body>'

@app.route('/check_key')
def check_key():
    k, uid = request.args.get('key','').strip(), request.args.get('telegram_id','').strip()
    if not k or not uid: return jsonify({"status": "error", "message": "Thiếu thông tin"})
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM license_keys WHERE license_key = ?", (k,)).fetchone()
    if not row: 
        conn.close()
        return jsonify({"status": "error", "message": "❌ Key không tồn tại!"})
    if row['is_used'] == 1:
        res = "✅ Key hợp lệ!" if row['used_by'] == uid else "❌ Key đã được dùng bởi tài khoản khác!"
        st = "success" if row['used_by'] == uid else "error"
        conn.close()
        return jsonify({"status": st, "message": res})
    conn.execute("UPDATE license_keys SET is_used = 1, used_by = ? WHERE license_key = ?", (uid, k))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "🎉 Kích hoạt thành công!"})

user_data, data_lock, waiting_key, verified = {}, Lock(), set(), set()

def get_cfg(cid):
    with data_lock:
        if cid not in user_data:
            user_data[cid] = {"active": None, "wait_link": None, "wait_bet": None, "escape": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "base_bet": 10.0}, "sprint": {"accounts": {}, "global_running": False, "asset_type": "BUILD", "bet_amount_total": "1"}}
        return user_data[cid]

threads = {}
def get_st(prefix, uid):
    k = f"{prefix}_{uid}"
    if k not in threads: threads[k] = {"profit": Decimal("0"), "bets": 0, "wins": 0, "losses": 0, "build": Decimal("1"), "stop": Event()}
    return threads[k]

@bot.message_handler(commands=['start'])
def start(m):
    if m.chat.id not in verified:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🌐 Tới Trang Lấy Key", url=f"{os.environ.get('RENDER_EXTERNAL_URL', 'https://bot-tool-golike.onrender.com')}/generate"),
                   types.InlineKeyboardButton("🔑 Nhập Key Kích Hoạt", callback_data="pkey"))
        bot.send_message(m.chat.id, "🔒 *XWORLD LICENSE GATEWAY*\n⚠️ Bạn cần Key bản quyền để dùng bot.", reply_markup=markup, parse_mode="Markdown")
        return
    main_menu(m.chat.id)

def main_menu(cid, mid=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🕹️ Vua Thoát Hiểm", callback_data="game_escape"), types.InlineKeyboardButton("🏃 Đua Tốc Độ", callback_data="game_sprint"))
    txt = "🎮 *XWORLD MULTI-GAME BOT*\n📌 Chọn tựa game:"
    if mid:
        try: bot.edit_message_text(txt, cid, mid, reply_markup=markup, parse_mode="Markdown"); return
        except: pass
    bot.send_message(cid, txt, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "pkey")
def pkey(c):
    waiting_key.add(c.message.chat.id)
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id, "🔑 **Nhập mã Key của bạn vào đây:**", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("game_"))
def sel_game(c):
    cid, g = c.message.chat.id, c.data.split("_")[1]
    get_cfg(cid)["active"] = g
    g_cfg, name = get_cfg(cid)[g], ("Vua Thoát Hiểm" if g == "escape" else "Đua Tốc Độ")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("⚙️ Thêm Nick", callback_data=f"act_{g}_link"),
               types.InlineKeyboardButton("🚀 Bật/Tắt Bot", callback_data=f"act_{g}_toggle"),
               types.InlineKeyboardButton("🪙 Đổi Coin", callback_data=f"act_{g}_asset"),
               types.InlineKeyboardButton("✏️ Đổi Cược", callback_data=f"act_{g}_bet"),
               types.InlineKeyboardButton("👥 DS Nick", callback_data=f"act_{g}_list"),
               types.InlineKeyboardButton("🔙 Quay lại", callback_data="back"))
    bot.edit_message_text(f"🎮 *GAME: {name.upper()}*\nTrạng thái: {'🟢 Chạy' if g_cfg['global_running'] else '🔴 Dừng'}\nNick: `{len(g_cfg['accounts'])}`", cid, c.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "back")
def back(c): main_menu(c.message.chat.id, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("act_"))
def acts(c):
    cid, parts = c.message.chat.id, c.data.split("_")
    g, act, cfg = parts[1], parts[2], get_cfg(cid)
    if act == "link":
        cfg["wait_link"] = g; bot.answer_callback_query(c.id); bot.send_message(cid, "📥 Dán link game vào đây!")
    elif act == "bet":
        cfg["wait_bet"] = g; bot.answer_callback_query(c.id); bot.send_message(cid, "✏️ Nhập số tiền cược:")
    elif act == "toggle":
        g_cfg = cfg[g]
        if not g_cfg["accounts"]: bot.answer_callback_query(c.id, "⚠️ Chưa có nick!", show_alert=True); return
        g_cfg["global_running"] = not g_cfg["global_running"]
        bot.answer_callback_query(c.id, "Đã đổi trạng thái bot!")
        if g_cfg["global_running"]:
            for uid, skey in g_cfg["accounts"].items():
                st = get_st(g, uid); st["stop"].clear()
                Thread(target=run_esc if g == "escape" else run_spr, args=(cid, uid, skey), daemon=True).start()
        else:
            for uid in g_cfg["accounts"]: get_st(g, uid)["stop"].set()
    elif act == "asset":
        g_cfg = cfg[g]
        g_cfg["asset_type"] = "USDT" if g_cfg["asset_type"] == "BUILD" else "BUILD"
        bot.answer_callback_query(c.id, f"Đổi sang {g_cfg['asset_type']}")
    elif act == "list":
        bot.send_message(cid, "👥 *Danh sách nick:*\n" + "\n".join([f"- `{u}`" for u in get_cfg(cid)[g]["accounts"]]), parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def msg(m):
    cid, txt = m.chat.id, m.text.strip()
    cfg = get_cfg(cid)
    if cid in waiting_key:
        waiting_key.remove(cid)
        try:
            res = requests.get(f"http://127.0.0.1:{os.environ.get('PORT', 5000)}/check_key?key={txt}&telegram_id={cid}", timeout=5).json()
            if res.get("status") == "success": 
                verified.add(cid)
                bot.reply_to(m, f"🎉 {res.get('message')}\n👉 Bấm `/start` để mở bot!", parse_mode="Markdown")
            else: 
                bot.reply_to(m, f"{res.get('message')}\n👉 Bấm `/start` thử lại.")
        except Exception as e: 
            bot.reply_to(m, f"❌ Lỗi: `{e}`", parse_mode="Markdown")
        return
    if cfg["wait_link"]:
        g = cfg["wait_link"]
        if "userId=" in txt and "secretKey=" in txt:
            try:
                p = parse_qs(urlparse(txt).query)
                uid, skey = int(p.get("userId", [None])[0]), p.get("secretKey", [None])[0]
                if uid and skey: cfg[g]["accounts"][uid] = skey; cfg["wait_link"] = None; bot.reply_to(m, "✅ Thêm nick thành công! Gõ `/start`.")
                return
            except: pass
        bot.reply_to(m, "⚠️ Link không hợp lệ!"); return
    if cfg["wait_bet"]:
        g = cfg["wait_bet"]
        try:
            val = float(txt)
            if val <= 0: raise ValueError()
            if g == "sprint": cfg[g]["bet_amount_total"] = str(val)
            else: cfg[g]["base_bet"] = val
            cfg["wait_bet"] = None; bot.reply_to(m, f"✅ Đã đổi cược thành `{val}`. Gõ `/start`.")
            return
        except: bot.reply_to(m, "⚠️ Nhập số hợp lệ lớn hơn 0!"); return
    if not txt.startswith("/"): bot.reply_to(m, "💡 Gõ `/start` để mở menu.")

def run_esc(cid, uid, skey):
    cfg = get_cfg(cid)["escape"]; st = get_st("escape", uid)
    while cfg["global_running"] and not st["stop"].is_set():
        try:
            r = requests.get("https://api.escapemaster.net/escape_game/my_joined", params={"asset": cfg["asset_type"], "page": 1}, headers={"user-id": str(uid), "user-secret-key": skey}, timeout=10).json()
            if r.get("code") == 0 and r.get("data", {}).get("items"):
                item = r["data"]["items"][0]; issue = str(item.get("issue_id"))
                if st.get("issue") != issue:
                    st["issue"] = issue; st["bets"] += 1; room = random.randint(1, 8)
                    requests.post("https://api.escapemaster.net/escape_game/enter_room", json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room}, headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
                    time.sleep(0.1)
                    requests.post("https://api.escapemaster.net/escape_game/bet", json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": room, "bet_amount": cfg["base_bet"]}, headers={"user-id": str(uid), "user-secret-key": skey, "content-type": "application/json"})
        except: pass
        time.sleep(3)

def run_spr(cid, uid, skey):
    cfg = get_cfg(cid)["sprint"]; st = get_st("sprint", uid); api = "https://api.sprintrun.win"
    h = {"accept": "*/*", "content-type": "application/json", "origin": api, "referer": f"{api}/", "user-agent": "Mozilla/5.0", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    while cfg["global_running"] and not st["stop"].is_set():
        try:
            r = requests.get(f"{api}/sprint/home?asset={cfg['asset_type']}", headers=h, timeout=10)
            if r.status_code != 200: time.sleep(3); continue
            d = r.json().get("data", {}); issue, expire, athletes = d.get("issue_id"), d.get("expire_seconds", 50), d.get("athlete_list", [])
            if len(athletes) < 3: time.sleep(3); continue
            chosen = [a["id"] for a in random.sample(athletes, 3)]
            each_bet = Decimal(str(cfg["bet_amount_total"])).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            for aid in chosen:
                requests.post(f"{api}/sprint/bet", json={"issue_id": issue, "bet_group": "winner", "asset_type": cfg["asset_type"], "athlete_id": aid, "bet_amount": float(each_bet)}, headers=h, timeout=10)
                time.sleep(0.2)
            st["bets"] += 1
            for _ in range(int(expire) if isinstance(expire, (int, float)) else 50):
                if not cfg["global_running"] or st["stop"].is_set(): break
                time.sleep(1)
        except: pass
        time.sleep(2)

if __name__ == "__main__":
    Thread(target=lambda: [bot.remove_webhook(), bot.infinity_polling(timeout=10, long_polling_timeout=5)], daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
