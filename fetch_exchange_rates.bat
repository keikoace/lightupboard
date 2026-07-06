@echo off
REM Fetch ECB exchange rates for Lightup.
REM Registered in Windows Task Scheduler to run daily at 17:00 CET.

cd /d "%~dp0"
python manage.py fetch_exchange_rates >> logs\exchange_rates.log 2>&1
