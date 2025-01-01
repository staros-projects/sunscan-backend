#!/bin/bash

WORKING_DIR=/var/www/sunscan-backend
VENV_DIR=$WORKING_DIR/venv
USERNAME=${FIRST_USER_NAME}
GROUPNAME=${FIRST_USER_NAME}

# Configure uvicorn

cat <<EOF > /etc/systemd/system/uvicorn.service
[Unit]
Description=Uvicorn instance to serve application
After=network.target

[Service]
User=$USERNAME
Group=$GROUPNAME
WorkingDirectory=$WORKING_DIR/app
ExecStart=$VENV_DIR/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Register systemd service

sudo systemctl daemon-reload
sudo systemctl enable uvicorn.service
