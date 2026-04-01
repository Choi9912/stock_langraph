@echo off
cd /d C:\Users\defy2\stock
C:\Users\defy2\AppData\Local\Programs\Python\Python312\python.exe daily_tracker.py --market us >> logs\us_%date:~0,4%-%date:~5,2%-%date:~8,2%.log 2>&1
