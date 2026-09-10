# The Klever Kobold — one-line install for Windows. Safe to re-run.
#
#   irm https://raw.githubusercontent.com/DeastinY/klever-kobold/main/deploy/install.ps1 | iex
#
# Installs uv and Ollama with winget if missing, then the kobold, pulls the two
# models and the rules index, and opens it in the browser.
$ErrorActionPreference = "Stop"
$repo = if ($env:KOBOLD_REPO) { $env:KOBOLD_REPO } else { "https://github.com/DeastinY/klever-kobold" }
function Say($t) { Write-Host "`n$t" -ForegroundColor Cyan }
function Have($c) { return [bool](Get-Command $c -ErrorAction SilentlyContinue) }

Say "1/4  uv"
if (-not (Have "uv")) {
  if (Have "winget") { winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements }
  else { irm https://astral.sh/uv/install.ps1 | iex }
  $env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Programs\uv;$env:Path"
}
uv --version

Say "2/4  Ollama"
if (-not (Have "ollama")) {
  if (Have "winget") { winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements }
  else { Write-Host "winget is not available. Install Ollama from https://ollama.com/download and run this again."; exit 1 }
  $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
}
try { Invoke-RestMethod http://localhost:11434/api/tags | Out-Null }
catch { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
ollama --version

Say "3/4  The Klever Kobold"
uv tool install --force "git+$repo"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
kobold setup

Say "4/4  Starting"
Write-Host "Runs at http://localhost:8765 - next time, just:  kobold serve"
Start-Job { Start-Sleep 3; Start-Process "http://localhost:8765" } | Out-Null
kobold serve
