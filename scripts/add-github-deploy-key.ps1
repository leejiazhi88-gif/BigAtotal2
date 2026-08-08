param(
  [string]$Owner = "leejiazhi88-gif",
  [string]$Repo = "BigAtotal2",
  [string]$Title = "codex-biga-total2",
  [string]$PublicKeyPath = "$env:USERPROFILE\.ssh\id_ed25519_codex_biga_total2.pub"
)

$ErrorActionPreference = "Stop"

if (-not $env:GITHUB_TOKEN) {
  throw "GITHUB_TOKEN is not set in this PowerShell session."
}

if (-not (Test-Path $PublicKeyPath)) {
  throw "Public key not found: $PublicKeyPath"
}

$pub = (Get-Content $PublicKeyPath -Raw).Trim()
$headers = @{
  Authorization = "Bearer $env:GITHUB_TOKEN"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$existing = Invoke-RestMethod `
  -Method Get `
  -Uri "https://api.github.com/repos/$Owner/$Repo/keys" `
  -Headers $headers

$match = $existing | Where-Object { $_.title -eq $Title -or $_.key -eq $pub } | Select-Object -First 1
if ($match) {
  Write-Host "Deploy key already exists: $($match.title)"
  exit 0
}

$body = @{
  title = $Title
  key = $pub
  read_only = $false
} | ConvertTo-Json

$created = Invoke-RestMethod `
  -Method Post `
  -Uri "https://api.github.com/repos/$Owner/$Repo/keys" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body

Write-Host "Deploy key added: $($created.title)"
