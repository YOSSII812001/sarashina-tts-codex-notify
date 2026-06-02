param(
    [switch]$ConfigureCodex,
    [switch]$DisableLegacyEdgeTts,
    [switch]$SkipPythonSetup,
    [string]$ToolsRoot = "$env:USERPROFILE\tools\sarashina2.2-tts",
    [string]$SkillRoot = "$env:USERPROFILE\.codex\skills\sarashina-tts"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step {
    param([string]$Message)
    Write-Host "[sarashina-tts] $Message"
}

function Copy-RepoFile {
    param([string]$RelativePath)
    $src = Join-Path $RepoRoot $RelativePath
    $dst = Join-Path $SkillRoot $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
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

function Set-CodexNotify {
    $configDir = Join-Path $env:USERPROFILE ".codex"
    $configPath = Join-Path $configDir "config.toml"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null

    $notifyScript = Join-Path $SkillRoot "scripts\codex_notify_sarashina_tts.py"
    if ($notifyScript.Contains("'")) {
        throw "The notify script path contains a single quote. Please move the repo to another path."
    }
    $line = "notify = ['py', '-X', 'utf8', '$notifyScript']"

    if (Test-Path -LiteralPath $configPath) {
        $backup = Backup-File $configPath
        $content = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
        if ($content -match '(?m)^notify\s*=') {
            $content = [regex]::Replace($content, '(?m)^notify\s*=.*$', $line, 1)
        } else {
            $content = $line + [Environment]::NewLine + $content
        }
        [System.IO.File]::WriteAllText($configPath, $content, (New-Object System.Text.UTF8Encoding $false))
        Write-Step "Updated Codex config: $configPath"
        if ($backup) { Write-Step "Backup: $backup" }
    } else {
        [System.IO.File]::WriteAllText($configPath, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))
        Write-Step "Created Codex config: $configPath"
    }
}

function Write-PythonEdgeForwarder {
    param([string]$Path)
    $code = @'
import runpy
import sys
from pathlib import Path


def main() -> int:
    payload = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    notify = Path.home() / ".codex" / "skills" / "sarashina-tts" / "scripts" / "codex_notify_sarashina_tts.py"
    if not notify.exists():
        return 0
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(notify), payload]
        runpy.run_path(str(notify), run_name="__main__")
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $backup = Backup-File $Path
    [System.IO.File]::WriteAllText($Path, $code, (New-Object System.Text.UTF8Encoding $false))
    Write-Step "Installed Edge Python forwarder: $Path"
    if ($backup) { Write-Step "Backup: $backup" }
}

function Write-PowerShellEdgeForwarder {
    param([string]$Path)
    $code = @'
param()

$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$log = Join-Path $env:TEMP "edge_tts_debug.log"

function Write-ForwardLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    "[$timestamp] EDGE DISABLED forwarder: $Message" | Out-File -FilePath $log -Append -Encoding utf8
}

