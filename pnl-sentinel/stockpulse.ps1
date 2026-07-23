#!/usr/bin/env pwsh
<#
.SYNOPSIS
    StockPulse service manager - bot (long-poll) + Razorpay webhook (:8000).
    Non-interactive: .\stockpulse.ps1 start|stop|restart|status [bot|webhook|both]
    Every start/restart KILLS strays first, so duplicate bot.py pollers (409
    collisions) and orphan webhooks can never stack up. Ported from nxbagger.ps1.
#>
param(
    [Parameter(Position=0)][string]$Command = "status",
    [Parameter(Position=1)][string]$Target  = "both"
)

$ROOT    = $PSScriptRoot
$LogsDir = Join-Path $ROOT ".logs"
$Py      = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
$WEB_PORT = 8000

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Ensure-Logs { if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory $LogsDir | Out-Null } }

function Get-DescendantPids ($parentPid, $all) {
    # BFS the process tree so a launcher's child python dies with it. O(1) lookups.
    if ($null -eq $all) { $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue }
    if (-not $all) { return @() }
    $byParent = @{}
    foreach ($p in $all) {
        $pp = [int]$p.ParentProcessId
        if (-not $byParent.ContainsKey($pp)) { $byParent[$pp] = New-Object System.Collections.ArrayList }
        [void]$byParent[$pp].Add([int]$p.ProcessId)
    }
    $seen = @{}; $stack = New-Object System.Collections.Stack; $stack.Push([int]$parentPid)
    while ($stack.Count -gt 0) {
        $c = $stack.Pop(); if ($seen.ContainsKey($c)) { continue }; $seen[$c] = $true
        if ($byParent.ContainsKey($c)) { foreach ($k in $byParent[$c]) { if (-not $seen.ContainsKey($k)) { $stack.Push($k) } } }
    }
    $out = New-Object System.Collections.ArrayList
    foreach ($k in $seen.Keys) { if ($k -ne [int]$parentPid) { [void]$out.Add($k) } }
    return $out
}

function Find-Pids ($what, $all) {
    # ponytail: match the app's own command-line signature (bot.py / webhook:app).
    # Unique to StockPulse on this box; if another project ever runs `bot.py`,
    # scope by ExecutablePath -like '*Alert-Money*' here.
    if ($null -eq $all) { $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue }
    if (-not $all) { return @() }
    if ($what -eq "bot") {
        return @($all | Where-Object {
            $_.Name -match '^(python|pythonw)\.exe$' -and $_.CommandLine -match '\bbot\.py\b'
        } | Select-Object -ExpandProperty ProcessId)
    }
    # webhook: match the uvicorn app signature (interpreter-agnostic)
    return @($all | Where-Object {
        $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'webhook:app'
    } | Select-Object -ExpandProperty ProcessId)
}

function Is-Running ($what) { (Find-Pids $what).Count -gt 0 }

function Kill-Target ($what) {
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $all  = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
        $pids = Find-Pids $what $all
        if ($pids.Count -eq 0) { return }
        $expanded = @{}
        foreach ($p in $pids) {
            $expanded[[int]$p] = $true
            foreach ($d in (Get-DescendantPids $p $all)) { $expanded[[int]$d] = $true }
        }
        foreach ($p in $expanded.Keys) {
            try { Stop-Process -Id $p -Force -ErrorAction Stop; Write-Host "  [KILL] $what PID $p" -ForegroundColor Red }
            catch { }
        }
        Start-Sleep -Milliseconds 600
    }
    if (Is-Running $what) { Write-Host "  [FAIL] $what still alive after 5 sweeps - kill manually" -ForegroundColor Red }
}

function Start-Bot {
    Ensure-Logs
    $log = Join-Path $LogsDir "bot.log"
    Start-Process -FilePath $Py -ArgumentList @("bot.py") -WorkingDirectory $ROOT `
        -WindowStyle Minimized -RedirectStandardOutput $log -RedirectStandardError "$log.err" | Out-Null
    Write-Host "  [OK]   bot starting (long-poll) -> $log" -ForegroundColor Green
}

function Start-Webhook {
    Ensure-Logs
    $log = Join-Path $LogsDir "webhook.log"
    Start-Process -FilePath $Py -ArgumentList @("-m","uvicorn","webhook:app","--port","$WEB_PORT") `
        -WorkingDirectory $ROOT -WindowStyle Minimized `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" | Out-Null
    Write-Host "  [OK]   webhook starting on :$WEB_PORT -> $log" -ForegroundColor Green
}

function Do-Start ($what) {
    # ponytail: .venv\Scripts\python.exe on this box is a REDIRECTOR stub that
    # launches C:\Python312\python.exe bot.py as a child worker (parent stub just
    # waits). So one start = stub + worker = ONE poller, not two. Kill-Target
    # matches both (both cmdlines contain bot.py / webhook:app), so stop is clean
    # and kill-before-start prevents stacking across sessions. Don't "dedupe" the
    # worker -- it's the real process.
    if ($what -eq "bot" -or $what -eq "both") { Write-Host "  [....] sweeping stray bot..." -ForegroundColor DarkGray; Kill-Target "bot"; Start-Bot }
    if ($what -eq "webhook" -or $what -eq "both") { Write-Host "  [....] sweeping stray webhook..." -ForegroundColor DarkGray; Kill-Target "webhook"; Start-Webhook }
}

function Do-Stop ($what) {
    if ($what -eq "bot" -or $what -eq "both") { Kill-Target "bot"; if (-not (Is-Running "bot")) { Write-Host "  [OK]   bot stopped" -ForegroundColor Green } }
    if ($what -eq "webhook" -or $what -eq "both") { Kill-Target "webhook"; if (-not (Is-Running "webhook")) { Write-Host "  [OK]   webhook stopped" -ForegroundColor Green } }
}

function Do-Status {
    $bot = if (Is-Running "bot") { "[RUNNING]" } else { "[STOPPED]" }
    $web = if (Is-Running "webhook") { "[RUNNING]" } else { "[STOPPED]" }
    Write-Host "  bot      $bot" -ForegroundColor $(if ($bot -eq "[RUNNING]") { "Green" } else { "DarkGray" })
    Write-Host "  webhook  :$WEB_PORT  $web" -ForegroundColor $(if ($web -eq "[RUNNING]") { "Green" } else { "DarkGray" })
}

switch ($Command.ToLower()) {
    "start"   { Do-Start   $Target.ToLower() }
    "stop"    { Do-Stop    $Target.ToLower() }
    "restart" { Do-Start   $Target.ToLower() }   # start already kills-first
    "status"  { Do-Status }
    default   { Write-Host "Usage: .\stockpulse.ps1 start|stop|restart|status [bot|webhook|both]" -ForegroundColor Yellow }
}
