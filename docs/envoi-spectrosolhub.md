# Envoyer les images d'un scan, d'un stack ou d'une animation sur SpectroSolHub depuis l'app

Le backend peut envoyer les images d'un scan traité, d'un stack ou d'une animation sur [SpectroSolHub](https://spectrosolhub.com), la plateforme de partage de la communauté des spectrohéliographes. Les sections 1 à 7 décrivent les scans ; la section 8 dit ce qui change pour les stacks et les animations (mêmes routes, même canal). C'est le SunScan qui envoie, pas le téléphone : l'app pilote, le backend fait le travail en tâche de fond et publie l'avancement sur un canal WebSocket.

Le fonctionnement est repris du client SpectroSolHub d'INTI Partner (connexion par identifiants, session d'observation, envoi des images par morceaux, publication).

**État des vérifications.** L'envoi des scans a été fait pour de bon sur spectrosolhub.com le 19/09/2026 (observations 4393 et 4394) : connexion, types d'image, métadonnées, publication, tout s'affiche comme prévu sur le site. L'envoi des stacks utilise exactement le même chemin (JPEG). **L'envoi des animations n'a jamais été essayé sur le vrai hub** : voir l'avertissement de la section 8.

## Ce qui a changé depuis la première version (19/09/2026 après-midi)

Pour qui a déjà branché l'envoi des scans. **Rien ne change pour les scans** : mêmes routes, même canal, même format de message, même ordre POST / abonnement / état. Les ajouts servent aux stacks et aux animations, détail en section 8.

| Où | Changement |
|---|---|
| `filename`, partout | accepte aussi le `path` d'un stack ou d'une animation (`storage/stacking/2026-09-18_11-12-53`). La clé du canal reste `md5(filename)` |
| `POST /spectrosolhub/scan/`, réponse | nouveau champ `type` : `scan`, `stack` ou `animation`. `defaults` gagne `date_known` (booléen) et `notes` (proposition de texte). Pour un scan : `true` et `""` |
| `POST /spectrosolhub/scan/`, `images` | pour un stack ou une animation, les `kind` sont différents (`clahe_sharpen`, `cont_raw`...) et varient selon le dossier : afficher la liste reçue, ne rien coder en dur |
| `POST /spectrosolhub/upload/`, requête | nouveau champ optionnel `observation_date` (`YYYY-MM-DDTHH:MM:SSZ`, UTC). **Obligatoire quand `date_known` vaut `false`**, c'est-à-dire pour tous les stacks et animations créés avant cette version : l'app doit demander la date de l'observation. Ignoré sinon |
| `POST /spectrosolhub/upload/`, erreurs | deux nouvelles clés, en 400 : `missing_observation_date`, `invalid_observation_date` |
| `GET /sunscan/stacked`, `GET /sunscan/animated` | chaque élément porte `hub_status` (`sent` / `not_sent`) et `spectrosolhub`. Nouveau paramètre `?hub_status=`, nouveau champ `hub_statuses` dans la réponse. Comme pour `GET /sunscan/scans` |
| Suppression des stacks / animations envoyés | routes existantes `DELETE /stacking/selection` et `DELETE /animations/selection`, qui prennent des noms de dossier (`folders=`), pas des chemins |
| Animations | envoyées en GIF, **jamais essayé sur le vrai hub** : à présenter comme expérimental, premier essai avec `publish: false` |

Les nouveaux stacks et animations enregistrent désormais leurs scans sources à la création : pour eux, date, raie, titre et note sont préremplis et `date_known` vaut `true`.

## À savoir avant de commencer

