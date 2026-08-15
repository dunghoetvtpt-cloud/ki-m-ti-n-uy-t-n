import os
import random
import string
import requests
from urllib.parse import quote
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, session

app = Flask(__name__)
app.secret_key = "LINKTASKS_SUPER_GOLD_2026"

USER_DB = {}
VALID_CODES = {}

SEEDS_CONFIG = {
    1: {"name": "🌱 Mầm Đậu Xanh", "cost": 30, "grow_seconds": 60, "reward": 35, "icon": "🌱"},
    2: {"name": "🌽 Bắp Ngô Vàng", "cost": 60, "grow_seconds": 180, "reward": 70, "icon": "🌽"},
    3: {"name": "🥔 Khoai Tây Hoàng Gia", "cost": 120, "grow_seconds": 420, "reward": 140, "icon": "🥔"},
    4: {"name": "🍓 Dâu Tây Kim Cương", "cost": 250, "grow_seconds": 900, "reward": 290, "icon": "🍓"},
    5: {"name": "🍎 Táo Vàng Thần Tài", "cost": 500, "grow_seconds": 1800, "reward": 580, "icon": "🍎"}
}

def get_current_user():
    if 'user_id' not in session:
        session['user_id'] = "USER_" + ''.join(random.choices(string.digits, k=6))
    
    user_id = session['user_id']
    if user_id not in USER_DB:
        USER_DB[user_id] = {
            "balance": 5000.0,
            "links_today": 0,
            "ref_count": 0,
            "ref_earnings": 0,
            "mine_played": 0,
            "farm": {"seed_id": None, "plant_time": None, "ripe_time": None}
        }
    return user_id, USER_DB[user_id]

