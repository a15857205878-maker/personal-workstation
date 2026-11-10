# File-protocol implementation. No model calls, watchers or message writes.
Set-StrictMode -Version Latest

function Read-RoomText([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "文件不存在: $Path" }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ($null -eq $text) { return '' }
    return $text.TrimStart([char]0xFEFF)
}

function Read-RoomFrontmatter([string]$Path) {
    $text = (Read-RoomText $Path).Replace("`r`n", "`n").Replace("`r", "`n")
    $lines = $text.Split("`n")
    $name = Split-Path $Path -Leaf
    if ($lines[0] -cne '---') { throw "${name}: 缺少 frontmatter 起始 ---" }
    $fields = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    $end = -1
    for ($i = 1; $i -lt $lines.Length; $i++) {
        $line = $lines[$i]
        if ($line -ceq '---') { $end = $i; break }
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith('#')) { continue }
        if ($line -notmatch '^\s*([^:]+):\s*(.*?)\s*$') { throw "${name}: 无效 frontmatter 行 $($i + 1)" }
        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if ($fields.ContainsKey($key)) { throw "${name}: frontmatter 字段重复: $key" }
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $fields.Add($key, $value)
    }
    if ($end -lt 0) { throw "${name}: 缺少 frontmatter 结束 ---" }
    $body = if ($end + 1 -lt $lines.Length) { ($lines[($end + 1)..($lines.Length - 1)] -join "`n").Trim([char[]]"`n") } else { '' }
    return [pscustomobject]@{ Fields = $fields; Body = $body }
}

function Get-RoomBrief([string]$Root) {
    $path = Join-Path $Root 'room/brief.md'
    $front = Read-RoomFrontmatter $path
    foreach ($key in @('场次', '目标', '语言', '轮次上限')) {
        if (-not $front.Fields.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($front.Fields[$key])) {
            throw "brief.md: 缺少必填字段 $key"
        }
    }
    $seats = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    $inTable = $false
    foreach ($line in $front.Body.Split("`n")) {
        if ($line -notmatch '^\s*\|') {
            if ($inTable) { break }
            continue
        }
        $cells = @($line.Trim().Trim('|').Split('|') | ForEach-Object { $_.Trim() })
        if (-not $inTable) {
            if ($cells.Count -eq 4 -and ($cells -join '|') -ceq '席|模型|职能|接线') { $inTable = $true }
            continue
        }
        if ($cells.Count -eq 4 -and @($cells | Where-Object { $_ -notmatch '^:?-+:?$' }).Count -eq 0) { continue }
        if ($cells.Count -ne 4 -or $cells[0] -cnotmatch '^[A-Za-z][A-Za-z0-9_-]*$') { throw 'brief.md: 无效席位表行' }
        if ($seats.ContainsKey($cells[0])) { throw "brief.md: 席位重复: $($cells[0])" }
        if ([string]::IsNullOrWhiteSpace($cells[1]) -or [string]::IsNullOrWhiteSpace($cells[2])) { throw 'brief.md: 席位模型或职能为空' }
        $seats.Add($cells[0], [pscustomobject]@{ Seat = $cells[0]; Model = $cells[1]; Role = $cells[2] })
    }
    if (-not $inTable -or $seats.Count -eq 0) { throw 'brief.md: 未找到非空席位表' }
    foreach ($special in @('U', 'SUM')) {
        if (-not $seats.ContainsKey($special)) {
            $label = if ($special -ceq 'U') { '用户' } else { '合流' }
            $seats.Add($special, [pscustomobject]@{ Seat = $special; Model = $label; Role = $label })
        }
    }
    return [pscustomobject]@{ Fields = $front.Fields; Seats = $seats }
}

function Resolve-RoomSeat($Brief, [string]$Seat) {
    # PROTOCOL R3 permits the explicit human-takeover token “用户”.
    $id = if ($Seat -ceq '用户') { 'U' } else { $Seat }
    if (-not $Brief.Seats.ContainsKey($id)) { throw "非法席位: $Seat" }
    return $id
}

