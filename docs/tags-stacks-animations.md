# Tags des stacks et des animations, et correction de leur date

Deux changements sur `GET /sunscan/stacked` et `GET /sunscan/animated`. Rien ne change pour les scans.

## 1. Corrigé : un stack envoyé sur SpectroSolHub remontait en tête de liste

`creation_date` était la date de modification du **dossier** du stack. Or cette date change dès qu'un fichier est ajouté au dossier : l'envoi sur SpectroSolHub y écrit sa marque, donc chaque stack envoyé prenait la date de l'envoi et passait en tête. Vérifié sur le SunScan de développement : les 5 premiers de la liste étaient exactement les 5 stacks envoyés.

`creation_date` vient maintenant du nom du dossier (`2026-01-22_10-50-10`, heure locale du SunScan), qui ne bouge jamais. Même champ, même format (secondes Unix) : **rien à changer dans l'app**. Les 5 stacks déjà touchés ont retrouvé leur place, sans rien réécrire sur la carte SD.

## 2. Nouveau : le tag, comme pour les scans

| Où | Quoi |
|---|---|
| chaque élément de `/sunscan/stacked` et `/sunscan/animated` | nouveau champ `tag` : clé de raie (`halpha`, `caIIK`, ...) ou `""` si non tagué. Mêmes clés que `scan.tag` |
| les deux routes | nouveau paramètre `?tag=<clé>`, et `?tag=none` pour les non tagués. Se combine avec `hub_status`, s'applique avant la pagination, `total` est le total filtré |
| réponse des deux routes | nouveau compteur `tags`, par exemple `{"halpha": 12, "": 120}` (`""` = non tagués, clé absente = 0). Comme pour les scans : calculé avec l'autre filtre (`hub_status`) mais sans le sien |
| `hub_statuses` | tient maintenant compte du filtre `tag` (même règle). Les deux clés `sent` et `not_sent` restent toujours présentes |

```
GET /sunscan/stacked?tag=halpha&page=1&size=20
{"total": 12, "scans": [{"path": "storage/stacking/2026-09-19_14-09-44", "tag": "halpha", "creation_date": 1789819784, ...}],
 "tags": {"halpha": 12, "": 120}, "hub_statuses": {"sent": 2, "not_sent": 10}}
```

Il n'y a pas de filtre par date ni par statut sur ces deux routes (pas de champs `days` ni `statuses`) : n'affiche que les filtres dont le compteur est présent dans la réponse.

### D'où vient le tag

- **Stacks et animations créés à partir de cette version** : le tag est repris automatiquement des scans sources, à la création. C'est la raie du premier scan tagué de la sélection, la même que celle écrite dans le filigrane des images. Si aucun scan n'est tagué, le stack n'a pas de tag. Une animation de stacks reprend le tag des stacks.
- **Tous ceux créés avant** (132 stacks et 42 animations sur le SunScan de développement) : `tag` vaut `""`. La raie n'a été enregistrée nulle part à l'époque, seulement incrustée dans le filigrane, et le backend ne devine pas. Ils apparaissent donc tous sous `?tag=none`, ce qui donne à l'app la liste exacte de ce qui reste à taguer.

### Taguer ou corriger à la main

La route des scans marche telle quelle avec le `path` d'un stack ou d'une animation :

```js
await fetch(api + '/sunscan/scan/tag/', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ filename: stack.path, tag: 'halpha' }),   // remplace le tag précédent
});
```

Pour rattraper l'historique : proposer le même sélecteur de raie que pour un scan, sur l'écran d'un stack et, idéalement, sur une sélection multiple (un appel par élément). Le filigrane de l'image rappelle souvent la raie à l'utilisateur. Comme pour les scans, la route ne sait pas retirer un tag, seulement le remplacer.

Taguer un stack ne change plus sa date ni sa place dans la liste (c'est le même mécanisme que la correction du point 1).

### Lien avec l'envoi SpectroSolHub

`defaults.line` de `POST /spectrosolhub/scan/` prend maintenant le tag du stack en priorité. Un ancien stack tagué à la main propose donc sa raie (`line_from_tag: true`) ; il faut toujours demander sa date d'observation (`date_known: false`).

## Compatibilité

| App | Backend | Résultat |
|---|---|---|
| ancienne | nouveau | inchangé : champs en plus ignorés, et l'ordre de la liste est corrigé sans rien faire |
| nouvelle | ancien | pas de champ `tags` dans la réponse : masquer le filtre, comme pour les scans. `?tag=` est ignoré par un ancien backend |
