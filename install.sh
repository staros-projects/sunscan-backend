#!/bin/bash

# Définir les couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # Pas de couleur

# Fonction pour afficher les messages d'erreur
function error_message() {
    echo -e "${RED}[ERREUR] $1${NC}"
}

# Fonction pour afficher les messages de succès
function success_message() {
    echo -e "${GREEN}[SUCCÈS] $1${NC}"
}

# Fonction pour afficher les messages d'information
function info_message() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

# Vérification des privilèges root
if [ "$EUID" -ne 0 ]; then
    error_message "Ce script doit être exécuté avec les privilèges root. Veuillez utiliser 'sudo'."
    exit 1
fi

# Étape 1 : Création de l'environnement virtuel
info_message "Création de l'environnement virtuel Python..."
python3 -m venv --system-site-packages venv
if [ $? -eq 0 ]; then
    success_message "L'environnement virtuel a été créé avec succès."
else
    error_message "Échec de la création de l'environnement virtuel."
    exit 1
fi

# Activer l'environnement virtuel
source venv/bin/activate

# Étape 2 : Installation des paquets système requis
info_message "Installation des paquets système requis..."
sudo apt-get update
sudo apt-get install -y gcc python3-dev libcap-dev libcamera-dev python3-libcamera python3-pyqt5 python3-prctl libatlas-base-dev ffmpeg uvicorn
if [ $? -eq 0 ]; then
    success_message "Les paquets système ont été installés avec succès."
else
    error_message "Échec de l'installation des paquets système."
    exit 1
fi

# Étape 3 : Installation des dépendances Python
info_message "Installation des dépendances Python à partir de requirements.txt..."
pip install -r app/requirements.txt
if [ $? -eq 0 ]; then
    success_message "Les dépendances Python ont été installées avec succès."
else
    error_message "Échec de l'installation des dépendances Python."
    exit 1
fi

# Étape 4 : Proposition d'installation du hotspot
read -p "Voulez-vous configurer le hotspot Wi-Fi maintenant ? (o/N) : " response
if [[ "$response" =~ ^[Oo]$ ]]; then
    info_message "Lancement du script de configuration du hotspot..."
    if [ -f system/usr/local/bin/configure_hotspot.sh ]; then
        sudo bash system/usr/local/bin/configure_hotspot.sh
        if [ $? -eq 0 ]; then
            success_message "Le hotspot Wi-Fi a été configuré avec succès."
        else
            error_message "Échec de la configuration du hotspot Wi-Fi."
        fi
    else
        error_message "Le script de configuration du hotspot est introuvable."
    fi
else
    info_message "Configuration du hotspot Wi-Fi ignorée."
fi

# Étape 5 : Instructions pour lancer le projet
success_message "L'installation est terminée."
info_message "Pour lancer le projet, exécutez les commandes suivantes :"
echo -e "${GREEN}source venv/bin/activate${NC}"
echo -e "${GREEN}cd app${NC}"
echo -e "${GREEN}python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload${NC}"
