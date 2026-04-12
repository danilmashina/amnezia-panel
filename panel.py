from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, os, time, json
from datetime import datetime

app = FastAPI()

# --- ПУТИ К ФАЙЛАМ ---
TRAFFIC_FILE = "/opt/amnezia/traffic.json"
PEERS_STATE_FILE = "/opt/amnezia/peers_state.json"
USERS_FILE = "/opt/amnezia/users.json"
LOG_FILE = "/opt/amnezia/panel.log"

def log(msg):
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except: pass

# --- ЛОГИКА ТРАФИКА (ИСПРАВЛЕНА) ---
def get_traffic_data():
    # Твои 420 ГБ заложены в стартовое значение
    defaults = {"all_time_bytes": 450971566080, "monthly_bytes": 450971566080, "current_month": datetime.now().month}
    try:
        if os.path.exists(TRAFFIC_FILE):
            with open(TRAFFIC_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return defaults

def save_traffic_data(data):
    with open(TRAFFIC_FILE, 'w') as f:
        json.dump(data, f)

def update_global_counters(delta):
    data = get_traffic_data()
    now_month = datetime.now().month
    if data.get("current_month") != now_month:
        data["monthly_bytes"] = 0
        data["current_month"] = now_month
    
    data["all_time_bytes"] += delta
    data["monthly_bytes"] += delta
    save_traffic_data(data)

# --- РАБОТА С ПИРАМИ ---
last_peer_totals = {}
def load_peers_state():
    global last_peer_totals
    if os.path.exists(PEERS_STATE_FILE):
        try:
            with open(PEERS_STATE_FILE, 'r') as f:
                last_peer_totals = json.load(f)
        except: last_peer_totals = {}

def save_peers_state():
    with open(PEERS_STATE_FILE, 'w') as f:
        json.dump(last_peer_totals, f)

def get_names():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# --- API ЭНДПОИНТЫ ---
@app.get("/api")
def api_peers():
    load_peers_state()
    try:
        out = subprocess.check_output("docker exec amnezia-awg awg show all dump", shell=True).decode().strip()
    except: return []

    lines = out.split('\n')
    result, total_delta, now, names = [], 0, int(time.time()), get_names()

    for line in lines:
        parts = line.split('\t')
        if len(parts) < 8: continue
        
        pk, hs, rx, tx = parts[1], int(parts[4]), int(parts[5]), int(parts[6])
        current_total = rx + tx
        prev_total = last_peer_totals.get(pk, 0)
        
        # Считаем только разницу (дельту)
        diff = current_total if current_total < prev_total else current_total - prev_total
        if 0 < diff < 10 * 1024**3: # Защита от скачков
            total_delta += diff
            last_peer_totals[pk] = current_total

        result.append({
            "name": names.get(pk, pk[:8] + "..."),
            "ip": parts[3],
            "status": "Online" if (now - hs) < 180 and hs > 0 else "Offline",
            "tr": f"{round(rx/1024**2,1)} MB ↓ {round(tx/1024**2,1)} MB ↑",
            "hs": datetime.fromtimestamp(hs).strftime('%H:%M:%S') if hs > 0 else "никогда"
        })

    if total_delta > 0:
        update_global_counters(total_delta)
        save_peers_state()
    return result

@app.get("/stats")
def get_stats():
    try:
        cpu = subprocess.check_output("docker stats --no-stream --format '{{.CPUPerc}}' amnezia-awg", shell=True).decode().strip()
        return {"cpu": cpu, "ram": "Доступно", "disk": "OK"}
    except: return {"cpu": "-", "ram": "-", "disk": "-"}

@app.get("/traffic")
def get_traffic():
    d = get_traffic_data()
    return {
        "monthly": f"{round(d['monthly_bytes'] / 1024**3, 2)} GB",
        "total": f"{round(d['all_time_bytes'] / 1024**3, 2)} GB"
    }

@app.get("/ping")
def get_ping():
    try:
        out = subprocess.check_output("ping -c 1 8.8.8.8", shell=True).decode()
        ms = re.search(r"time=([\d.]+)", out).group(1)
        return {"ping": ms}
    except: return {"ping": "-"}

@app.get("/speedtest")
def do_speedtest():
    try:
        out = subprocess.check_output("speedtest-cli --simple", shell=True).decode()
        dl = re.search(r"Download: ([\d.]+)", out).group(1)
        ul = re.search(r"Upload: ([\d.]+)", out).group(1)
        return {"download": dl + " Mbps", "upload": ul + " Mbps"}
    except: return {"download": "N/A", "upload": "N/A"}

# --- ТВОЙ КРАСИВЫЙ ДИЗАЙН ---
@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Amnezia AWG Control</title>
        <style>
            body { background: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; margin: 0; padding: 20px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: #1e293b; padding: 20px; border-radius: 16px; border: 1px solid #334155; }
            .card h3 { color: #94a3b8; font-size: 12px; text-transform: uppercase; margin: 0 0 10px; }
            .val { font-size: 28px; font-weight: bold; color: #38bdf8; }
            table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 16px; overflow: hidden; }
            th, td { padding: 16px; text-align: left; border-bottom: 1px solid #334155; }
            th { background: #334155; color: #94a3b8; font-size: 13px; }
            .online { color: #4ade80; font-weight: bold; }
            .offline { color: #f87171; }
            .btn { background: #38bdf8; color: #0f172a; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="grid">
            <div class="card"><h3>Трафик (Все время)</h3><div id="t-all" class="val">...</div></div>
            <div class="card"><h3>Трафик (Месяц)</h3><div id="t-mon" class="val">...</div></div>
            <div class="card"><h3>Пинг</h3><div id="ping" class="val">-</div><br><button class="btn" onclick="checkPing()">Проверить</button></div>
            <div class="card"><h3>Скорость</h3><div id="speed" class="val">-</div><br><button class="btn" id="s-btn" onclick="runSpeed()">Начать</button></div>
        </div>
        <table>
            <thead><tr><th>Имя</th><th>Статус</th><th>Активность</th><th>Трафик</th><th>IP</th></tr></thead>
            <tbody id="peers"></tbody>
        </table>
        <script>
            async function load() {
                const r = await fetch('/api'); const d = await r.json();
                document.getElementById('peers').innerHTML = d.map(p => `
                    <tr>
                        <td><strong>${p.name}</strong></td>
                        <td class="${p.status.toLowerCase()}">${p.status}</td>
                        <td>${p.hs}</td>
                        <td>${p.tr}</td>
                        <td><small>${p.ip}</small></td>
                    </tr>`).join('');
            }
            async function updateTraffic() {
                const r = await fetch('/traffic'); const d = await r.json();
                document.getElementById('t-all').innerText = d.total;
                document.getElementById('t-mon').innerText = d.monthly;
            }
            async function checkPing() {
                const r = await fetch('/ping'); const d = await r.json();
                document.getElementById('ping').innerText = d.ping + ' ms';
            }
            async function runSpeed() {
                const b = document.getElementById('s-btn'); b.disabled = true; b.innerText = '...';
                const r = await fetch('/speedtest'); const d = await r.json();
                document.getElementById('speed').innerHTML = `<small>⬇️ ${d.download}<br>⬆️ ${d.upload}</small>`;
                b.disabled = false; b.innerText = 'Начать';
            }
            setInterval(load, 5000); setInterval(updateTraffic, 30000);
            load(); updateTraffic();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