function Get-RoomTurn([string]$Root, $Brief) {
    $text = Read-RoomText (Join-Path $Root 'room/turn.md')
    $values = @{}
    foreach ($key in @('持权', '轮次', '自')) {
        $matchesForKey = [regex]::Matches($text, '(?m)^' + [regex]::Escape($key) + ':\s*([^\r\n]*)\r?$')
        if ($matchesForKey.Count -ne 1 -or [string]::IsNullOrWhiteSpace($matchesForKey[0].Groups[1].Value)) {
            throw "turn.md: 字段 $key 必须存在且唯一、非空"
        }
        $values[$key] = $matchesForKey[0].Groups[1].Value.Trim()
    }
    try { $null = Resolve-RoomSeat $Brief $values['持权'] }
    catch { throw "turn.md: 当前持权无效 ($($values['持权']))，拒绝移交或诊断；请先核对令牌" }
    $round = 0
    if (-not [int]::TryParse($values['轮次'], [ref]$round) -or $round -lt 1) { throw 'turn.md: 轮次必须为正整数' }
    return [pscustomobject]@{ Text = $text; Holder = $values['持权']; Round = $round }
}

function Get-RoomMessages([string]$Root) {
    $directory = Join-Path $Root 'room/messages'
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw 'room/messages/ 不存在' }
    [string[]]$paths = @(Get-ChildItem -LiteralPath $directory -File -Filter '*.md' | ForEach-Object { $_.FullName })
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    foreach ($path in $paths) {
        $name = Split-Path $path -Leaf
        $front = Read-RoomFrontmatter $path
        foreach ($key in @('seat', 'model', 'role', 'round', 'at')) {
            if (-not $front.Fields.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($front.Fields[$key])) {
                throw "${name}: 缺少必填字段 $key"
            }
        }
        if ($name -match '[^\x00-\x7F]') { throw "${name}: 消息文件名必须为 ASCII" }
        $round = 0
        if (-not [int]::TryParse($front.Fields['round'], [ref]$round) -or $round -lt 1) { throw "${name}: round 必须为正整数" }
        $timestamp = [datetimeoffset]::MinValue
        $at = $front.Fields['at']
        if ($at -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$' -or
            -not [datetimeoffset]::TryParse($at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$timestamp)) {
            throw "${name}: at 必须为含时区的 ISO 8601 时间"
        }
        [pscustomobject]@{
            Name = $name; Seat = $front.Fields['seat']; Model = $front.Fields['model']
            Role = $front.Fields['role']; Round = $round; Body = $front.Body
        }
    }
}

function Format-RoomMessages([object[]]$Messages) {
    $blocks = [Collections.Generic.List[string]]::new()
    $previous = -1
    foreach ($message in $Messages) {
        if ($message.Round -ne $previous) {
            $blocks.Add("══ 第 $($message.Round) 轮 ══")
            $previous = $message.Round
        }
        $header = if ($message.Seat -ceq 'SUM') { '── 合流 ──' } else { "▌$($message.Seat) · $($message.Model) · $($message.Role)" }
        $blocks.Add($header + "`n" + $message.Body)
    }
    if ($blocks.Count -eq 0) { return '' }
    return ($blocks -join "`n`n") + "`n`n"
}

