@echo off
chcp 65001 >/dev/null
title ひすい野ヴィラ 遺影写真作成ツール

cd /d "%~dp0"

:: 仮想環境の確認
if not exist ".venv\Scripts\activate.bat" (
    echo [エラー] セットアップが完了していません。
    echo 「セットアップ.bat」を先に実行してください。
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

:: ブラウザを起動（Flask の起動を少し待つ）
start "" /b cmd /c "timeout /t 2 /nobreak >/dev/null && start http://localhost:5001"

echo  起動中...ブラウザが開くまでお待ちください。
echo  終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。
echo.
python app.py
