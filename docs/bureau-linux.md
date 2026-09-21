# Bureau Linux à la demande : côté app mobile

Le SunScan se pilote depuis le téléphone : sur le terrain, personne ne regarde le bureau Linux du Pi. Il tournait pourtant en permanence. Maintenant **le Pi démarre sans bureau**, et l'app propose de l'allumer à celui qui en a besoin, pour développer sur le Pi par exemple.

## En bref

- **Rien d'obligatoire.** Le bureau est éteint par défaut par le backend lui-même, à chaque démarrage, sans appel de l'app. Vaut aussi pour les SunScan déjà en service : le bureau disparaît au deuxième démarrage après la mise à jour.
- **À faire :** dans les réglages, un interrupteur « Bureau Linux » (partie 2). Deux appels : `GET /sunscan/desktop` pour l'état, `POST /sunscan/desktop` pour changer.
- **À envisager :** une option « Garder le bureau au démarrage », pour les développeurs (partie 3).
- **Attention :** éteindre le bureau ferme tout ce qui y est ouvert (VSCode, terminal, navigateur), sans sauvegarde. Demander confirmation avant.
- La liaison avec le téléphone n'est pas touchée : le backend est un service système, il continue pendant et après la bascule. Pas de reconnexion à gérer.

## 1. Les deux routes

### `GET /sunscan/desktop`

```json
{"supported": true, "running": false, "state": "inactive", "at_boot": false}
```

| Champ | Sens | Usage dans l'app |
|---|---|---|
| `supported` | `false` sur une image sans bureau (Raspberry Pi OS Lite) | masquer tout le réglage |
| `running` | le bureau tourne, ou démarre | valeur de l'interrupteur |
| `at_boot` | le bureau démarre avec le Pi | valeur de l'option « Garder au démarrage » |
| `state` | état systemd : `active`, `inactive`, `activating`, `deactivating`, `failed` | diagnostic seulement, ne pas l'afficher |

Un backend plus ancien répond 404 : masquer le réglage, comme pour `supported: false`.

### `POST /sunscan/desktop`

Le corps reprend les champs du `GET`. Chacun est facultatif, il en faut au moins un, et celui qui est absent n'est pas modifié.

| Champ | Sens |
|---|---|
| `running` | `true` démarre le bureau, `false` l'arrête. Ne vaut que jusqu'à l'extinction du Pi : au démarrage suivant il est de nouveau éteint |
| `at_boot` | `true` : le bureau démarre avec le Pi. `false` : retour au comportement par défaut. Ne change pas le bureau en cours |

```json
{"running": true}
{"running": true, "at_boot": true}
{"running": false, "at_boot": false}
```

La réponse (200) est le même objet que le `GET`, lu **après** la bascule : s'en servir pour mettre l'écran à jour, sans refaire de `GET`. Demander l'état déjà en place n'est pas une erreur.

**Durée.** L'appel ne répond qu'une fois la bascule finie, et l'arrêt peut prendre jusqu'à 45 s si une application tarde à se fermer. Donc : indicateur d'attente, interrupteur désactivé pendant l'appel, et un délai d'expiration de 60 s si `fetch` en a un.

**Erreurs**, au format `{"status": "failed", "error": "<code>", "detail": "..."}` :

| HTTP | `error` | Cas | Côté app |
|---|---|---|---|
| 409 | `recording` | `running` demandé pendant l'enregistrement d'un scan : démarrer le bureau charge le CPU et la carte SD, et pourrait faire perdre des images | message « réessayer après le scan ». `at_boot` seul reste accepté |
| 501 | `unsupported` | pas de bureau installé | ne devrait pas arriver si le réglage est masqué |
| 500 | `set_default_failed`, `start_failed`, `stop_failed` | `systemctl` a échoué, le message système est dans `detail` | message générique, `detail` dans les logs |
| 422 | | ni `running` ni `at_boot` dans le corps | erreur de code |

## 2. L'interrupteur « Bureau Linux »

À placer dans les réglages, près de l'extinction et du redémarrage du SunScan.

| État | Affichage |
|---|---|
| `GET` en cours, 404, ou `supported: false` | rien |
| `running: false` | interrupteur éteint, avec une phrase d'explication (voir les libellés) |
| `running: true` | interrupteur allumé |
| `POST` en cours | interrupteur désactivé, indicateur d'attente |
| erreur | interrupteur remis sur la dernière valeur connue, message d'erreur |

- **Lire l'état à chaque ouverture de l'écran**, pas une fois pour toutes : le bureau peut avoir été allumé depuis un autre téléphone ou à la main.
- **Allumer :** pas de confirmation, c'est sans risque.
- **Éteindre :** fenêtre de confirmation avant l'appel, tout ce qui est ouvert sur le bureau est perdu.
- Ne pas basculer l'interrupteur avant la réponse (pas de mise à jour optimiste) : afficher `running` de la réponse.

```js
const [desktop, setDesktop] = useState(null);      // null : réglage masqué
const [busy, setBusy] = useState(false);

const loadDesktop = async () => {
  try {
    const response = await fetch(api + '/sunscan/desktop');
    const json = response.ok ? await response.json() : null;   // 404 : backend plus ancien
    setDesktop(json && json.supported ? json : null);
  } catch (e) {
    setDesktop(null);
  }
};

const switchDesktop = async (body) => {             // {running: true}, {at_boot: false}...
  setBusy(true);
  setErrorLabel('');
  try {
    const response = await fetch(api + '/sunscan/desktop', { method: 'POST', headers, body: JSON.stringify(body) });
    const json = await response.json();
    if (response.ok) setDesktop(json);
    else setErrorLabel(t('desktop:error.' + json.error, { defaultValue: t('desktop:error.generic') }));
  } catch (e) {
    setErrorLabel(t('desktop:error.generic'));
  } finally {
    setBusy(false);
  }
};

const onToggle = (value) => {
  if (value) switchDesktop({ running: true });
  else confirm(t('desktop:confirmStop.title'), t('desktop:confirmStop.message'), () => switchDesktop({ running: false }));
};
```

