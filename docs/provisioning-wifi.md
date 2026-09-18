# Connecter le SunScan au WiFi de la maison depuis l'app

Par défaut, le SunScan est un point d'accès WiFi (`sunscan-<id>`, adresse `10.42.0.1`). Le backend permet maintenant à l'app de lui faire rejoindre le WiFi de la maison : l'app affiche les réseaux vus par le SunScan, l'utilisateur choisit le sien et tape le mot de passe, le SunScan s'y connecte. Ensuite, le téléphone et le SunScan sont sur le même réseau.

Une fois le réseau enregistré, le SunScan le rejoint tout seul au démarrage quand il est à portée. Loin de la maison (sur le terrain), il redémarre en hotspot comme avant. Rien ne change pour l'utilisateur qui ne configure jamais de réseau.

Toutes les routes sont sur le port 8000, comme le reste de l'API.

## Le point à comprendre avant tout

Le Pi n'a qu'une seule puce WiFi : **quand il rejoint le réseau de la maison, le hotspot s'arrête et le téléphone perd la connexion**. L'app ne peut donc pas attendre la réponse « connecté » sur la même requête. Le déroulé est le suivant :

1. L'app envoie SSID et mot de passe, le backend répond tout de suite `202`.
2. 2 secondes plus tard, le SunScan quitte le hotspot et essaie de rejoindre le réseau (45 s maximum).
3. **Réussite** : le SunScan est sur le réseau de la maison. L'utilisateur y remet son téléphone, l'app retrouve le SunScan par mDNS (voir plus bas).
4. **Échec** (mauvais mot de passe, réseau hors de portée...) : le SunScan supprime le réseau et relance son hotspot. Un mauvais mot de passe est détecté en ~10 s, le hotspot est de retour ~15 s après l'envoi ; les autres échecs peuvent prendre jusqu'aux 45 s. Le téléphone s'y reconnecte (en général tout seul), et l'app lit la raison de l'échec dans `GET /network/status`.

## 1. État du réseau : `GET /network/status`

```json
{
  "supported": true,
  "device_id": "9713dd",
  "hostname": "sunscan",
  "mode": "hotspot",
  "ssid": "sunscan-9713dd",
  "ip": "10.42.0.1",
  "hotspot": {"ssid": "sunscan-9713dd", "ip": "10.42.0.1"},
  "saved_networks": ["Livebox-53E0"],
  "attempt": {
    "state": "failed",
    "ssid": "Livebox-53E0",
    "error": "wrong_password",
    "detail": "Error: Connection activation failed: Secrets were required, but not provided.",
    "ip": "",
    "started_at": 1790000000,
    "finished_at": 1790000030
  },
  "last_client": {"ssid": "Livebox-53E0", "ip": "192.168.1.5", "at": 1789990000}
}
```

| Champ | Signification |
|---|---|
| `supported` | `false` sur les vieilles images sans NetworkManager (Buster/Bullseye) : masquer la fonction. Dans ce cas, c'est le seul champ présent |
| `device_id` | 6 derniers chiffres hexa de l'adresse MAC. Identifie le SunScan, c'est aussi la fin du SSID du hotspot et l'`id` annoncé en mDNS. **À mémoriser dans l'app** |
| `mode` | `hotspot`, `client` (sur un réseau de la maison), `connecting`, `disconnected` |
| `ssid`, `ip` | réseau et adresse actuels |
| `saved_networks` | réseaux enregistrés, à proposer à l'oubli |
| `attempt` | dernière tentative de connexion. `state` : `idle` (jamais), `connecting`, `connected`, `failed`. Conservée après un redémarrage |
| `last_client` | dernière connexion réussie à un réseau de la maison, avec l'adresse obtenue. `null` si jamais |

Les dates sont des timestamps Unix en secondes.

## 2. Lister les réseaux : `GET /network/wifi/scan`

Le scan prend 3 à 10 secondes : afficher un indicateur de chargement.

```json
{
  "supported": true,
  "cached": false,
  "scanned_at": 1790000000,
  "networks": [
    {"ssid": "Livebox-53E0", "signal": 66, "band": "5GHz", "security": "psk", "saved": true, "in_use": false},
    {"ssid": "SFR_5AB0", "signal": 30, "band": "2.4GHz", "security": "psk", "saved": false, "in_use": false}
  ]
}
```

