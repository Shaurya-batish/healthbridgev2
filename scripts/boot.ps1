# HealthBridge - one-command integrated boot (Windows / PowerShell)
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\boot.ps1
#
# Brings up Postgres, Redis, Core, AI and Web via Docker Compose, waits for
# each to actually answer, seeds facilities/users and demo patients, then
# prints a status summary. Everything is transcribed to boot-log.txt at the
# repo root so the whole run can be read back in one go.

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogPath = Join-Path $RepoRoot 'boot-log.txt'
if (Test-Path $LogPath) { Remove-Item $LogPath -Force }
Start-Transcript -Path $LogPath -Force | Out-Null

$Compose = @('compose', '-f', 'infra/docker-compose.yml')
$Failed  = $false

function Section($text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

function Wait-ForHttp {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 240
    )
    Write-Host "Waiting for $Name at $Url (up to $TimeoutSeconds s)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastErr  = ''
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -lt 500) {
                Write-Host "  OK  $Name responded $($resp.StatusCode)" -ForegroundColor Green
                return $true
            }
            $lastErr = "HTTP $($resp.StatusCode)"
        } catch {
            $lastErr = $_.Exception.Message
        }
        Start-Sleep -Seconds 3
    }
    Write-Host "  FAIL  $Name never became ready. Last error: $lastErr" -ForegroundColor Red
    return $false
}

# ---------------------------------------------------------------- preflight
Section 'Preflight'
Write-Host "Repo root: $RepoRoot"

& docker version --format '{{.Server.Version}}' 2>&1 | Out-String | ForEach-Object { Write-Host "Docker server: $($_.Trim())" }
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not responding. Start Docker Desktop, wait for the whale icon to stop animating, then re-run." -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}

if (-not (Test-Path '.env')) {
    if (Test-Path '.env.example') {
        Copy-Item '.env.example' '.env'
        Write-Host "Created .env from .env.example (ABDM/NHA creds intentionally left blank)."
    }
} else {
    Write-Host ".env already present."
}

# ------------------------------------------------------------------- build
Section 'Build and start the stack'
Write-Host "This is the first integrated build - expect it to take several minutes."
& docker @Compose up --build -d 2>&1 | Tee-Object -Variable upOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose up FAILED. Full output is above and in boot-log.txt." -ForegroundColor Red
    Section 'Container status'
    & docker @Compose ps -a 2>&1 | Out-Host
    Stop-Transcript | Out-Null
    exit 1
}

Section 'Container status'
& docker @Compose ps 2>&1 | Out-Host

# ------------------------------------------------------------------ health
Section 'Service readiness'
$coreOk = Wait-ForHttp -Name 'Core'  -Url 'http://localhost:8000/health' -TimeoutSeconds 240
$webOk  = Wait-ForHttp -Name 'Web'   -Url 'http://localhost:3000/login'  -TimeoutSeconds 240
$aiOk   = Wait-ForHttp -Name 'AI'    -Url 'http://localhost:8100/health' -TimeoutSeconds 60

if (-not $coreOk) {
    $Failed = $true
    Section 'Core service logs (last 120 lines)'
    & docker @Compose logs --tail 120 core 2>&1 | Out-Host
    Section 'Postgres logs (last 40 lines)'
    & docker @Compose logs --tail 40 postgres 2>&1 | Out-Host
}
if (-not $webOk) {
    $Failed = $true
    Section 'Web service logs (last 120 lines)'
    & docker @Compose logs --tail 120 web 2>&1 | Out-Host
}
if (-not $aiOk) {
    Write-Host "AI service is not answering. This is NON-FATAL by design: the ASHA" -ForegroundColor Yellow
    Write-Host "checklist path runs the same rule table without it (CLAUDE.md, Offline" -ForegroundColor Yellow
    Write-Host "degradation). It usually means Ollama is not running on the host." -ForegroundColor Yellow
    Section 'AI service logs (last 60 lines)'
    & docker @Compose logs --tail 60 ai 2>&1 | Out-Host
}

if (-not $coreOk) {
    Write-Host ""
    Write-Host "Core is down - skipping seed. Fix Core first." -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}

# ----------------------------------------------------- migrations verified
Section 'Alembic migration state'
& docker @Compose exec -T core alembic current 2>&1 | Out-Host

Section 'Tables created in Postgres'
& docker @Compose exec -T postgres psql -U healthbridge -d healthbridge -c "\dt" 2>&1 | Out-Host

# -------------------------------------------------------------------- seed
Section 'Seed 1/2 - facilities and users'
Get-Content 'scripts/seed_facilities_and_users.sql' -Raw | & docker @Compose exec -T postgres psql -U healthbridge -d healthbridge -v ON_ERROR_STOP=1 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "  Facility/user seed FAILED." -ForegroundColor Red; $Failed = $true }
else { Write-Host "  OK" -ForegroundColor Green }

Section 'Seed 2/2 - demo patients (through the real API)'
# Piped into the core container's python: inside that container
# http://localhost:8000 is Core itself, which is the script's default.
Get-Content 'scripts/seed_demo_patients.py' -Raw | & docker @Compose exec -T core python - 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Host "  Demo patient seed FAILED." -ForegroundColor Red; $Failed = $true }
else { Write-Host "  OK" -ForegroundColor Green }

# ----------------------------------------------------------- verify counts
Section 'Row counts after seeding'
$countSql = @"
SELECT 'facilities' AS t, count(*) FROM facilities
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'patients', count(*) FROM patients
UNION ALL SELECT 'encounters', count(*) FROM encounters
UNION ALL SELECT 'triage_records', count(*) FROM triage_records
UNION ALL SELECT 'queue_tokens', count(*) FROM queue_tokens
UNION ALL SELECT 'escalation_events', count(*) FROM escalation_events
UNION ALL SELECT 'audit_log', count(*) FROM audit_log;
"@
$countSql | & docker @Compose exec -T postgres psql -U healthbridge -d healthbridge 2>&1 | Out-Host

# ----------------------------------------------------------------- summary
Section 'SUMMARY'
if ($Failed) {
    Write-Host "Boot completed WITH FAILURES - see the sections marked FAIL above." -ForegroundColor Red
} else {
    Write-Host "Stack is up and seeded." -ForegroundColor Green
}
Write-Host ""
Write-Host "  Web (both surfaces) : http://localhost:3000"
Write-Host "  Core API            : http://localhost:8000/docs"
Write-Host "  AI service          : http://localhost:8100/docs  (AI reachable: $aiOk)"
Write-Host ""
Write-Host "  ASHA   : asha1   / asha-demo-pass"
Write-Host "  Doctor : doctor1 / doctor-demo-pass"
Write-Host "  Admin  : admin1  / admin-demo-pass"
Write-Host ""
Write-Host "Full transcript written to: $LogPath"

Stop-Transcript | Out-Null
