Set sh = CreateObject("WScript.Shell")
backend = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = """C:\Program Files\FreeCAD 1.1\bin\python.exe"" -m uvicorn main:app --host 127.0.0.1 --port 8787"
sh.Run "cmd /c cd /d """ & backend & """ && " & cmd, 0, False