| Champ | Signification |
|---|---|
| `ssid` | un seul élément par SSID (le meilleur signal). Les réseaux cachés et le hotspot du SunScan ne sont pas listés |
| `signal` | 0 à 100, pour l'icône de force (par ex. 0-30 / 30-55 / 55-75 / 75-100) |
| `security` | `open` (pas de mot de passe), `psk` (WPA/WPA2), `sae` (WPA3), `wep` et `enterprise` (non supportés : afficher grisé) |
| `saved` | réseau déjà enregistré sur le SunScan |
| `in_use` | réseau actuel |
| `cached` | `true` si le scan a échoué et que ce sont les résultats précédents (`scanned_at` donne leur date, `null` si aucun). Proposer « Réessayer » |

`?refresh=false` renvoie les derniers résultats sans scanner.

Prévoir aussi une entrée « Autre réseau… » pour saisir un SSID caché à la main (`hidden: true` ci-dessous).

## 3. Se connecter : `POST /network/wifi/connect`

```json
{"ssid": "Livebox-53E0", "password": "motdepasse", "hidden": false}
```

`password` : vide ou absent pour un réseau `open`. `hidden` : optionnel, `true` pour un réseau caché.

| Cas | Code HTTP | Corps |
|---|---|---|
| Accepté | 202 | `{"status": "connecting", "ssid": "...", "switch_in": 2, "timeout": 45}` |
| Requête invalide | 400 | `{"status": "failed", "error": "<code>", "detail": "..."}` |
| Une tentative est déjà en cours | 409 | `{"status": "failed", "error": "busy", ...}` |
| Pas de NetworkManager | 501 | `{"status": "failed", "error": "not_supported", ...}` |

Codes d'erreur renvoyés immédiatement (à valider aussi côté app avant l'envoi) :

| `error` | Cause |
|---|---|
| `invalid_ssid` | SSID vide, plus de 32 octets, ou SSID du hotspot SunScan |
| `invalid_password` | mot de passe de moins de 8 ou plus de 63 caractères |
| `unsupported_security` | réseau WEP ou entreprise (802.1X) |

Codes d'erreur de la tentative, lus ensuite dans `attempt.error` :

| `error` | Message à afficher |
|---|---|
| `wrong_password` | Mot de passe incorrect |
| `network_not_found` | Réseau introuvable (hors de portée, ou SSID mal saisi) |
| `timeout` | Le réseau n'a pas répondu à temps |
| `no_address` | Connecté, mais la box n'a pas donné d'adresse |
| `connection_failed` | Autre erreur (le détail brut est dans `attempt.detail`, pour les logs) |

Si le même SSID était déjà enregistré (changement de mot de passe de la box, par exemple), l'ancien profil n'est remplacé qu'en cas de réussite.

## 4. Retrouver le SunScan sur le réseau de la maison

Le backend s'annonce en mDNS / DNS-SD :

- type de service : `_sunscan._tcp`
- nom : `SunScan <device_id>`
- port : `8000`
- TXT : `id=<device_id>`, `version=<version de l'API>`

Avec Expo, [`react-native-zeroconf`](https://github.com/balthazar/react-native-zeroconf) fait l'affaire. Il faut un *development build* : le module est natif, il ne marche pas dans Expo Go.

```js
import Zeroconf from 'react-native-zeroconf';

const zeroconf = new Zeroconf();
zeroconf.on('resolved', service => {
  // service.txt.id, service.addresses (IPv4 et IPv6), service.port
  if (service.txt?.id === savedDeviceId) {
    const ip = service.addresses.find(a => a.includes('.'));
    connectTo(`http://${ip}:${service.port}`);
  }
});
zeroconf.scan('sunscan', 'tcp', 'local.');
// zeroconf.stop() quand l'écran se ferme
```

Configuration dans `app.json` :

- **iOS** (obligatoire depuis iOS 14, sinon rien n'est trouvé) :
  ```json
  "ios": {
    "infoPlist": {
      "NSLocalNetworkUsageDescription": "SunScan a besoin d'accéder au réseau local pour trouver votre appareil.",
      "NSBonjourServices": ["_sunscan._tcp"]
    }
  }
  ```
  La première recherche déclenche la demande d'autorisation « réseau local ». Si l'utilisateur refuse, la découverte ne trouvera jamais rien.
- **Android** : permissions `ACCESS_WIFI_STATE` et `CHANGE_WIFI_MULTICAST_STATE` (le module prend lui-même le verrou multicast).

Filtrer sur `txt.id` et pas sur le nom d'hôte : tous les SunScan s'appellent `sunscan.local` (avahi renomme le deuxième en `sunscan-2.local`).

Solutions de repli, dans cet ordre, si rien n'est trouvé au bout de ~10 s :

1. `last_client.ip` mémorisé à la dernière connexion (la box redonne en général la même adresse) : `GET http://<ip>:8000/network/status` et vérifier `device_id`.
2. `http://sunscan.local:8000` : marche bien sur iOS, variable sur Android.
3. Saisie manuelle de l'adresse IP.