function Write-RoomAtomic([string]$Path, [string]$Text) {
    $directory = Split-Path $Path -Parent
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "输出目录不存在: $directory" }
    $temporary = Join-Path $directory ('.room-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Set-Content -LiteralPath $temporary -Value $Text -Encoding UTF8 -NoNewline
        [IO.File]::Move($temporary, $Path, $true)
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-RoomBlockTemplate([string]$Root) {
    $persona = (Read-RoomText (Join-Path $Root 'persona/conductor.md')).Replace("`r`n", "`n")
    $section = [regex]::Match($persona, '(?ms)^### 3\.2[^\n]*\n(?<section>.*?)(?=^### |^## |\z)')
    if (-not $section.Success) { throw 'conductor.md: 找不到 persona §3.2，拒绝自创格式' }
    $fence = [regex]::Match($section.Groups['section'].Value, '(?ms)^```[^\n]*\n(?<block>.*?)^```\s*$')
    if (-not $fence.Success) { throw 'conductor.md: §3.2 中缺少席位块模板' }
    return $fence.Groups['block'].Value.TrimEnd([char[]]"`n")
}

function Invoke-RoomCommand {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Arguments)
    if ($Arguments.Count -eq 0) { throw '用法: room next <seat> | bake | card <seat> [-n N] | status | --check' }
    $command = $Arguments[0]
    if ($command -cnotin @('next', 'bake', 'card', 'status')) { throw "未知命令: $command" }
    if ($command -cin @('bake', 'status') -and $Arguments.Count -ne 1) { throw "$command 不接受额外参数" }
    if ($command -ceq 'next' -and $Arguments.Count -ne 2) { throw '用法: room next <seat>' }
    if ($command -ceq 'card' -and $Arguments.Count -notin @(2, 4)) { throw '用法: room card <seat> [-n N]' }
    switch -CaseSensitive ($command) {
        'next' {
            $brief = Get-RoomBrief $Root
            $turn = Get-RoomTurn $Root $brief
            $null = Resolve-RoomSeat $brief $Arguments[1]
            $updated = [regex]::Replace($turn.Text, '(?m)^持权:[^\r\n]*', '持权: ' + $Arguments[1])
            $updated = [regex]::Replace($updated, '(?m)^自:[^\r\n]*', '自: ' + [datetimeoffset]::Now.ToString('o', [Globalization.CultureInfo]::InvariantCulture))
            # Re-read before replacement to avoid knowingly overwriting a changed token.
            if ((Read-RoomText (Join-Path $Root 'room/turn.md')) -cne $turn.Text) { throw 'turn.md 已被其他写者更改，拒绝覆盖' }
            Write-RoomAtomic (Join-Path $Root 'room/turn.md') $updated
            return "持权: $($Arguments[1])"
        }
        'bake' {
            $messages = @(Get-RoomMessages $Root)
            $text = Format-RoomMessages -Messages $messages
            Write-RoomAtomic (Join-Path $Root 'room/log.md') $text
            return "已生成 room/log.md（$($messages.Count) 条消息）"
        }
        'card' {
            $count = 6
            if ($Arguments.Count -eq 4) {
                if ($Arguments[2] -cne '-n' -or -not [int]::TryParse($Arguments[3], [ref]$count) -or $count -lt 1) { throw '-n 必须为正整数' }
            }
            $brief = Get-RoomBrief $Root
            $seat = Resolve-RoomSeat $brief $Arguments[1]
            $turn = Get-RoomTurn $Root $brief
            $template = Get-RoomBlockTemplate $Root
            $all = @(Get-RoomMessages $Root)
            $recent = @($all | Select-Object -Last $count)
            $history = if ($recent.Count) { (Format-RoomMessages -Messages $recent).TrimEnd([char[]]"`n") } else { '暂无消息；不要代替其他席位发言。' }
            $spec = $brief.Seats[$seat]
            $lines = @(
                '# 席位块格式要求',
                "你的席位: $seat · $($spec.Model) · $($spec.Role)",
                '以下格式原样摘自 persona §3.2；请使用你的席位信息填写。',
                '```', $template, '```', '',
                '# 本场摘要',
                "场次: $($brief.Fields['场次'])", "目标: $($brief.Fields['目标'])",
                "语言: $($brief.Fields['语言'])", "轮次: $($turn.Round)", "轮次上限: $($brief.Fields['轮次上限'])", '',
                "# 最近消息（$($recent.Count) 条）", $history, '',
                '请只回一个席位块，不要复述上下文'
            )
            Write-RoomAtomic (Join-Path $Root "card/$seat.md") (($lines -join "`n") + "`n")
            return "已生成 card/$seat.md"
        }
        'status' {
            $brief = Get-RoomBrief $Root
            $turn = Get-RoomTurn $Root $brief
            $messages = @(Get-RoomMessages $Root)
            $latest = if ($messages.Count) { $messages[-1].Seat } else { '无' }
            return "持权: $($turn.Holder) | 轮次: $($turn.Round) | 消息: $($messages.Count) | 最近: $latest"
        }
    }
}
