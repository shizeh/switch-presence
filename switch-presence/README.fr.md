# Switch Presence

[English](README.md) | **Français**

Affiche le jeu auquel tu joues sur **Nintendo Switch** ou **Nintendo Switch 2** directement sur ton profil Discord.

Les consoles Nintendo n'ont pas d'intégration Discord native. Switch Presence est donc **manuel** : tu choisis ton jeu dans la liste, et il apparaît sur ton profil avec la jaquette, le nom de la console et un chrono de session.

> Créé par **Baptiste Shizeh**. Projet de fan, non affilié à Nintendo ni à Discord.

## Fonctionnalités

- Choix de la console : Nintendo Switch ou Nintendo Switch 2
- Liste de jeux avec recherche, favoris (★) et ajout de tes propres jeux
- Jaquette en grand, icône de la console en badge, chrono de session
- Message perso optionnel (ex : « Niveau 12 »)
- Thème sombre / clair
- Export / import de ta liste de jeux

## Installation (version .exe)

1. Télécharge `SwitchPresence.exe` depuis la page [Releases](../../releases).
2. Ouvre l'application **Discord** sur ton PC (pas le navigateur).
3. Lance `SwitchPresence.exe`, choisis ta console et double-clique sur un jeu.

Dans Discord, vérifie **Paramètres > Confidentialité des activités > Partager mon activité détectée**.

## Lancer depuis le code

```
python -m pip install -r requirements.txt
python switch_presence.py
```

Pour fabriquer toi-même le `.exe` (Windows) : double-clique sur `build.bat`. Le fichier arrive dans `dist/`.

## Publier l'appli pour que tout le monde l'utilise (mainteneur)

Pour que les utilisateurs n'aient **rien à configurer** :

1. Crée l'application Discord et uploade les images (voir la section suivante).
2. Colle son Application ID dans `DEFAULT_CLIENT_ID` en haut de `switch_presence.py` (identifiant public, pas un secret).
3. Compile le `.exe` (`build.bat`) ou pousse un tag : `git tag v1.0.0 && git push origin v1.0.0`. GitHub Actions compile `SwitchPresence.exe` et le publie dans les Releases.

Toutes les personnes qui utilisent l'appli passent alors par **ton** application Discord. Les jaquettes et icônes que tu uploades dedans sont partagées entre tous. Pour qu'un nouveau jeu ait sa cover pour tout le monde, ajoute-le à `BUILTIN_GAMES`, uploade son image, puis publie une nouvelle version.

Un utilisateur qui ajoute un jeu à lui peut donner un lien `https://` vers une image comme cover : ça ne demande aucun upload.

> Windows SmartScreen peut afficher un avertissement au premier lancement : l'exe n'est pas signé numériquement (une signature est payante). Clique sur « Informations complémentaires » puis « Exécuter quand même ». Certains antivirus signalent aussi à tort les `.exe` créés avec PyInstaller. Le code source complet est ici, et tu peux compiler toi-même.

## Configuration Discord (une seule fois)

Discord n'affiche une Rich Presence qu'à travers une « application » Discord. Il en faut une seule pour tous les jeux.

1. Va sur le [Developer Portal](https://discord.com/developers/applications) et clique sur **New Application**.
2. Copie l'**Application ID** (onglet *General Information*) dans `Options > Paramètres` de l'appli.
   Si tu distribues l'appli, tu peux aussi le mettre dans `DEFAULT_CLIENT_ID` en haut de `switch_presence.py` : c'est un identifiant public, pas un secret.
3. Dans **Rich Presence > Art Assets**, uploade :
   - `switch1` et `switch2` : les icônes de console (exemples dans `assets/`)
   - une image par jeu, dont le **nom de fichier sans extension** est la clé (ex : `mario_kart_world`)
4. Attends quelques minutes que Discord prenne en compte les images.

## Ajouter un jeu

Dans l'appli : **+ Ajouter un jeu**, puis le nom et la clé de la cover (ou un lien https vers une image). Si tu laisses la clé vide, l'appli en génère une à partir du nom du jeu et te l'indique.

Pour ajouter un jeu à la liste intégrée, ajoute une ligne dans `BUILTIN_GAMES` en haut de `switch_presence.py`.

## À propos des jaquettes

Les jaquettes appartiennent à leurs éditeurs. Ce dépôt ne les distribue pas : le dossier `assets/covers/` est ignoré par Git. Utilise tes propres images pour ton application Discord.

## Limites

- Le petit en-tête « Playing on PlayStation » est une fonction native de Discord, indisponible pour les Rich Presence personnalisées. Switch Presence affiche donc le nom de la console sous le nom du jeu.
- Le client Discord de bureau doit être ouvert.

## Licence

MIT. Voir [LICENSE](LICENSE).
