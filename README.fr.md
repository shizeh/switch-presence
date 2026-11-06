# Switch Presence

[English](README.md) | **Français**

Affiche le jeu auquel tu joues sur **Nintendo Switch** ou **Nintendo Switch 2** directement sur ton profil Discord.

Les consoles Nintendo n'ont pas d'intégration Discord native. Switch Presence est donc **manuel** : tu choisis ton jeu dans la liste, et il apparaît sur ton profil avec la jaquette, le nom de la console et un chrono de session.

> Créé par **Baptiste Shizeh**. Projet de fan, non affilié à Nintendo ni à Discord.

## Fonctionnalités

- **Disponible en français, anglais et espagnol** : anglais par défaut, et tu peux en changer à tout moment dans Paramètres > Général
- Choix de la console : Nintendo Switch ou Nintendo Switch 2
- Liste de jeux avec recherche, favoris (★) et ajout de tes propres jeux
- Jaquette en grand, icône de la console en badge, chrono de session
- **Personnalisation simple** avec interrupteurs et aperçu en direct (chrono, console, badge, bouton « Get this status »)
- **Centre d'aide** intégré avec des tutoriels pas à pas, et un moyen rapide de me contacter
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

Toutes les personnes qui utilisent l'appli passent alors par **ton** application Discord. Les jaquettes et icônes que tu uploades dedans sont partagées entre tous. Pour qu'un nouveau jeu ait sa cover pour tout le monde, uploade son image puis ajoute-le dans `games.json` (voir plus bas) : aucun nouvel `.exe` n'est nécessaire.

Un utilisateur qui ajoute un jeu à lui peut donner un lien `https://` vers une image comme cover (testé avec une image Wikimedia) : ça ne demande aucun upload.

> Windows SmartScreen peut afficher un avertissement au premier lancement : l'exe n'est pas signé numériquement (une signature est payante). Clique sur « Informations complémentaires » puis « Exécuter quand même ». Certains antivirus signalent aussi à tort les `.exe` créés avec PyInstaller. Le code source complet est ici, et tu peux compiler toi-même.

### Ajouter des jeux sans recompiler

L'appli télécharge [`games.json`](games.json) depuis ce dépôt à chaque lancement (et garde une copie pour le mode hors-ligne). Pour ajouter un jeu :

1. Uploade sa cover dans Art Assets (Developer Portal). `prepare_covers.py` en prépare plusieurs d'un coup.
2. Ajoute une ligne dans `games.json` sur GitHub (icône crayon, puis *Commit changes*) :
   ```json
   { "name": "Super Mario Odyssey", "cover": "super_mario_odyssey" }
   ```

Tout le monde reçoit le jeu au prochain lancement (ou via **Options > Actualiser la liste des jeux**). Quand tu publies un nouvel `.exe`, augmente `latest_version` dans `games.json` : les anciennes versions afficheront un lien « Version disponible ».

## Configuration Discord (une seule fois)

Discord n'affiche une Rich Presence qu'à travers une « application » Discord. Il en faut une seule pour tous les jeux.

1. Va sur le [Developer Portal](https://discord.com/developers/applications) et clique sur **New Application**.
2. Copie l'**Application ID** (onglet *General Information*) dans `Options > Paramètres` de l'appli.
   Si tu distribues l'appli, tu peux aussi le mettre dans `DEFAULT_CLIENT_ID` en haut de `switch_presence.py` : c'est un identifiant public, pas un secret.
3. Dans **Rich Presence > Art Assets**, uploade :
   - `badge_switch1` et `badge_switch2` : les badges de console, deux images carrées 512×512 à toi (le petit rond affiché dans le coin de la cover)
   - `default_cover` : l'image affichée pour les jeux sans jaquette (le logo de l'appli convient)
   - une image par jeu, dont le **nom de fichier sans extension** est la clé (ex : `mario_kart_world`)
4. Attends quelques minutes que Discord prenne en compte les images.

## Ajouter un jeu

Dans l'appli : **+ Ajouter un jeu**, puis le nom du jeu. Pour la cover, colle un lien direct vers une image (finissant par `.png` ou `.jpg`) ; si tu laisses vide, une image par défaut s'affiche. Le nom du jeu s'affiche toujours correctement.

Tu veux qu'un jeu soit ajouté pour tout le monde avec sa vraie jaquette ? **Aide > Demander l'ajout d'un jeu** ouvre une demande sur GitHub.

## Traductions

L'appli existe en **français, anglais et espagnol**. Les textes sont dans le dossier [`locales`](locales), un fichier JSON par langue. Pour ajouter une langue :

1. Copie `locales/en.json` en `locales/xx.json` (`xx` = code de la langue, par exemple `de`).
2. Traduis les valeurs (garde les clés et les `{variables}` intactes) et mets dans `"_name"` le nom de la langue dans cette langue, par exemple `"Deutsch"`.
3. Ouvre une pull request, ou envoie-moi le fichier via une [demande GitHub](../../issues/new). La langue apparaît alors automatiquement dans **Paramètres > Général**.

## À propos des jaquettes

Les jaquettes appartiennent à leurs éditeurs. Ce dépôt ne les distribue pas : le dossier `assets/covers/` est ignoré par Git. Utilise tes propres images pour ton application Discord.

## Contact

Un bug, une idée, un jeu à ajouter ? Ouvre une [demande GitHub](../../issues/new) ou écris-moi sur Discord : **Shizeh**. L'appli a aussi **Aide > Contacter le créateur**.

## Limites

- Le petit en-tête « Playing on PlayStation » est une fonction native de Discord, indisponible pour les Rich Presence personnalisées. Switch Presence affiche donc le nom de la console sous le nom du jeu.
- Le client Discord de bureau doit être ouvert.

## Licence

MIT. Voir [LICENSE](LICENSE).
