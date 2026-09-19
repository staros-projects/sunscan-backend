# Images Hε d'un scan Ca II H : côté app mobile

La raie Hε (3970,08 Å) est dans l'aile rouge de Ca II H, à 1,6 Å du cœur. Un scan Ca II H la contient donc déjà. Le backend en tire maintenant trois images de plus, pendant le traitement normal du scan, pour environ 4 s de calcul en plus.

## En bref

- **Rien d'obligatoire.** Les images arrivent dans `images` de `POST /sunscan/scan`, que `PictureScreen.js` parcourt déjà de façon générique : elles s'affichent dans la bande de vignettes avec le code actuel.
- **À faire, avec le suivi de progression :** une clé de traduction pour la nouvelle étape (partie 3).
- **À envisager :** proposer de retraiter quand on tague `caIIH` un scan déjà traité (partie 1).

## 1. Quand les images existent

Deux conditions, vérifiées **au moment du traitement** :

1. le scan est tagué `caIIH` (fichier `tag_caIIH`, posé par `POST /sunscan/scan/tag/`) ;
2. le spectre du scan confirme que la raie est bien Ca II H. Le tag seul ne suffit pas : un scan Ca II K tagué `caIIH` par erreur est écarté.

Donc le tag doit être posé **avant** `POST /sunscan/scan/process/`. C'est le cas quand il est choisi dans `ModalLineSelector` juste après le scan. S'il est posé ou corrigé plus tard avec le `LineSelector` de `PictureScreen.js`, les images Hε n'apparaissent qu'après un nouveau traitement. Proposer ce retraitement à ce moment-là évite que l'utilisateur les cherche.

Pas d'images Hε dans ces cas, sans erreur ni message, le reste du traitement est normal :

- la raie scannée n'est pas Ca II H, quel que soit le tag ;
- la raie est trop près du bord du spectre, scan mal centré sur la raie (il faut une quinzaine de colonnes de chaque côté du cœur) ;
- traitement hélium (`advanced: 'heI'`) ou raie libre (`offset` différent de 0).

## 2. Ce que renvoie `POST /sunscan/scan`

Trois entrées de plus dans `images`, même format que les autres : `[libellé, existe, date]`.

```json
"hepsilon":        ["Hε : Clahe + Unsharp mask", true, 1789813227.7],
"hepsilon_color":  ["Hε : Artificial color",     true, 1789813227.7],
"hepsilon_protus": ["Hε : Artificial eclipse",   true, 1789813227.7]
```

| Clé | Image | Fichiers `sunscan_<clé>.*` |
|---|---|---|
| `hepsilon` | surface à la longueur d'onde de Hε, même traitement que `clahe` | `jpg`, `png` 16 bits, `fits` |
| `hepsilon_color` | la même, colorisée | `jpg` |
| `hepsilon_protus` | protubérances en Hε, disque masqué | `jpg`, `png` 16 bits |

- Elles sont placées après `clahe_colour` et avant `raw` : les images Ca II H restent en tête, et `clahe` reste l'image affichée à l'ouverture.
- Les clés sont présentes pour tous les scans, avec `existe` à `false` quand il n'y a pas d'image, comme `helium` aujourd'hui.
- L'URL se construit comme les autres : `/<scan.path>/sunscan_hepsilon.jpg?v=<date>`. Le téléchargement actuel (`downloadSunscanImage`) fonctionne tel quel.
- Le libellé n'est pas traduit, comme les autres. Il est affiché dans `ScanInfo` (type d'image).

L'image de surface ressemble à une photosphère avec des facules : à cette résolution l'aile de Ca II H domine, c'est normal. Celle des protubérances est la plus parlante. Elles sont plus faibles qu'en Ca II H, et certaines n'y apparaissent pas du tout.

## 3. Progression

Nouvelle clé d'étape sur le canal `scan_progress_<key>` : **`image_hepsilon`**, envoyée en dernier, seulement quand les images Hε sont produites.

Ça ne concerne que la version de l'app qui écoute ce canal, voir [progression-traitement.md](progression-traitement.md) ; la version publiée ne l'écoute pas et n'a rien à faire. À ajouter avec les autres clés `process:step.*`, dans `localization/fr/` et `localization/en/` :

```js
image_hepsilon: 'Images Hε',
```

Sans cette clé, le libellé générique prévu dans cette doc s'affiche. Quand le scan est tagué `caIIH` mais écarté par la vérification du spectre, l'étape n'est jamais envoyée et le pourcentage passe directement de la dernière étape à `completed`.

## 4. Ce qui n'existe pas pour Hε

- **Planisphère.** Pas de `sunscan_hepsilon*_proj.jpg`. Rien à changer : `PictureScreen.js` ne trouve aucune entrée correspondante dans `scan.planispheres` et n'affiche donc rien.
- **Empilement et animation.** Le backend choisit lui-même les types d'images qu'il empile ou anime, et Hε n'en fait pas partie. Rien à changer.
- **Négatif.** Pas d'image négative Hε.
- **Anciennes images.** Si un scan traité en `caIIH` est ensuite retagué puis retraité, les fichiers Hε du premier traitement restent dans le dossier et `existe` reste à `true`. Même comportement que pour `doppler` ou `negative` aujourd'hui.

## 5. Pour tester

Sur le Pi de développement :

| Scan | Tag | Résultat attendu |
|---|---|---|
| `2025_10_04/sunscan_2025_10_04-10_54_44` | `caIIH` | les trois images Hε, protubérance visible au limbe droit |
| `2025_07_12/sunscan_2025_07_12-08_15_52` | `caIIH` | aucune image Hε : c'est en réalité un scan Ca II K |
| n'importe quel scan `halpha` | `halpha` | aucune image Hε, traitement inchangé |

Les images n'existent qu'après un traitement fait avec le nouveau backend : relance le traitement du scan depuis l'app.
