param(
  [string]$Owner = "leejiazhi88-gif",
  [string]$Repo = "BigAtotal2",
  [string]$Branch = "main",
  [string]$Message = "Sync dashboard files"
)

$ErrorActionPreference = "Stop"

if (-not $env:GITHUB_TOKEN) {
  throw "GITHUB_TOKEN is not set in this PowerShell session."
}

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

$headers = @{
  Authorization = "Bearer $env:GITHUB_TOKEN"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}

function Invoke-GitHubJson {
  param(
    [string]$Method,
    [string]$Uri,
    $Body = $null
  )

  if ($null -eq $Body) {
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
  }

  $json = $Body | ConvertTo-Json -Depth 20
  return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/json; charset=utf-8" -Body $json
}

$api = "https://api.github.com/repos/$Owner/$Repo"
$files = @(git ls-files)
if (-not $files -or $files.Count -eq 0) {
  throw "No tracked files found. Commit or add files before uploading."
}

function ConvertTo-GitHubPath {
  param([string]$Path)

  $normalized = $Path -replace "\\", "/"
  return (($normalized -split "/") | ForEach-Object {
    [System.Uri]::EscapeDataString($_)
  }) -join "/"
}

function Get-RemoteFileSha {
  param([string]$Path)

  $escapedPath = ConvertTo-GitHubPath $Path
  try {
    $remote = Invoke-GitHubJson -Method "Get" -Uri "$api/contents/$escapedPath`?ref=$Branch"
    return $remote.sha
  } catch {
    return $null
  }
}

Write-Host "Uploading $($files.Count) tracked files to $Owner/$Repo ($Branch) ..."

$uploaded = 0
foreach ($file in $files) {
  $bytes = [System.IO.File]::ReadAllBytes((Join-Path $repoRoot $file))
  $content = [Convert]::ToBase64String($bytes)
  $escapedPath = ConvertTo-GitHubPath $file
  $sha = Get-RemoteFileSha $file

  $body = @{
    message = "$Message`: $file"
    content = $content
    branch = $Branch
  }
  if ($sha) {
    $body.sha = $sha
  }

  Invoke-GitHubJson -Method "Put" -Uri "$api/contents/$escapedPath" -Body $body | Out-Null
  $uploaded += 1
  Write-Host "  uploaded $file"
}

Write-Host "Uploaded successfully:"
Write-Host "  https://github.com/$Owner/$Repo/tree/$Branch"
Write-Host "  files $uploaded"
