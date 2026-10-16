@echo off
if "%1"=="" goto help
if "%1"=="images" goto images
if "%1"=="health" goto health
if "%1"=="test" goto test

:images
python scripts\build_images.py
goto end

:health
python scripts\health_check.py
goto end

:test
python -m pytest backend\tests -v
goto end

:help
echo Usage: make [images ^| health ^| test]
goto end

:end
