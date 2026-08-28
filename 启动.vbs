' BunkrDownloader 静默启动器（无控制台窗口）
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("Wscript.Shell")

' 获取脚本所在目录作为项目根目录
rootDir = fso.GetParentFolderName(Wscript.ScriptFullName)
' 工作目录设为 gui 子目录
ws.CurrentDirectory = rootDir & "\gui"
' 直接启动 electron，不经过 cmd
ws.Run "node_modules\electron\dist\electron.exe .", 0, False
