# fix-proxy.ps1
# Clear leftover Windows system proxy (e.g. Clash 127.0.0.1:7877) when VPN client is closed.
# Usage: Right-click -> Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File fix-proxy.ps1

$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# Warn if the VPN proxy core is still running (it will just re-enable the proxy)
$clash = Get-Process | Where-Object { $_.ProcessName -like "*Clash*" }
if ($clash) {
    Write-Host "WARNING: VPN proxy client is still running:" -ForegroundColor Yellow
    $clash | ForEach-Object { Write-Host ("  - " + $_.ProcessName + " (PID " + $_.Id + ")") }
    Write-Host "Exit the VPN client first, otherwise it will re-enable the system proxy." -ForegroundColor Yellow
    $confirm = Read-Host "Continue to force-disable system proxy anyway? (y/n)"
    if ($confirm -ne 'y') { exit }
}

# Disable system proxy and remove leftover proxy server address
Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 0
Remove-ItemProperty -Path $regPath -Name ProxyServer -ErrorAction SilentlyContinue

$state = Get-ItemProperty -Path $regPath
Write-Host ""
Write-Host ("ProxyEnable = " + $state.ProxyEnable + "  (0 = disabled, OK)") -ForegroundColor Green
Write-Host "System proxy cleared. Restart your browser/apps to apply direct connection." -ForegroundColor Green
Write-Host "If you use Clash, remember to turn OFF 'System Proxy' switch in its UI before exiting."
Read-Host "Press Enter to exit"
