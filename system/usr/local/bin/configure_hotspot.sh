#!/bin/bash

# Ce script configure un hotspot.
# il se base sur les commande nmcli et le network-manager.
# si il n'existe pas alors installer le network-manager
# sudo apt-get install network-manager
# vous pouvez aussi modifier la configuration du SSID.
# voir plus bas dans le fichier.

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # Pas de couleur

# Fonction pour afficher les messages avec couleur
function print_message() {
    local color="$1"
    local message="$2"
    echo -e "${color}${message}${NC}"
}

# Vérification des privilèges root
if [[ $EUID -ne 0 ]]; then
    print_message "$RED" "Ce script doit être exécuté avec des privilèges root."
    exit 1
fi

# Vérification de la présence de nmcli
if ! command -v nmcli &> /dev/null; then
    print_message "$RED" "nmcli n'est pas installé. Veuillez installer NetworkManager."
    exit 1
fi

# Vérifier la disponibilité de l'interface Wi-Fi
wifi_interface=$(nmcli device | grep wifi | awk '{print $1}')
if [ -z "$wifi_interface" ]; then
    error_message "Aucune interface Wi-Fi détectée. Assurez-vous que votre matériel Wi-Fi est correctement configuré."
    exit 1
fi

# Vérifier si le Wi-Fi est activé
nmcli radio wifi on
info_message "Activation du Wi-Fi..."

# Vérification de l'interface Wi-Fi
INTERFACE="wlan0"
if ! nmcli device status | grep -q "$INTERFACE"; then
    print_message "$RED" "L'interface $INTERFACE n'est pas disponible. Veuillez vérifier votre matériel."
    exit 1
fi

# Vérifier que les paquets susceptibles de causer des conflits ne sont pas installés
conflicting_packages=("dnsmasq" "hostapd")
for pkg in "${conflicting_packages[@]}"; do
    if dpkg -l | grep -q "^ii  $pkg"; then
        print_message "$YELLOW" "Le paquet '$pkg' est installé et peut causer des conflits. Il est recommandé de le désinstaller."
        read -p "Voulez-vous désinstaller '$pkg' maintenant ? (o/N) : " response
        if [[ "$response" =~ ^[Oo]$ ]]; then
            apt-get remove --purge -y "$pkg"
            if [ $? -eq 0 ]; then
                print_message "$GREEN" "'$pkg' a été désinstallé avec succès."
            else
                print_message "$RED" "Échec de la désinstallation de '$pkg'."
                exit 1
            fi
        else
            print_message "$RED" "Veuillez désinstaller '$pkg' manuellement avant de continuer."
            exit 1
        fi
    else
        print_message "$GREEN" "Le paquet '$pkg' n'est pas installé."
    fi
done

# Configuration du hotspot
SSID="sunscanperso"
PASSWORD="passwordperso"

print_message "$YELLOW" "Création de la connexion hotspot..."
nmcli con add type wifi ifname "$INTERFACE" con-name hotspot autoconnect yes ssid "$SSID"
if [[ $? -ne 0 ]]; then
    print_message "$RED" "Échec de la création de la connexion hotspot."
    exit 1
fi

print_message "$YELLOW" "Configuration de la sécurité du hotspot..."
nmcli con modify hotspot wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"
if [[ $? -ne 0 ]]; then
    print_message "$RED" "Échec de la configuration de la sécurité du hotspot."
    exit 1
fi

print_message "$YELLOW" "Configuration du mode et du partage IPv4..."
nmcli con modify hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
if [[ $? -ne 0 ]]; then
    print_message "$RED" "Échec de la configuration du mode et du partage IPv4."
    exit 1
fi

# Activation du hotspot
print_message "$YELLOW" "Activation du hotspot..."
nmcli con up hotspot
if [[ $? -ne 0 ]]; then
    print_message "$RED" "Échec de l'activation du hotspot."
    exit 1
else
    print_message "$GREEN" "Le hotspot a été activé avec succès."
fi

# Vérification de l'état du hotspot
print_message "$YELLOW" "Vérification de l'état du hotspot..."
nmcli -f NAME,DEVICE,STATE con show --active | grep -q "hotspot.*$INTERFACE.*activated"
if [[ $? -ne 0 ]]; then
    print_message "$RED" "Le hotspot n'est pas activé correctement."
    exit 1
else
    print_message "$GREEN" "Le hotspot est activé et fonctionne correctement."
fi

print_message "$GREEN" "Configuration du hotspot terminée avec succès."
