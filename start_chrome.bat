@echo off
setlocal
set "HERE=%~dp0"
set "CHROME=%HERE%bin\chrome\chrome.exe"
set "PROFILE=%APPDATA%\SupportBot\chrome-profile"
if not exist "%CHROME%" set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
"%CHROME%" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%PROFILE%" ^
  --no-first-run ^
  --no-default-browser-check ^
  --start-minimized ^
  "https://appslab.helpdeskeddy.com/ru/ticket/list/filter/id/3/page/1"