- **Le SunScan doit avoir un accès internet.** Depuis son hotspot, rien ne peut partir : il faut qu'il soit connecté à un WiFi (voir `provisioning-wifi.md`). Sans internet, les routes répondent `hub_unreachable`. Pour guider l'utilisateur, regarde `mode` dans `GET /network/status` : si c'est `hotspot`, propose l'écran de connexion au WiFi.
- **Le mot de passe n'est jamais conservé.** Le backend l'échange contre un jeton d'API et ne garde que le jeton (fichier lisible par le backend seul, hors de `storage/`). Le mot de passe transite en clair entre le téléphone et le SunScan sur le WiFi local, comme le mot de passe WiFi du provisioning.
- **Un seul envoi à la fois** pour tout le SunScan.
- **Seuls les JPEG partent sur le hub.** Le SER, les FITS et les PNG 16 bits restent sur le SunScan et ne sont sauvegardés nulle part ailleurs. C'est important pour la suppression des scans envoyés, voir la section 7.

Toutes les erreurs ont la même forme, avec un code HTTP adapté :

```json
{"status": "failed", "error": "<clé à traduire>", "detail": "<message brut, pour les logs>"}
```

## 1. Le compte

### État du compte

`GET /spectrosolhub/status`

```json
{"connected": true, "username": "guillaume", "site": "https://spectrosolhub.com",
 "verified": null, "error": "", "detail": "", "quota": null, "upload": null}
```

- `connected` : le SunScan a un jeton. Réponse immédiate, sans internet.
- `upload` : `{"key", "filename"}` de l'envoi en cours, sinon `null`. Utile pour reprendre le suivi à l'ouverture de l'app.

