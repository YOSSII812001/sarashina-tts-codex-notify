param(
    [Parameter(Mandatory = $true)]
    [string]$SourceWav,

    [Parameter(Mandatory = $true)]
    [string]$PromptText,

    [double]$StartSeconds = 0,
    [double]$DurationSeconds = 10,
    [string]$PromptName = "private long reference",
    [string]$OutputWav = "$env:USERPROFILE\.codex\skills\sarashina-tts\assets\prompt_private_reference_long.wav",
    [string]$SettingsPath = "$env:USERPROFILE\.codex\skills\sarashina-tts\settings.json",
    [int]$SampleRate = 24000
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[sarashina-tts] $Message"
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg was not found. Install ffmpeg, then run this script again."
}

if (-not (Test-Path -LiteralPath $SourceWav)) {
    throw "Source WAV not found: $SourceWav"
}

if ([string]::IsNullOrWhiteSpace($PromptText)) {
    throw "PromptText is required. It must match the spoken words in the reference audio."
}

if ($StartSeconds -lt 0) {
    throw "StartSeconds must be 0 or greater."
}

if ($DurationSeconds -lt 0) {
    throw "DurationSeconds must be 0 or greater. Use 0 to read until the end."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputWav) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SettingsPath) | Out-Null

$filter = "highpass=f=80,lowpass=f=12000,loudnorm=I=-18:LRA=11:TP=-1.5"
$ffmpegArgs = @(
    "-y",
    "-hide_banner",
    "-ss", $StartSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
    "-i", $SourceWav
)

if ($DurationSeconds -gt 0) {
    $ffmpegArgs += @("-t", $DurationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture))
}

$ffmpegArgs += @(
    "-af", $filter,
    "-ar", "$SampleRate",
    "-ac", "1",
    "-map_metadata", "-1",
    $OutputWav
)

Write-Step "Creating private voice reference: $OutputWav"
& ffmpeg @ffmpegArgs

$settings = [ordered]@{
    prompt_name = $PromptName
    prompt_file = $OutputWav
    prompt_text = $PromptText
}

$json = $settings | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($SettingsPath, $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))

Write-Step "Updated settings: $SettingsPath"
Write-Step "Restart the Sarashina daemon so the new reference is loaded."
