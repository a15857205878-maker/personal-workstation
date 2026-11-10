param([switch]$SmokeTest)

# UTF-8 with BOM is required by Windows PowerShell 5.1 for the Chinese messages.
$ErrorActionPreference = 'Stop'
$appDirectory = $PSScriptRoot
Set-Location -LiteralPath $appDirectory

function Show-LaunchError([string]$message) {
    if ($SmokeTest) {
        [Console]::Error.WriteLine($message)
    } else {
        Add-Type -AssemblyName System.Windows.Forms
        [void][System.Windows.Forms.MessageBox]::Show($message, '个人工具中心启动失败', 'OK', 'Error')
    }
}

try {
    $candidates = @()
    foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
        foreach ($command in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($command.Source -and $command.Source -notlike '*\Microsoft\WindowsApps\*') {
                $prefix = @()
                if ($name -eq 'py.exe') { $prefix = @('-3') }
                $candidates += @{ Path = $command.Source; Prefix = $prefix }
            }
        }
    }
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled -PathType Leaf) {
        $candidates += @{ Path = $bundled; Prefix = @() }
    }

    $selected = $null
    $probe = 'import sys, tkinter as t, PIL; assert sys.version_info >= (3, 10); r=t.Tk(); r.withdraw(); r.update(); r.destroy()'
    foreach ($candidate in $candidates) {
        # Native stderr is not a terminating PowerShell error during interpreter probes.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $prefix = $candidate.Prefix
            & $candidate.Path @prefix '-c' $probe *> $null
            if ($LASTEXITCODE -eq 0) {
                $selected = $candidate
                break
            }
        } catch {
            # Try the next locally available interpreter; nothing is installed.
        } finally {
            $ErrorActionPreference = $previousPreference
        }
    }
    if ($null -eq $selected) {
        Show-LaunchError "没有找到可用的 Python 3.10+ 、Tkinter 与 Pillow。请使用已具备 Tkinter 与 Pillow 的本机 Python，或保留 Codex 附带运行时。此启动器不会下载或安装依赖。"
        exit 1
    }

    $appFile = Join-Path $appDirectory 'app.py'
    $prefix = $selected.Prefix
    # A hidden python.exe preserves stderr. Wait so startup/runtime failures remain visible.
    $errorLog = Join-Path $appDirectory 'startup-error.log'
    $arguments = @($prefix) + @('"' + $appFile + '"')
    if ($SmokeTest) {
        $errorLog = Join-Path $appDirectory '.smoke-launch-error.log'
        $arguments += '--smoke-test'
    }
    $process = Start-Process -FilePath $selected.Path -ArgumentList $arguments -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardError $errorLog -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        $detail = ''
        if (Test-Path -LiteralPath $errorLog) {
            $detail = Get-Content -LiteralPath $errorLog -Raw -ErrorAction SilentlyContinue
        }
        Show-LaunchError "程序未能正常运行（退出码 $($process.ExitCode)）。错误记录：$errorLog`n`n$detail"
        if ($SmokeTest) { Remove-Item -LiteralPath $errorLog -ErrorAction SilentlyContinue }
        exit $process.ExitCode
    }
    if ($SmokeTest) { Remove-Item -LiteralPath $errorLog -ErrorAction SilentlyContinue }
    exit 0
} catch {
    Show-LaunchError "启动失败：$($_.Exception.Message)"
    exit 1
}
