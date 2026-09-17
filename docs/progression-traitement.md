# Suivre le traitement d'un scan depuis le frontend

Le backend publie maintenant l'avancement du traitement (pourcentage et étape en cours), sa fin et ses erreurs sur un nouveau canal WebSocket : `scan_progress_<key>`.

L'ancien canal `scan_process_<key>` est conservé tel quel pour les versions de l'app déjà installées. Le nouveau code n'a plus besoin de l'écouter.

## La clé

`key = md5(scan.ser)`, exactement comme aujourd'hui. Elle est aussi renvoyée dans la réponse du POST.

## 1. Lancer le traitement

`POST /sunscan/scan/process/`, même corps qu'avant. La réponse n'est plus `null` :

| Cas | Code HTTP | Corps |
|---|---|---|
| Traitement lancé | 200 | `{"status": "started", "key": "<md5>"}` |
| Fichier SER introuvable | 404 | `{"status": "failed", "error": "file_not_found", "key": "<md5>"}` |

Abonne-toi **avant** d'envoyer le POST, pour ne pas manquer les premiers messages.

## 2. Écouter le canal `scan_progress_<key>`

Format du message, champs séparés par `;#;` comme les autres canaux :

```
scan_progress_<key>;#;<status>;#;<percent>;#;<step>;#;<error>;#;<detail>
```

Avec le `subscribe` actuel, le callback reçoit un tableau :

| Index | Champ | Valeurs |
|---|---|---|
| `message[1]` | `status` | `processing`, `completed`, `failed` |
| `message[2]` | `percent` | entier en texte, `0` à `99` pendant le traitement, `100` uniquement avec `completed` |
| `message[3]` | `step` | clé de l'étape en cours (voir plus bas) ; en cas d'échec, l'étape où ça a cassé |
| `message[4]` | `error` | clé d'erreur, vide sauf si `failed` |
| `message[5]` | `detail` | message d'erreur brut du backend, vide sauf si `failed`. Pour les logs, pas pour l'utilisateur |

Exemples réels :

```
scan_progress_dace50...;#;processing;#;0;#;starting;#;;#;
scan_progress_dace50...;#;processing;#;12;#;reading_scan;#;;#;
scan_progress_dace50...;#;processing;#;93;#;image_continuum;#;;#;
scan_progress_dace50...;#;completed;#;100;#;done;#;;#;
scan_progress_dace50...;#;failed;#;47;#;correcting_geometry;#;reconstruction_failed;#;Shape of array too small...
```

Comportement à connaître :

- Le backend n'envoie que le **dernier état**, au rythme de la boucle WebSocket (2 à 4 messages par seconde). Il n'y a pas de file d'attente : des pourcentages peuvent être sautés, c'est normal.
- Le pourcentage ne recule jamais pendant un traitement.
- **Tous** les clients connectés reçoivent les messages (contrairement à `scan_process_<key>`, consommé par un seul client).
- À chaque connexion ou reconnexion du WebSocket, le backend renvoie l'état courant de tous les scans suivis : traitements en cours, et traitements terminés depuis moins de 30 minutes. Comme `channels` survit aux reconnexions dans `WSProvider`, un écran abonné se resynchronise tout seul après un passage en arrière-plan. Conséquence : le callback peut recevoir deux fois le même état final, il doit être idempotent.
- Un message `completed` ou `failed` est toujours le dernier d'un traitement. Se désabonner à ce moment-là.

## 3. Clés d'étape (`step`) à traduire

| Clé | Signification | Plage approximative |
|---|---|---|
| `starting` | traitement en file, pas encore commencé | 0 % |
| `reading_scan` | lecture du fichier SER, image moyenne | 0 à 32 % |
| `building_disk` | extraction de la raie, reconstruction du disque brut | 32 à 48 % |
| `correcting_geometry` | lignes défectueuses, flat, tilt, mise au rond (toutes les images) | 48 à 80 % |
| `image_surface` | images surface, CLAHE, couleur, négatif | 80 à 93 % |
| `image_continuum` | image continuum | |
| `image_prominences` | image protubérances | |
| `image_doppler` | images Doppler, seulement si demandé | |
| `image_helium` | images hélium, seulement en mode `heI` (remplace les quatre précédentes) | |
| `done` | terminé, accompagne `completed` | 100 % |

Les plages se resserrent quand le Doppler est actif. Ne t'appuie pas dessus, utilise `percent`.

Prévois un libellé générique pour une clé inconnue : d'autres étapes pourront être ajoutées côté backend sans changer le protocole.

## 4. Clés d'erreur (`error`)

| Clé | Cause |
|---|---|
| `file_not_found` | le fichier SER n'existe pas |
| `reconstruction_failed` | INTI n'a pas pu reconstruire le disque (scan trop court, pas de soleil, bords introuvables...) |
| `image_generation_failed` | le disque est reconstruit mais la création des images a échoué |

Même règle : libellé générique pour une clé inconnue.

## 5. Récupérer l'état à la demande

`POST /sunscan/scan/process/status/` avec `{"filename": scan.ser}` renvoie le dernier état connu :

```json
{"key": "<md5>", "status": "processing", "percent": 12, "step": "reading_scan", "error": "", "detail": ""}
```

`status` vaut `unknown` si le backend ne connaît aucun traitement pour ce scan (jamais lancé depuis son démarrage, ou terminé depuis plus de 30 minutes). Utile à l'ouverture d'un écran pour savoir si un traitement est déjà en cours. L'état est en mémoire : il est perdu au redémarrage du backend.

## 6. Exemple (Card.js / PictureScreen.js)

```js
const key = md5(scan.ser);
const channel = 'scan_progress_' + key;

const stop = (status) => {
  unsubscribe(channel);
  setIsStarted(false);
  setScanStatus(status);          // 'completed' ou 'failed'
};

// 1. s'abonner avant le POST
subscribe(channel, (message) => {
  const [, status, percent, step, error] = message;
  if (status === 'processing') {
    setProgress(parseInt(percent, 10));
    setStepLabel(t('process:step.' + step, { defaultValue: t('process:step.generic') }));
    return;
  }
  if (status === 'failed') {
    setErrorLabel(t('process:error.' + error, { defaultValue: t('process:error.generic') }));
  }
  stop(status);
});

// 2. lancer le traitement
setIsStarted(true);
setProgress(0);
const response = await fetch('http://' + myContext.apiURL + '/sunscan/scan/process/', { /* comme avant */ });
const json = await response.json();
if (json && json.status === 'failed') {   // json vaut null avec un ancien backend
  setErrorLabel(t('process:error.' + json.error, { defaultValue: t('process:error.generic') }));
  stop('failed');
}
```

## Compatibilité

| App | Backend | Résultat |
|---|---|---|
| ancienne | nouveau | inchangé : l'app ignore le canal `scan_progress_<key>` et reçoit toujours `scan_process_<key>;#;completed` ou `failed` |
| nouvelle | ancien | le POST répond `null` et aucun message de progression n'arrive. Pour gérer ce cas, garder en secours l'abonnement à `scan_process_<key>` (`message[1]` = `completed` ou `failed`) |
