from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess
import re
import time

app = FastAPI()

def get_peers():
    try:
        out = subprocess.check_output(
            "docker exec amnezia-awg awg show",
            shell=True
        ).decode()
    except:
        return []

    peers = out.split("peer: ")[1:]
    data = []

    for p in peers:
        key = p.split("\n")[0].strip()

        ip = re.search(r"allowed ips: (.*)", p)
        hs = re.search(r"latest handshake: (.*)", p)
        tr = re.search(r"transfer: (.*)", p)

        ip = ip.group(1) if ip else "-"
        hs = hs.group(1) if hs else "never"
        tr = tr.group(1) if tr else "0"

        online = "🟢" if "second" in hs else "⚫"

        data.append({
            "key": key,
            "ip": ip,
            "handshake": hs,
            "transfer": tr,
            "online": online
        })

    return data


@app.get("/", response_class=HTMLResponse)
def dashboard():

    peers = get_peers()

    cards = ""

    for p in peers:
        cards += f"""
        <div class="card">
            <div class="ip">{p['ip']}</div>
            <div class="status">{p['online']} {p['handshake']}</div>
            <div class="transfer">{p['transfer']}</div>
        </div>
        """

    return f"""
    <html>
    <head>
    <meta http-equiv="refresh" content="5">
    <style>
    body {{
        background:#0f172a;
        color:white;
        font-family:Arial;
        padding:20px
    }}

    .card {{
        background:#020617;
        padding:15px;
        margin:10px;
        border-radius:12px
    }}

    .ip {{
        font-size:18px;
        font-weight:bold
    }}

    .status {{
        margin-top:5px;
        color:#22c55e
    }}

    .transfer {{
        margin-top:5px;
        color:#94a3b8
    }}

    </style>
    </head>

    <body>
    <h2>Amnezia Users</h2>
    {cards}
    </body>
    </html>
    """