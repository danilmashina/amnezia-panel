from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, os, time, json
from datetime import datetime

app = FastAPI()

TRAFFIC_FILE = "/opt/amnezia/traffic.json"

# ---------------- helpers ----------------

def human(b):
    for u in ["B","KB","MB","GB","TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def bytes_from(v):
    m = re.match(r"([0-9.]+)\s*([A-Za-z]+)", v)
    if not m:
        return 0
    n = float(m.group(1))
    u = m.group(2).strip()
    if u == "KiB": return n * 1024
    if u == "MiB": return n * 1024 * 1024
    if u == "GiB": return n * 1024 * 1024 * 1024
    if u == "B": return n
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
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        total = round(total/1024/1024/1024,1)
        used = round(used/1024/1024/1024,1)
        return f"{used}/{total} GB"
    except:
        return "-"

# --------- PING через VPN ---------

def ping_vpn():
    try:
        o = subprocess.check_output(
            "ping -c 1 138.124.99.81",
            shell=True,
            timeout=5
        ).decode()
        ms = re.search(r"time=([\d.]+)", o)
        if ms:
            return ms.group(1)
        return "-"
    except:
        return "-"

# --------- SPEEDTEST ---------

def speedtest():
    try:
        result = subprocess.check_output(
            "speedtest --simple",
            shell=True,
            timeout=300
        ).decode().strip()
        
        lines = result.split('\n')
        if len(lines) >= 2:
            try:
                download = float(lines[0])
                upload = float(lines[1])
                return {"download": f"{download:.1f}", "upload": f"{upload:.1f}"}
            except:
                return {"download": "-", "upload": "-"}
        return {"download": "-", "upload": "-"}
    except Exception as e:
        print(f"Speedtest error: {e}")
        return {"download": "-", "upload": "-"}

# --------- PEERS ---------

def peers():
    try:
        out = subprocess.check_output(
            "docker exec amnezia-awg wg show",
            shell=True
        ).decode()
    except Exception as e:
        print(f"Error running wg show: {e}")
        return []

    peers_list = out.split("peer: ")[1:]
    result = []
    total_traffic = 0

    for p in peers_list:
        # Ищем allowed ips - может быть с маской типа 10.8.1.4/32
        ip_match = re.search(r"allowed ips: ([\d.]+(?:/\d+)?)", p)
        hs_match = re.search(r"latest handshake: (.*)", p)

        if not ip_match:
            continue
            
        ip = ip_match.group(1).strip()
        # Убираем маску если есть
        if "/" in ip:
            ip = ip.split("/")[0]
            
        hs = hs_match.group(1) if hs_match else "never"

        online = False
        if "second" in hs:
            online = True
        elif "minute" in hs:
            try:
                n = int(hs.split()[0])
                if n < 2:
                    online = True
            except:
                pass

        tr = "0"
        rb = 0
        sb = 0
        
        m = re.search(r"transfer: ([\d.]+\s+[A-Za-z]+) received, ([\d.]+\s+[A-Za-z]+) sent", p)
        if m:
            r = m.group(1)
            s = m.group(2)

            rb = bytes_from(r)
            sb = bytes_from(s)
            total = rb + sb
            total_traffic += total

            tr = f"{human(rb)} ↓ {human(sb)} ↑ | Σ {human(total)}"

        hs = hs.replace("seconds","сек").replace("second","сек").replace("minutes","мин").replace("minute","мин").replace("hours","ч").replace("hour","ч").replace("ago","назад").replace("never","никогда")

        result.append({
            "ip": ip,
            "hs": hs,
            "online": online,
            "tr": tr
        })

    if total_traffic > 0:
        update_traffic(total_traffic)

    return result    if total_traffic > 0:
        update_traffic(total_traffic)

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
    return {"ping_vpn": ping_vpn()}

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
            padding: 20px;
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
            margin-bottom: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 5px;
        }

        .header p {
            color: #94a3b8;
            font-size: 12px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            margin-bottom: 40px;
        }

        .stat-card {
            background: rgba(30, 41, 59, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            padding: 12px;
            transition: all 0.3s ease;
        }

        .stat-card:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: rgba(148, 163, 184, 0.4);
            transform: translateY(-3px);
        }

        .stat-icon {
            font-size: 18px;
            margin-bottom: 4px;
        }

        .stat-label {
            font-size: 10px;
            color: #94a3b8;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .stat-value {
            font-size: 14px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 6px;
            font-family: 'Courier New', monospace;
            word-break: break-word;
        }

        .stat-bar {
            width: 100%;
            height: 4px;
            background: rgba(71, 85, 105, 0.3);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 6px;
        }

        .stat-fill {
            height: 100%;
            border-radius: 2px;
            transition: width 0.5s ease;
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
            margin-top: 6px;
            padding: 6px 10px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            border: none;
            border-radius: 6px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 10px;
            text-transform: uppercase;
            font-family: 'Inter', sans-serif;
        }

        .action-btn:hover:not(:disabled) {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            transform: translateY(-2px);
        }

        .action-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .section-title {
            font-size: 18px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(99, 102, 241, 0.3);
        }

        .peers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }

        .peer-card {
            background: rgba(30, 41, 59, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            padding: 16px;
            transition: all 0.3s ease;
        }

        .peer-card:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: rgba(99, 102, 241, 0.5);
            transform: translateY(-5px);
        }

        .peer-name {
            font-size: 16px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 10px;
            cursor: pointer;
            word-break: break-all;
        }

        .peer-name:hover {
            color: #93c5fd;
        }

        .peer-status {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            font-weight: 600;
            font-size: 12px;
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
            font-size: 11px;
            color: #cbd5e1;
            background: rgba(15, 23, 42, 0.5);
            padding: 6px 10px;
            border-radius: 6px;
            margin-bottom: 10px;
            word-break: break-all;
            border: 1px solid rgba(71, 85, 105, 0.3);
        }

        .peer-info {
            font-size: 11px;
            color: #cbd5e1;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }

        .peer-traffic {
            font-size: 11px;
            color: #06b6d4;
            font-weight: 600;
            margin-bottom: 10px;
            padding: 6px 10px;
            background: rgba(6, 182, 212, 0.1);
            border-radius: 6px;
            border-left: 3px solid #06b6d4;
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #94a3b8;
        }

        .traffic-info {
            font-size: 9px;
            color: #94a3b8;
            margin-top: 3px;
            padding: 3px 0;
            border-top: 1px solid rgba(148, 163, 184, 0.1);
        }

        .traffic-row {
            display: flex;
            justify-content: space-between;
            margin: 2px 0;
        }

    </style>
</head>

<body>
    <div class="container">
        <div class="header">
            <h1>Shield Amnezia Panel</h1>
            <p>Monitoring and management of WireGuard peers</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">CPU</div>
                <div class="stat-label">CPU</div>
                <div class="stat-value" id="cpu">-</div>
                <div class="stat-bar">
                    <div class="stat-fill cpu" id="cpu-bar" style="width: 0%"></div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">RAM</div>
                <div class="stat-label">RAM</div>
                <div class="stat-value" id="ram" style="font-size: 12px;">-</div>
                <div class="stat-bar">
                    <div class="stat-fill ram" id="ram-bar" style="width: 0%"></div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">DISK</div>
                <div class="stat-label">Disk</div>
                <div class="stat-value" id="disk" style="font-size: 12px;">-</div>
                <div class="stat-bar">
                    <div class="stat-fill disk" id="disk-bar" style="width: 0%"></div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon">PING</div>
                <div class="stat-label">Ping (VPN)</div>
                <div class="stat-value" id="ping-vpn">-</div>
                <button class="action-btn" id="ping-vpn-btn" onclick="doPingVPN()">Check</button>
            </div>

            <div class="stat-card">
                <div class="stat-icon">SPEED</div>
                <div class="stat-label">Speedtest</div>
                <div class="stat-value" id="speed" style="font-size: 11px;">-</div>
                <button class="action-btn" id="speed-btn" onclick="doSpeedtest()">Start</button>
            </div>

            <div class="stat-card">
                <div class="stat-icon">TRAFFIC</div>
                <div class="stat-label">Traffic</div>
                <div class="stat-value" id="traffic" style="font-size: 12px;">-</div>
                <div class="traffic-info">
                    <div class="traffic-row">
                        <span>Monthly:</span>
                        <span id="traffic-monthly">0 GB</span>
                    </div>
                    <div class="traffic-row">
                        <span>Total:</span>
                        <span id="traffic-total">0 GB</span>
                    </div>
                </div>
            </div>
        </div>

        <h2 class="section-title">Active Peers</h2>
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

                if (!data || data.length === 0) {
                    grid.innerHTML = '<div class="empty-state"><p>No active peers</p></div>';
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
                            ${p.online ? 'Online' : 'Offline'}
                        </div>

                        <div class="peer-ip">${p.ip}</div>

                        <div class="peer-info">
                            <span>Activity:</span>
                            <span>${p.hs}</span>
                        </div>

                        <div class="peer-traffic">${p.tr}</div>
                    `;

                    grid.appendChild(card);
                });
            } catch (err) {
                console.error('Load error:', err);
            }
        }

        function rename(ip) {
            editing = ip;
            const input = prompt('Enter peer name:', localStorage[ip] || ip);
            if (input) {
                localStorage[ip] = input;
                load();
            }
            editing = null;
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

        async function doPingVPN() {
            const btn = document.getElementById('ping-vpn-btn');
            btn.disabled = true;
            btn.innerText = 'Checking...';

            try {
                const r = await fetch("/ping");
                const p = await r.json();
                document.getElementById("ping-vpn").innerText = (p.ping_vpn !== "-" ? p.ping_vpn + " ms" : "-");
            } catch (err) {
                console.error('Ping error:', err);
                document.getElementById("ping-vpn").innerText = "Error";
            }

            setTimeout(() => {
                btn.disabled = false;
                btn.innerText = 'Check';
            }, 1000);
        }

        async function doSpeedtest() {
            const btn = document.getElementById('speed-btn');
            const speedEl = document.getElementById('speed');
            btn.disabled = true;
            btn.innerText = 'Testing...';
            speedEl.innerText = 'Wait...';

            try {
                const r = await fetch("/speedtest");
                const s = await r.json();
                speedEl.innerHTML = `<div style="font-size: 11px;">D: ${s.download} Mbps<br>U: ${s.upload} Mbps</div>`;
            } catch (err) {
                console.error('Speedtest error:', err);
                speedEl.innerText = 'Error';
            }

            setTimeout(() => {
                btn.disabled = false;
                btn.innerText = 'Start';
            }, 2000);
        }

        load();
        stats();
        updateTraffic();

        setInterval(() => {
            load();
            stats();
            updateTraffic();
        }, 10000);
    </script>
</body>
</html>
    """
