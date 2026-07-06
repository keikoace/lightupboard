@echo off
REM Run this once (as Administrator) to register the daily exchange-rate fetch
REM in Windows Task Scheduler. After that it runs automatically every day at 17:00.

set TASK_NAME=LightupFetchExchangeRates
set SCRIPT_PATH=%~dp0fetch_exchange_rates.bat

REM Create logs directory if it doesn't exist
if not exist "%~dp0logs" mkdir "%~dp0logs"

REM Delete any previous version of the task
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Register: run daily at 17:00, even if the machine was off at that time (run on resume)
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%SCRIPT_PATH%\"" ^
  /sc daily ^
  /st 17:00 ^
  /f

if %errorlevel% == 0 (
    echo.
    echo SUCCESS: Task "%TASK_NAME%" registered.
    echo It will run daily at 17:00 and log to: %~dp0logs\exchange_rates.log
) else (
    echo.
    echo FAILED to register task. Make sure you ran this as Administrator.
)

pause
