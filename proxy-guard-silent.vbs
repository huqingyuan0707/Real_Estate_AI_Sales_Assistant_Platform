' proxy-guard-silent.vbs - silent wrapper for proxy-guard.ps1
' Task Scheduler runs this via wscript.exe; Run(..., 0, False) = hidden window,
' no more PowerShell window flash every minute. Guard logic unchanged.
CreateObject("WScript.Shell").Run _
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""D:\Real_Estate_AI_Assistant_Platform\proxy-guard.ps1""", _
    0, False
