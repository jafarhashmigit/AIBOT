@echo off
cd /d C:\Users\Dell\Documents\1\AIBOT
if not exist reports\phase3 mkdir reports\phase3
".venv\Scripts\python.exe" src\phase3\run_phase3.py > reports\phase3\run_stdout.txt 2> reports\phase3\run_stderr.txt
echo EXITCODE=%ERRORLEVEL%> reports\phase3\run_exit.txt
