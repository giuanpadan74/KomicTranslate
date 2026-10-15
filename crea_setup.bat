@echo off
REM ============================================================
REM  KomicTranslate - Crea il distribuibile in un colpo solo
REM
REM  Uso:  crea_setup.bat [percorso_backup.zip]
REM  Senza argomenti: crea il backup (Backups\KomicTranslate_DATA_ORA.zip)
REM  e poi compila dist\KomicTranslate_DATA_ORA.exe con dentro il backup.
REM  Con un .zip esistente: salta il backup e compila solo l'exe.
REM
REM  Sul nuovo PC basta il singolo exe: guida, Python 3.12 automatico
REM  se manca, .venv, dipendenze e verifica finale.
REM  Prima build richiede internet (installa PyInstaller una volta sola).
REM ============================================================
setlocal
cd /d "%~dp0"

if "%~1"=="--help" goto :help
if "%~1"=="/?" goto :help

set "SRC=%~1"
if defined SRC (
    if not exist "%SRC%" (
        echo ERRORE: file non trovato: "%SRC%"
        pause
        exit /b 1
    )
    echo Uso zip esistente, salto il backup: "%SRC%"
    goto :exe_phase
)

REM ---------- Python di build + PyInstaller (servono a entrambe le fasi) ----------
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if "%PYEXE%"=="" (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 set "PYEXE=python"
)
if "%PYEXE%"=="" (
    echo ERRORE: nessun Python trovato (.venv o PATH^).
    pause
    exit /b 1
)

%PYEXE% -m PyInstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installo PyInstaller ^(serve internet, solo macchina di build^)...
    %PYEXE% -m pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo ERRORE: impossibile installare PyInstaller.
        pause
        exit /b 1
    )
)

set "LOGOARG="
if exist "installer\logo.png" set "LOGOARG=--add-data installer\logo.png;."
set "VERARG="
if exist "version_info.txt" set "VERARG=--version-file version_info.txt"

REM ---------- launcher avvia.exe (splash con logo) ----------
echo Preparo avvia.exe...
if not exist "assets\icons\launcher.ico" (
    %PYEXE% -c "from PIL import Image; im=Image.open('LogoSetup.jpg').convert('RGB'); im.save('assets/icons/launcher.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" >nul 2>&1
)
set "ICONARG="
if exist "assets\icons\launcher.ico" set "ICONARG=--icon assets\icons\launcher.ico"
%PYEXE% -m PyInstaller --noconfirm --clean --onefile --noconsole --name avvia %VERARG% %ICONARG% %LOGOARG% installer\launcher.py
if %ERRORLEVEL% NEQ 0 (
    echo ERRORE nella compilazione di avvia.exe.
    pause
    exit /b 1
)
copy /y "dist\avvia.exe" "avvia.exe" >nul
del "dist\avvia.exe" 2>nul
if exist "avvia.spec" del "avvia.spec"
echo avvia.exe pronto.

REM ================= FASE 1: backup =================
echo.
echo  ===== FASE 1/2: backup =====
echo.
set "BACKUPDIR=%~dp0Backups"
if not exist "%BACKUPDIR%" (
    mkdir "%BACKUPDIR%"
    echo Cartella Backups creata.
)

for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "TS=%%T"
set "ZIP=%BACKUPDIR%\KomicTranslate_%TS%.zip"
set "STAGE=%BACKUPDIR%\Temp_%TS%"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"

echo Raccolta file in corso...
echo Esclusioni: venv .venv __pycache__ logs
echo.

for %%D in (app assets baloons config docs fonts installer modules tests wave rs_core wheels) do (
    if exist "%%D" call :rcopy "%%D"
)

for %%P in (*.py *.bat *.ps1 *.txt *.md *.json *.ttf *.otf *.woff *.woff2 LICENSE) do (
    if exist "%%P" copy /y "%%P" "%STAGE%\" >nul
)
REM launcher + logo distribuiti (pattern sopra non coprono .exe/.jpg)
if exist "avvia.exe" copy /y "avvia.exe" "%STAGE%\" >nul
if exist "LogoSetup.jpg" copy /y "LogoSetup.jpg" "%STAGE%\" >nul

