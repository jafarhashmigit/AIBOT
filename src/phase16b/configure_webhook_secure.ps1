# Secure local Discord webhook configuration for Phase 16B.
# Reads webhook via hidden SecureString input. Never echoes the secret.
# Writes only to gitignored .env at repo root.

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

Write-Host "Phase 16B secure webhook configuration"
Write-Host "Repo: $RepoRoot"
Write-Host "Paste the NEW Discord webhook URL (input hidden). Press Enter when done."
Write-Host "Do NOT use the previously exposed webhook."

$secure = Read-Host -AsSecureString "DISCORD_WEBHOOK_URL"
if ($null -eq $secure -or $secure.Length -eq 0) {
    Write-Host "ERROR: empty input; .env not modified"
    exit 2
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
}

if ([string]::IsNullOrWhiteSpace($plain)) {
    Write-Host "ERROR: empty webhook after decode; .env not modified"
    exit 2
}
if ($plain -notmatch '^https://(discord\.com|discordapp\.com)/api/webhooks/') {
    Write-Host "ERROR: value does not look like a Discord webhook URL; .env not modified"
    $plain = $null
    exit 3
}

$envPath = Join-Path $RepoRoot ".env"
$lines = @()
if (Test-Path $envPath) {
    foreach ($line in Get-Content -Path $envPath -Encoding UTF8) {
        if ($line -match '^\s*DISCORD_WEBHOOK_URL\s*=') {
            continue
        }
        $lines += $line
    }
}
$lines += ("DISCORD_WEBHOOK_URL=" + $plain)
$plain = $null

# Write without dumping contents to console
[System.IO.File]::WriteAllLines($envPath, $lines)

# Verify presence only
$configured = $false
foreach ($line in Get-Content -Path $envPath -Encoding UTF8) {
    if ($line -match '^\s*DISCORD_WEBHOOK_URL\s*=\s*(.+)\s*$') {
        $val = $Matches[1].Trim().Trim('"').Trim("'")
        if (-not [string]::IsNullOrWhiteSpace($val)) {
            $configured = $true
        }
    }
}

if (-not $configured) {
    Write-Host "ERROR: DISCORD_WEBHOOK_URL missing or empty after write"
    exit 4
}

Write-Host "OK: DISCORD_WEBHOOK_URL configured in gitignored .env (value not shown)"
Write-Host "Press Enter to close this window."
[void][Console]::ReadLine()
exit 0
