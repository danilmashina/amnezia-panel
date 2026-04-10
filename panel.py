from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, os, time, json
from datetime import datetime

app = FastAPI()

TRAFFIC_FILE = "/opt/amnezia/traffic.json"

# ---------------- helpers ----------------

def parse_mem(v):
    m = re.match(r"([0-9.]+)([A-Za-z]+)", v.strip())
    if not m:
        return 0
    n = float(m.group(1))
    u = m.group(2)
    if u == "KiB": return n * 1024
    if u == "MiB": return n * 1024 * 1024
    if u == "GiB": return n * 1024 * 1024 * 1024
    return n

def human(b):
    for u in ["B","KB","MB","GB","TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024

def bytes_from(v):
    m = re.match(r"([0-9.]+)\s*([A-Za-z]+)", v)
    n = float(m.group(1))
    u = m.group(2)
    if u == "KiB": return n * 1024
    if u == "MiB": return n * 1024 * 1024
    if u == "GiB": return n * 1024 * 1024 * 1024
    return n

# --------- Traffic File Management ---------

def get_traffic_data():
    if not os.path.exists(TRAFFIC_FILE):
        return {"monthly": 0, "total": 0, "last_month": 0}
    
    try:
        with open(TRAFFIC_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"monthly": 0, "total": 0, "last_month": 0}

def save_traffic_data(data):
    try:
        os.makedirs(os.path.dirname(TRAFFIC_FILE), exist_ok=True)
        with open(TRAFFIC_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def update_traffic(bytes_amount):
    data = get_traffic_data()
    current_month = datetime.now().month
    
    # Если месяц изменился, сбросить месячный счетчик
    if 'last_month' in data and data['last_month'] != current_month:
        data['monthly'] = 0
    
    data['monthly'] += bytes_amount
    data['total'] += bytes_amount
    data['last_month'] = current_month
    
    save_traffic_data(data)

# --------- CPU docker ---------

def cpu():
    try:
        out = subprocess.check_output(
            "docker stats amnezia-awg --no-stream --format '{{.CPUPerc}}'",
            shell=True
        ).decode().strip()
        return out
    except:
        return "-"

# --------- RAM ALL containers ---------

def ram():
    try:
        out = subprocess.check_output("free -b", shell=True).decode().splitlines()[1].split()
        total = int(out[1])
        used = int(out[2])
        return f"{human(used)}/{human(total)}"
    except:
        return "-"

# --------- DISK ---------

def disk():
    st = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free = st.f_bfree * st.f_frsize
    used = total - free
    total = round(total/1024/1024/1024,1)
    used = round(used/1024/1024/1024,1)
    return f"{used}/{total} GB"

# --------- PING через VPN ---------

def ping_vpn():
    try:
        o = subprocess.check_output(
            "ping -c 1 138.124.99.81",
            shell=True,
            timeout=5
        ).decode()
        ms = re.search("time=(.*) ms", o).group(1)
        return ms
    except:
        return "-"

# --------- SPEEDTEST ---------

def speedtest():
    try:
        # Проверяем наличие speedtest-cli
        result = subprocess.check_output(
            "speedtest-cli --simple",
            shell=True,
            timeout=300
        ).decode().strip()
        
        lines = result.split('\n')
        if len(lines) >= 2:
            download = float(lines[0])  # Mbps
            upload = float(lines[1])    # Mbps
            return {"download": f"{download:.1f} Mbps", "upload": f"{upload:.1f} Mbps"}
        return {"download": "-", "upload": "-"}
    except:
        return {"download": "-", "upload": "-"}

# --------- PEERS ---------

def peers():
    out = subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    peers = out.split("peer: ")[1:]
    result = []

    for p in peers:
        ip = re.search("allowed ips: (.*)", p)
        hs = re.search("latest handshake: (.*)", p)

        ip = ip.group(1)
        hs = hs.group(1) if hs else "never"

        online = False

        if "second" in hs:
            online = True

        if "minute" in hs:
            n = int(hs.split()[0])
            if n < 2:
                online = True

        m = re.search(
            "transfer: (.*) received, (.*) sent",
            p
        )

        if m:
            r = m.group(1)
            s = m.group(2)

            rb = bytes_from(r)
            sb = bytes_from(s)

            total = rb + sb

            tr = f"{human(rb)} ↓ {human(sb)} ↑ | Σ {human(total)}"
        else:
            tr = "0"

        hs = hs.replace("seconds","сек")
        hs = hs.replace("second","сек")
        hs = hs.replace("minutes","мин")
        hs = hs.replace("minute","мин")
        hs = hs.replace("hours","ч")
        hs = hs.replace("hour","ч")
        hs = hs.replace("ago","назад")
        hs = hs.replace("never","никогда")

        result.append({
            "ip": ip,
            "hs": hs,
            "online": online,
            "tr": tr
        })

    return result

# --------- API ---------

@app.get("/api")
def api():
    return peers()

@app.get("/stats")
def stats():
    return {
        "cpu": cpu(),
        "ram": ram(),
        "disk": disk()
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

        .header p {
            color: #94a3b8;
            font-size: 16px;
            font-weight: 300;
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

        .action-btn:hover:not(:disabled) {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(59, 130, 246, 0.3);
        }

        .action-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .action-btn:active:not(:disabled) {
            transform: translateY(0);
        }

        .action-btn.speed {
            background: linear-gradient(135deg, #8b5cf6, #7c3aed);
        }

        .action-btn.speed:hover:not(:disabled) {
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            box-shadow: 0 10px 20px rgba(139, 92, 246, 0.3);
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

        .peer-name:hover {
            color: #93c5fd;
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

        .peer-status.online {
            color: #10b981;
        }

        .peer-status.offline {
            color: #94a3b8;
        }

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

        .peer-info-label {
            color: #94a3b8;
        }

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

        .peer-rename.active {
            display: flex;
        }

        .peer-rename input {
            flex: 1;
            padding: 8px 12px;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(99, 102, 241, 0.5);
            border-radius: 8px;
            color: #e2e8f0;
            font-size: 13px;
            transition: border-color 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .peer-rename input:focus {
            outline: none;
            border-color: rgba(99, 102, 241, 1);
            background: rgba(15, 23, 42, 0.9);
        }

        .peer-rename button {
            padding: 8px 16px;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 12px;
            font-family: 'Inter', sans-serif;
        }

        .peer-rename button:hover {
            background: linear-gradient(135deg, #4f46e5, #4338ca);
            transform: translateY(-2px);
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
            .header h1 {
                font-size: 36px;
            }

            .stats-grid {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 12px;
            }

            .stat-card {
                padding: 16px;
            }

            .stat-value {
                font-size: 18px;
            }

            .peers-grid {
                grid-template-columns: 1fr;
            }

            .peer-card {
                padding: 16px;
            }
        }

    </style>
</head>

<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Amnezia Panel</h1>
            <p>Мониторинг и управление WireGuard пирами</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-label">CPU</div>
                <div class="stat-value" id="cpu">-</div>
                <div class="stat-bar">
                    <div class="stat-fill cpu" id="cpu-bar" style="width: 0%"></div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">💾</div>
                <div class="stat-label">RAM</div>
                <div class="stat-value" id="ram" style="font-size: 20px;">-</div>
                <div class="stat-bar">
                    <div class="stat-fill ram" id="ram-bar" style="width: 0%"></div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">🗄️</div>
                <div class="stat-label">Disk</div>
                <div class="stat-value" id="disk" style="font-size: 20px;">-</div>
                <div class="stat-bar">
                    <div class="stat-fill disk" id="disk-bar" style="width: 0%"></div>
                </div>
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
                    <div class="traffic-row">
                        <span>За месяц:</span>
                        <span id="traffic-monthly">0 GB</span>
                    </div>
                    <div class="traffic-row">
                        <span>Всего:</span>
                        <span id="traffic-total">0 GB</span>
                    </div>
                </div>
            </div>
        </div>

        <h2 class="section-title">Активные пиры</h2>
        <div class="peers-grid" id="grid"></div>
    </div>

    <script>
        let editing = null;

        async function load() {
            if (editing) return;

            try {
                const r = await fetch("/api");
                const data = await r.json();

                const grid = document.getElementById('grid');
                grid.innerHTML = "";

                if (data.length === 0) {
                    grid.innerHTML = '<div class="empty-state"><p>📭 Нет активных пиров</p></div>';
                    return;
                }

                data.forEach(p => {
                    const name = localStorage[p.ip] || p.ip;

                    const card = document.createElement('div');
                    card.className = 'peer-card';
                    card.innerHTML = `
                        <div class="peer-name" onclick="rename('${p.ip}')">${name}</div>
                        
                        <div class="peer-status ${p.online ? 'online' : 'offline'}">
                            <div class="status-dot ${p.online ? 'online' : 'offline'}"></div>
                            ${p.online ? '● Онлайн' : '● Не активен'}
                        </div>

                        <div class="peer-ip">${p.ip}</div>

                        <div class="peer-info">
                            <span class="peer-info-label">Активность:</span>
                            <span>${p.hs}</span>
                        </div>

                        <div class="peer-traffic">📤 ${p.tr}</div>

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

        function rename(ip) {
            editing = ip;
            const renameEl = document.getElementById("r" + ip);
            renameEl.classList.add('active');
            document.getElementById("i" + ip).focus();
        }

        function save(ip) {
            const v = document.getElementById("i" + ip).value;
            if (v.trim()) {
                localStorage[ip] = v;
            }
            editing = null;
            load();
        }

        async function stats() {
            try {
                const r = await fetch("/stats");
                const s = await r.json();

                document.getElementById("cpu").innerText = s.cpu;
                document.getElementById("ram").innerText = s.ram;
                document.getElementById("disk").innerText = s.disk;

                if (s.cpu && s.cpu !== "-") {
                    const cpuVal = parseFloat(s.cpu);
                    if (!isNaN(cpuVal)) {
                        document.getElementById("cpu-bar").style.width = Math.min(cpuVal, 100) + "%";
                    }
                }

                if (s.ram && s.ram !== "-") {
                    const ramParts = s.ram.split("/");
                    if (ramParts.length === 2) {
                        const used = parseFloat(ramParts[0]);
                        const total = parseFloat(ramParts[1]);
                        if (!isNaN(used) && !isNaN(total) && total > 0) {
                            const ramVal = (used / total) * 100;
                            document.getElementById("ram-bar").style.width = Math.min(ramVal, 100) + "%";
                        }
                    }
                }

                if (s.disk && s.disk !== "-") {
                    const diskParts = s.disk.split("/");
                    if (diskParts.length === 2) {
                        const used = parseFloat(diskParts[0]);
                        const total = parseFloat(diskParts[1]);
                        if (!isNaN(used) && !isNaN(total) && total > 0) {
                            const diskVal = (used / total) * 100;
                            document.getElementById("disk-bar").style.width = Math.min(diskVal, 100) + "%";
                        }
                    }
                }
            } catch (err) {
                console.error('Stats error:', err);
            }
        }

        async function updateTraffic() {
            try {
                const r = await fetch("/traffic");
                const t = await r.json();

                const monthlyGB = (t.monthly / (1024 * 1024 * 1024)).toFixed(2);
                const totalGB = (t.total / (1024 * 1024 * 1024)).toFixed(2);

                document.getElementById("traffic-monthly").innerText = monthlyGB + " GB";
                document.getElementById("traffic-total").innerText = totalGB + " GB";
            } catch (err) {
                console.error('Traffic error:', err);
            }
        }

        async function doPing() {
            const btn = document.getElementById('ping-btn');
            btn.disabled = true;
            btn.innerText = 'Проверка...';

            try {
                const r = await fetch("/ping");
                const p = await r.json();
                document.getElementById("ping").innerText = (p.ping !== "-" ? p.ping + " ms" : "-");
            } catch (err) {
                console.error('Ping error:', err);
                document.getElementById("ping").innerText = "Ошибка";
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
                const r = await fetch("/speedtest");
                const s = await r.json();
                speedEl.innerHTML = `<div style="font-size: 14px;">⬇️ ${s.download}<br>⬆️ ${s.upload}</div>`;
            } catch (err) {
                console.error('Speedtest error:', err);
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
