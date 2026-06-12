@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [エラー] 仮想環境が見つかりません。先に「セットアップ.bat」を実行してください。
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
echo ひすい野ヴィラ 遺影写真作成ツール を起動しています...
python app.py
