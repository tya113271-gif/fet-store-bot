Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\azeal\.gemini\antigravity\scratch\FET_BOT_DASHBOARD"
WshShell.Run chr(34) & "C:\Users\azeal\AppData\Local\Programs\Python\Python312\python.exe" & chr(34) & " app.py", 0
Set WshShell = Nothing
