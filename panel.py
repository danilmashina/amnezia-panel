from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, json, os, time

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
        if n < 10:
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
        hs=hs.group(1) if hs else "никогда"
        tr=tr.group(1) if tr else "0"

        online=parse_online(hs)

        data.append({
            "ip":ip,
            "hs":hs,
            "tr":tr,
            "online":online
        })

    return data


def disk():
    st=os.statvfs("/")
    total=st.f_blocks*st.f_frsize
    free=st.f_bfree*st.f_frsize
    used=total-free

    total=round(total/1024/1024/1024,1)
    used=round(used/1024/1024/1024,1)

    return f"{used}/{total} GB"


def ping():
    try:
        out=subprocess.check_output(
            "ping -c 1 1.1.1.1",
            shell=True
        ).decode()

        ms=re.search("time=(.*) ms",out).group(1)
        return ms
    except:
        return "-"


def to_bytes(v):

    n=float(v.split()[0])
    u=v.split()[1]

    if u=="KiB": return n*1024
    if u=="MiB": return n*1024*1024
    if u=="GiB": return n*1024*1024*1024

    return n


def human(v):

    for u in ["B","KB","MB","GB","TB"]:
        if v<1024:
            return f"{v:.1f} {u}"
        v/=1024


def total_traffic():

    out=subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    rx=0
    tx=0

    for line in out.splitlines():

        if "transfer:" in line:

            m=re.search("transfer: (.*) received, (.*) sent",line)
            if not m: continue

            r=m.group(1)
            s=m.group(2)

            rx+=to_bytes(r)
            tx+=to_bytes(s)

    return human(rx+tx)


def system():

    load = open("/proc/loadavg").read().split()[0]

    mem = open("/proc/meminfo").read()

    total = int(re.search(r"MemTotal:\s+(\d+)",mem).group(1))
    free = int(re.search(r"MemAvailable:\s+(\d+)",mem).group(1))

    used = total - free

    total = round(total/1024/1024,1)
    used = round(used/1024/1024,1)

    return {
        "cpu": load,
        "ram": f"{used}/{total} GB",
        "disk": disk(),
        "ping": ping(),
        "traffic": total_traffic()
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
background:#020617;
color:white;
font-family:Inter,Arial;
padding:20px
}

.top{
display:flex;
gap:15px;
margin-bottom:20px;
flex-wrap:wrap
}

.stat{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:12px;
min-width:150px
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

.rename{
margin-top:8px;
display:flex;
justify-content:flex-end;
}

.rename button{
padding:4px 10px;
font-size:12px;
background:#1d4ed8;
border-radius:6px;
border:0;
color:white;
cursor:pointer
}

input.rename-input{
display:none;
width:100%;
margin-top:6px;
background:#020617;
border:1px solid #1e293b;
color:white;
padding:6px;
border-radius:6px
}

</style>

<script>

let editing=false

async function load(){

if(editing) return

r=await fetch("/api")
data=await r.json()

online=0

data.sort((a,b)=> b.online-a.online)

grid.innerHTML=""

search=document.getElementById("search").value.toLowerCase()

data.forEach(p=>{

name=localStorage[p.ip]||p.ip

if(!name.toLowerCase().includes(search) &&
!p.ip.includes(search)) return

if(p.online) online++

grid.innerHTML+=card(p,name)

})

onlineEl.innerText=online
}


function card(p,name){

return `
<div class="card">

<div class="name">${name}</div>

<div class="${p.online?'online':'offline'}">
${p.online?'🟢 Онлайн':'⚫ Не активен'}
</div>

<div class="ip">${p.ip}</div>

<div>
Последняя активность: ${p.hs}
</div>

<div class="tr">
Трафик: ${p.tr}
</div>

<input class="rename-input" id="i_${p.ip}" placeholder="Имя">

<div class="rename">
<button onclick="rename('${p.ip}')">Переименовать</button>
</div>

</div>
`
}


function rename(ip){

input=document.getElementById("i_"+ip)

if(input.style.display=="block"){

save(ip)
editing=false
input.style.display="none"

}else{

editing=true
input.style.display="block"
input.focus()

}
}


function save(ip){
name=document.getElementById("i_"+ip).value
localStorage[ip]=name
fetch("/save?ip="+ip+"&name="+name)
}


async function stats(){

r=await fetch("/stats")
s=await r.json()

cpu.innerText=s.cpu
ram.innerText=s.ram
disk.innerText=s.disk
ping.innerText=s.ping+" ms"
traffic.innerText=s.traffic

}


setInterval(()=>{
load()
stats()
},3000)

</script>

</head>

<body onload="load();stats()">

<h2>Amnezia Panel</h2>

<div class="top">

<div class="stat">
Онлайн<br><span id="onlineEl"></span>
</div>

<div class="stat">
CPU<br><span id="cpu"></span>
</div>

<div class="stat">
RAM<br><span id="ram"></span>
</div>

<div class="stat">
Диск<br><span id="disk"></span>
</div>

<div class="stat">
Ping<br><span id="ping"></span>
</div>

<div class="stat">
Трафик<br><span id="traffic"></span>
</div>

</div>

<input id="search" class="search" placeholder="Поиск..." onkeyup="load()">

<div id="grid" class="grid"></div>

</body>
</html>
"""
