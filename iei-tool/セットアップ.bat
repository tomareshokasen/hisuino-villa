@echo off
chcp 65001 > nul
echo ==========================================
echo  ひすい野ヴィラ 遺影写真作成ツール
echo  初回セットアップ
echo ==========================================
echo.

cd /d "%~dp0"

:: Python の確認
python --version > nul 2>&1
if errorlevel 1 (
  echo [エラー] Pythonがインストールされていません。
  echo https://www.python.org/downloads/ からインストールしてください。
  pause
  exit /b 1
)

echo Pythonが確認できました。
echo.

:: 仮想環境の作成
if not exist ".venv" (
  echo 仮想環境を作成中...
  python -m venv .venv
)

:: パッケージのインストール
echo パッケージをインストール中（数分かかる場合があります）...
call .venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo.
echo ==========================================
echo  セットアップが完了しました！
echo  「起動.bat」をダブルクリックして起動してください。
echo ==========================================
echo.
pause