## 5. Revenir au hotspot / oublier un réseau

- `POST /network/hotspot` : repasse en hotspot tout de suite. Les réseaux enregistrés sont conservés : au prochain démarrage, le SunScan rejoindra le réseau de la maison s'il est à portée. Réponse `{"status": "ok", "switching": true, "switch_in": 2}`, ou `"switching": false` si le hotspot est déjà actif.
- `POST /network/wifi/forget` avec `{"ssid": "Livebox-53E0"}` : supprime le réseau. Si c'est le réseau actuel, le SunScan repasse en hotspot (le téléphone perd la connexion, comme pour `connect`). `404` avec `error: "not_found"` si le réseau n'est pas enregistré.

Filet de sécurité hors app : `reset_hotspot.sh` à la racine du backend remet le nom du hotspot par défaut.

## 6. Comportement automatique du SunScan

- **Au démarrage** : réseau de la maison s'il est à portée, sinon hotspot. Plusieurs réseaux enregistrés et à portée : NetworkManager prend le dernier utilisé.
- **Coupure de la box** (redémarrage de la box la nuit par exemple) : le SunScan retombe en hotspot. Toutes les 2 minutes, s'il n'a **aucun téléphone connecté à son hotspot**, il regarde si un réseau enregistré est revenu et le rejoint. Il ne quitte jamais le hotspot pendant qu'un téléphone l'utilise.

## 7. Parcours proposé pour l'app

**Écran « Réseau WiFi »** (dans les réglages, visible seulement si `supported`) :

- mode actuel : « Hotspot sunscan-9713dd » ou « Connecté à Livebox-53E0 (192.168.1.5) »
- bouton « Connecter à mon WiFi » → écran liste
- liste des `saved_networks` avec « Oublier »
- en mode client : bouton « Revenir au hotspot »

**Écran liste** : `GET /network/wifi/scan` au montage, pull-to-refresh. Tap sur un réseau → saisie du mot de passe (sauf `open`), avec un bouton pour afficher/masquer le mot de passe. Les réseaux 5 GHz sont utilisables, le Pi 4 est bi-bande.

**Après l'envoi (202)** :

1. Écran d'attente : « Le SunScan rejoint <ssid>… La connexion avec le SunScan va être coupée, c'est normal. » Mémoriser `device_id` et `ssid` avant l'envoi.
2. Au bout de ~5 s, demander à l'utilisateur de mettre son téléphone sur `<ssid>`. Sur Android, `Linking.sendIntent('android.settings.WIFI_SETTINGS')` ouvre les réglages WiFi. Sur iOS, pas de lien direct fiable : juste un texte.
3. Lancer en parallèle, pendant ~75 s (2 s + 45 s de tentative + 30 s de retour du hotspot) :
   - la découverte mDNS avec l'`id` mémorisé → trouvé = **réussite**, basculer l'app sur la nouvelle adresse ;
   - un `GET http://10.42.0.1:8000/network/status` toutes les 3 s, timeout court (2 s) → répond avec `attempt.state == "failed"` = **échec** : afficher le message de `attempt.error` et revenir à la saisie du mot de passe.
4. Rien après 75 s : proposer les deux pistes (« Vérifiez que votre téléphone est sur <ssid> » / « Reconnectez-vous au hotspot sunscan-<id> ») et relancer la recherche.

Une fois l'app reconnectée, `GET /network/status` confirme : `mode == "client"`, `attempt.state == "connected"`.

## Sécurité

Le mot de passe passe en clair dans la requête HTTP, mais seulement sur le hotspot, qui est chiffré en WPA2. Il est stocké par NetworkManager dans `/etc/NetworkManager/system-connections/` (lisible par root seulement), jamais par le backend. Aucune route ne le renvoie.