`GET /spectrosolhub/status?verify=true` vérifie en plus le jeton auprès du hub (jusqu'à 10 s) :

| `verified` | `error` | Signification |
|---|---|---|
| `true` | | compte valide, `quota` est rempli |
| `false` | `hub_unreachable` | pas d'internet ou hub injoignable. Le compte est **conservé**, `connected` reste `true` |
| `false` | `token_expired` | jeton révoqué ou expiré. Le compte est **oublié**, `connected` passe à `false` : redemander la connexion |

`quota` : `{"storage_bytes", "used_storage_bytes", "image_count", "used_image_count"}`. Une valeur à `0` pour un plafond signifie « pas de plafond connu ».

### Se connecter

`POST /spectrosolhub/login` avec `{"username": "...", "password": "...", "totp_code": ""}`

Réponse 200 : le même objet que `/spectrosolhub/status`, avec `connected: true`.

| Code | `error` | Quoi faire |
|---|---|---|
| 400 | `missing_credentials` | identifiant ou mot de passe vide |
| 401 | `invalid_credentials` | identifiants refusés |
| 403 | `totp_required` | compte protégé par la double authentification : afficher le champ du code à 6 chiffres et renvoyer la même requête avec `totp_code` |
| 403 | `invalid_totp` | le code envoyé est refusé |
| 503 | `hub_unreachable` | pas d'internet ou hub injoignable |
| 502 | `hub_rejected`, `hub_error` | autre refus (4xx) ou panne (5xx) du hub, voir `detail` |

### Se déconnecter

`POST /spectrosolhub/logout` : le SunScan oublie le jeton. Le jeton reste listé dans le compte sur le site (nommé `SunScan <nom de l'appareil>`), où l'utilisateur peut le révoquer.

## 2. Préparer l'écran d'envoi d'un scan

`POST /spectrosolhub/scan/` avec `{"filename": scan.ser}`

```json
{
  "key": "<md5 de scan.ser>",
  "images": [
    {"kind": "clahe", "label": "Clahe + Unsharp mask", "path": "storage/scans/.../sunscan_clahe.jpg", "size": 347640, "default": true},
    {"kind": "raw", "label": "Raw", "path": "storage/scans/.../sunscan_raw.jpg", "size": 135619, "default": false}
  ],
  "defaults": {"title": "H-alpha - 2026-09-18", "line": "halpha", "line_from_tag": true,
               "observation_date": "2026-09-18T13:42:28.359Z", "publish": true},
  "lines": [{"key": "halpha", "label": "Hα line - 6562.81 Å", "hub_label": "H-alpha", "wavelength": 6562.81}],
  "last_upload": null
}
```

- `images` : les images envoyables de ce scan, dans l'ordre d'envoi. `path` s'affiche avec `http://<api>/<path>`. `default` indique celles cochées par défaut (tout sauf le brut et quelques variantes). `images` vide = scan pas encore traité.
- `defaults.line` : la raie du scan, d'après son tag. **Les tags ne sont pas fiables** (scans Ca II H tagués K et inversement) : affiche un sélecteur alimenté par `lines`, prérempli avec `defaults.line`, et laisse l'utilisateur corriger. Si `line_from_tag` vaut `false`, le scan n'a pas de tag et `halpha` n'est qu'une valeur par défaut : demande confirmation.
- `type` (absent de l'exemple ci-dessus par souci de place) : `scan`, `stack` ou `animation`.
- `defaults.date_known` et `defaults.notes` : toujours `true` et vide pour un scan, voir la section 8.
- `last_upload` : le dernier envoi réussi de ce scan, ou `null` :

```json
{"session_id": 41, "url": "https://spectrosolhub.com/observation/41", "published": true,
 "title": "H-alpha - 2026-09-18", "images": ["clahe", "protus"], "uploaded_at": 1789816238}
```

S'il existe, préviens avant de renvoyer : **chaque envoi crée une nouvelle observation sur le hub**, la précédente n'est ni remplacée ni supprimée.

Erreurs : 400 `invalid_path`, 404 `file_not_found`.

## 3. Lancer l'envoi

`POST /spectrosolhub/upload/`

```json
{"filename": "<scan.ser>", "images": ["clahe", "protus", "cont"], "title": "", "notes": "", "line": "halpha", "publish": true}
```

Seul `filename` est obligatoire.

| Champ | Défaut | Rôle |
|---|---|---|
| `images` | les images `default` | liste de `kind`. L'ordre n'a pas d'importance, le backend envoie toujours dans l'ordre de `images` de la section 2 |
| `title` | `<raie> - <date>` | titre de l'observation |
| `notes` | | texte libre affiché avec l'observation |
| `line` | le tag du scan, sinon `halpha` | clé de raie choisie par l'utilisateur |
| `publish` | `true` | `false` : l'observation reste un brouillon, visible du seul compte, publiable ensuite depuis le site |
| `observation_date` | | ignoré pour un scan. Obligatoire pour un stack ou une animation dont la date n'est pas connue, voir la section 8 |

Réponse **202**, immédiate : `{"status": "started", "key": "<md5>", "images": ["clahe", "protus", "cont"]}`

| Code | `error` | Cause |
|---|---|---|
| 401 | `not_connected` | pas de compte sur le SunScan : ouvrir l'écran de connexion |
| 409 | `busy` | un autre envoi est en cours (voir `upload` dans `/spectrosolhub/status`) |
| 409 | `processing_in_progress` | le scan est en cours de traitement, ses images sont en train d'être réécrites |
| 409 | `not_processed` | le scan n'a aucune image |
| 400 | `invalid_image` | un `kind` demandé n'existe pas pour ce scan |
| 400 | `no_image` | `images` est une liste vide |
| 400 | `invalid_line` | clé de raie inconnue |
| 400 | `missing_observation_date`, `invalid_observation_date` | stacks et animations seulement, voir la section 8 |
| 400 / 404 | `invalid_path`, `file_not_found` | |

Un 202 ne dit rien du résultat : l'absence d'internet, par exemple, n'apparaît qu'ensuite, sur le canal.

## 4. Suivre l'envoi : canal `spectrosolhub_upload_<key>`

Même message que `scan_progress_<key>` (voir `progression-traitement.md`), avec quatre champs de plus :

```
spectrosolhub_upload_<key>;#;<status>;#;<percent>;#;<step>;#;<error>;#;<detail>;#;<image>;#;<images>;#;<url>;#;<published>
```

| Index | Champ | Valeurs |
|---|---|---|
| `message[1]` | `status` | `processing`, `completed`, `failed` |
| `message[2]` | `percent` | `0` à `99`, `100` uniquement avec `completed`. Calculé sur les octets envoyés |
| `message[3]` | `step` | `starting`, `checking_account`, `creating_session`, `uploading_images`, `publishing`, `done` |
| `message[4]` | `error` | clé d'erreur, vide sauf si `failed` |
| `message[5]` | `detail` | message brut, pour les logs |
| `message[6]` | `image` | numéro de l'image en cours, à partir de 1 (`0` avant la première) |
| `message[7]` | `images` | nombre d'images à envoyer. De quoi afficher « Image 2 / 5 » |
| `message[8]` | `url` | page de l'observation sur le hub, vide tant qu'elle n'est pas créée |
| `message[9]` | `published` | `1` si l'observation est publiée, sinon `0` |

Exemples, relevés pendant les tests contre un faux hub (seul le nom du site a été remplacé). Le dernier : le hub refuse tous les morceaux de la 2e image, la 1re est passée, les nouveaux essais sont épuisés.

```
spectrosolhub_upload_8ef689...;#;processing;#;5;#;uploading_images;#;;#;;#;1;#;3;#;https://spectrosolhub.com/observation/41;#;0
spectrosolhub_upload_8ef689...;#;completed;#;100;#;done;#;;#;;#;3;#;3;#;https://spectrosolhub.com/observation/41;#;1
spectrosolhub_upload_8ef689...;#;failed;#;47;#;uploading_images;#;hub_error;#;PUT /api/uploads/u2/parts/1 : HTTP 503 Service unavailable;#;2;#;3;#;https://spectrosolhub.com/observation/41;#;0
```

Comme pour le traitement : seul le dernier état est envoyé (des pourcentages peuvent être sautés), tous les clients le reçoivent, et il est renvoyé à chaque (re)connexion du WebSocket pendant 30 minutes après la fin.

### L'ordre à respecter : POST, puis abonnement, puis un appel d'état

**Attention, ce n'est pas le même ordre que pour le traitement.** Renvoyer un scan est courant (après un échec, justement). Or l'état final de l'envoi précédent reste rejouable 30 minutes : un écran abonné *avant* le POST peut le recevoir et croire le nouvel envoi déjà terminé.

Le backend remet l'état du scan à zéro **avant** de répondre 202. Donc :

1. `POST /spectrosolhub/upload/`, attendre le 202 ;
2. s'abonner à `spectrosolhub_upload_<key>` ;
3. appeler **une fois** `POST /spectrosolhub/upload/status/` pour rattraper ce qui s'est passé entre 1 et 2 (un échec immédiat faute d'internet arrive en quelques millisecondes).

Avec cet ordre, un état périmé est impossible. Il reste un effet cosmétique à gérer côté app : un message WebSocket émis avant la réponse de l'étape 3 peut être lu après elle, donc un pourcentage plus petit peut arriver après un plus grand (vu en test : `5`, `2`, `100`). Trois règles suffisent :

- pendant `processing`, n'affiche jamais un pourcentage inférieur au précédent (`Math.max`) ;
- un état `completed` ou `failed` l'emporte toujours ;
- après un état final, ignore tout et désabonne-toi.

### Fin de l'envoi

- `completed` avec `published` à `1` : tout est en ligne. Propose d'ouvrir `url`.
- `completed` avec `published` à `0` alors que `publish: true` était demandé : les images sont sur le hub mais la publication a été refusée. L'observation est un brouillon, à publier depuis le site. Ce n'est pas un échec.
- `failed` avec `url` non vide : l'observation a été créée puis l'envoi a cassé. **Un brouillon incomplet reste sur le hub**, le backend ne sait pas le supprimer. Donne `url` à l'utilisateur pour qu'il le retrouve. Un nouvel envoi créera une autre observation.

Un morceau d'image refusé ou perdu est renvoyé automatiquement (3 essais) : une coupure WiFi brève ne fait pas échouer l'envoi.

### Clés d'erreur du canal

| Clé | Cause |
|---|---|
| `hub_unreachable` | pas d'internet (SunScan en hotspot ?) ou hub injoignable, y compris en cours d'envoi |
| `token_expired` | jeton révoqué ou expiré. Le compte est oublié : redemander la connexion, puis renvoyer |
| `quota_exceeded` | plus assez de place sur le compte (nombre d'images ou volume). Vérifié avant de créer quoi que ce soit sur le hub |
| `hub_rejected` | le hub a refusé une requête (4xx), voir `detail` |
| `hub_error` | panne du hub (5xx) malgré les nouveaux essais |
| `upload_failed` | erreur inattendue côté SunScan, voir `detail` |

Prévois un libellé générique pour une clé ou une étape inconnue.

## 5. Récupérer l'état à la demande

`POST /spectrosolhub/upload/status/` avec `{"filename": scan.ser}` :

```json
{"key": "<md5>", "status": "processing", "percent": 37, "step": "uploading_images", "error": "", "detail": "",
 "image": 2, "images": 3, "url": "https://spectrosolhub.com/observation/41", "published": 0}
```

`status` vaut `unknown` si aucun envoi de ce scan n'est connu (jamais lancé depuis le démarrage du backend, ou terminé depuis plus de 30 minutes). L'état est en mémoire. Ce qui est durable, c'est `last_upload` (section 2) et la marque du scan (section 7).

## 6. Exemple

```js
const key = md5(scan.ser);
const channel = 'spectrosolhub_upload_' + key;
let finished = false;

const apply = ([, status, percent, step, error, , image, images, url, published]) => {
  if (finished) return;
  if (status === 'processing') {
    setProgress((p) => Math.max(p, parseInt(percent, 10)));      // ne jamais reculer
    setStepLabel(t('hub:step.' + step, { defaultValue: t('hub:step.generic') }));
    setImageLabel(image > 0 ? `${image} / ${images}` : '');
    return;
  }
  if (status === 'unknown') return;
  finished = true;
  unsubscribe(channel);
  setSessionUrl(url);                                            // peut être rempli même en cas d'échec
  if (status === 'failed') setErrorLabel(t('hub:error.' + error, { defaultValue: t('hub:error.generic') }));
  else setPublished(published === '1');
  setUploadStatus(status);
};

// 1. lancer l'envoi
setProgress(0);
const response = await fetch(api + '/spectrosolhub/upload/', { method: 'POST', headers, body: JSON.stringify({ filename: scan.ser, images, title, notes, line, publish }) });
const json = await response.json();
if (response.status !== 202) {
  setErrorLabel(t('hub:error.' + json.error, { defaultValue: t('hub:error.generic') }));
  return;
}

// 2. s'abonner, 3. rattraper l'état une fois
subscribe(channel, apply);
const s = await (await fetch(api + '/spectrosolhub/upload/status/', { method: 'POST', headers, body: JSON.stringify({ filename: scan.ser }) })).json();
apply([channel, s.status, String(s.percent), s.step, s.error, s.detail, String(s.image), String(s.images), s.url, String(s.published)]);
```

## 7. Marquer, filtrer et supprimer les scans envoyés

Un scan dont un envoi s'est **terminé avec succès** est marqué. La marque vient d'un fichier écrit dans le dossier du scan à la fin de l'envoi, pas des messages WebSocket : elle survit aux redémarrages et disparaît avec le scan.

Chaque scan renvoyé par `GET /sunscan/scans` et `POST /sunscan/scan` porte deux champs de plus :

- `hub_status` : `sent` ou `not_sent` ;
- `spectrosolhub` : l'objet `last_upload` de la section 2, ou `null`. De quoi afficher un badge et ouvrir l'observation.

### Filtrer

`GET /sunscan/scans?hub_status=sent` (ou `not_sent`). Le filtre se combine avec `tag`, `status`, `date_from` et `date_to`, et s'applique avant la pagination. La réponse contient le compteur `hub_statuses`, calculé comme les autres compteurs (avec les autres filtres, sans le sien) :

```json
{"total": 12, "scans": [], "tags": {}, "statuses": {}, "days": {}, "hub_statuses": {"sent": 12, "not_sent": 92}}
```

Une autre valeur que `sent` ou `not_sent` répond 422.

### Supprimer les scans envoyés

Pas de nouvelle route : filtre, puis supprime avec la route existante.

```js
const { scans } = await (await fetch(api + '/sunscan/scans?hub_status=sent&size=1000')).json();
await fetch(api + '/sunscan/scans/delete/', { method: 'POST', headers, body: JSON.stringify({ paths: scans.map((s) => s.path) }) });
```

### Ce que la marque garantit, et ce qu'elle ne garantit pas

À dire clairement dans la confirmation de suppression, parce que « envoyé » se lit vite comme « sauvegardé » :

- **`sent` = toutes les images *choisies* lors du dernier envoi ont été acceptées par le hub.** Ce peut être une seule image sur six (voir `spectrosolhub.images`).
- **Le SER, les FITS et les PNG 16 bits ne sont jamais envoyés.** Supprimer un scan `sent`, c'est perdre définitivement ses données brutes : on ne pourra plus le retraiter. Seuls des JPEG 8 bits existent sur le hub.
- La marque dit « a été envoyé », pas « est toujours sur le hub » : si l'utilisateur supprime l'observation sur le site, le scan reste `sent`.
- Un scan retraité après l'envoi reste `sent`, alors que ses images ont changé.
- Un envoi `failed` ne marque pas le scan, même si une partie des images est arrivée.

## 8. Stacks et animations

Mêmes routes, même canal, mêmes erreurs. À la place de `scan.ser`, mets dans `filename` le **`path` du stack ou de l'animation**, tel que renvoyé par `GET /sunscan/stacked` et `GET /sunscan/animated` (par exemple `storage/stacking/2026-09-18_11-12-53`). La clé du canal reste `md5(filename)`. `POST /spectrosolhub/scan/` répond avec `type` à `stack` ou `animation`.

### Les images

| | Stack | Animation |
|---|---|---|
| Fichiers | JPEG | GIF |
| `kind` | `clahe_sharpen`, `clahe_raw`, `cont_sharpen`, `negative_raw`, `color_sharpen`, `protus_raw`... | `clahe`, `clahe_sharpen`, `clahe_raw`, `cont`, `negative`, `protus`... |
| `default` | une image par type, la version `sharpen` quand elle existe | pareil |

Ne code pas la liste en dur : elle varie d'un dossier à l'autre (selon l'âge du stack et ce que contenaient les scans). Affiche ce que renvoie `images`. Les aperçus (`*_preview`) et les fichiers étrangers trouvés dans certains dossiers ne sont jamais proposés.

### La date d'observation : le point à ne pas rater

Le dossier d'un stack ou d'une animation porte la date de sa **création**, pas celle de l'observation. Un stack fait le 19/09 à partir de scans du 18/09 s'appelle `2026-09-19_13-54-22` ; l'écart peut être de plusieurs mois. Le backend ne devine donc jamais la date à partir du dossier : une date fausse dans une archive scientifique est pire qu'une date demandée.

- **Stacks et animations créés à partir de cette version** : le backend enregistre à la création les scans sources, leur raie et leurs dates. `defaults.date_known` vaut `true` et tout est prérempli :

```json
{"title": "H-alpha - 2026-09-18 - stack of 2 scans", "line": "halpha", "line_from_tag": true,
 "observation_date": "2026-09-18T08:29:28.000Z", "date_known": true,
 "notes": "Stack of 2 scans, 2026-09-18 08:25:51 to 08:33:06 UT", "publish": true}
```

  La date d'un stack est la moyenne de ses scans, celle qui est écrite dans le filigrane de ses images ; celle d'une animation est son premier scan. C'est le champ `observation_date` des listes (voir `tags-stacks-animations.md`). Le nom d'observateur passé au stacking est envoyé avec chaque image. Pour une animation de stacks, ce sont les dates des stacks sources, si elles sont connues.

- **Tous ceux créés avant** (132 stacks et 44 animations sur le SunScan de développement) : `date_known` vaut `false`, `observation_date` vaut `null`, `line_from_tag` vaut `false`, sauf si le stack a été tagué à la main depuis (voir `tags-stacks-animations.md`) : sa raie est alors proposée. L'app doit **demander la date et l'heure de l'observation** (en UTC) et la raie, puis les envoyer :

```json
{"filename": "storage/stacking/2025-07-12_10-02-11", "line": "caIIK", "observation_date": "2025-07-12T07:55:00Z"}
```

| Code | `error` | Cause |
|---|---|---|
| 400 | `missing_observation_date` | date inconnue du backend et absente de la requête |
| 400 | `invalid_observation_date` | format attendu : `YYYY-MM-DDTHH:MM:SSZ`, en UTC |

  Pour aider l'utilisateur, le filigrane des images d'un stack contient sa date moyenne (« 3 stacked images - 2025/07/12 07:55:00 UT ») : affiche l'image à côté du champ.

Quand la date est connue du backend, un `observation_date` envoyé par l'app est ignoré : il ne peut pas remplacer une date sûre.

`defaults.notes` est une proposition pour préremplir le champ. L'envoi prend `notes` tel quel : si l'utilisateur vide le champ, rien n'est envoyé.

### Animations : avertissement

Les animations sont envoyées telles quelles, en `image/gif`. **Rien ne dit que le hub les accepte** : INTI Partner et JSol'Ex, dont ce code est tiré, n'envoient que du JPEG, et cela n'a pas pu être essayé. Deux issues possibles au premier essai réel :

- le hub accepte : rien à changer ;
- le hub refuse : l'envoi se termine en `failed` avec `hub_rejected`, et `detail` contient la réponse du hub. **Un brouillon vide reste alors sur le compte** (`url` le désigne), à supprimer à la main sur le site.

Fais ce premier essai avec `publish: false`. Tant qu'il n'a pas été fait, présente la fonction comme expérimentale dans l'app, ou masque-la pour les animations. Si le hub refuse, il faudra retirer les animations côté backend plutôt que de laisser les utilisateurs créer des brouillons vides.

### Marquer, filtrer, supprimer

Comme pour les scans (section 7) : chaque élément de `GET /sunscan/stacked` et `GET /sunscan/animated` porte `hub_status` et `spectrosolhub`, et les deux routes acceptent `?hub_status=sent` ou `not_sent`, appliqué avant la pagination. La réponse contient `hub_statuses`, calculé comme pour les scans (avec l'autre filtre, `tag`, sans le sien), les deux clés toujours présentes :

```json
{"total": 1, "scans": [], "tags": {"": 1}, "hub_statuses": {"sent": 1, "not_sent": 131}}
```

Le filtre `?tag=` et le compteur `tags` des stacks et des animations sont décrits dans `tags-stacks-animations.md`.

Suppression avec les routes existantes, qui prennent les **noms de dossier** et non les chemins :

```js
const { scans } = await (await fetch(api + '/sunscan/stacked?hub_status=sent&size=1000')).json();
const query = scans.map((s) => 'folders=' + encodeURIComponent(s.path.split('/').pop())).join('&');
await fetch(api + '/stacking/selection?' + query, { method: 'DELETE' });      // '/animations/selection' pour les animations
```

Les mêmes réserves s'appliquent : seuls les JPEG ou GIF choisis sont sur le hub, les PNG 16 bits du stack ne le sont pas.

## Compatibilité

| App | Backend | Résultat |
|---|---|---|
| ancienne | nouveau | inchangé : l'app ignore le canal `spectrosolhub_upload_<key>` et les champs `hub_status` et `spectrosolhub` des scans |
| nouvelle | ancien | les routes `/spectrosolhub/*` répondent 404 : masquer la fonction. Tester avec `GET /spectrosolhub/status` au démarrage |
| nouvelle | backend du 19/09 au matin (scans seulement) | `POST /spectrosolhub/scan/` répond 400 `invalid_path` pour un stack ou une animation : masquer la fonction pour eux |
