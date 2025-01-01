#!/bin/bash

# Install modules needed by INTI
cd /var/www/sunscan-backend

python3 -m venv --system-site-packages venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r app/requirements.txt

# Install JSol'Ex Scripting Engine

JSOLEX_DIR=/var/www/sunscan-backend/app/jsolex
mkdir -p ${JSOLEX_DIR}

curl -sSL -o jsolex-scripting.zip https://jsolex.s3.eu-west-3.amazonaws.com/jsolex-scripting-/jsolex-scripting-2.8.1-linux-aarch64.zip
unzip jsolex-scripting.zip -d $JSOLEX_DIR
rm -f jsolex-scripting.zip

# Fixup ownership
chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /var/www/sunscan-backend
