#!/bin/bash

curl -fsSL https://deb.nodesource.com/setup_23.x -o nodesource_setup.sh
bash nodesource_setup.sh
apt-get install -y nodejs

cd ${WORK_DIR}/tmp/repo/webapp
npm install
npm run build

mkdir -p ${ROOTFS_DIR}/var/www/sunscan-backend
cp -rp ${WORK_DIR}/tmp/repo/app ${ROOTFS_DIR}/var/www/sunscan-backend
cp -rp ${WORK_DIR}/tmp/repo/webapp ${ROOTFS_DIR}/var/www/sunscan-backend

on_chroot <<EOF
cd /var/www
rm -rf html
ln -s sunscan-backend/webapp/dist html
EOF
