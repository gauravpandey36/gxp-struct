# Publish GxP-Struct to GitHub (PowerShell).
#
# Usage:  .\scripts\publish.ps1
#
# Optional parameters:
#   -GhUser    GitHub username  (default: gauravpandey36)
#   -GhRepo    Repo name        (default: gxp-struct)
#   -GhVis     "public" or "private" (default: public)

param(
    [string]$GhUser = "gauravpandey36",
    [string]$GhRepo = "gxp-struct",
    [ValidateSet("public", "private")]
    [string]$GhVis  = "public"
)

$ErrorActionPreference = "Stop"

# Move to the project root regardless of where the script was invoked from.
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> Project root: $(Get-Location)"

# 1. Smoke test
Write-Host "==> Running smoke test (rules-only, no API calls)"
$smokeLog = Join-Path $env:TEMP "gxp_smoke.log"
$smokeOut = & python validation_test.py --rules-only 2>&1
$smokeOut | Out-File -FilePath $smokeLog -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Host "Smoke test failed. Output:"
    Get-Content $smokeLog
    exit 1
}
Write-Host ($smokeOut | Select-Object -Last 1)

# 2. Clean any half-initialized .git
if (Test-Path ".git") {
    Write-Host "==> Removing existing .git directory (previous attempt cleanup)"
    try {
        Remove-Item -Recurse -Force ".git"
    } catch {
        Write-Host "Could not remove .git: $_"
        Write-Host "Pause OneDrive sync (right-click tray icon -> Pause syncing) and retry."
        exit 1
    }
}

# 3. Init, stage, commit
Write-Host "==> git init -b main"
git init -b main | Out-Null
git config user.email "chotupandey616@gmail.com"
git config user.name  "Gourav Pandey"

git add -A
$staged = (git status --short | Measure-Object -Line).Lines
Write-Host "==> Staged $staged files"

$commitArgs = @(
    "commit",
    "-m", "GxP-Struct v0.1: machine-readable standard for pharmaceutical SOPs",
    "-m", "- Schema specification for representing pharma SOPs in a machine-readable form (the `"Fourth Translation`").",
    "-m", "- Reference implementation: deterministic rule engine + .gxp parser + RAG fallback + audit log.",
    "-m", "- Canonical example: examples/Deviation_SOP.gxp covering Deviation/CAPA, 23 rules across 8 tag families.",
    "-m", "- Golden Q&A suite: 10/10 passing on deterministic path with no API calls.",
    "-m", "- Designed against 21 CFR Part 11 / EU GMP Annex 11."
)
& git @commitArgs | Out-Null

$commit = git log --oneline -1
Write-Host "==> Committed: $commit"

# 4. Push
$ghAvailable = Get-Command gh -ErrorAction SilentlyContinue
if ($ghAvailable) {
    Write-Host "==> gh CLI detected — creating repo and pushing in one step"
    & gh repo create "$GhUser/$GhRepo" `
        "--$GhVis" `
        --source=. `
        --remote=origin `
        --description "Open-source machine-readable standard for pharmaceutical SOPs — deterministic, auditable, GxP-aligned" `
        --push

    Write-Host "==> Adding topics"
    & gh repo edit "$GhUser/$GhRepo" `
        --add-topic pharmaceutical `
        --add-topic gxp `
        --add-topic rag `
        --add-topic 21-cfr-part-11 `
        --add-topic open-standard `
        --add-topic life-sciences `
        --add-topic deterministic-ai `
        --add-topic validated-state

    Write-Host "==> Enabling Discussions"
    & gh repo edit "$GhUser/$GhRepo" --enable-discussions
} else {
    Write-Host "==> gh CLI not found — using git push directly"
    Write-Host "    First, create the empty repo at:"
    Write-Host "    https://github.com/new"
    Write-Host "    Name: $GhRepo, Visibility: $GhVis. Leave README/license/.gitignore unticked."
    Read-Host "    Press Enter once the empty repo exists on GitHub"
    git remote add origin "https://github.com/$GhUser/$GhRepo.git"
    git push -u origin main
}

Write-Host ""
Write-Host "==> Done."
Write-Host "    Live URL:  https://github.com/$GhUser/$GhRepo"
Write-Host "    Commit:    $commit"
