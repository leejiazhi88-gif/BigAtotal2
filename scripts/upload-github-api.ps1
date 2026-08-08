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
$files = git ls-files
if (-not $files) {
  throw "No tracked files found. Commit or add files before uploading."
}

Write-Host "Uploading $($files.Count) tracked files to $Owner/$Repo ($Branch) ..."

$treeItems = @()
foreach ($file in $files) {
  $bytes = [System.IO.File]::ReadAllBytes((Join-Path $repoRoot $file))
  $content = [Convert]::ToBase64String($bytes)
  $blob = Invoke-GitHubJson -Method "Post" -Uri "$api/git/blobs" -Body @{
    content = $content
    encoding = "base64"
  }

  $treeItems += @{
    path = ($file -replace "\\", "/")
    mode = "100644"
    type = "blob"
    sha = $blob.sha
  }

  Write-Host "  prepared $file"
}

$currentCommitSha = $null
try {
  $ref = Invoke-GitHubJson -Method "Get" -Uri "$api/git/ref/heads/$Branch"
  $currentCommitSha = $ref.object.sha
  Write-Host "Found existing $Branch at $currentCommitSha"
} catch {
  Write-Host "No existing $Branch ref found; creating first commit."
}

$tree = Invoke-GitHubJson -Method "Post" -Uri "$api/git/trees" -Body @{
  tree = $treeItems
}

$commitBody = @{
  message = $Message
  tree = $tree.sha
}
if ($currentCommitSha) {
  $commitBody.parents = @($currentCommitSha)
}

$commit = Invoke-GitHubJson -Method "Post" -Uri "$api/git/commits" -Body $commitBody

if ($currentCommitSha) {
  Invoke-GitHubJson -Method "Patch" -Uri "$api/git/refs/heads/$Branch" -Body @{
    sha = $commit.sha
    force = $false
  } | Out-Null
} else {
  Invoke-GitHubJson -Method "Post" -Uri "$api/git/refs" -Body @{
    ref = "refs/heads/$Branch"
    sha = $commit.sha
  } | Out-Null
}

Write-Host "Uploaded successfully:"
Write-Host "  https://github.com/$Owner/$Repo/tree/$Branch"
Write-Host "  commit $($commit.sha)"
