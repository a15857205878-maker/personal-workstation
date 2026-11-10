# PowerShell 7 entry point. Examples: ./room.ps1 status; ./room.ps1 --check
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'room 需要 PowerShell 7 (pwsh)' }
    . (Join-Path $PSScriptRoot 'room-core.ps1')
    $root = Split-Path $PSScriptRoot -Parent
    if ($args.Count -gt 0 -and $args[0] -ceq '--check') {
        if ($args.Count -ne 1) { throw '--check 不接受额外参数' }
        . (Join-Path $PSScriptRoot 'room-check.ps1')
        if (Invoke-RoomCheck -RealRoot $root) { exit 0 } else { exit 1 }
    }
    Invoke-RoomCommand -Root $root -Arguments $args
    exit 0
} catch {
    [Console]::Error.WriteLine('room: ' + $_.Exception.Message)
    exit 1
}
