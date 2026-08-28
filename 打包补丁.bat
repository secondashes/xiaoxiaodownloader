@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  打包 补丁.exe（PyInstaller onefile 内嵌 update/）
echo ============================================
echo.
echo 工作原理：
echo   1. 把当前 update/ 文件夹整体打包进单文件 补丁.exe
echo   2. 用户把 补丁.exe 放到本体目录（与 小小下载器/ 同级）双击
echo   3. 程序遍历内嵌的 update/ 文件，逐个复制到本体目录同名相对路径
echo   4. 复制完成后延迟 3 秒自删（补丁.exe 自身被锁，需 spawn 外部 cmd 延时删除）
echo.
echo 前置条件：已安装 Python + PyInstaller
echo   pip install pyinstaller
echo.
echo 改 update/ 内容后重新打包：双击本脚本即可
echo.

python -m PyInstaller patch_runtime.spec --noconfirm --clean
if errorlevel 1 (
  echo.
  echo [失败] 打包出错，请检查上方日志
  pause
  exit /b 1
)

echo.
echo 正在复制到根目录 补丁.exe ...
if exist "dist\patch_runtime\补丁.exe" (
  copy /y "dist\patch_runtime\补丁.exe" "补丁.exe" >nul
) else if exist "dist\patch_runtime\patch_runtime.exe" (
  copy /y "dist\patch_runtime\patch_runtime.exe" "补丁.exe" >nul
) else (
  echo [警告] 未找到打包产物，请检查 dist\patch_runtime\ 目录
  dir dist\patch_runtime\ 2>nul
  pause
  exit /b 1
)

echo.
echo [完成] 已生成 补丁.exe
echo.
echo 使用方法：
echo   1. 把 补丁.exe 复制到用户机器的 小小下载器.exe 所在目录
echo   2. 关闭正在运行的 小小下载器.exe
echo   3. 双击 补丁.exe，按提示操作
echo   4. 更新完成后补丁程序自动关闭并自删
echo   5. 重新启动 小小下载器.exe 即可使用新功能
echo.
pause
