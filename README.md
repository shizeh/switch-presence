# Switch Presence

<p align="center"><img src="assets/icon.png" width="128" alt="Switch Presence logo"></p>

**English** | [Français](README.fr.md)

Show the game you're playing on your **Nintendo Switch** or **Nintendo Switch 2** right on your Discord profile.

Nintendo consoles have no native Discord integration, so Switch Presence is **manual**: you pick your game in a list, and it appears on your profile with the cover art, the console name and a session timer.

> Made by **Baptiste Shizeh**. Fan project, not affiliated with Nintendo or Discord.

## Features

- Choose your console: Nintendo Switch or Nintendo Switch 2
- Game list with search, favorites (★) and your own custom games
- Big cover art, console badge, session timer
- Optional custom message (e.g. "Level 12")
- Dark and light themes
- Export / import your game list

## Quick start (Windows)

1. Download **`SwitchPresence.exe`** from the [Releases page](../../releases/latest).
2. Open the **Discord desktop app** on your PC (the browser version won't work).
3. Run `SwitchPresence.exe`, pick your console, then **double-click a game**.

That's it, your profile now shows the game. Click **Stop** to remove it. Closing the app also clears it.

### Nothing shows on Discord?

- Make sure you use the **Discord desktop app**, not the website.
- In Discord, go to **Settings > Activity Privacy** and turn on **Share my detected activity**.
- Look at your profile from another account or ask a friend: Discord sometimes displays your own activity differently.
- Covers can take a few minutes to appear after a new game is added.

### Windows shows a warning at first launch

You may see a blue "Windows protected your PC" screen. The app is not digitally signed (signing costs money). Click **More info**, then **Run anyway**. Some antivirus programs also flag any app built with PyInstaller by mistake. The full source code is in this repository, and you can [build it yourself](#build-it-yourself).

## Adding your own game

Click **+ Add a game** in the app, then enter:

- the game name
- a cover: a direct image link (`https://…`) works with no setup. Leave it empty to use the built-in key.

Right-click a game to add it to favorites, change its cover, or remove it.

## Using your own Discord application (optional)

By default the app uses the project's Discord application, with all the built-in covers. If you want your own:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Copy its **Application ID** (General Information tab).
3. Paste it in **Options > Settings** in the app.
4. In **Rich Presence > Art Assets**, upload `assets/switch1.png`, `assets/switch2.png` and one image per game. The image name (without extension) is the cover key, for example `mario_kart_world`.

## Build it yourself

You need [Python 3.10+](https://www.python.org/downloads/) (tick "Add Python to PATH" when installing).

```
python -m pip install -r requirements.txt
python switch_presence.py
```

To create the `.exe`, double-click **`build.bat`**. The file appears in the `dist` folder.

## For the maintainer: publishing a release

1. Create the Discord application and upload the images (see above).
2. Paste its Application ID in `DEFAULT_CLIENT_ID` at the top of `switch_presence.py` (it is a public ID, not a secret).
3. Push a tag to build and publish the `.exe` automatically with GitHub Actions:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
4. To add a built-in game: upload its cover, add a line in `BUILTIN_GAMES`, then publish a new version. `prepare_covers.py` can prepare many covers at once.

## Cover art

Game covers belong to their publishers. This repository does not distribute them: the `assets/covers/` folder is ignored by Git.

## Limitations

- The small "Playing on PlayStation" header is a native Discord feature and isn't available to custom Rich Presence. Switch Presence shows the console name under the game name instead.
- The Discord desktop app must be open.

## License

MIT. See [LICENSE](LICENSE).
