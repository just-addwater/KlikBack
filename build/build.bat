@echo off
rem KlikBack release build: sync gate (research checkout only) -> PyInstaller
rem -> exe-adjacent files -> zip. Run from anywhere; paths may contain spaces.
setlocal enabledelayedexpansion

set "BUILD=%~dp0"
set "PUBLIC=%BUILD%.."
set "REPO=%BUILD%..\.."

rem On the research checkout, regenerate the public engine and prove it.
rem A public checkout has no tools\ and skips straight to freezing.
if exist "%REPO%\tools\klikback_weave.py" (
    echo === weave ===
    py -3 "%REPO%\tools\klikback_weave.py" || exit /b 1
    echo === sync gate ===
    py -3 "%REPO%\tools\klikback_sync_validation.py" || exit /b 1
)

rem The version is hand-kept in three files and read by two consumers -- the
rem zip name comes from __version__, the exe's Windows version resource from
rem version_info.txt -- so a partial bump ships rather than failing. Checked
rem before freezing, so a mismatch costs a second.
echo === version guard ===
py -3 "%BUILD%check_version.py" || exit /b 1

for /f %%v in ('py -3 -c "import sys; sys.path.insert(0, r'%PUBLIC%\src'); import klikback; print(klikback.__version__)"') do set "VERSION=%%v"
if not defined VERSION exit /b 1

echo === PyInstaller ===
py -3 -m PyInstaller --noconfirm --clean "%BUILD%klikback.spec" --distpath "%BUILD%dist" --workpath "%BUILD%work" || exit /b 1

set "OUT=%BUILD%dist\KlikBack"

echo === exe-adjacent files ===
copy /y "%BUILD%README.txt" "%OUT%\README.txt" >nul || exit /b 1
rem The GPL travels with the binaries, not just with the source.
copy /y "%PUBLIC%\LICENSE" "%OUT%\LICENSE" >nul || exit /b 1

rem So do everyone else's licences. This reads the build environment rather
rem than a hand-kept list, and fails if a component's text has gone missing.
echo === third-party notices ===
py -3 "%BUILD%third_party_notices.py" "%OUT%" --version %VERSION% || exit /b 1
if not exist "%OUT%\artwork" mkdir "%OUT%\artwork"
xcopy /y /q "%PUBLIC%\src\klikback\core\artwork\*" "%OUT%\artwork\" >nul || exit /b 1

echo === zip ===
rem Python, not Compress-Archive: py is already required, and PowerShell's
rem Archive module is broken on some machines.
py -3 -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', root_dir=sys.argv[2], base_dir='KlikBack')" "%BUILD%dist\KlikBack-%VERSION%" "%BUILD%dist" || exit /b 1

echo Done: %BUILD%dist\KlikBack-%VERSION%.zip
endlocal
