@echo off
chcp 65001 >/dev/null
title ひすい野ヴィラ 遺影ツール セットアップ
echo.
echo  ひすい野ヴィラ 遺影写真作成ツール
echo  =================================
echo  初回セットアップを開始します
echo.

cd /d "%~dp0"

:: Python の確認
python --version >/dev/null 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Python が見つかりません。
    echo Python 3.10 以上をインストールしてください。
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  Python が見つかりました。仮想環境を作成します...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [エラー] 仮想環境の作成に失敗しました。
    pause
    exit /b 1
)

echo  パッケージをインストールします（数分かかります）...
call .venv\Scriptsctivate.bat
pip install --upgrade pip -q
pip install -r requirements.txt

echo.
echo  =================================
echo  セットアップが完了しました！
echo.
echo  次の手順：
echo  1. config.json を開き Gemini API キーを設定
echo  2.「起動.bat」をダブルクリックして起動
echo  =================================
echo.
pause
