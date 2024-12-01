#!/bin/bash

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Messages
function error_message() {
    echo -e "${RED}[ERREUR] $1${NC}"
}

function success_message() {
    echo -e "${GREEN}[SUCCÈS] $1${NC}"
}

function info_message() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

# Vérification des privilèges root
if [ "$EUID" -ne 0 ]; then
    error_message "Ce script doit être exécuté avec les privilèges root. Veuillez utiliser 'sudo'."
    exit 1
fi

# Déterminer le répertoire de travail (working directory)
WORKING_DIR="$(cd "$(dirname "$0")" && pwd)/app"
info_message "Répertoire de travail déterminé : $WORKING_DIR"

# Déterminer le répertoire du venv
VENV_DIR="$(cd "$(dirname "$0")" && pwd)/venv"
info_message "Répertoire de l'environnement virtuel (venv) : $VENV_DIR"

# Déterminer l'utilisateur et le groupe actuels
USER=$(logname)
GROUP=$(id -gn "$USER")
info_message "Utilisateur actuel : $USER"
info_message "Groupe actuel : $GROUP"

# Chemin du fichier de service temporaire
SERVICE_FILE_TMP="/tmp/uvicorn.service"

# Créer le fichier de service avec les valeurs dynamiques
info_message "Création du fichier de service temporaire..."
cat <<EOF > "$SERVICE_FILE_TMP"
[Unit]
Description=Uvicorn instance to serve application
After=network.target

[Service]
User=$USER
Group=$GROUP
WorkingDirectory=$WORKING_DIR
ExecStart=$VENV_DIR/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

if [ $? -eq 0 ]; then
    success_message "Fichier de service temporaire créé : $SERVICE_FILE_TMP"
else
    error_message "Échec de la création du fichier de service temporaire."
    exit 1
fi

# Copier le fichier de service dans /etc/systemd/system
info_message "Copie du fichier de service dans /etc/systemd/system..."
SERVICE_FILE_DEST="/etc/systemd/system/uvicorn.service"
sudo cp "$SERVICE_FILE_TMP" "$SERVICE_FILE_DEST"

if [ $? -eq 0 ]; then
    success_message "Fichier de service copié avec succès : $SERVICE_FILE_DEST"
else
    error_message "Échec de la copie du fichier de service."
    exit 1
fi

# Déclarer le service auprès de systemd
info_message "Déclaration du service auprès de systemd..."
sudo systemctl daemon-reload
sudo systemctl enable uvicorn.service

if [ $? -eq 0 ]; then
    success_message "Service uvicorn déclaré avec succès et activé pour le démarrage automatique."
else
    error_message "Échec de la déclaration ou de l'activation du service."
    exit 1
fi

# Démarrer le service
info_message "Démarrage du service uvicorn..."
sudo systemctl start uvicorn.service

if [ $? -eq 0 ]; then
    success_message "Service uvicorn démarré avec succès."
else
    error_message "Échec du démarrage du service uvicorn."
    exit 1
fi

# Afficher l'état du service
info_message "Vérification de l'état du service uvicorn..."
sudo systemctl status uvicorn.service
