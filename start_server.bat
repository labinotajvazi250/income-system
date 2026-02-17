@echo off
cd /d C:\income_system

REM Nise serverin ne background (kjo dritare do fshihet nga VBS)
start "" /b py app.py

REM prit pak sa te ndizet serveri
timeout /t 2 /nobreak >nul

REM hape dashboard automatikisht (LD ose DL)
start "" http://127.0.0.1:5000/dashboard?b=LD

exit
