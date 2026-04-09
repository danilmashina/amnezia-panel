from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import subprocess, re, json, os

app = FastAPI()
DB="users.json"

def load():
    if not os.path.exists(DB):
        return {}
    return json.load(open(DB))

def save(db):
    json.dump(db,open(DB,"w"))

def peers():

    out=subprocess.check_output(
        "docker exec amnezia-awg wg show",
        shell=True
    ).decode()

    peers=out.split("peer: ")[1:]
    data=[]

    for p in peers:

        key=p.split("\n")[0]

        ip=re.search("allowed ips: (.*)",p)
        hs=re.search("latest handshake: (.*)",p)
        tr=re.search("transfer: (.*)",p)
        ep=re.search("endpoint: (.*)",p)

        ip=ip.group(1) if ip else "-"
        hs=hs.group(1) if hs else "never"
        tr=tr.group(1) if tr else "0"
        ep=ep.group(1) if ep else "-"

        online=("second" in hs or "minute" in hs)

        data.append({
            "ip":ip,
            "hs":hs,
            "tr":tr,
            "ep":ep,
            "online":online
        })

    return data


@app.get("/api")
def api():
    return peers()

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
font-family:Arial;
padding:20px
}

.top{
display:flex;
gap:20px;
margin-bottom:20px
}

.stat{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:12px
}

.grid{
display:grid;
grid-template-columns:repeat(auto-fill,300px);
gap:15px
}

.card{
background:#020617;
border:1px solid #1e293b;
padding:15px;
border-radius:12px;
transition:0.2s
}

.card:hover{
border-color:#2563eb
}

.name{
font-size:18px;
font-weight:bold
}

.online{
color:#22c55e
}

.offline{
color:#6b7280
}

.ip{
color:#94a3b8
}

.tr{
color:#38bdf8
}

input{
width:100%;
margin-top:5px;
background:#020617;
border:1px solid #1e293b;
color:white;
padding:5px
}

button{
width:100%;
margin-top:5px;
background:#2563eb;
border:0;
padding:6px;
color:white;
cursor:pointer
}

</style>

<script>

async function load(){

r=await fetch("/api")
data=await r.json()

grid=document.getElementById("grid")

grid.innerHTML=""

online=0

data.forEach(p=>{

if(p.online) online++

name=localStorage[p.ip]||p.ip

grid.innerHTML+=`
<div class="card">

<div class="name">${name}</div>

<div class="${p.online?"online":"offline"}">
${p.online?"● online":"● offline"}
</div>

<div class="ip">${p.ip}</div>
<div>${p.hs}</div>
<div class="tr">${p.tr}</div>

<input id="i_${p.ip}" placeholder="Имя"/>

<button onclick="save('${p.ip}')">
Save
</button>

</div>
`
})

document.getElementById("online").innerText=
online+" / "+data.length

}

function save(ip){

name=document.getElementById("i_"+ip).value
fetch("/save?ip="+ip+"&name="+name)
localStorage[ip]=name

}

setInterval(load,3000)

</script>

</head>

<body onload="load()">

<h2>Amnezia Panel</h2>

<div class="top">

<div class="stat">
Online: <span id="online"></span>
</div>

</div>

<div id="grid" class="grid"></div>

</body>
</html>
"""