# --- HTML/CSS GIAO DIỆN SIÊU ĐẸP ---
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkTasks Gold - Game & Task</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #0b0f19; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .bg-card { background-color: #161e2e; }
        .border-gold { border-color: #eab308; }
        .text-gold { color: #facc15; }
        .bg-gold { background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%); }
        .bg-gold-glow { box-shadow: 0 0 20px rgba(234, 179, 8, 0.3); }
        
        /* Hiệu ứng Mine Card */
        .mine-btn {
            background: linear-gradient(145deg, #1e293b, #0f172a);
            box-shadow: inset 2px 2px 5px rgba(255,255,255,0.05), inset -2px -2px 5px rgba(0,0,0,0.5);
            transition: all 0.2s ease;
        }
        .mine-btn:hover { transform: translateY(-2px); border-color: #facc15; }
        .mine-btn:active { transform: scale(0.95); }
    </style>
</head>
<body class="flex flex-col md:flex-row min-h-screen">

    <aside class="w-full md:w-64 bg-card border-r border-slate-800 p-5 flex flex-col justify-between">
        <div>
            <div class="flex items-center gap-3 mb-8">
                <div class="w-10 h-10 bg-gold rounded-xl flex items-center justify-center font-black text-xl text-black shadow-lg">LT</div>
                <span class="text-xl font-extrabold tracking-wider">Link<span class="text-gold">Tasks</span></span>
            </div>

            <div class="bg-slate-900 border border-gold/30 p-4 rounded-2xl mb-6 flex items-center justify-between shadow-inner">
                <div>
                    <p class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">SỐ DƯ HIỆN TẠI</p>
                    <p id="user-balance" class="text-xl font-black text-gold">0 VNĐ</p>
                </div>
                <div class="w-10 h-10 bg-yellow-500/10 rounded-full flex items-center justify-center text-gold">
                    <i class="fa-solid fa-coins text-lg"></i>
                </div>
            </div>

            <nav class="space-y-2">
                <button onclick="showTab('mine')" id="nav-mine" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold bg-gold text-black shadow-lg">
                    <i class="fa-solid fa-bomb text-lg"></i> Dò Mìn Thần Tài
                </button>
                <button onclick="showTab('farm')" id="nav-farm" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold text-slate-400 hover:text-white hover:bg-slate-800 transition">
                    <i class="fa-solid fa-wheat-awn text-lg"></i> Nông Trại Vàng
                </button>
                <button onclick="showTab('task')" id="nav-task" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold text-slate-400 hover:text-white hover:bg-slate-800 transition">
                    <i class="fa-solid fa-list-check text-lg"></i> Làm Nhiệm Vụ
                </button>
            </nav>
        </div>
        <p id="user-id" class="text-xs text-slate-500 text-center pt-4 border-t border-slate-800">ID: USER_000000</p>
    </aside>

    <main class="flex-1 p-4 md:p-8 max-w-4xl mx-auto">

        <div id="tab-mine" class="space-y-6">
            <div class="bg-card p-6 rounded-3xl border border-slate-800 shadow-2xl relative overflow-hidden">
                <div class="absolute -top-10 -right-10 w-40 h-40 bg-yellow-500/10 rounded-full blur-3xl"></div>
                
                <div class="text-center mb-6">
                    <h2 class="text-2xl font-black tracking-wide text-gold flex items-center justify-center gap-2">
                        <i class="fa-solid fa-gem"></i> DÒ MÌN 3x3 GOLD
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">Lật ô may mắn - Tránh bom và nhân tiền thưởng gấp nhiều lần!</p>
                </div>

                <div class="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 mb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                    <div class="flex items-center gap-3 w-full sm:w-auto">
                        <span class="text-xs font-bold text-slate-400">Tiền cược:</span>
                        <select id="mine-bet" class="bg-slate-800 border border-slate-700 text-gold font-bold px-4 py-2 rounded-xl focus:outline-none focus:border-gold">
                            <option value="200">200 VNĐ</option>
                            <option value="500">500 VNĐ</option>
                            <option value="1000">1.000 VNĐ</option>
                            <option value="5000">5.000 VNĐ</option>
                        </select>
                    </div>
                    
                    <div class="text-center">
                        <p class="text-[10px] text-slate-400 font-bold">HỆ SỐ THƯỞNG</p>
                        <p id="mine-mult" class="text-xl font-black text-green-400">1.0x</p>
                    </div>

                    <button onclick="startMineGame()" id="btn-start-mine" class="w-full sm:w-auto bg-gold text-black font-extrabold px-6 py-2.5 rounded-xl shadow-lg hover:brightness-110 active:scale-95 transition">
                        BẮT ĐẦU CHƠI
                    </button>
                </div>

                <div id="mine-grid" class="grid grid-cols-3 gap-3 max-w-[300px] mx-auto mb-6 pointer-events-none opacity-50">
                    </div>

                <div class="text-center">
                    <p id="mine-status" class="text-sm font-bold text-yellow-400 mb-3">Hãy chọn tiền cược và bấm Bắt đầu!</p>
                    <button id="mine-cashout" onclick="cashoutMine()" class="hidden bg-gradient-to-r from-green-500 to-emerald-600 text-black font-black text-lg px-8 py-3 rounded-2xl shadow-xl hover:scale-105 active:scale-95 transition">
                        <i class="fa-solid fa-sack-dollar mr-2"></i> CHỐT LÃI RÚT TIỀN (<span id="mine-prize-text">0đ</span>)
                    </button>
                </div>
            </div>
        </div>

        <div id="tab-farm" class="hidden space-y-6">
            
            <div class="bg-card p-6 rounded-3xl border border-slate-800 shadow-2xl relative overflow-hidden">
                <h3 class="text-xl font-black text-gold mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-wheat-awn"></i> MẢNH ĐẤT NÔNG TRẠI
                </h3>

                <div id="farm-plot" class="bg-slate-900 border-2 border-dashed border-slate-700 rounded-2xl p-6 text-center flex flex-col items-center justify-center min-h-[160px]">
                    <p class="text-slate-500 text-sm font-semibold">Đang tải thông tin đất...</p>
                </div>
            </div>

            <div class="bg-card p-6 rounded-3xl border border-slate-800">
                <h4 class="text-lg font-bold mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-store text-gold"></i> Cửa Hàng Hạt Giống
                </h4>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div class="bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-gold/50 transition flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="text-3xl">🌱</span>
                            <div>
                                <p class="font-bold text-white">Mầm Đậu Xanh</p>
                                <p class="text-xs text-slate-400">Giá: <span class="text-gold font-bold">30đ</span> · Thu: <span class="text-green-400 font-bold">35đ</span></p>
                                <span class="text-[10px] text-slate-500 font-semibold">Thời gian: 1 phút</span>
                            </div>
                        </div>
                        <button onclick="plantSeed(1)" class="bg-gold text-black font-bold px-4 py-2 rounded-xl text-xs hover:brightness-110">Trồng</button>
                    </div>

                    <div class="bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-gold/50 transition flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="text-3xl">🌽</span>
                            <div>
                                <p class="font-bold text-white">Bắp Ngô Vàng</p>
                                <p class="text-xs text-slate-400">Giá: <span class="text-gold font-bold">60đ</span> · Thu: <span class="text-green-400 font-bold">70đ</span></p>
                                <span class="text-[10px] text-slate-500 font-semibold">Thời gian: 3 phút</span>
                            </div>
                        </div>
                        <button onclick="plantSeed(2)" class="bg-gold text-black font-bold px-4 py-2 rounded-xl text-xs hover:brightness-110">Trồng</button>
                    </div>

                    <div class="bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-gold/50 transition flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="text-3xl">🥔</span>
                            <div>
                                <p class="font-bold text-white">Khoai Tây Hoàng Gia</p>
                                <p class="text-xs text-slate-400">Giá: <span class="text-gold font-bold">120đ</span> · Thu: <span class="text-green-400 font-bold">140đ</span></p>
                                <span class="text-[10px] text-slate-500 font-semibold">Thời gian: 7 phút</span>
                            </div>
                        </div>
                        <button onclick="plantSeed(3)" class="bg-gold text-black font-bold px-4 py-2 rounded-xl text-xs hover:brightness-110">Trồng</button>
                    </div>

                    <div class="bg-slate-900 p-4 rounded-2xl border border-slate-800 hover:border-gold/50 transition flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="text-3xl">🍎</span>
                            <div>
                                <p class="font-bold text-white">Táo Vàng Thần Tài</p>
                                <p class="text-xs text-slate-400">Giá: <span class="text-gold font-bold">500đ</span> · Thu: <span class="text-green-400 font-bold">580đ</span></p>
                                <span class="text-[10px] text-slate-500 font-semibold">Thời gian: 30 phút</span>
                            </div>
                        </div>
                        <button onclick="plantSeed(5)" class="bg-gold text-black font-bold px-4 py-2 rounded-xl text-xs hover:brightness-110">Trồng</button>
                    </div>
                </div>
            </div>
        </div>

        <div id="tab-task" class="hidden">
            <div class="bg-card p-6 rounded-3xl border border-slate-800">
                <h3 class="text-xl font-bold text-gold mb-2">Làm Nhiệm Vụ Kiếm VNĐ</h3>
                <p class="text-sm text-slate-400">Hoàn thành vượt link để nhận tiền thưởng trực tiếp vào số dư tài khoản.</p>
            </div>
        </div>

    </main>

    <script>
        // INIT GRID DÒ MÌN TRỐNG
        function initGrid() {
            let html = '';
            for(let i=0; i<9; i++) {
                html += `<button onclick="pickMine(${i})" class="mine-btn h-20 rounded-2xl border border-slate-700/50 text-2xl font-black flex items-center justify-center">❓</button>`;
            }
            document.getElementById('mine-grid').innerHTML = html;
        }
        initGrid();

        function updateUserData() {
            fetch('/api/user-info').then(r=>r.json()).then(data=>{
                document.getElementById('user-balance').innerText = data.balance.toLocaleString('vi-VN') + ' VNĐ';
                document.getElementById('user-id').innerText = 'ID: ' + data.user_id;
            });
        }

        function showTab(tab) {
            ['mine', 'farm', 'task'].forEach(t => {
                document.getElementById('tab-' + t).classList.add('hidden');
                let nav = document.getElementById('nav-' + t);
                if(nav) nav.className = "w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold text-slate-400 hover:text-white hover:bg-slate-800 transition";
            });

            document.getElementById('tab-' + tab).classList.remove('hidden');
            let activeNav = document.getElementById('nav-' + tab);
            if(activeNav) activeNav.className = "w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold bg-gold text-black shadow-lg";

            if(tab === 'farm') loadFarm();
        }

        // GAME DÒ MÌN
        function startMineGame() {
            let bet = document.getElementById('mine-bet').value;
            fetch('/api/mine/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({bet: parseInt(bet)})
            }).then(r=>r.json()).then(data=>{
                if(data.error) return alert(data.error);
                renderMineGrid(data.grid);
                document.getElementById('mine-grid').classList.remove('pointer-events-none', 'opacity-50');
                document.getElementById('mine-status').innerText = 'Hãy chọn 1 ô an toàn!';
                document.getElementById('mine-mult').innerText = '1.0x';
                document.getElementById('mine-cashout').classList.add('hidden');
                updateUserData();
            });
        }

        function renderMineGrid(grid) {
            let html = '';
            grid.forEach((cell, idx) => {
                let cellIcon = cell === '?' ? '❓' : cell;
                let bgStyle = cell === '💎' ? 'bg-green-500/20 border-green-500' : (cell === '💥' ? 'bg-red-500/20 border-red-500' : '');
                html += `<button onclick="pickMine(${idx})" class="mine-btn h-20 rounded-2xl border border-slate-700/50 text-2xl font-black flex items-center justify-center ${bgStyle}">${cellIcon}</button>`;
            });
            document.getElementById('mine-grid').innerHTML = html;
        }

        function pickMine(idx) {
            fetch('/api/mine/pick', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index: idx})
            }).then(r=>r.json()).then(data=>{
                renderMineGrid(data.grid);
                if(data.status === 'BOOM') {
                    document.getElementById('mine-status').innerText = '💥 BẠN ĐÃ TRÚNG MÌN (THUA CUỘC)!';
                    document.getElementById('mine-grid').classList.add('pointer-events-none', 'opacity-50');
                    document.getElementById('mine-cashout').classList.add('hidden');
                    updateUserData();
                } else if(data.status === 'CONTINUE') {
                    document.getElementById('mine-mult').innerText = data.multiplier + 'x';
                    document.getElementById('mine-prize-text').innerText = data.prize.toLocaleString('vi-VN') + 'đ';
                    document.getElementById('mine-status').innerText = `Xuất sắc! Nhân hệ số ${data.multiplier}x`;
                    document.getElementById('mine-cashout').classList.remove('hidden');
                }
            });
        }

        function cashoutMine() {
            fetch('/api/mine/cashout', {method: 'POST'}).then(r=>r.json()).then(data=>{
                alert(data.message);
                document.getElementById('mine-grid').classList.add('pointer-events-none', 'opacity-50');
                document.getElementById('mine-cashout').classList.add('hidden');
                document.getElementById('mine-status').innerText = 'Đã chốt lãi thành công!';
                updateUserData();
            });
        }

        // GAME NÔNG TRẠI
        function loadFarm() {
            fetch('/api/farm/status').then(r=>r.json()).then(data=>{
                let plot = document.getElementById('farm-plot');
                if(!data.planted) {
                    plot.innerHTML = `
                        <div class="text-4xl mb-2">🤎</div>
                        <p class="text-gold font-bold">Đất Đang Trống</p>
                        <p class="text-xs text-slate-400 mt-1">Chọn loại hạt giống bên dưới để bắt đầu gieo mầm!</p>
                    `;
                } else if(data.is_ripe) {
                    plot.innerHTML = `
                        <div class="text-5xl mb-2 animate-bounce">${data.icon}</div>
                        <p class="text-green-400 font-extrabold text-lg">${data.seed_name} Đã Chín!</p>
                        <button onclick="harvestFarm()" class="mt-3 bg-gradient-to-r from-green-500 to-emerald-600 text-black font-black px-6 py-2.5 rounded-xl text-sm shadow-lg hover:scale-105">
                            THU HOẠCH (+${data.reward}đ)
                        </button>
                    `;
                } else {
                    plot.innerHTML = `
                        <div class="text-4xl mb-2 animate-pulse">${data.icon}</div>
                        <p class="text-gold font-bold">Đang Trồng ${data.seed_name}</p>
                        <p class="text-xs text-slate-300 font-semibold mt-1">⏳ Còn lại: <span class="text-yellow-400 font-bold">${data.remaining_secs} giây</span></p>
                    `;
                    setTimeout(loadFarm, 2000); // Tự động làm mới đếm ngược
                }
            });
        }

        function plantSeed(seedId) {
            fetch('/api/farm/plant', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({seed_id: seedId})
            }).then(r=>r.json()).then(data=>{
                alert(data.message);
                updateUserData();
                loadFarm();
            });
        }

        function harvestFarm() {
            fetch('/api/farm/harvest', {method: 'POST'}).then(r=>r.json()).then(data=>{
                alert(data.message);
                updateUserData();
                loadFarm();
            });
        }

        updateUserData();
    </script>
</body>
</html>
"""

# --- BACKEND API ---

@app.rout
