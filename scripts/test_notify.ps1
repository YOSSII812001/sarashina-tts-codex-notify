param(
    [string]$SkillRoot = "$env:USERPROFILE\.codex\skills\sarashina-tts",
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$notify = Join-Path $SkillRoot "scripts\codex_notify_sarashina_tts.py"
if (-not (Test-Path -LiteralPath $notify)) {
    throw "Notify script not found: $notify"
}

$outDir = Join-Path $env:TEMP "sarashina_tts_outputs"
$started = Get-Date
$runnerPath = Join-Path $env:TEMP ("sarashina_notify_test_" + [guid]::NewGuid().ToString("N") + ".py")
$runnerCode = @"
import json
import runpy
import sys

notify = r'''$notify'''
message = "\u30b5\u30e9\u30b7\u30caTTS\u306e\u901a\u77e5\u30c6\u30b9\u30c8\u3067\u3059\u3002"
payload = json.dumps({"last-assistant-message": message}, ensure_ascii=False)
sys.argv = [notify, payload]
runpy.run_path(notify, run_name="__main__")
"@

[System.IO.File]::WriteAllText($runnerPath, $runnerCode, (New-Object System.Text.UTF8Encoding $false))
py -X utf8 $runnerPath

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$newFile = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $outDir) {
        $newFile = Get-ChildItem -LiteralPath $outDir -Filter "*.wav" |
            Where-Object { $_.LastWriteTime -gt $started } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($newFile) { break }
    }
}

if (-not $newFile) {
    throw "No new WAV was generated within $TimeoutSeconds seconds."
}

$newFile | Select-Object FullName,Length,LastWriteTime
