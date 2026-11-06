@echo off
setlocal enableextensions enabledelayedexpansion

REM ============================================================
REM  ComfyUI-Mie 短剧工作台 启动脚本（与 ComfyUI 解耦）
REM  - 先清理占用 8199 端口的旧进程
REM  - 首次运行自动 pip install -r requirements.txt
REM  - 启动 Flask WebUI (8199) 并打开浏览器
REM  - ComfyUI 由启动器另行起停（见 F:\Mie-Skills\AGENTS.md），本脚本不管它
REM  - 资产库与 LLM 密钥都在 ComfyUI 插件目录里，用 MIE_PLUGIN_ROOT 指过去
REM ============================================================

cd /d "%~dp0"

set "WEBUI_PORT=8199"
REM 用 127.0.0.1 打开浏览器。localhost 会先解析到 IPv6 ::1，但 Flask 只监听
REM IPv4 (0.0.0.0)，浏览器要等 ~2 秒超时再回退 127.0.0.1。
set "DISPLAY_HOST=127.0.0.1"

REM 资产库与 mie_llm_keys.json 都在 ComfyUI 插件目录里。
if "%MIE_PLUGIN_ROOT%"=="" (
    set "MIE_PLUGIN_ROOT=C:\PP\V9\V9-Large\ComfyUI_Mie_2026_V9.0_Large\ComfyUI\custom_nodes\comfyui_mienodes"
)

echo ============================================================
echo   ComfyUI-Mie 短剧工作台
echo ============================================================
echo.

REM --- 0. 清理占用 WEBUI_PORT 的旧进程（避免端口冲突）---
echo [清理] 检查端口 %WEBUI_PORT% 是否被占用...
set "KILLED=0"
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr ":%WEBUI_PORT% " ^| findstr "LISTENING"') do (
    echo       发现占用进程 PID=%%P，正在结束...
    taskkill /F /PID %%P >nul 2>&1
    set "KILLED=1"
)
if "!KILLED!"=="0" (
    echo       端口 %WEBUI_PORT% 空闲。
) else (
    echo       已清理旧进程，等待 1 秒释放端口...
    ping -n 2 127.0.0.1 >nul
)
echo.

REM --- 1. 定位 Python: 优先 .venv, 不存在就创建 ---
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    set "PYCMD=%VENV_PY%"
    echo [1/4] 使用项目 .venv: %VENV_PY%
) else (
    echo [1/4] 未找到 .venv, 正在创建...
    where py >nul 2>&1 && set "SYSPY=py" || set "SYSPY=python"
    %SYSPY% --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 找不到 Python。请先安装 Python 3.10+ 并加入 PATH。
        pause
        exit /b 1
    )
    %SYSPY% -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo [错误] 创建 .venv 失败。
        pause
        exit /b 1
    )
    set "PYCMD=%VENV_PY%"
    echo       .venv 创建完成.
)

REM --- 2. 检查依赖 (装到 .venv, 首次自动) ---
echo [2/4] 检查依赖...
"%PYCMD%" -c "import flask, mie_llm, mie_craft" >nul 2>&1
if errorlevel 1 (
    echo       缺少依赖，正在安装 requirements.txt 到 .venv ...
    "%PYCMD%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败。请手动运行: "%PYCMD%" -m pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo       依赖安装完成。
) else (
    echo       依赖已就绪。
)

REM --- 3. 预检：资产库与密钥文件在不在 ---
echo.
echo [3/4] 预检...
"%PYCMD%" -c "import sys; sys.path.insert(0,'.'); from app import config; from app.services import library; print('       插件根  :', config.PLUGIN_ROOT); print('       资产库  :', library.library_dir()); print('       密钥文件:', config.LLM_KEYS_FILE)" 2>nul

REM --- 4. 启动 Flask WebUI ---
echo.
echo [4/4] 启动 Flask WebUI...
echo       地址: http://%DISPLAY_HOST%:%WEBUI_PORT%
echo       局域网浏览器可用 http://<本机IP>:%WEBUI_PORT%
echo       按 Ctrl+C 停止。
echo ============================================================
echo.

REM 启动后延迟打开浏览器
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://%DISPLAY_HOST%:%WEBUI_PORT%"

REM 单进程，不开 --reload：第二个进程会跟渲染队列抢活。
set "FLASK_PORT=%WEBUI_PORT%"
set "FLASK_HOST=0.0.0.0"
set "MIE_WEB_PORT=%WEBUI_PORT%"
set "MIE_WEB_HOST=0.0.0.0"
"%PYCMD%" -m app.flask_app
if errorlevel 1 (
    echo.
    echo [错误] WebUI 退出码 %errorlevel%。
    pause
)
endlocal
