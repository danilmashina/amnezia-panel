from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import subprocess, re, os, time, json
from datetime import datetime

app = FastAPI()

# Логирование в файл
LOG_FILE = "/opt/amnezia/panel.log"
TRAFFIC_FILE = "/opt/amnezia/traffic.json"
PEERS_STATE_FILE = "/opt/amnezia/peers_state.json"

# Формат:
# {
#   "<ip/cidr>": {
#       "total": <bytes>,
#       "paused": <bool>
#   }
# }
peer_state = {}


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
        print(msg)
    except Exception:
        print(msg)


def load_peers_state():
    global peer_state
    try:
        if os.path.exists(PEERS_STATE_FILE):
            with open(PEERS_STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                normalized = {}
                for k, v in raw.items():
                    if isinstance(v, dict):
                        normalized[k] = {
                            "total": float(v.get("total", 0)),
                            "paused": bool(v.get("paused", False)),
                        }
                    else:
                        normalized[k] = {"total": float(v or 0), "paused": False}
                peer_state = normalized
            else:
                peer_state = {}
            log(f"[PEERS] Loaded state: {len(peer_state)} peers")
    except Exception as e:
        log(f"[PEERS] Error loading state: {e}")
        peer_state = {}


def save_peers_state():
    try:
        os.makedirs(os.path.dirname(PEERS_STATE_FILE), exist_ok=True)
        with open(PEERS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(peer_state, f)
    except Exception as e:
        log(f"[PEERS] Error saving state: {e}")


def ensure_state(ip_cidr):
    if ip_cidr not in peer_state or not isinstance(peer_state[ip_cidr], dict):
        peer_state[ip_cidr] = {"total": 0.0, "paused": False}
    return peer_state[ip_cidr]


load_peers_state()

# ---------------- helpers ----------------

def human(b):
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def bytes_from(v):
    m = re.match(r"([0-9.]+)\s*([A-Za-z]+)", (v or "").strip())
    if not m:
        return 0
    n = float(m.group(1))
    u = m.group(2)
    if u == "B":
        return n
    if u == "KiB":
        return n * 1024
    if u == "MiB":
        return n * 1024 * 1024
    if u == "GiB":
        return n * 1024 * 1024 * 1024
    if u == "TiB":
        return n * 1024 * 1024 * 1024 * 1024
    return n


# --------- Traffic File Management ---------

def get_traffic_data():
    defaults = {
        "all_time": 420.0 * 1024 * 1024 * 1024,
        "monthly": 0.0,
        "last_runtime_val": 0,
        "current_month": datetime.now().month,
    }

    try:
        if os.path.exists(TRAFFIC_FILE):
            with open(TRAFFIC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return defaults
            data.setdefault("all_time", defaults["all_time"])
            data.setdefault("monthly", defaults["monthly"])
            data.setdefault("last_runtime_val", defaults["last_runtime_val"])
            data.setdefault("current_month", defaults["current_month"])
            return data
        return defaults
    except Exception as e:
        log(f"[TRAFFIC] get_traffic_data error: {e}")
        return defaults


def save_traffic_data(data):
    try:
        os.makedirs(os.path.dirname(TRAFFIC_FILE), exist_ok=True)
        with open(TRAFFIC_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        log(f"[TRAFFIC] Save error: {e}")


def update_total_traffic(delta):
    try:
        data = get_traffic_data()
        now_month = datetime.now().month
        if data.get("current_month") != now_month:
            data["monthly"] = 0.0
            data["current_month"] = now_month

        data["all_time"] += delta
        data["monthly"] += delta
        save_traffic_data(data)
        return data
    except Exception as e:
        log(f"[TRAFFIC] update_total_traffic error: {e}")
        return get_traffic_data()


# --------- Peer Pause/Resume ---------

def set_peer_pause(ip_cidr, pause):
    ip = (ip_cidr or "").split("/")[0].strip()
    if not ip:
        return False, "bad ip"

    rules = [
        f"-s {ip} -j DROP",
        f"-d {ip} -j DROP",
    ]

    try:
        for r in rules:
            check = subprocess.run(
                f"docker exec amnezia-awg iptables -C FORWARD {r}",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            exists = check.returncode == 0

            if pause and not exists:
                subprocess.check_call(
                    f"docker exec amnezia-awg iptables -I FORWARD {r}",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if (not pause) and exists:
                subprocess.check_call(
                    f"docker exec amnezia-awg iptables -D FORWARD {r}",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        return True, "ok"
    except Exception as e:
        return False, str(e)


# --------- CPU ---------

def cpu():
    try:
        out = subprocess.check_output(
            "docker stats --no-stream --format '{{.CPUPerc}}' $(docker ps -q)",
            shell=True,
        ).decode().strip()

        total_cpu = 0
        for line in out.split("\n"):
            if line and "%" in line:
                total_cpu += float(line.replace("%", "").strip())

        return f"{total_cpu:.2f}%"
    except Exception:
        return "-"


# --------- RAM ---------

def ram():
    try:
        out = subprocess.check_output(
            "docker stats --no-stream --format '{{.MemUsage}}' $(docker ps -q)",
            shell=True,
        ).decode().strip()

        total_used = 0
        for line in out.split("\n"):
            if line and "/" in line:
                used_str = line.split("/")[0].strip()
                total_used += bytes_from(used_str)

        return f"{human(total_used)}/2.0 GB"
    except Exception:
        return "-"


# --------- DISK ---------

def disk():
    st = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free = st.f_bfree * st.f_frsize
    used = total - free
    total = round(total / 1024 / 1024 / 1024, 1)
    used = round(used / 1024 / 1024 / 1024, 1)
    return f"{used}/{total} GB"


# --------- PING ---------

def ping_vpn():
    try:
        o = subprocess.check_output(
            "ping -c 1 8.8.8.8",
            shell=True,
            timeout=5,
        ).decode()
        ms = re.search(r"time=([\d.]+)\s*ms", o)
        return ms.group(1) if ms else "-"
    except Exception:
        return "-"


# --------- SPEEDTEST ---------

def speedtest():
    try:
        result = subprocess.check_output(
            "speedtest -f json",
            shell=True,
            timeout=300,
            stderr=subprocess.DEVNULL,
        ).decode().strip()

        data = json.loads(result)
        download = data.get("download", {}).get("bandwidth", 0) * 8 / 1000000
        upload = data.get("upload", {}).get("bandwidth", 0) * 8 / 1000000

        return {"download": f"{download:.1f} Mbps", "upload": f"{upload:.1f} Mbps"}
    except Exception:
        return {"download": "-", "upload": "-"}


# --------- PEERS ---------

def peers():
    try:
        out = subprocess.check_output(
            "docker exec amnezia-awg wg show",
            shell=True,
        ).decode()
    except Exception as e:
        log(f"[PEERS] Error running wg show: {e}")
        return []

    blocks = out.split("peer: ")[1:]
    result = []
    total_new_traffic = 0
    changed = False

    for p in blocks:
        ip_m = re.search("allowed ips: (.*)", p)
        hs_m = re.search("latest handshake: (.*)", p)
        tr_m = re.search("transfer: (.*) received, (.*) sent", p)
        if not ip_m:
            continue

        ip = ip_m.group(1).strip()
        hs = hs_m.group(1) if hs_m else "never"

        online = False
        if "second" in hs:
            online = True
        if "minute" in hs:
            try:
                if int(hs.split()[0]) < 2:
                    online = True
            except Exception:
                pass

        state = ensure_state(ip)
        paused = bool(state.get("paused", False))
        if paused:
            online = False

        if tr_m:
            r = tr_m.group(1)
            s = tr_m.group(2)
            rb = bytes_from(r)
            sb = bytes_from(s)
            current_total = rb + sb

            prev_total = float(state.get("total", 0))
            if current_total < prev_total:
                diff = current_total
            else:
                diff = current_total - prev_total

            if diff > 0 and diff < 50 * 1024 * 1024 * 1024:
                total_new_traffic += diff

            if abs(current_total - prev_total) > 0:
                state["total"] = current_total
                changed = True

            tr = f"{human(rb)} ↓ {human(sb)} ↑ | Σ {human(current_total)}"
        else:
            tr = "0"

        hs_ru = hs
        hs_ru = hs_ru.replace("seconds", "сек")
        hs_ru = hs_ru.replace("second", "сек")
        hs_ru = hs_ru.replace("minutes", "мин")
        hs_ru = hs_ru.replace("minute", "мин")
        hs_ru = hs_ru.replace("hours", "ч")
        hs_ru = hs_ru.replace("hour", "ч")
        hs_ru = hs_ru.replace("ago", "назад")
        hs_ru = hs_ru.replace("never", "никогда")

        result.append({
            "ip": ip,
            "hs": hs_ru,
            "online": online,
            "paused": paused,
            "tr": tr,
        })

    if total_new_traffic > 0:
        update_total_traffic(total_new_traffic)

    if changed:
        save_peers_state()

    return result


# --------- API ---------

@app.get("/api")
def api():
    return peers()


@app.post("/api/peer/{peer_ip:path}/pause")
def pause_peer(peer_ip: str):
    ok, err = set_peer_pause(peer_ip, True)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=500)

    st = ensure_state(peer_ip)
    st["paused"] = True
    save_peers_state()
    return {"ok": True, "ip": peer_ip, "paused": True}


@app.post("/api/peer/{peer_ip:path}/resume")
def resume_peer(peer_ip: str):
    ok, err = set_peer_pause(peer_ip, False)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=500)

    st = ensure_state(peer_ip)
    st["paused"] = False
    save_peers_state()
    return {"ok": True, "ip": peer_ip, "paused": False}


@app.get("/stats")
def stats():
    return {
        "cpu": cpu(),
        "ram": ram(),
        "disk": disk(),
    }


@app.get("/ping")
def p():
    return {"ping": ping_vpn()}


@app.get("/speedtest")
def speed():
    return speedtest()


@app.get("/traffic")
def traffic():
    return get_traffic_data()


# --------- UI ---------

@app.get("/", response_class=HTMLResponse)
def ui():
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amnezia Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%);
            color: #e2e8f0;
            padding: 40px 20px;
            min-height: 100vh;
            position: relative;
            overflow-x: hidden;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 20% 50%, rgba(99, 102, 241, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 80%, rgba(139, 92, 246, 0.1) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }

        .header {
            margin-bottom: 50px;
            text-align: center;
        }

        .header h1 {
            font-size: 48px;
            font-weight: 700;
            background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
            letter-spacing: -1px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 15px;
            margin-bottom: 50px;
        }

        .stat-card {
            background: rgba(30, 41, 59, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            padding: 16px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
        }

        .stat-card:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: rgba(148, 163, 184, 0.4);
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(59, 130, 246, 0.1);
        }

        .stat-icon {
            font-size: 24px;
            margin-bottom: 8px;
        }

        .stat-label {
            font-size: 11px;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 16px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 8px;
            font-family: 'Courier New', monospace;
            word-break: break-word;
        }

        .stat-bar {
            width: 100%;
            height: 4px;
            background: rgba(71, 85, 105, 0.3);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 8px;
        }

        .stat-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease;
            background: linear-gradient(90deg, #3b82f6, #06b6d4);
        }

        .stat-fill.cpu {
            background: linear-gradient(90deg, #f97316, #ff6b35);
        }

        .stat-fill.ram {
            background: linear-gradient(90deg, #8b5cf6, #a78bfa);
        }

        .stat-fill.disk {
            background: linear-gradient(90deg, #10b981, #34d399);
        }

        .action-btn {
            width: 100%;
            margin-top: 8px;
            padding: 8px 12px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            border: none;
            border-radius: 6px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            font-family: 'Inter', sans-serif;
        }

        .action-btn.pause {
            background: linear-gradient(135deg, #ef4444, #dc2626);
        }

        .action-btn.resume {
            background: linear-gradient(135deg, #22c55e, #16a34a);
        }

        .action-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(59, 130, 246, 0.3);
        }

        .action-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .action-btn.speed {
            background: linear-gradient(135deg, #8b5cf6, #7c3aed);
        }

        .section-title {
            font-size: 24px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 30px;
            padding-bottom: 12px;
            border-bottom: 2px solid rgba(99, 102, 241, 0.3);
        }

        .peers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 24px;
        }

        .peer-card {
            background: rgba(30, 41, 59, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 16px;
            padding: 24px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .peer-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
        }

        .peer-card:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: rgba(99, 102, 241, 0.5);
            transform: translateY(-8px);
            box-shadow: 0 25px 50px rgba(99, 102, 241, 0.15);
        }

        .peer-name {
            font-size: 18px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 12px;
            cursor: pointer;
            transition: color 0.2s;
            word-break: break-all;
        }

        .peer-status {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
            font-weight: 600;
            font-size: 14px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        .status-dot.online {
            background: #10b981;
            box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
        }

        .status-dot.offline {
            background: #64748b;
            animation: none;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .peer-status.online { color: #10b981; }
        .peer-status.offline { color: #94a3b8; }

        .peer-ip {
            font-family: 'Courier New', monospace;
            font-size: 13px;
            color: #cbd5e1;
            background: rgba(15, 23, 42, 0.5);
            padding: 8px 12px;
            border-radius: 8px;
            margin-bottom: 12px;
            word-break: break-all;
            border: 1px solid rgba(71, 85, 105, 0.3);
        }

        .peer-info {
            font-size: 13px;
            color: #cbd5e1;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .peer-info-label { color: #94a3b8; }

        .peer-traffic {
            font-size: 13px;
            color: #06b6d4;
            font-weight: 600;
            margin-bottom: 12px;
            padding: 8px 12px;
            background: rgba(6, 182, 212, 0.1);
            border-radius: 8px;
            border-left: 3px solid #06b6d4;
        }

        .peer-rename {
            display: none;
            margin-top: 12px;
            gap: 8px;
        }

        .peer-rename.active { display: flex; }

        .peer-rename input {
            flex: 1;
            padding: 8px 12px;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(99, 102, 241, 0.5);
            border-radius: 8px;
            color: #e2e8f0;
            font-size: 13px;
            font-family: 'Inter', sans-serif;
        }

        .peer-rename button {
            padding: 8px 16px;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            font-size: 12px;
            font-family: 'Inter', sans-serif;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #94a3b8;
        }

        .traffic-info {
            font-size: 9px;
            color: #94a3b8;
            margin-top: 4px;
            padding: 4px 0;
            border-top: 1px solid rgba(148, 163, 184, 0.1);
        }

        .traffic-row {
            display: flex;
            justify-content: space-between;
            margin: 3px 0;
        }

        @media (max-width: 768px) {
            .header h1 { font-size: 36px; }
            .stats-grid { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
            .stat-card { padding: 16px; }
            .stat-value { font-size: 18px; }
            .peers-grid { grid-template-columns: 1fr; }
            .peer-card { padding: 16px; }
        }

    </style>
</head>

<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Amnezia Panel</h1>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-label">CPU</div>
                <div class="stat-value" id="cpu">-</div>
                <div class="stat-bar"><div class="stat-fill cpu" id="cpu-bar" style="width: 0%"></div></div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">💾</div>
                <div class="stat-label">RAM</div>
                <div class="stat-value" id="ram" style="font-size: 20px;">-</div>
                <div class="stat-bar"><div class="stat-fill ram" id="ram-bar" style="width: 0%"></div></div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">🗄️</div>
                <div class="stat-label">Disk</div>
                <div class="stat-value" id="disk" style="font-size: 20px;">-</div>
                <div class="stat-bar"><div class="stat-fill disk" id="disk-bar" style="width: 0%"></div></div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">🌐</div>
                <div class="stat-label">Ping (VPN)</div>
                <div class="stat-value" id="ping">-</div>
                <button class="action-btn" id="ping-btn" onclick="doPing()">Проверить</button>
            </div>

            <div class="stat-card">
                <div class="stat-icon">⚡</div>
                <div class="stat-label">Speedtest</div>
                <div class="stat-value" id="speed" style="font-size: 16px;">-</div>
                <button class="action-btn speed" id="speed-btn" onclick="doSpeedtest()">Начать</button>
            </div>

            <div class="stat-card">
                <div class="stat-icon">📡</div>
                <div class="stat-label">Трафик</div>
                <div class="stat-value" id="traffic" style="font-size: 18px;">-</div>
                <div class="traffic-info">
                    <div class="traffic-row"><span>За месяц:</span><span id="traffic-monthly">0 GB</span></div>
                    <div class="traffic-row"><span>Всего:</span><span id="traffic-total">0 GB</span></div>
                </div>
            </div>
        </div>

        <h2 class="section-title">Пользователи</h2>
        <div class="peers-grid" id="grid"></div>
    </div>

    <script>
        let editing = null;

        async function load() {
            if (editing) return;
            try {
                const r = await fetch('/api');
                const data = await r.json();

                const grid = document.getElementById('grid');
                grid.innerHTML = '';

                if (data.length === 0) {
                    grid.innerHTML = '<div class="empty-state"><p>📭 Нет активных пиров</p></div>';
                    return;
                }

                data.forEach(p => {
                    const name = localStorage[p.ip] || p.ip;
                    const paused = !!p.paused;

                    const card = document.createElement('div');
                    card.className = 'peer-card';
                    card.innerHTML = `
                        <div class="peer-name" onclick="rename('${p.ip}')">${name}</div>

                        <div class="peer-status ${p.online ? 'online' : 'offline'}">
                            <div class="status-dot ${p.online ? 'online' : 'offline'}"></div>
                            ${paused ? '● Пауза' : (p.online ? '● Онлайн' : '● Не активен')}
                        </div>

                        <div class="peer-ip">${p.ip}</div>

                        <div class="peer-info">
                            <span class="peer-info-label">Активность:</span>
                            <span>${p.hs}</span>
                        </div>

                        <div class="peer-traffic">📤 ${p.tr}</div>

                        <button class="action-btn ${paused ? 'resume' : 'pause'}" onclick="togglePeer('${encodeURIComponent(p.ip)}', ${paused})">
                            ${paused ? 'Возобновить' : 'Остановить'}
                        </button>

                        <div class="peer-rename" id="r${p.ip}">
                            <input id="i${p.ip}" placeholder="Введите имя пира" value="${name}">
                            <button onclick="save('${p.ip}')">OK</button>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            } catch (err) {
                console.error('Load error:', err);
            }
        }

        async function togglePeer(ipEnc, isPaused) {
            const endpoint = isPaused ? 'resume' : 'pause';
            try {
                const resp = await fetch(`/api/peer/${ipEnc}/${endpoint}`, { method: 'POST' });
                if (!resp.ok) {
                    const t = await resp.text();
                    alert('Ошибка: ' + t);
                }
            } catch (e) {
                alert('Ошибка сети');
            }
            load();
        }

        function rename(ip) {
            editing = ip;
            const renameEl = document.getElementById('r' + ip);
            renameEl.classList.add('active');
            document.getElementById('i' + ip).focus();
        }

        function save(ip) {
            const v = document.getElementById('i' + ip).value;
            if (v.trim()) localStorage[ip] = v;
            editing = null;
            load();
        }

        async function stats() {
            try {
                const r = await fetch('/stats');
                const s = await r.json();

                document.getElementById('cpu').innerText = s.cpu;
                document.getElementById('ram').innerText = s.ram;
                document.getElementById('disk').innerText = s.disk;

                if (s.cpu && s.cpu !== '-') {
                    const cpuVal = parseFloat(s.cpu);
                    if (!isNaN(cpuVal)) document.getElementById('cpu-bar').style.width = Math.min(cpuVal, 100) + '%';
                }

                if (s.ram && s.ram !== '-') {
                    const ramParts = s.ram.split('/');
                    if (ramParts.length === 2) {
                        const used = parseFloat(ramParts[0]);
                        const total = parseFloat(ramParts[1]);
                        if (!isNaN(used) && !isNaN(total) && total > 0) {
                            const ramVal = (used / total) * 100;
                            document.getElementById('ram-bar').style.width = Math.min(ramVal, 100) + '%';
                        }
                    }
                }

                if (s.disk && s.disk !== '-') {
                    const diskParts = s.disk.split('/');
                    if (diskParts.length === 2) {
                        const used = parseFloat(diskParts[0]);
                        const total = parseFloat(diskParts[1]);
                        if (!isNaN(used) && !isNaN(total) && total > 0) {
                            const diskVal = (used / total) * 100;
                            document.getElementById('disk-bar').style.width = Math.min(diskVal, 100) + '%';
                        }
                    }
                }
            } catch (err) {
                console.error('Stats error:', err);
            }
        }

        async function updateTraffic() {
            try {
                const r = await fetch('/traffic');
                const t = await r.json();
                const monthlyGB = (t.monthly / (1024 * 1024 * 1024)).toFixed(2);
                const totalGB = (t.all_time / (1024 * 1024 * 1024)).toFixed(2);
                document.getElementById('traffic-monthly').innerText = monthlyGB + ' GB';
                document.getElementById('traffic-total').innerText = totalGB + ' GB';
            } catch (err) {
                console.error('Traffic error:', err);
            }
        }

        async function doPing() {
            const btn = document.getElementById('ping-btn');
            btn.disabled = true;
            btn.innerText = 'Проверка...';
            try {
                const r = await fetch('/ping');
                const p = await r.json();
                document.getElementById('ping').innerText = (p.ping !== '-' ? p.ping + ' ms' : '-');
            } catch (err) {
                document.getElementById('ping').innerText = 'Ошибка';
            }
            setTimeout(() => {
                btn.disabled = false;
                btn.innerText = 'Проверить';
            }, 1000);
        }

        async function doSpeedtest() {
            const btn = document.getElementById('speed-btn');
            const speedEl = document.getElementById('speed');
            btn.disabled = true;
            btn.innerText = 'Тестирование...';
            speedEl.innerText = '⏳';

            try {
                const r = await fetch('/speedtest');
                const s = await r.json();
                speedEl.innerHTML = `<div style="font-size: 14px;">⬇️ ${s.download}<br>⬆️ ${s.upload}</div>`;
            } catch (err) {
                speedEl.innerText = 'Ошибка';
            }

            setTimeout(() => {
                btn.disabled = false;
                btn.innerText = 'Начать';
            }, 2000);
        }

        load();
        stats();
        updateTraffic();

        setInterval(() => {
            load();
            stats();
            updateTraffic();
        }, 3000);
    </script>
</body>
</html>
    """
