@echo off
chcp 65001 >nul
title AIsChat 安装程序

echo.
echo  ╔══════════════════════════════════════╗
echo  ║       AIsChat 启动器 安装程序        ║
echo  ╚══════════════════════════════════════╝
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  [提示] 需要管理员权限来创建快捷方式
    echo  正在请求提权...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 安装目录
set "INSTALL_DIR=%LOCALAPPDATA%\AIsChat"
set "EXE_NAME=AIsChat.exe"

echo  安装目录: %INSTALL_DIR%
echo.

:: 创建安装目录
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo  [√] 创建安装目录
)

:: 复制文件
echo  [√] 正在复制文件...
xcopy /E /I /Y "%~dp0dist\AIsChat\*" "%INSTALL_DIR%\" >nul 2>&1

:: 创建开始菜单快捷方式
set "SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if not exist "%SHORTCUT_DIR%\AIsChat" mkdir "%SHORTCUT_DIR%\AIsChat"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_DIR%\AIsChat\AIsChat 启动器.lnk'); $sc.TargetPath = '%INSTALL_DIR%\%EXE_NAME%'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'AIsChat 桌面启动器'; $sc.Save()"
echo  [√] 创建开始菜单快捷方式

:: 创建桌面快捷方式
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\AIsChat 启动器.lnk'); $sc.TargetPath = '%INSTALL_DIR%\%EXE_NAME%'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'AIsChat 桌面启动器'; $sc.Save()"
echo  [√] 创建桌面快捷方式

echo.
echo  ══════════════════════════════════════
echo   安装完成！
echo   启动器位置: %INSTALL_DIR%\%EXE_NAME%
echo   可在开始菜单或桌面找到快捷方式
echo  ══════════════════════════════════════
echo.

pause
