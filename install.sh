#!/bin/bash

apt update
apt install python3 python3-pip -y

pip3 install -r requirements.txt --break-system-packages

pkill -f panel.py || true

nohup python3 -m uvicorn panel:app --host 0.0.0.0 --port 8080 > panel.log 2>&1 &