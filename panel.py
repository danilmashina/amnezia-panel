from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import subprocess, re, json, os, datetime, time

app = FastAPI()

DB="names.json"
TRAFFIC="traffic.json"

def load(path):
    if not os.path.exists(path):
        return {}
    return json.load(open(path))

def save(path,data):
    json.dump(data,open(path,"w"))

def bytes_from(v):

    n=float(v.split()[0])
    u=v.split()[1]

    if u=="KiB": return n*1024
    if u=="MiB": return n*1024*1024
    if u=="GiB": return n*1024*1024*1024

    return n

def human(b):

    for u in ["B","KB","MB","GB","TB"]:
        if b<1024:
            return f"{b:.1f} {u}"
        b/=1024

def cpu():

    with open("/proc/stat") as f:
        l=f.readline()

    v=list(map(int,l.split()[1:]))

    idle=v[3]
    total=sum(v)

    time.sleep(0.1)

    with open("/proc/stat") as f:
        l=f.readline()

    v2=list(map(int,l.split()[1:]))

    idle2=v2[3]
    total2=sum(v2)

    cpu=100*(1-(idle2-idle)/(total2-total))

    return round(cpu,1)

def ram():

    m=open("/proc/meminfo").read()

    total=int(re.search(r"MemTotal:\s+(\d+)",m).group(1))
    free=int(re.search(r"MemAvailable:\s+(\d+)",m).group(1))

    used=total-free

    total=round(total/1024/1024,1)
    used=round(used/1024/1024,1)

    return f"{used}/{total} GB"

def disk():

    st=os.statvfs("/")

    total=st.f_blocks*st.f_frsize
    free=st.f_bfree*st.f_frsize

    used=total-free

    return f"{round(used/1024/1024/1024,1)}/{round(total/1024/1024/1024,1)} GB"

def ping():

    try:
        o=subprocess.check_output("ping -c 1 1.1.1.1",shell=True).decode()
        ms=re.search("time=(.*) ms",o).group(1)
        return ms
    except:
        return "-"

def peers():

    out=subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    peers=out.split("peer: ")[1:]

    res=[]

    for p in peers:

        ip=re.search("allowed ips: (.*)",p)
        hs=re.search("latest handshake: (.*)",p)
        tr=re.search("transfer: (.*)",p)

        ip=ip.group(1)
        hs=hs.group(1) if hs else "never"

        online=False

        if "second" in hs:
            online=True

        if "minute" in hs:
            n=int(hs.split()[0])
            if n < 3:
                online=True

        if tr:

            m=re.search("transfer: (.*) received, (.*) sent",p)

            r=m.group(1)
            s=m.group(2)

            rb=bytes_from(r)
            sb=bytes_from(s)

            total=rb+sb

            tr=f"{human(rb)} ↓ {human(sb)} ↑ | Σ {human(total)}"

        else:
            tr="0"

        hs=hs.replace("seconds","сек")
        hs=hs.replace("second","сек")
        hs=hs.replace("minutes","мин")
        hs=hs.replace("minute","мин")
        hs=hs.replace("hours","ч")
        hs=hs.replace("hour","ч")
        hs=hs.replace("ago","назад")

        res.append({
            "ip":ip,
            "hs":hs,
            "online":online,
            "tr":tr
        })

    return res

@app.get("/api")
def api():
    return peers()

@app.get("/stats")
def stats():

    return {
        "cpu":cpu(),
        "ram":ram(),
        "disk":disk()
    }

@app.get("/ping")
def p():
    return {"ping":ping()}

@app.get("/",response_class=HTMLResponse)
def ui():

    return """
<html>
<head>

<style>

body{
background:#020617;
color:white;
font-family:Inter;
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
padding:14px;
border-radius:12px;
min-width:140px
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
transition:0.2s
}

.card:hover{
border-color:#3b82f6;
box-shadow:0 0 20px rgba(59,130,246,.2)
}

.name{
font-weight:bold;
cursor:pointer;
font-size:16px
}

.online{color:#22c55e}
.offline{color:#64748b}
.tr{color:#38bdf8}

.rename{
display:none;
margin-top:8px
}

button{
background:#2563eb;
border:none;
padding:6px 12px;
border-radius:6px;
color:white;
cursor:pointer
}

</style>

<script>

let editing=null

async function load(){

if(editing) return

r=await fetch("/api")
data=await r.json()

grid.innerHTML=""

data.forEach(p=>{

name=localStorage[p.ip]||p.ip

grid.innerHTML+=`

<div class="card">

<div class="name" onclick="rename('${p.ip}')">
${name}
</div>

<div class="${p.online?'online':'offline'}">
${p.online?'● Онлайн':'● Не активен'}
</div>

<div>${p.ip}</div>

<div>Активность: ${p.hs}</div>

<div class="tr">${p.tr}</div>

<div class="rename" id="r${p.ip}">
<input id="i${p.ip}">
<button onclick="save('${p.ip}')">OK</button>
</div>

</div>
`
})
}

function rename(ip){

editing=ip
document.getElementById("r"+ip).style.display="block"

}

function save(ip){

v=document.getElementById("i"+ip).value

localStorage[ip]=v

editing=null

load()
}

async function stats(){

r=await fetch("/stats")
s=await r.json()

cpu.innerText=s.cpu+" %"
ram.innerText=s.ram
disk.innerText=s.disk

}

async function doPing(){

r=await fetch("/ping")
p=await r.json()

ping.innerText=p.ping+" ms"

}

setInterval(()=>{load();stats()},3000)

</script>

</head>

<body onload="load();stats()">

<h2>Amnezia Panel</h2>

<div class="top">

<div class="stat">CPU<br><span id="cpu"></span></div>
<div class="stat">RAM<br><span id="ram"></span></div>
<div class="stat">Disk<br><span id="disk"></span></div>

<div class="stat">
Ping<br>
<span id="ping">-</span>
<br>
<button onclick="doPing()">ping</button>
</div>

</div>

<div id="grid" class="grid"></div>

</body>
</html>
"""