## 3. L'option « Garder le bureau au démarrage »

Pour celui qui développe sur le Pi tous les jours, et ne veut pas rallumer le bureau depuis l'app à chaque démarrage. Une case à cocher sous l'interrupteur, liée à `at_boot` :

```js
const onKeepAtBoot = (value) => switchDesktop({ at_boot: value });
```

- Elle ne démarre ni n'arrête le bureau : cocher la case bureau éteint ne prend effet qu'au prochain démarrage du Pi. Pour les deux à la fois : `{running: true, at_boot: true}`.
- Pas de confirmation, dans un sens comme dans l'autre.
- Si les réglages ont une partie « avancé » ou « développeur », c'est sa place : la plupart des utilisateurs n'en ont pas besoin.

## 4. Libellés

Propositions, à mettre dans un espace de noms `desktop`. Les clés `error.*` reprennent les codes `error` du backend, avec `error.generic` en repli pour un code inconnu.

| Clé | Français | Anglais |
|---|---|---|
| `title` | Bureau Linux | Linux desktop |
| `hint` | Éteint par défaut pour laisser toute la puissance du SunScan aux scans. À allumer seulement pour travailler sur le Raspberry Pi avec un écran. | Off by default, to keep all the power of the SunScan for the scans. Turn it on only to work on the Raspberry Pi with a screen. |
| `keepAtBoot` | Garder le bureau au démarrage | Keep the desktop at startup |
| `confirmStop.title` | Éteindre le bureau ? | Turn off the desktop? |
| `confirmStop.message` | Les applications ouvertes sur le bureau du SunScan seront fermées, le travail non enregistré sera perdu. | The applications opened on the SunScan desktop will be closed, unsaved work will be lost. |
| `error.recording` | Un scan est en cours. Réessayez une fois le scan terminé. | A scan is in progress. Try again once it is finished. |
| `error.generic` | Le bureau n'a pas pu être modifié. | The desktop could not be changed. |

## 5. Pour tester

Depuis un ordinateur sur le même réseau, ou en SSH sur le Pi :

```bash
curl http://sunscan.local:8000/sunscan/desktop
curl -X POST -H 'Content-Type: application/json' -d '{"running": true}' http://sunscan.local:8000/sunscan/desktop
```

- **Ne pas tester l'arrêt depuis le bureau du Pi** (navigateur ou terminal ouvert dessus) : il est fermé avec le reste. Depuis le téléphone ou en SSH.
- Le 409 : lancer un scan, puis envoyer `{"running": true}` pendant l'enregistrement.
- Quand le Pi a démarré sans bureau, l'écran HDMI affiche la console texte (connexion automatique) et VNC ne répond pas, il a besoin du bureau. La commande `curl` ci-dessus, avec `localhost`, rallume le bureau depuis cette console.

## 6. Ce qu'on y gagne

Mesuré sur Pi 4, Bookworm, bureau au repos, sans application ouverte : environ **70 Mo** de mémoire et **1 à 3 %** d'un cœur. C'est modeste. Le gain devient important dès qu'une application reste ouverte sur le bureau : VSCode seul occupe plus de 2 Go sur les 3,8 Go du Pi, rendus au traitement des scans quand le bureau est éteint. Le Pi démarre aussi sans charger le bureau en même temps que le backend.

## 7. Côté backend

- Module [app/desktop.py](../app/desktop.py) : `systemctl start|stop display-manager.service` et `systemctl set-default graphical.target|multi-user.target`, par `sudo -n` (le service tourne sous `admin`, comme pour `shutdown`). L'alias `display-manager.service` évite de dépendre de lightdm.
- `desktop.apply_default()`, appelé au lancement de [app/main.py](../app/main.py) : si le Pi est réglé pour démarrer sur le bureau et que `at_boot` n'a pas été demandé, il passe en démarrage console. **Le backend n'arrête jamais lui-même un bureau en cours** : il redémarre bien plus souvent que le Pi (changement de code, plantage), et l'arrêter là fermerait l'éditeur de celui qui développe sur le Pi. D'où le bureau encore présent au premier démarrage après une mise à jour.
- `at_boot: true` est mémorisé par le fichier `~/.config/sunscan/desktop_at_boot`, hors du dossier de l'application pour qu'une mise à jour ne l'écrase pas. Passer par la route, pas par `raspi-config` ni `systemctl set-default` : sans ce fichier, un démarrage sur le bureau choisi à la main est annulé au prochain démarrage du backend.
- **Image système** (clonée depuis le Pi de développement) : ce fichier est cloné avec le reste. Avant de cloner, envoyer `{"at_boot": false}` et vérifier que le `GET` répond `"at_boot": false`.
- La cible de démarrage est changée **avant** l'arrêt du bureau : si l'appel vient du bureau lui-même, il est tué par l'arrêt mais le choix est déjà enregistré.
- La connexion automatique de lightdm (`autologin-user`) est celle de l'image, elle n'est pas modifiée : au démarrage du bureau, la session `admin` s'ouvre seule.
