from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import subprocess
import re
import json
import os

app = FastAPI()

DB = "users.json"

def load_names():
    if not os.path.exists(DB):
        return {}
    return json.load(open(DB))

def save_names(data):
    json.dump(data, open(DB,"w"))

def get_peers():
    out = subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

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

        online = "online" if "second" in hs or "minute" in hs else "offline"

        data.append({
            "key": key,
            "ip": ip,
            "handshake": hs,
            "transfer": tr,
            "online": online
        })

    return data


@app.get("/save")
def save(ip:str,name:str):
    db = load_names()
    db[ip]=name
    save_names(db)
    return {"ok":True}


@app.get("/", response_class=HTMLResponse)
def ui():

    peers = get_peers()
    names = load_names()

    cards=""

    for p in peers:

        name = names.get(p["ip"],p["ip"])
        status = "🟢" if p["online"]=="online" else "⚫"

        cards += f"""
        <div class="card">
            <div class="top">
                <div class="name">{name}</div>
                <div class="status">{status}</div>
            </div>

            <div class="ip">{p['ip']}</div>
            <div class="hs">{p['handshake']}</div>
            <div class="tr">{p['transfer']}</div>

            <input placeholder="Имя..." id="i_{p['ip']}"/>
            <button onclick="save('{p['ip']}')">Save</button>
        </div>
        """

    return f"""
<html>
<head>
<meta http-equiv="refresh" content="5">

<style>

body {{
background:#020617;
color:white;
font-family:Arial;
padding:20px
}}

.grid {{
display:grid;
grid-template-columns:repeat(auto-fill,300px);
gap:15px
}}

.card {{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:12px
}}

.name {{
font-size:18px;
font-weight:bold
}}

.status {{
float:right
}}

.ip {{
color:#94a3b8;
margin-top:5px
}}

.hs {{
color:#22c55e;
margin-top:5px
}}

.tr {{
color:#38bdf8;
margin-top:5px
}}

input {{
margin-top:10px;
width:100%;
padding:5px;
background:#020617;
border:1px solid #1e293b;
color:white
}}

button {{
margin-top:5px;
width:100%;
padding:5px;
background:#2563eb;
border:0;
color:white;
cursor:pointer
}}

</style>

<script>
function save(ip){{
name=document.getElementById("i_"+ip).value
fetch("/save?ip="+ip+"&name="+name)
}}
</script>

</head>

<body>

<h2>Amnezia Users</h2>

<div class="grid">
{cards}
</div>

</body>
</html>
"""