function Read-Payload {
    try {
        $stream = [Console]::OpenStandardInput()
        $ms = New-Object System.IO.MemoryStream
        $buf = New-Object byte[] 8192
        while (($n = $stream.Read($buf, 0, $buf.Length)) -gt 0) {
            $ms.Write($buf, 0, $n)
        }
        if ($ms.Length -gt 0) {
            return [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
        }
    } catch {
        Write-ForwardLog "stdin read failed: $_"
    }

    $shared = Join-Path $env:TEMP "claude_hook_stdin.json"
    if (Test-Path $shared) {
        try {
            $age = ((Get-Date) - (Get-Item $shared).LastWriteTime).TotalSeconds
            if ($age -le 10) {
                return [System.IO.File]::ReadAllText($shared, [System.Text.Encoding]::UTF8)
            }
        } catch { }
    }
    return $null
}

$payload = Read-Payload
$notify = Join-Path $env:USERPROFILE ".codex\skills\sarashina-tts\scripts\codex_notify_sarashina_tts.py"
if ($payload -and (Test-Path $notify)) {
    $runId = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $payloadPath = Join-Path $env:TEMP "edge_to_sarashina_$runId.json"
    $runnerPath = Join-Path $env:TEMP "edge_to_sarashina_$runId.py"
    [System.IO.File]::WriteAllText($payloadPath, $payload, (New-Object System.Text.UTF8Encoding $false))
    $runner = @"
import pathlib
import runpy
import sys

notify = r'''$notify'''
payload_path = r'''$payloadPath'''
payload = pathlib.Path(payload_path).read_text(encoding='utf-8')
sys.argv = [notify, payload]
runpy.run_path(notify, run_name='__main__')
"@
    [System.IO.File]::WriteAllText($runnerPath, $runner, (New-Object System.Text.UTF8Encoding $false))
    $p = Start-Process -FilePath "py" -ArgumentList @("-X", "utf8", $runnerPath) -WindowStyle Hidden -PassThru
    $null = $p.WaitForExit(8000)
    Write-ForwardLog "forwarded to sarashina notify"
} else {
    Write-ForwardLog "no payload or sarashina notify missing"
}
'@
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $backup = Backup-File $Path
    [System.IO.File]::WriteAllText($Path, $code, (New-Object System.Text.UTF8Encoding $false))
    Write-Step "Installed Edge PowerShell forwarder: $Path"
    if ($backup) { Write-Step "Backup: $backup" }
}

Write-Step "Installing Codex skill files"
New-Item -ItemType Directory -Force -Path $SkillRoot | Out-Null
Copy-RepoFile "SKILL.md"
Copy-RepoFile "scripts\codex_notify_sarashina_tts.py"
Copy-RepoFile "scripts\sarashina_tts_daemon.py"
Copy-RepoFile "scripts\test_notify.ps1"
Copy-RepoFile "scripts\create_voice_reference.ps1"
Copy-RepoFile "templates\settings.example.json"
Copy-RepoFile "templates\settings.long-reference.example.json"

$settingsPath = Join-Path $SkillRoot "settings.json"
if (-not (Test-Path -LiteralPath $settingsPath)) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot "templates\settings.example.json") -Destination $settingsPath
    Write-Step "Created settings.json"
} else {
    Write-Step "settings.json already exists; keeping it"
}

if ($SkipPythonSetup) {
    Write-Step "Skipped upstream repo and Python setup."
} else {
    Write-Step "Preparing upstream Sarashina2.2-TTS repository"
    if (-not (Test-Path -LiteralPath $ToolsRoot)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ToolsRoot) | Out-Null
        git clone https://github.com/sbintuitions/sarashina2.2-tts.git $ToolsRoot
    } else {
        Write-Step "Upstream repo already exists: $ToolsRoot"
    }

    $venvPython = Join-Path $ToolsRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creating Python 3.11 venv"
        py -3.11 -m venv --system-site-packages (Join-Path $ToolsRoot ".venv")
    }

    Write-Step "Installing Python package. This can take a while."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e $ToolsRoot
}

if ($ConfigureCodex) {
    Set-CodexNotify
} else {
    Write-Step "Skipped Codex config update. Add -ConfigureCodex to update config.toml."
}

if ($DisableLegacyEdgeTts) {
    Write-Step "Installing legacy Edge TTS forwarders"
    Write-PythonEdgeForwarder (Join-Path $env:USERPROFILE ".codex\skills\edge-tts\scripts\codex_notify_edge_tts.py")
    Write-PowerShellEdgeForwarder (Join-Path $env:USERPROFILE ".codex\skills\edge-tts\scripts\speak_edge_tts.ps1")
    $claudeEdge = Join-Path $env:USERPROFILE ".claude\speak_edge_tts.ps1"
    if (Test-Path -LiteralPath $claudeEdge) {
        Write-PowerShellEdgeForwarder $claudeEdge
    }
}

Write-Step "Done. Restart Codex, then run scripts\test_notify.ps1."
