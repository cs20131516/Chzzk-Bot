@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 치지직 봇 - 배포 패키지 빌드

set VERSION=1.0
set SRC_DIR=%~dp0
set RELEASE_DIR=%~dp0..\ChzzkBot-Release
set APP_DIR=%RELEASE_DIR%\app
set ZIP_NAME=ChzzkBot-v%VERSION%.zip
set ZIP_PATH=%~dp0..\%ZIP_NAME%

echo ============================================================
echo   치지직 봇 - 배포 패키지 빌드
echo   버전: %VERSION%
echo ============================================================
echo.

:: ──────────────────────────────────────────────
:: 1. Release 폴더 확인
:: ──────────────────────────────────────────────
if not exist "%RELEASE_DIR%\install.bat" (
    echo [오류] ChzzkBot-Release 폴더를 찾을 수 없습니다.
    echo        %RELEASE_DIR%
    pause & exit /b 1
)

:: ──────────────────────────────────────────────
:: 2. app/ 폴더 초기화
:: ──────────────────────────────────────────────
echo [1/4] app/ 폴더 준비 중...
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
mkdir "%APP_DIR%"
mkdir "%APP_DIR%\memory"
mkdir "%APP_DIR%\data"

:: ──────────────────────────────────────────────
:: 3. 소스 파일 복사
:: ──────────────────────────────────────────────
echo [2/4] 소스 파일 복사 중...

:: Python 소스 파일
for %%F in (
    main.py
    config.py
    chat_sender.py
    chat_reader.py
    llm_handler.py
    audio_capture.py
    speech_recognition.py
    requirements.txt
    .env.example
    LICENSE
) do (
    if exist "%SRC_DIR%%%F" (
        copy /y "%SRC_DIR%%%F" "%APP_DIR%\%%F" >nul
        echo   복사: %%F
    ) else (
        echo   [경고] 파일 없음: %%F
    )
)

:: memory 패키지
copy /y "%SRC_DIR%memory\__init__.py" "%APP_DIR%\memory\" >nul
copy /y "%SRC_DIR%memory\memory_manager.py" "%APP_DIR%\memory\" >nul
copy /y "%SRC_DIR%memory\memory_store.py" "%APP_DIR%\memory\" >nul
echo   복사: memory\*.py

:: data 기본 JSON 파일
for %%F in (chat_memory.json my_chat_memory.json streamer_memory.json) do (
    if exist "%SRC_DIR%data\%%F" (
        copy /y "%SRC_DIR%data\%%F" "%APP_DIR%\data\%%F" >nul
    )
)
echo   복사: data\*.json

echo.
echo [3/4] 파일 목록 확인:
echo -------------------------------------------
dir /b /s "%APP_DIR%" 2>nul | find /v "__pycache__"
echo -------------------------------------------
echo.

:: ──────────────────────────────────────────────
:: 4. ZIP 패키징
:: ──────────────────────────────────────────────
echo [4/4] ZIP 패키징 중...

:: 기존 zip 삭제
if exist "%ZIP_PATH%" del /f "%ZIP_PATH%"

:: PowerShell로 압축 (python/ 폴더 제외)
powershell -NoProfile -Command ^
    "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

if exist "%ZIP_PATH%" (
    echo.
    echo ============================================================
    echo   빌드 완료!
    echo   출력: %ZIP_PATH%
    for %%A in ("%ZIP_PATH%") do echo   크기: %%~zA bytes
    echo ============================================================
) else (
    echo [오류] ZIP 생성 실패
    pause & exit /b 1
)

echo.
pause