if not exist "%STAGE%\requirements.txt" (
    echo ERRORE: requirements.txt assente dallo staging, backup annullato.
    rmdir /s /q "%STAGE%"
    pause
    exit /b 1
)
if not exist "%STAGE%\app\models" (
    echo AVVISO: nel backup manca la cartella app\models
) else if not exist "%STAGE%\app\models\region_edit_session.py" (
    echo AVVISO: nel backup manca app\models\region_edit_session.py
) else if not exist "%STAGE%\app\models\__init__.py" (
    echo AVVISO: nel backup manca app\models\__init__.py
)

echo.
echo Compressione in: "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIP%' -Force"
if %ERRORLEVEL% NEQ 0 (
    echo ERRORE nella compressione.
    rmdir /s /q "%STAGE%"
    pause
    exit /b 1
)
rmdir /s /q "%STAGE%"

if not exist "%ZIP%" (
    echo ERRORE: zip non creato.
    pause
    exit /b 1
)
for %%S in ("%ZIP%") do echo Backup completato: %%~nxS ^(%%~zS byte^)
REM potatura: tieni gli ultimi 5 backup, elimina i piu' vecchi
set "KEPT=0"
for /f "delims=" %%Z in ('dir /b /o-d /a-d "%BACKUPDIR%\KomicTranslate_*.zip" 2^>nul') do (
    set /a KEPT+=1 >nul
    call :prune_one "%%Z"
)
set "SRC=%ZIP%"

REM ================= FASE 2: exe =================
:exe_phase
echo.
echo  ===== FASE 2/2: eseguibile =====
echo.
echo Backup: "%SRC%"
REM nome exe = nome backup (cosi' la versione si distingue)
for %%B in ("%SRC%") do set "BNAME=%%~nB"
set "EXE=dist\%BNAME%.exe"
echo Exe: "%EXE%"
REM (Python di build gia' rilevato a inizio script)

if not exist "build_exe" mkdir "build_exe"
echo Copio il backup come payload...
copy /y "%SRC%" "build_exe\payload.zip" >nul
if %ERRORLEVEL% NEQ 0 (
    echo ERRORE nella copia del payload.
    pause
    exit /b 1
)

echo.
echo Compilo l'exe (pochi minuti)...
%PYEXE% -m PyInstaller --noconfirm --clean --onefile --name "%BNAME%" %VERARG% --add-data "build_exe\payload.zip;." %LOGOARG% installer\installer_exe.py
if %ERRORLEVEL% NEQ 0 (
    echo ERRORE nella compilazione.
    pause
    exit /b 1
)

if not exist "%EXE%" (
    echo ERRORE: exe non generato.
    pause
    exit /b 1
)

echo.
echo Self-test dell'exe (verifica payload incluso)...
"%EXE%" --self-test
if %ERRORLEVEL% NEQ 0 (
    echo ERRORE: self-test fallito, l'exe non e' affidabile.
    pause
    exit /b 1
)

echo.
echo  ================================================
echo   EXE PRONTO: "%~dp0%EXE%"
for %%S in ("%EXE%") do echo   Dimensione: %%~zS byte
echo   Distribuisci questo singolo file sul nuovo PC:
echo   doppio click e segui la guida (se manca Python 3.12
echo   lo scarica e installa da solo^).
echo  ================================================
REM pulizia artefatti temporanei di build (exe e backup restano)
if exist "build" rmdir /s /q "build"
if exist "build_exe\payload.zip" del "build_exe\payload.zip"
if exist "%BNAME%.spec" del "%BNAME%.spec"
pause
exit /b 0

:rcopy
robocopy "%~1" "%STAGE%\%~1" /E /XD venv .venv __pycache__ logs target /NFL /NDL /NJH /NJS /NP
if %ERRORLEVEL% GEQ 8 echo AVVISO: robocopy %~1, codice %ERRORLEVEL%
exit /b 0

:prune_one
if %KEPT% GTR 5 del "%BACKUPDIR%\%~1"
exit /b 0

:help
echo Uso: crea_setup.bat [percorso_backup.zip]
echo   Senza argomenti: backup + exe in sequenza.
echo   Con uno .zip: salta il backup, compila solo l'exe.
exit /b 0
