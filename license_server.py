import time
import random
import requests
from decimal import Decimal, ROUND_DOWN
from threading import Thread, Lock, Event

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
        account_threads[key] = {"total_profit": Decimal("0"), "total_bets": 0, "wins": 0, "losses": 0, "streak_loss": 0, "current_build": Decimal("1"), "random_stop": Event()}
    return account_threads[key]

# Engine 1: Vua Thoát Hiểm
def run_escape_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["escape"]
    acc_st = get_account_state("escape", uid)
    headers = {"Content-Type": "application/json", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey, "Accept": "application/json", "xb-language": "vi-VN"}
    session = requests.Session()
    def enter_room(r_id):
        try:
            resp = session.post("https://api.escapemaster.net/escape_game/enter_room", json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": r_id}, headers=headers, timeout=5)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except: return False
    def place_bet(r_id, amt):
        try:
            resp = session.post("https://api.escapemaster.net/escape_game/bet", json={"asset_type": cfg["asset_type"], "user_id": uid, "room_id": r_id, "bet_amount": amt}, headers=headers, timeout=5)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except: return False
    def get_my_joined():
        try:
            resp = session.get("https://api.escapemaster.net/escape_game/my_joined", params={"asset": cfg["asset_type"], "page": 1, "page_size": 10}, headers=headers, timeout=5)
            if resp.status_code == 200: return resp.json().get("data", {}).get("items", [])
        except: pass
        return []
    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            items = get_my_joined()
            if items:
                latest_issue = str(items[0].get("issue_id"))
                if acc_st.get("current_issue") != latest_issue:
                    acc_st["current_issue"] = latest_issue
                    acc_st["total_bets"] += 1
                    room = random.randint(1, 8)
                    bet_amt = float(cfg["base_bet"])
                    if enter_room(room):
                        time.sleep(0.3)
                        if place_bet(room, bet_amt):
                            time.sleep(22)
                            for _ in range(12):
                                history_items = get_my_joined()
                                matched = [it for it in history_items if str(it.get("issue_id")) == latest_issue]
                                if matched:
                                    item_res = matched[0]
                                    award = float(item_res.get("award_amount", 0))
                                    bet_val = float(item_res.get("bet_amount", bet_amt))
                                    is_killed = not (award > bet_val)
                                    killer_room = item_res.get("killed_room_id") or item_res.get("killer_room") or item_res.get("killer")
                                    if killer_room is not None:
                                        try:
                                            k_int = int(killer_room)
                                            if k_int in cfg["killer_stats"]: cfg["killer_stats"][k_int] += 1
                                            if is_killed:
                                                acc_st["losses"] += 1; acc_st["total_profit"] -= Decimal(str(bet_val))
                                            else:
                                                acc_st["wins"] += 1; acc_st["total_profit"] += Decimal(str(award - bet_val))
                                            break
                                        except: pass
                                time.sleep(2)
        except: pass
        time.sleep(3)

# Engine 2: Đua Tốc Độ
def run_sprint_bot_engine(chat_id, uid, skey):
    cfg = get_user_config(chat_id)["sprint"]
    acc_st = get_account_state("sprint", uid)
    base_api = "https://api.sprintrun.win"
    headers = {"accept": "*/*", "content-type": "application/json", "origin": "https://sprintrun.win", "referer": "https://sprintrun.win/", "user-agent": "Mozilla/5.0", "user-id": str(uid), "user-login": "login_v2", "user-secret-key": skey}
    while cfg["global_running"] and not acc_st["random_stop"].is_set():
        try:
            if acc_st["streak_loss"] >= cfg["lose_limit"]:
                acc_st["streak_loss"] = 0
                acc_st["current_build"] = Decimal(str(cfg["bet_amount_total"]))
                time.sleep(cfg["rest_rounds"] * 60)
                continue
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
            random.shuffle(athletes)
            chosen = [a["id"] for a in random.sample(athletes, 3)]
            each_bet = acc_st["current_build"].quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            total_bet_amount = each_bet * Decimal(len(chosen))
            for aid in chosen:
                requests.post(f"{base_api}/sprint/bet", json={"issue_id": issue_id, "bet_group": "winner", "asset_type": cfg["asset_type"], "athlete_id": aid, "bet_amount": float(each_bet)}, headers=headers, timeout=10)
                time.sleep(0.2)
            acc_st["total_bets"] += 1
            for _ in range(int(expire) if isinstance(expire, (int, float)) else 50):
                if not cfg["global_running"] or acc_st["random_stop"].is_set(): break
                time.sleep(1)
            winner = None
            for _ in range(30):
                res_r = requests.get(f"{base_api}/sprint/issue_result?issue={issue_id}&asset={cfg['asset_type']}", headers=headers, timeout=10)
                if res_r.status_code == 200:
                    rank = res_r.json().get("data", {}).get("athlete_rank", [])
                    if rank: winner = rank[0]; break
                time.sleep(1)
            if winner in chosen:
                acc_st["total_profit"] += (each_bet * Decimal("5")) - total_bet_amount
                acc_st["wins"] += 1; acc_st["streak_loss"] = 0; acc_st["current_build"] = Decimal(str(cfg["bet_amount_total"]))
            else:
                acc_st["total_profit"] -= total_bet_amount
                acc_st["losses"] += 1; acc_st["streak_loss"] += 1; acc_st["current_build"] = acc_st["current_build"] * Decimal(str(cfg["lose_multiplier"]))
        except: pass
        time.sleep(2)
