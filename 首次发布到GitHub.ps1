param(
  [Parameter(Mandatory = $true)]
  [string]$RepositoryUrl
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "未找到 git，请先安装 Git for Windows。"
}

if (-not (Test-Path -LiteralPath ".git")) {
  git init
}

if (-not (git config user.name)) {
  git config user.name "Campus Radar"
}
if (-not (git config user.email)) {
  git config user.email "campus-radar@local"
}

git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "init: 2027 campus radar"
}

git branch -M main
$existingRemote = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0 -and $existingRemote) {
  git remote set-url origin $RepositoryUrl
} else {
  git remote add origin $RepositoryUrl
}

git push -u origin main
Write-Host ""
Write-Host "代码已推送。下一步：GitHub 仓库 Settings -> Pages -> Source 选择 GitHub Actions。" -ForegroundColor Green
