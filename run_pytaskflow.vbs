Option Explicit

Dim shell, fso, repoDir, pythonw

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(repoDir, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(pythonw) Then
    MsgBox "Python virtual environment was not found." & vbCrLf & vbCrLf & _
        "Run setup.bat first, then double-click this file again.", _
        vbExclamation, "pyTaskFlow"
    WScript.Quit 1
End If

shell.CurrentDirectory = repoDir
shell.Run """" & pythonw & """ -m pytaskflow", 0, False
