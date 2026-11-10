# Self-check fixtures are created only under the OS temporary directory.
function Invoke-RoomCheck {
    param([Parameter(Mandatory)][string]$RealRoot)
    if (-not (Get-Command Invoke-RoomCommand -ErrorAction SilentlyContinue)) {
        Write-Host '[FAIL] runner: Invoke-RoomCommand is not implemented'
        return $false
    }
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $sandbox = Join-Path $tempBase ('room-check-' + [guid]::NewGuid().ToString('N'))
    $passed = 0
    $failed = 0
    function Assert-Room([bool]$Condition, [string]$Message) {
        if (-not $Condition) { throw $Message }
    }
    function Put-Text([string]$Path, [string]$Text) {
        Set-Content -LiteralPath $Path -Value $Text -Encoding UTF8 -NoNewline
    }
    function Bytes-Key([string]$Path) {
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($Path))
    }
    function Expect-Failure([scriptblock]$Action, [string[]]$Contains) {
        $problem = $null
        try { & $Action | Out-Null } catch { $problem = $_.Exception.Message }
        Assert-Room ($null -ne $problem) 'Expected a failure, but command succeeded'
        foreach ($part in $Contains) {
            Assert-Room ($problem.Contains($part)) "Error did not mention '$part': $problem"
        }
    }
    function Snapshot-Live {
        $entries = [Collections.Generic.List[string]]::new()
        foreach ($file in @(Get-ChildItem -LiteralPath $RealRoot -File -Recurse)) {
            $relative = [IO.Path]::GetRelativePath($RealRoot, $file.FullName)
            if ($relative -match '^bin[\\/]') { continue }
            $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
            $entries.Add("$relative=$hash")
        }
        $agents = Join-Path (Split-Path $RealRoot -Parent) 'AGENTS.md'
        if (Test-Path -LiteralPath $agents) {
            $entries.Add('AGENTS.md=' + (Get-FileHash -LiteralPath $agents -Algorithm SHA256).Hash)
        }
        $entries.Sort([StringComparer]::Ordinal)
        return ($entries -join "`n")
    }
    function New-Fixture([string]$Name) {
        $root = Join-Path $sandbox $Name
        foreach ($dir in @('room/messages', 'persona', 'card', 'drafts')) {
            New-Item -ItemType Directory -Path (Join-Path $root $dir) -Force | Out-Null
        }
        Put-Text (Join-Path $root 'room/brief.md') @'
---
场次: 自检房间
目标: 验证中文与文件协议
轮次上限: 3
语言: 简体中文
---
| 席 | 模型 | 职能 | 接线 |
|---|---|---|---|
| A | gpt-5 | 提案 | 外接 |
| B | deepseek-flash | 评审 | 本机 |
| U | 用户 | 裁决 | — |
'@
        Put-Text (Join-Path $root 'room/turn.md') "# 回合权`r`n`r`n持权: A`r`n轮次: 1`r`n自: 2026-10-24T03:30:00+09:00`r`n`r`n<!-- keep -->`r`n"
        Copy-Item -LiteralPath (Join-Path $RealRoot 'persona/conductor.md') -Destination (Join-Path $root 'persona/conductor.md')
        return $root
    }
    function Add-Message([string]$Root, [int]$Index, [string]$Seat, [int]$Round = 1) {
        $name = '20261024T{0:D4}-{1}-model.md' -f $Index, $Seat
        $text = "---`nseat: $Seat`nmodel: model`nrole: 测试席`nround: $Round`nat: 2026-10-24T03:20:11+09:00`n---`n`n主张：M$('{0:D2}' -f $Index)`n置信：中`n"
        Put-Text (Join-Path $Root "room/messages/$name") $text
        return $name
    }
    function Run-Case([string]$Name, [scriptblock]$Body) {
        try { & $Body; Write-Host "[PASS] $Name"; $script:roomCheckPassed++ }
        catch { Write-Host "[FAIL] ${Name}: $($_.Exception.Message)"; $script:roomCheckFailed++ }
    }
    $script:roomCheckPassed = 0
    $script:roomCheckFailed = 0
    Write-Host 'room --check (HANDOFF v0.2 / PROTOCOL v0.1)'
    Write-Host 'Fixtures: isolated temporary directory; no live room commands.'
    try {
        $before = Snapshot-Live
        New-Item -ItemType Directory -Path $sandbox | Out-Null
        Run-Case 'S1: next A -> A message -> next B -> B message -> next SUM -> merge -> bake' {
            $r = New-Fixture 's1'
            Invoke-RoomCommand -Root $r -Arguments @('next', 'A') | Out-Null
            Add-Message $r 1 A | Out-Null
            Invoke-RoomCommand -Root $r -Arguments @('next', 'B') | Out-Null
            Add-Message $r 2 B | Out-Null
            Invoke-RoomCommand -Root $r -Arguments @('next', 'SUM') | Out-Null
            Add-Message $r 3 SUM | Out-Null
            Invoke-RoomCommand -Root $r -Arguments @('bake') | Out-Null
            $log = Get-Content -LiteralPath (Join-Path $r 'room/log.md') -Raw -Encoding UTF8
            Assert-Room ($log.IndexOf('▌A') -ge 0 -and $log.IndexOf('▌A') -lt $log.IndexOf('▌B') -and $log.IndexOf('▌B') -lt $log.IndexOf('── 合流 ──')) 'Wrong block order'
            Assert-Room ($log.Contains('══ 第 1 轮 ══') -and $log.Contains('主张：M01')) 'Missing Chinese text or round heading'
            Assert-Room (@(Get-ChildItem -LiteralPath (Join-Path $r 'room/messages') -File).Count -eq 3) 'Messages were removed'
        }
        Run-Case 'S2: corrupt current holder Z9 is rejected; turn bytes unchanged' {
            $r = New-Fixture 's2'
            $p = Join-Path $r 'room/turn.md'
            Put-Text $p ((Get-Content -LiteralPath $p -Raw -Encoding UTF8).Replace('持权: A', '持权: Z9'))
            $old = Bytes-Key $p
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('next', 'A') } @('Z9')
            Assert-Room ((Bytes-Key $p) -ceq $old) 'Corrupt token was overwritten'
        }
        Run-Case 'next: invalid target rejected; valid transfer preserves other fields and uses ISO time' {
            $r = New-Fixture 'next'
            $p = Join-Path $r 'room/turn.md'
            $old = Bytes-Key $p
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('next', 'Z8') } @('Z8')
            Assert-Room ((Bytes-Key $p) -ceq $old) 'Invalid target changed turn'
            Invoke-RoomCommand -Root $r -Arguments @('next', 'U') | Out-Null
            $turn = Get-Content -LiteralPath $p -Raw -Encoding UTF8
            Assert-Room ($turn.Contains('持权: U') -and $turn.Contains('轮次: 1') -and $turn.Contains('<!-- keep -->')) 'Transfer damaged unrelated content'
            Assert-Room ($turn -match '(?m)^自: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}\r?$') 'Timestamp is not ISO 8601'
            Put-Text $p ($turn.Replace('持权: U', '持权: 用户'))
            Invoke-RoomCommand -Root $r -Arguments @('next', 'A') | Out-Null
        }
        Run-Case 'S3: bake is byte-idempotent; missing seat names file and preserves existing log' {
            $r = Join-Path $sandbox 's1'
            $p = Join-Path $r 'room/log.md'
            $old = Bytes-Key $p
            Invoke-RoomCommand -Root $r -Arguments @('bake') | Out-Null
            Assert-Room ((Bytes-Key $p) -ceq $old) 'bake bytes differ'
            $bad = '20261024T0004-A-model.md'
            Put-Text (Join-Path $r "room/messages/$bad") "---`nmodel: x`nrole: x`nround: 1`nat: 2026-10-24T03:20:11+09:00`n---`ninvalid"
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('bake') } @($bad, 'seat')
            Assert-Room ((Bytes-Key $p) -ceq $old) 'Failed bake changed log'
        }
        Run-Case 'bake: ordinal filename order and round transitions' {
            $r = New-Fixture 'order'
            Add-Message $r 2 B 2 | Out-Null
            Add-Message $r 1 A 1 | Out-Null
            Invoke-RoomCommand -Root $r -Arguments @('bake') | Out-Null
            $log = Get-Content -LiteralPath (Join-Path $r 'room/log.md') -Raw -Encoding UTF8
            Assert-Room ($log.IndexOf('M01') -lt $log.IndexOf('M02') -and $log.Contains('══ 第 2 轮 ══')) 'Sort or round heading incorrect'
        }
        Run-Case 'frontmatter: blank required fields, duplicate keys, invalid round/time are rejected' {
            $r = New-Fixture 'invalid'
            $name = Add-Message $r 1 A
            $p = Join-Path $r "room/messages/$name"
            $original = Get-Content -LiteralPath $p -Raw -Encoding UTF8
            foreach ($key in @('seat', 'model', 'role', 'round', 'at')) {
                $bad = [regex]::Replace($original, "(?m)^${key}:.*$", "${key}:")
                Put-Text $p $bad
                Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('bake') } @($name, $key)
            }
            Put-Text $p ($original.Replace('round: 1', 'round: nope'))
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('bake') } @($name, 'round')
            Put-Text $p ($original.Replace('2026-10-24T03:20:11+09:00', 'yesterday'))
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('bake') } @($name, 'at')
            Put-Text $p ($original.Replace('seat: A', "seat: A`nseat: B"))
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('bake') } @($name, 'seat')
        }
        Run-Case 'card: exact persona format, brief summary, default 6 / -n 2, fixed ending' {
            $r = New-Fixture 'card'
            foreach ($i in 1..8) { Add-Message $r $i A | Out-Null }
            Invoke-RoomCommand -Root $r -Arguments @('card', 'B') | Out-Null
            $p = Join-Path $r 'card/B.md'
            $card = Get-Content -LiteralPath $p -Raw -Encoding UTF8
            Assert-Room ($card.Contains('▌{席号} · {模型} · {职能}') -and $card.Contains('{依据 / 正文要点：不超过 3 条}')) 'Persona template changed'
            Assert-Room ($card.Contains('自检房间') -and $card.Contains('验证中文与文件协议') -and $card.Contains('简体中文') -and $card.Contains('轮次上限: 3')) 'Brief summary incomplete'
            Assert-Room (-not $card.Contains('主张：M02') -and $card.Contains('主张：M03') -and $card.Contains('主张：M08')) 'Default count is not 6'
            Assert-Room ($card.TrimEnd().EndsWith('请只回一个席位块，不要复述上下文')) 'Card ending changed'
            Invoke-RoomCommand -Root $r -Arguments @('card', 'B', '-n', '2') | Out-Null
            $card = Get-Content -LiteralPath $p -Raw -Encoding UTF8
            Assert-Room (-not $card.Contains('主张：M06') -and $card.Contains('主张：M07') -and $card.Contains('主张：M08')) 'Custom count is not 2'
            $old = Bytes-Key $p
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('card', '../outside') } @('outside')
            Expect-Failure { Invoke-RoomCommand -Root $r -Arguments @('card', 'B', '-n', '0') } @('-n')
            Assert-Room ((Bytes-Key $p) -ceq $old) 'Invalid card request changed output'
        }
        Run-Case 'status: one line with holder, round, message count and latest seat; no writes' {
            $r = New-Fixture 'status'
            Add-Message $r 2 B | Out-Null
            Add-Message $r 1 A | Out-Null
            $line = Invoke-RoomCommand -Root $r -Arguments @('status')
            Assert-Room ($line -is [string] -and $line -notmatch '[\r\n]') 'status is not one line'
            foreach ($part in @('持权: A', '轮次: 1', '消息: 2', '最近: B')) { Assert-Room ($line.Contains($part)) "Missing status: $part" }
            Assert-Room (-not (Test-Path -LiteralPath (Join-Path $r 'room/log.md'))) 'status wrote a log'
        }
        Run-Case 'empty room: bake/card/status work without inventing messages' {
            $r = New-Fixture 'empty'
            Invoke-RoomCommand -Root $r -Arguments @('bake') | Out-Null
            Assert-Room ((Get-Item -LiteralPath (Join-Path $r 'room/log.md')).Length -eq 0) 'Empty log is not empty'
            Invoke-RoomCommand -Root $r -Arguments @('card', 'SUM') | Out-Null
            $line = Invoke-RoomCommand -Root $r -Arguments @('status')
            Assert-Room ($line.Contains('消息: 0') -and $line.Contains('最近: 无')) 'Empty status incorrect'
        }
        Run-Case 'live rules, turn, messages, logs, cards and drafts unchanged' {
            Assert-Room ((Snapshot-Live) -ceq $before) 'Live files changed during check'
        }
    } catch {
        Write-Host "[FAIL] check setup: $($_.Exception.Message)"
        $script:roomCheckFailed++
    } finally {
        if (Test-Path -LiteralPath $sandbox) {
            $resolved = [IO.Path]::GetFullPath($sandbox)
            if ($resolved.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -and
                (Split-Path $resolved -Leaf) -match '^room-check-[a-f0-9]{32}$') {
                Remove-Item -LiteralPath $resolved -Recurse -Force
            } else { throw 'Refused to clean a path outside the temporary fixture directory' }
        }
    }
    Write-Host ('Result: {0} passed, {1} failed' -f $script:roomCheckPassed, $script:roomCheckFailed)
    return ($script:roomCheckFailed -eq 0)
}
