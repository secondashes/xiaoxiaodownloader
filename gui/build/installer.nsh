; 小小下载器 NSIS 安装脚本定制（electron-builder include）
; 1) 默认安装到 D:\小小下载器（本机无历史安装记录时；有记录则沿用上次安装目录）
; 2) 覆盖安装（升级）和控制面板卸载都只删除程序自身文件，
;    保留 data/（登录信息、缓存、设置、下载记录）和用户放在安装目录的其他文件

!macro preInit
  ; 无历史安装记录时，把默认安装位置改为 D:\小小下载器
  ; （electron-builder 会读取此注册表值作为默认 $INSTDIR；
  ;   已有记录说明装过，跳过写入 → 沿用上次安装目录）
  ; D 盘不存在时不写（回落到系统默认 Program Files）
  SetRegView 64
  ReadRegStr $0 HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation
  ${If} $0 == ""
  ${AndIf} ${FileExists} "D:\*.*"
    WriteRegExpandStr HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\小小下载器"
  ${EndIf}
  SetRegView 32
  ReadRegStr $0 HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation
  ${If} $0 == ""
  ${AndIf} ${FileExists} "D:\*.*"
    WriteRegExpandStr HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\小小下载器"
  ${EndIf}
!macroend

!macro customRemoveFiles
  ; 覆盖安装（升级时 electron-builder 会先运行旧卸载器）和卸载共用此宏：
  ; 只删除程序自身文件，绝不动 data/ 用户数据
  Delete "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$INSTDIR\xxd.app"
  Delete "$INSTDIR\gui_bridge.py"
  RMDir /r "$INSTDIR\resources"
  ; 历史补丁可能把旧版后端释放到安装根目录（优先级高于 resources/ 内置后端），
  ; 升级时必须清掉，否则会一直用旧后端
  RMDir /r "$INSTDIR\bunkr_bridge"
  ; 仅当目录为空时移除（data/ 存在时整个安装目录连同用户数据一起保留）
  RMDir "$INSTDIR"
!macroend
