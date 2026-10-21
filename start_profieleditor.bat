@echo off
rem ============================================================================
rem  Start de Profieleditor: lokale server + browsertabblad.
rem  De paden (prfl_map, koppeltabel, uitvoer_map) staan in profieleditor.ini; bij de eerste
rem  start maakt de editor dat bestand uit profieleditor.voorbeeld.ini.
rem  Sluit dit venster (of Ctrl+C) om de editor te stoppen.
rem ============================================================================
setlocal
cd /d "%~dp0"
title Profieleditor

rem Optioneel: vast pad naar python.exe, bijvoorbeeld
rem set "PYTHON=C:\ProgramData\miniforge3\python.exe"
set "PYTHON="

rem Een ander .ini-bestand kan als eerste argument worden meegegeven. Zonder argument kiest
rem app.py zelf profieleditor.ini (en maakt die bij de eerste start uit het voorbeeld).
set "INI=%~1"
set "INI_ARG="
if not "%INI%"=="" set INI_ARG=--ini "%INI%"
if not "%INI%"=="" if not exist "%INI%" (
    rem tussen aanhalingstekens: een ) in het pad, zoals in "(x86)", zou dit blok anders afsluiten
    echo Instellingenbestand niet gevonden: "%INI%"
    goto :fout
)

if defined PYTHON goto :start

rem Zoek een werkende Python 3 (de Microsoft Store-snelkoppeling "python" telt niet)
py -3 -c "import sys" >nul 2>&1 && (set "PYTHON=py -3" & goto :start)
python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && (set "PYTHON=python" & goto :start)
for %%P in (
    "C:\ProgramData\miniforge3\python.exe"
    "%USERPROFILE%\miniforge3\python.exe"
    "C:\ProgramData\anaconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do if exist %%P (set "PYTHON=%%~P" & goto :start)

echo Geen Python 3 gevonden. Zet het pad naar python.exe bovenaan in %~nx0 (set "PYTHON=...").
goto :fout

:start
echo Python: %PYTHON%
if "%INI%"=="" echo Instellingen: profieleditor.ini naast app.py
if not "%INI%"=="" echo Instellingen: %INI%
echo.
if "%PYTHON:~0,3%"=="py " (
    %PYTHON% "%~dp0app.py" %INI_ARG%
) else (
    "%PYTHON%" "%~dp0app.py" %INI_ARG%
)
if errorlevel 1 goto :fout
exit /b 0

:fout
echo.
echo De Profieleditor kon niet worden gestart.
pause
exit /b 1
