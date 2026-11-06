@echo off
echo === Switch Presence : creation du .exe ===
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error
python -m PyInstaller --onefile --noconsole --clean --name SwitchPresence ^
  --icon assets\icon.ico ^
  --add-data "assets\icon.ico;assets" ^
  --add-data "assets\icon.png;assets" ^
  switch_presence.py
if errorlevel 1 goto :error
echo.
echo Termine ! Ton executable est dans le dossier "dist".
pause
exit /b 0

:error
echo.
echo Une erreur est survenue. Copie le message ci-dessus pour demander de l'aide.
pause
exit /b 1
