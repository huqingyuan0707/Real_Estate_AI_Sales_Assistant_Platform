# proxy-guard.ps1 - 系统代理守护脚本
# 作用：当系统代理指向的本地端口已无人监听（VPN 已退出但代理设置残留）时，
#       自动清除系统代理，恢复直连，让浏览器立即可用。
# 原则：VPN 正常运行时绝不改动任何设置；只处理"死代理"残留。
# 日志：同目录 proxy-guard.log

$ErrorActionPreference = 'SilentlyContinue'
$logFile = Join-Path $PSScriptRoot 'proxy-guard.log'

function Log($msg) {
    ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) | Add-Content -Path $logFile -Encoding UTF8
}

$reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

# 1. 系统代理未启用 -> 无需处理
if ($reg.ProxyEnable -ne 1) { exit 0 }

# 2. 代理地址不是本地回环 -> 不干预（可能是用户手动配的网关代理）
if ($reg.ProxyServer -notmatch '^127\.0\.0\.1:(\d+)$') { exit 0 }
$port = [int]$Matches[1]

# 3. 端口有人监听 -> VPN 正常，保留代理设置
$listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listen) { exit 0 }

# 4. 端口已死 -> 清除系统代理并通知系统立即刷新
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Value 0

$sig = '[DllImport("wininet.dll", SetLastError=true)] public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);'
$type = Add-Type -MemberDefinition $sig -Name WinInet -Namespace ProxyGuard -PassThru
$type::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null  # 39 = INTERNET_OPTION_SETTINGS_CHANGED
$type::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null  # 37 = INTERNET_OPTION_REFRESH

Log ("dead proxy 127.0.0.1:$port cleared, direct connection restored")
