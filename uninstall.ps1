param(
    [switch]$RemoveCodexNotify,
    [switch]$RemoveSkill,
    [switch]$RemoveUpstreamRepo,
    [switch]$StopDaemon,
    [string]$ToolsRoot = "$env:USERPROFILE\tools\sarashina2.2-tts",
    [string]$SkillRoot = "$env:USERPROFILE\.codex\skills\sarashina-tts"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[sarashina-tts] $Message"
}

function Backup-File {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        $backup = "$Path.bak-$stamp"
        Copy-Item -LiteralPath $Path -Destination $backup -Force
        return $backup
    }
    return $null
}

if ($StopDaemon) {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*sarashina_tts_daemon.py*' } |
        ForEach-Object {
            Write-Step "Stopping daemon PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force
        }
}

if ($RemoveCodexNotify) {
    $configPath = Join-Path $env:USERPROFILE ".codex\config.toml"
    if (Test-Path -LiteralPath $configPath) {
        $backup = Backup-File $configPath
        $content = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
        $content = [regex]::Replace(
            $content,
            "(?m)^notify\s*=\s*\[.*sarashina-tts.*codex_notify_sarashina_tts\.py.*\]\s*\r?\n?",
            ""
        )
        [System.IO.File]::WriteAllText($configPath, $content, (New-Object System.Text.UTF8Encoding $false))
        Write-Step "Removed Sarashina notify line from Codex config"
        if ($backup) { Write-Step "Backup: $backup" }
    }
}

if ($RemoveSkill -and (Test-Path -LiteralPath $SkillRoot)) {
    Write-Step "Removing skill directory: $SkillRoot"
    Remove-Item -LiteralPath $SkillRoot -Recurse -Force
}

if ($RemoveUpstreamRepo -and (Test-Path -LiteralPath $ToolsRoot)) {
    Write-Step "Removing upstream repository: $ToolsRoot"
    Remove-Item -LiteralPath $ToolsRoot -Recurse -Force
}

Write-Step "Done."

