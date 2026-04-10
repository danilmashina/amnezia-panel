from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess, re, json, os, time, datetime

app = FastAPI()
DB="users.json"
TRAFFIC_DB="traffic.json"


def load_json(path):
    if not os.path.exists(path):
        return {}
    return json.load(open(path))


def save_json(path,data):
    json.dump(data,open(path,"w"))


def translate_time(t):

    t=t.replace("seconds","сек")
    t=t.replace("second","сек")
    t=t.replace("minutes","мин")
    t=t.replace("minute","мин")
    t=t.replace("hours","ч")
    t=t.replace("hour","ч")

    return t


def parse_online(hs):

    if "second" in hs:
        return True

    if "minute" in hs:
        n=int(hs.split()[0])
        if n < 10:
            return True

    return False


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


def get_total():

    out=subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    total=0

    for line in out.splitlines():

        if "transfer:" in line:

            m=re.search("transfer: (.*) received, (.*) sent",line)
            if not m: continue

            r=m.group(1)
            s=m.group(2)

            total+=to_bytes(r)
            total+=to_bytes(s)

    return total


def traffic_stats():

    now=datetime.datetime.now()
    today=now.strftime("%Y-%m-%d")
    month=now.strftime("%Y-%m")

    db=load_json(TRAFFIC_DB)

    total=get_total()

    if "start_total" not in db:
        db["start_total"]=total

    if "today" not in db or db["today"]!=today:
        db["today"]=today
        db["today_start"]=total

    if "month" not in db or db["month"]!=month:
        db["month"]=month
        db["month_start"]=total

    save_json(TRAFFIC_DB,db)

    today_bytes=total-db["today_start"]
    month_bytes=total-db["month_start"]
    total_bytes=total-db["start_total"]

    return {
        "today":human(today_bytes),
        "month":human(month_bytes),
        "total":human(total_bytes)
    }


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
        hs=translate_time(hs)

        tr=tr.group(1) if tr else "0"
        tr=tr.replace("received","↓")
        tr=tr.replace("sent","↑")

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


def system():

    load = open("/proc/loadavg").read().split()[0]

    mem = open("/proc/meminfo").read()

    total = int(re.search(r"MemTotal:\s+(\d+)",mem).group(1))
    free = int(re.search(r"MemAvailable:\s+(\d+)",mem).group(1))

    used = total - free

    total = round(total/1024/1024,1)
    used = round(used/1024/1024,1)

    t=traffic_stats()

    return {
        "cpu": load,
        "ram": f"{used}/{total} GB",
        "disk": disk(),
        "ping": ping(),
        "today": t["today"],
        "month": t["month"],
        "total": t["total"]
    }


@app.get("/api")
def api():
    return peers()


@app.get("/stats")
def stats():
    return system()


@app.get("/",response_class=HTMLResponse)
def ui():
    return """
<html>
<head>

<style>
body{background:#020617;color:white;font-family:Inter;padding:20px}
.top{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.stat{background:#020617;border:1px solid #1e293b;padding:15px;border-radius:12px;min-width:150px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,320px);gap:15px}
.card{background:#020617;border:1px solid #1e293b;padding:15px;border-radius:14px}
.name{font-weight:bold}
.online{color:#22c55e}
.offline{color:#6b7280}
.ip{color:#94a3b8}
.tr{color:#38bdf8}
</style>

<script>

async function load(){

r=await fetch("/api")
data=await r.json()

grid.innerHTML=""

data.forEach(p=>{

name=localStorage[p.ip]||p.ip

grid.innerHTML+=`
<div class="card">

<div class="name">${name}</div>

<div class="${p.online?'online':'offline'}">
${p.online?'🟢 Онлайн':'⚫ Не активен'}
</div>

<div class="ip">${p.ip}</div>

<div>Активность: ${p.hs}</div>

<div class="tr">Трафик: ${p.tr}</div>

</div>
`
})
}

async function stats(){

r=await fetch("/stats")
s=await r.json()

cpu.innerText=s.cpu
ram.innerText=s.ram
disk.innerText=s.disk
ping.innerText=s.ping+" ms"
today.innerText=s.today
month.innerText=s.month
total.innerText=s.total

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
<div class="stat">Ping<br><span id="ping"></span></div>

<div class="stat">Сегодня<br><span id="today"></span></div>
<div class="stat">Месяц<br><span id="month"></span></div>
<div class="stat">Всего<br><span id="total"></span></div>

</div>

<div id="grid" class="grid"></div>

</body>
</html>
"""
