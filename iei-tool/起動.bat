@echo off
chcp 65001 >/dev/null
title ひすい野ヴィラ 遺影写真作成ツール

pushd "%~dp0"

:: 仮想環境の確認
if not exist ".venv\Scriptsctivate.bat" (
    echo [エラー] セットアップが完了していません。
    echo 「セットアップ.bat」を先に実行してください。
    popd
    pause
    exit /b 1
)

call .venv\Scriptsctivate.bat

echo  起動中...ブラウザが開くまでお待ちください。
echo  終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。
echo.

:: ブラウザを2秒後に開く
start /b cmd /c "timeout /t 2 /nobreak >/dev/null && start http://localhost:5001"

python app.py
popd
