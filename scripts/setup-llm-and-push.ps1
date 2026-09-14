<#
  HealthBridge -- one-shot: commit the QA work, install/verify the local LLM,
  then prove the AI path end to end against a real complaint.

  Ordered deliberately: git first (seconds, and it is the step whose failure
  mode is catastrophic), Ollama second (a ~2.5 GB download you can walk away
  from), verification last.

  Run:
      powershell -ExecutionPolicy Bypass -File .\scripts\setup-llm-and-push.ps1

  To also push, create an EMPTY private repo on GitHub first, then pass its URL:
      powershell -ExecutionPolicy Bypass -File .\scripts\setup-llm-and-push.ps1 `
          -RemoteUrl https://github.com/<you>/healthbridge.git

  Without -RemoteUrl the script commits locally and stops before pushing --
  it will not invent a remote for you.
#>
param(
    [string]$RemoteUrl = "",
    [string]$Branch    = "qa/overnight-2026-09-13",
    [switch]$SkipOllama,
    [switch]$SkipGit
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Section($t) {
    Write-Host ""
    Write-Host "=== $t ===" -ForegroundColor Cyan
}
function Ok($t)   { Write-Host "  [ok]   $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [warn] $t" -ForegroundColor Yellow }
function Bad($t)  { Write-Host "  [FAIL] $t" -ForegroundColor Red }

Write-Host "Repo root: $RepoRoot"

# ---------------------------------------------------------------------------
# 1. Commit the QA session's working tree onto a branch
# ---------------------------------------------------------------------------
if (-not $SkipGit) {
    Section "Git -- branch, commit, (optional) push"

    git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Bad "Not a git repository. Run 'git init' first, then re-run this script."
        exit 1
    }

    $current = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($current -ne $Branch) {
        git show-ref --verify --quiet "refs/heads/$Branch"
        if ($LASTEXITCODE -eq 0) { git checkout $Branch } else { git checkout -b $Branch }
        if ($LASTEXITCODE -ne 0) { Bad "Could not switch to $Branch"; exit 1 }
    }
    Ok "on branch $Branch"

    # Show what is about to be committed BEFORE committing it. .gitignore
    # already excludes .env, scratch_*, boot-log.txt and 'Claude outputs/' --
    # if any of those appear below, stop and fix .gitignore first.
    Write-Host ""
    Write-Host "  Files that will be committed:" -ForegroundColor Gray
    git add -A
    git status --short | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }

    $leaks = git diff --cached --name-only | Select-String -Pattern '(^|/)\.env$|^scratch_|^boot-log\.txt$|^Claude outputs/'
    if ($leaks) {
        Bad "Secrets or scratch files are staged:"
        $leaks | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        Bad "Aborting before commit. Fix .gitignore, run 'git rm --cached <file>', re-run."
        exit 1
    }
    Ok "no secrets or scratch files staged"

    $staged = git diff --cached --name-only
    if (-not $staged) {
        Warn "nothing to commit -- working tree already clean"
    } else {
        $msg = @"
QA: fix clean-DB migration, patient detail 500, and 11 more

Overnight QA and repair pass of 13-14 September 2026 -- the first time the
stack was booted as an integrated whole. Three critical defects that the
existing 129 tests could not have caught:

- alembic upgrade head failed on any clean database: every postgresql.ENUM
  was pre-created with checkfirst=True and then handed to create_table,
  which emits CREATE TYPE again. Fixed with create_type=False on all 13.
- GET /patients/{abha} returned 500 for every patient with an encounter --
  PatientDetailResponse is built in Python, so Pydantic v2 rejected the raw
  ORM rows in encounters.
- Both patient detail pages then crashed in the server render: Core returns
  {patient, encounters}, both pages cast it to a flat Patient. Added a
  PatientDetail type.

Root cause of all three: tests/conftest.py builds tables via
model.__table__.create(engine) against in-memory SQLite, so no test had ever
executed a migration or a JSONB code path.

Also fixed: the offline-save dead end, five facility controls that reported
success regardless of the write, absent request validation across the API,
the seed script's 403, the raw invalid_credentials on the login screen,
131px of horizontal overflow at 768px, and eight unlabelled inputs.

Tests: 129 -> 149, including a real-Postgres Alembic smoke test that
reproduces the migration bug exactly when the fix is reverted.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LwnqEHzqAkqGu9bkZ2VStS
"@
        git commit -m $msg
        if ($LASTEXITCODE -ne 0) { Bad "commit failed"; exit 1 }
        Ok "committed"
    }

    if ($RemoteUrl) {
        $hasOrigin = (git remote) -contains 'origin'
        if (-not $hasOrigin) { git remote add origin $RemoteUrl; Ok "added remote origin -> $RemoteUrl" }
        git push -u origin $Branch
        if ($LASTEXITCODE -ne 0) {
            Bad "push failed -- check the URL and that you are authenticated to GitHub"
        } else {
            Ok "pushed. The project now exists somewhere other than this laptop."
        }
    } else {
        Warn "no -RemoteUrl given, so nothing was pushed."
        Warn "The project still exists only on this laptop. Create a private repo and re-run with -RemoteUrl."
    }
}

# ---------------------------------------------------------------------------
# 2. Ollama + phi4-mini
# ---------------------------------------------------------------------------
function Get-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        'C:\Program Files\Ollama\ollama.exe'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

if (-not $SkipOllama) {
    Section "Ollama -- install and pull phi4-mini"

    $ollama = Get-OllamaExe
    if (-not $ollama) {
        Warn "Ollama is not installed. Installing via winget (a UAC prompt may appear)..."
        winget install --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        Start-Sleep -Seconds 5
        $ollama = Get-OllamaExe
    }

    if (-not $ollama) {
        Bad "Ollama still not found. Install it manually from https://ollama.com/download,"
        Bad "then re-run this script (it will skip straight past the git step if already committed)."
    } else {
        Ok "ollama at $ollama"

        # The installer starts ollama serve as a background service; give it a
        # moment before the first API call.
        Start-Sleep -Seconds 3

        $have = & $ollama list 2>&1 | Out-String
        if ($have -match 'phi4-mini') {
            Ok "phi4-mini already pulled"
        } else {
            Write-Host "  Pulling phi4-mini (~2.5 GB). This is the long part." -ForegroundColor Gray
            & $ollama pull phi4-mini
            if ($LASTEXITCODE -ne 0) { Bad "pull failed"; } else { Ok "phi4-mini pulled" }
        }
    }
}

# ---------------------------------------------------------------------------
# 3. Verify the whole AI path
# ---------------------------------------------------------------------------
Section "Verification"

try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $names = ($tags.models | ForEach-Object { $_.name }) -join ', '
    Ok "Ollama reachable. Models: $names"
} catch {
    Bad "Ollama not reachable on http://localhost:11434 -- is 'ollama serve' running?"
}

try {
    $h = Invoke-RestMethod -Uri 'http://localhost:8100/health' -TimeoutSec 5
    if ($h.ollama_reachable) {
        Ok "AI service sees Ollama (ollama_reachable=true, whisper_available=$($h.whisper_available))"
    } else {
        Bad "AI service is up but ollama_reachable=false."
        Warn "Most likely cause: OLLAMA_HOST inside the container points at the container itself."
        Warn "Compose defaults to http://host.docker.internal:11434, which is correct -- but the"
        Warn "repo-root .env sets http://localhost:11434. If compose is picking that up, it breaks."
        Warn "Check with:  docker compose -f infra/docker-compose.yml exec ai printenv OLLAMA_HOST"
    }
} catch {
    Warn "AI service not reachable on :8100 -- start the stack first (scripts\boot.ps1)."
}

# The real question is not 'does it respond' but 'does phi4-mini extract
# usable facts from how an ASHA actually types'. Danger signs are deliberately
# present here: fast breathing + not drinking. Expect severity RED from the
# RULE ENGINE, never from the model.
$complaint = '3 saal ka bacha, 2 din se tez bukhar, saans bahut tez chal rahi hai, paani bilkul nahi pi raha, do baar ulti hui'
$body = @{ complaint_text = $complaint; age_months = 36 } | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Method Post -Uri 'http://localhost:8100/triage/extract' `
                           -ContentType 'application/json' -Body $body -TimeoutSec 60
    Ok "extraction returned"
    Write-Host ""
    Write-Host "  Complaint: $complaint" -ForegroundColor Gray
    Write-Host "  Severity : $($r.severity)   (rule $($r.rule_id), $($r.rule_version))" -ForegroundColor White
    Write-Host "  Facts    :" -ForegroundColor Gray
    $r.extracted_facts | ConvertTo-Json -Depth 6 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    Write-Host ""
    if ($r.severity -eq 'RED') {
        Ok "RED, as expected for fast breathing + refusing fluids."
    } else {
        Warn "Expected RED for this complaint but got $($r.severity)."
        Warn "That is an EXTRACTION quality problem, not a rules problem -- look at the facts above"
        Warn "and check which danger-sign fields phi4-mini failed to populate."
    }
} catch {
    $resp = $_.Exception.Response
    if ($resp -and $resp.StatusCode.value__ -eq 503) {
        Warn "503 ai_unavailable -- this is the INTENDED degradation path, not a crash."
        Warn "It means Ollama is unreachable from the AI service, or the model returned non-JSON."
    } else {
        Bad "extract call failed: $($_.Exception.Message)"
    }
}

Section "Done"
Write-Host "Next, if verification was clean: walk the ASHA -> doctor journey and RECORD THE SCREEN."
Write-Host "The recording is what permanently retires the 'never been run' risk."
