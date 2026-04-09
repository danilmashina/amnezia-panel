from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, json, os

app = FastAPI()
DB="users.json"

def load():
    if not os.path.exists(DB):
        return {}
    return json.load(open(DB))

def save(db):
    json.dump(db,open(DB,"w"))

def parse_online(hs):
    if "second" in hs:
        return True
    if "minute" in hs:
        n=int(hs.split()[0])
        if n < 2:
            return True
    return False

def peers():
    out=subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    peers=out.split("peer: ")[1:]
    data=[]

    for p in peers:
        ip=re.search("allowed ips: (.*)",p)
        hs=re.search("latest handshake: (.*)",p)
        tr=re.search("transfer: (.*)",p)

        ip=ip.group(1) if ip else "-"
        hs=hs.group(1) if hs else "never"
        tr=tr.group(1) if tr else "0"

        data.append({
            "ip":ip,
            "hs":hs,
            "tr":tr,
            "online":parse_online(hs)
        })
    return data

def system():
    load = open("/proc/loadavg").read().split()[0]
    mem = open("/proc/meminfo").read()

    total = int(re.search(r"MemTotal:\s+(\d+)",mem).group(1))
    free = int(re.search(r"MemAvailable:\s+(\d+)",mem).group(1))

    used = total - free

    total = round(total/1024/1024,1)
    used = round(used/1024/1024,1)

    up = open("/proc/uptime").read().split()[0]
    up = int(float(up))

    h = up//3600
    m = (up%3600)//60

    return {
        "cpu": load,
        "ram": f"{used}/{total} GB",
        "uptime": f"{h}h {m}m"
    }

@app.get("/api")
def api():
    return peers()

@app.get("/stats")
def stats():
    return system()

@app.get("/save")
def rename(ip:str,name:str):
    db=load()
    db[ip]=name
    save(db)
    return {"ok":True}

@app.get("/",response_class=HTMLResponse)
def ui():
    return """
<html>
<head>

<style>
body{
margin:0;
background:#020617;
color:white;
font-family:Inter,Arial;
display:flex
}

.sidebar{
width:220px;
background:#020617;
border-right:1px solid #1e293b;
padding:20px;
height:100vh
}

.logo{
font-size:18px;
font-weight:bold;
margin-bottom:30px
}

.menu{
color:#94a3b8;
margin:10px 0;
cursor:pointer
}

.menu:hover{
color:white
}

.main{
flex:1;
padding:20px
}

.top{
display:flex;
gap:15px;
margin-bottom:20px
}

.stat{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:12px;
min-width:130px
}

.grid{
display:grid;
grid-template-columns:repeat(auto-fill,320px);
gap:15px
}

.card{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:14px;
transition:.2s
}

.card:hover{
border-color:#2563eb
}

.name{
font-size:16px;
font-weight:bold
}

.online{color:#22c55e}
.offline{color:#6b7280}

.ip{color:#94a3b8;margin-top:4px}
.tr{color:#38bdf8;margin-top:4px}

.search{
padding:8px;
background:#020617;
border:1px solid #1e293b;
color:white;
width:300px;
margin-bottom:15px
}

input{
width:100%;
margin-top:6px;
background:#020617;
border:1px solid #1e293b;
color:white;
padding:6px;
border-radius:6px
}

button{
width:100%;
margin-top:6px;
background:#2563eb;
border:0;
padding:7px;
color:white;
border-radius:6px
}
</style>

<script>

async function load(){

r=await fetch("/api")
data=await r.json()

online=0
offline=0

data.sort((a,b)=> b.online-a.online)

grid=document.getElementById("grid")
grid.innerHTML=""

search=document.getElementById("search").value.toLowerCase()

data.forEach(p=>{

name=localStorage[p.ip]||p.ip

if(!name.toLowerCase().includes(search) &&
!p.ip.includes(search)) return

if(p.online) online++
else offline++

grid.innerHTML+=`
<div class="card">

<div class="name">${name}</div>

<div class="${p.online?'online':'offline'}">
${p.online?'● Online':'● Offline'}
</div>

<div class="ip">${p.ip}</div>
<div>${p.hs}</div>
<div class="tr">${p.tr}</div>

<input id="i_${p.ip}" placeholder="Имя">

<button onclick="save('${p.ip}')">Save</button>

</div>
`

})

document.getElementById("online").innerText=online
document.getElementById("offline").innerText=offline
document.getElementById("total").innerText=data.length
}

async function stats(){
r=await fetch("/stats")
s=await r.json()

cpu.innerText=s.cpu
ram.innerText=s.ram
uptime.innerText=s.uptime
}

function save(ip){
name=document.getElementById("i_"+ip).value
localStorage[ip]=name
fetch("/save?ip="+ip+"&name="+name)
}

setInterval(()=>{
load()
stats()
},3000)

</script>

</head>

<body onload="load();stats()">

<div class="sidebar">
<div class="logo">Amnezia Panel</div>
<div class="menu">Dashboard</div>
<div class="menu">Peers</div>
<div class="menu">Logs</div>
<div class="menu">Settings</div>
</div>

<div class="main">

<div class="top">

<div class="stat">
Online<br><span id="online"></span>
</div>

<div class="stat">
Offline<br><span id="offline"></span>
</div>

<div class="stat">
Total<br><span id="total"></span>
</div>

<div class="stat">
CPU<br><span id="cpu"></span>
</div>

<div class="stat">
RAM<br><span id="ram"></span>
</div>

<div class="stat">
Uptime<br><span id="uptime"></span>
</div>

</div>

<input id="search" class="search" placeholder="Search..." onkeyup="load()">

<div id="grid" class="grid"></div>

</div>

</body>
</html>
"""
