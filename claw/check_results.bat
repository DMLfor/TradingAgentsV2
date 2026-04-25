@echo off
chcp 65001 >nul
cd /d C:\Users\dblank\code\TradingAgentsV2

echo === TradingAgentsV2 Task Results Check ===
echo.
echo [1/3] Registered tasks status:
python scripts/claw_register.py --list
echo.
echo [2/3] Today's reports:
python scripts/claw_check.py --today
echo.
echo [3/3] Latest individual reports:
echo   -- ETFTracker-515180:
python scripts/claw_check.py --task ETFTracker-515180 --today 2>nul || echo      (no recent report)
echo.
echo   -- ETFTracker-159545:
python scripts/claw_check.py --task ETFTracker-159545 --today 2>nul || echo      (no recent report)
echo.
echo   -- GrowthBoardRank:
python scripts/claw_check.py --task GrowthBoardRank --today 2>nul || echo      (no recent report)
echo.
echo === Check complete. Reports dir: %CD%\reports ===
