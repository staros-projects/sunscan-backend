#!/bin/bash

# Patch NGINX configuration

cat << EOF > /etc/nginx/sites-available/default
server {
	listen 80 default_server;

	root /var/www/html;

	index index.html;

	server_name sunscan.local;

    location / {
        try_files \$uri /index.html;
    }

}

EOF
