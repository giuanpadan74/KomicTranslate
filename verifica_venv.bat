@echo off
REM ============================================================
REM  KomicTranslate - Verifica installazione in .venv (funzione 2)
REM
REM  Uso:  verifica_venv.bat [cartella_installazione]
REM  Controlla: .venv presente, Python ^>= 3.11, import base
REM  (PySide6/PIL/numpy/cv2), torch, compilazione comic.py,
REM  coerenza dipendenze (pip check). Riepilogo PASS/FAIL.
REM  L'exe di setup esegue gli stessi controlli a fine installazione.
REM
REM  Nota tecnica: niente output catturato con for /f (le virgolette
REM  annidate rompono il parsing di cmd); solo ERRORLEVEL + output diretto.
REM ============================================================
setlocal
cd /d "%~dp0"

if "%~1"=="--help" goto :help
if "%~1"=="/?" goto :help

set "DEST=%~1"
if "%DEST%"=="" set /p "DEST=Cartella installazione da verificare: "
set "DEST=%DEST:"=%"
if "%DEST%"=="" (
    echo ERRORE: indica la cartella. Uso: verifica_venv.bat CARTELLA
    pause
    exit /b 1
)
if not exist "%DEST%\.venv\Scripts\python.exe" (
    echo [FAIL] .venv assente in "%DEST%"
    pause
    exit /b 1
)
set "VPY=%DEST%\.venv\Scripts\python.exe"
set /a PASS=0 >nul
set /a FAIL=0 >nul

echo.
echo  Verifica di: "%DEST%"
echo.

REM --- versione Python: mostra + gate >= 3.11 ---
"%VPY%" --version
"%VPY%" -c "import sys;a,b=sys.version_info[:2];exit(0 if (a*100+b)>=311 else 1)" >nul 2>nul
if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] versione ^>= 3.11 ) else ( set /a FAIL+=1 >nul & echo  [FAIL] versione ^>= 3.11 )

REM --- import base ---
"%VPY%" -c "import PySide6,PIL,numpy,cv2" >nul 2>&1
if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] import PySide6/PIL/numpy/cv2 ) else ( set /a FAIL+=1 >nul & echo  [FAIL] import PySide6/PIL/numpy/cv2 )

REM --- torch: mostra versione + gate ---
"%VPY%" -c "import torch;print('  torch:',torch.__version__)"
if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] torch importabile ) else ( set /a FAIL+=1 >nul & echo  [FAIL] torch non importabile )

REM --- py7zr: la policy Windows puo' bloccarne la DLL nativa ---
"%VPY%" -c "import py7zr" >nul 2>&1
if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] py7zr importabile ^(supporto .7z^) ) else ( set /a FAIL+=1 >nul & echo  [FAIL] py7zr non importabile ^(DLL bloccata da policy?^) )

REM --- cuda disponibile o solo CPU (solo informativo) ---
"%VPY%" -c "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if %ERRORLEVEL% EQU 0 ( echo  [INFO] torch CUDA disponibile ) else ( echo  [INFO] torch solo CPU )

REM --- comic.py compila ---
if exist "%DEST%\comic.py" (
    "%VPY%" -m py_compile "%DEST%\comic.py" >nul 2>&1
    if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] comic.py compila ) else ( set /a FAIL+=1 >nul & echo  [FAIL] comic.py non compila )
) else (
    set /a FAIL+=1 >nul & echo  [FAIL] comic.py assente in "%DEST%"
)

REM --- coerenza dipendenze ---
"%VPY%" -m pip check >nul 2>&1
if %ERRORLEVEL% EQU 0 ( set /a PASS+=1 >nul & echo  [PASS] pip check ^(dipendenze coerenti^) ) else ( set /a FAIL+=1 >nul & echo  [FAIL] pip check ^(conflitti^) )

echo.
echo  Risultato: %PASS% PASS, %FAIL% FAIL
if %FAIL% EQU 0 (
    echo  INSTALLAZIONE OK - ambiente .venv funzionante.
    pause
    exit /b 0
) else (
    echo  INSTALLAZIONE DA RIPARARE - vedi FAIL qui sopra.
    pause
    exit /b 1
)

:help
echo Uso: verifica_venv.bat [cartella_installazione]
exit /b 0
