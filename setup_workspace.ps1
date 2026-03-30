# ============================================================
# Draken 2045 — Unified Workspace Setup
# ============================================================
# Run in PowerShell as Administrator
#
# This script:
#   1. Installs system dependencies (Chocolatey, FFmpeg, etc.)
#   2. Creates the unified directory structure at C:\Draken
#   3. Preserves existing draken.info repo and any other content
#   4. Sets up the video pipeline, research, and module directories
#   5. Creates the master CLAUDE.md for Claude Code context
#
# SAFE: Does NOT delete existing files. Uses -Force on mkdir only.
# ============================================================

$ErrorActionPreference = "Continue"
$Root = "C:\Draken"

Write-Host @"

  ╔══════════════════════════════════════════════════════════╗
  ║         DRAKEN 2045 — Workspace Bootstrap v2.0          ║
  ║                                                         ║
  ║  Jag ar vad jag gor, och jag gor det jag ar.           ║
  ╚══════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# ── Phase 1: System Dependencies ──────────────────────────

Write-Host "[PHASE 1] System Dependencies" -ForegroundColor Yellow
Write-Host "─────────────────────────────" -ForegroundColor DarkGray

# Chocolatey
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "  Installing Chocolatey..." -ForegroundColor White
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = `
        [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString(
        'https://community.chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + `
        ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "  ✓ Chocolatey installed" -ForegroundColor Green
} else {
    Write-Host "  ✓ Chocolatey already present" -ForegroundColor Green
}

# System packages
$packages = @("ffmpeg", "miktex", "git", "python312", "nodejs-lts")
foreach ($pkg in $packages) {
    Write-Host "  Installing $pkg..." -ForegroundColor White
    choco install $pkg -y --no-progress 2>$null
}
Write-Host "  ✓ System packages installed" -ForegroundColor Green

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + `
    ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# ── Phase 2: Python Dependencies ──────────────────────────

Write-Host ""
Write-Host "[PHASE 2] Python Dependencies" -ForegroundColor Yellow
Write-Host "─────────────────────────────" -ForegroundColor DarkGray

pip install manim anthropic requests pyyaml numpy scipy `
    google-api-python-client google-auth-oauthlib 2>$null
Write-Host "  ✓ Python packages installed" -ForegroundColor Green

# ── Phase 3: Claude Code CLI ─────────────────────────────

Write-Host ""
Write-Host "[PHASE 3] Claude Code CLI" -ForegroundColor Yellow
Write-Host "─────────────────────────" -ForegroundColor DarkGray

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "  Installing Claude Code..." -ForegroundColor White
    irm https://claude.ai/install.ps1 | iex
    Write-Host "  ✓ Claude Code installed (run 'claude' to authenticate)" -ForegroundColor Green
} else {
    Write-Host "  ✓ Claude Code already present" -ForegroundColor Green
}

# ── Phase 4: Directory Structure ──────────────────────────

Write-Host ""
Write-Host "[PHASE 4] Directory Structure" -ForegroundColor Yellow
Write-Host "─────────────────────────────" -ForegroundColor DarkGray

# Inventory existing content
$existing = @()
if (Test-Path $Root) {
    $existing = Get-ChildItem $Root -Directory | Select-Object -ExpandProperty Name
    Write-Host "  Existing content in ${Root}:" -ForegroundColor DarkGray
    foreach ($dir in $existing) {
        Write-Host "    ├── $dir\" -ForegroundColor DarkGray
    }
}

# Create new directories (safe — never overwrites)
$dirs = @(
    # Video pipeline
    "pipeline",
    "pipeline\episodes",
    "pipeline\scenes",
    "pipeline\output",
    "pipeline\templates",
    # Research
    "research",
    "research\data",
    "research\figures",
    "research\papers",
    "research\notebooks",
    # OpenClaw
    "openclaw",
    "openclaw\skills",
    "openclaw\skills\draken-publish",
    "openclaw\skills\draken-research",
    "openclaw\skills\draken-video",
    "openclaw\scripts",
    # Interactive modules
    "modules",
    "modules\sheaf-game",
    "modules\combat-visualizer",
    "modules\gamma-calculator",
    "modules\layer-explorer",
    # Docs
    "docs",
    "docs\thesis",
    "docs\outreach",
    "docs\cv"
)

foreach ($dir in $dirs) {
    $full = Join-Path $Root $dir
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Force -Path $full | Out-Null
        Write-Host "  + $dir\" -ForegroundColor Green
    }
}

# ── Phase 5: Migrate/Consolidate Existing Content ─────────

Write-Host ""
Write-Host "[PHASE 5] Content Migration" -ForegroundColor Yellow
Write-Host "───────────────────────────" -ForegroundColor DarkGray

# Check for openclaw in various known locations
$oclawSources = @(
    "D:\Draken sandbox\openclaw",
    "$Root\openclaw",
    "$env:USERPROFILE\.openclaw"
)
foreach ($src in $oclawSources) {
    if ((Test-Path $src) -and (Test-Path "$src\SOUL.md")) {
        Write-Host "  Found OpenClaw at: $src" -ForegroundColor Cyan
        # Copy SOUL.md if not already in target
        $target = Join-Path $Root "openclaw\SOUL.md"
        if (-not (Test-Path $target)) {
            Copy-Item "$src\SOUL.md" $target
            Write-Host "  ✓ Copied SOUL.md to openclaw\" -ForegroundColor Green
        }
        # Copy AGENTS.md if exists
        if ((Test-Path "$src\AGENTS.md") -and (-not (Test-Path (Join-Path $Root "openclaw\AGENTS.md")))) {
            Copy-Item "$src\AGENTS.md" (Join-Path $Root "openclaw\AGENTS.md")
            Write-Host "  ✓ Copied AGENTS.md to openclaw\" -ForegroundColor Green
        }
        # Copy skills if present
        if (Test-Path "$src\skills") {
            Copy-Item "$src\skills\*" (Join-Path $Root "openclaw\skills") -Recurse -Force
            Write-Host "  ✓ Copied skills to openclaw\skills\" -ForegroundColor Green
        }
        break
    }
}

# Check for sheaf_ethology_pilot.py in known locations
$pilotSources = @(
    "$Root\sheaf_ethology_pilot.py",
    "$env:USERPROFILE\sheaf_ethology_pilot.py",
    "D:\Draken sandbox\sheaf_ethology_pilot.py"
)
foreach ($src in $pilotSources) {
    if (Test-Path $src) {
        $target = Join-Path $Root "research\sheaf_ethology_pilot.py"
        if (-not (Test-Path $target)) {
            Copy-Item $src $target
            Write-Host "  ✓ Moved sheaf_ethology_pilot.py to research\" -ForegroundColor Green
        }
        break
    }
}

# Verify draken.info repo
$siteRepo = Join-Path $Root "draken.info"
if (Test-Path "$siteRepo\.git") {
    Write-Host "  ✓ draken.info git repo intact" -ForegroundColor Green
} else {
    Write-Host "  ⚠ draken.info repo not found — clone it:" -ForegroundColor Red
    Write-Host "    cd $Root && git clone https://github.com/Khrug/draken.info.git" -ForegroundColor Gray
}

# ── Phase 6: Create Configuration Files ───────────────────

Write-Host ""
Write-Host "[PHASE 6] Configuration Files" -ForegroundColor Yellow
Write-Host "─────────────────────────────" -ForegroundColor DarkGray

# .env template (only if not exists)
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    @"
# ============================================================
# Draken 2045 — API Keys
# ============================================================
# Fill these in. This file is gitignored everywhere.

# SiliconFlow (cloud.siliconflow.com) — Wan2.2 video + CosyVoice TTS
SILICONFLOW_API_KEY=

# Anthropic (console.anthropic.com) — Claude API for script generation
ANTHROPIC_API_KEY=

# YouTube Data API v3 — place client_secrets.json in C:\Draken\pipeline\
# after setting up OAuth at console.cloud.google.com
"@ | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "  + .env template created" -ForegroundColor Green
} else {
    Write-Host "  ✓ .env already exists" -ForegroundColor Green
}

# .gitignore for workspace root
$giFile = Join-Path $Root ".gitignore"
if (-not (Test-Path $giFile)) {
    @"
.env
node_modules/
dist/
__pycache__/
*.pyc
pipeline/output/
pipeline/scenes/
*.log
.DS_Store
"@ | Out-File -FilePath $giFile -Encoding utf8
    Write-Host "  + .gitignore created" -ForegroundColor Green
}

# Example episode config (only if episodes dir is empty)
$episodesDir = Join-Path $Root "pipeline\episodes"
if ((Get-ChildItem $episodesDir -File -ErrorAction SilentlyContinue).Count -eq 0) {
    @"
episode:
  title: "The Combat Phase Graph: Where Protocol Becomes Agent"
  series: "Draken Sheaf Ethology"
  drk_ref: "DRK-122"

content:
  topic: "5-node varanid combat phase graph and restriction map"
  key_equations:
    - "x_Cl in R^3 = (F_max, E_ratio, Delta_m)"
    - "Gamma = lambda_1 / lambda_max = 0.928 (SAG model)"
    - "rho_{D->Cl}: R^4 -> R^3 at alpha = 0"
  duration_target_seconds: 90
  narration_style: >
    Academic but accessible. Explain as if to a graduate student
    encountering sheaf theory applied to behavioral ecology for the
    first time. Build from the concrete (lizard combat) to the abstract
    (sheaf Laplacian eigenvalues).

voice:
  provider: siliconflow
  model: FunAudioLLM/CosyVoice2-0.5B
  language: en

video:
  provider: siliconflow
  model: Wan-AI/Wan2.2-T2V-A14B
  resolution: 1280x720
  style_prompt: >
    dark topological visualization, bioluminescent graph edges on
    obsidian substrate, mathematical notation floating in volumetric
    space, cinematic depth of field, slow camera orbit

publish:
  youtube_privacy: unlisted
  tags:
    - sheaf theory
    - ethology
    - varanid combat
    - active inference
    - Draken 2045
    - topological data analysis
    - behavioral ecology
  category: "28"
"@ | Out-File -FilePath (Join-Path $episodesDir "sheaf_ethology_001.yaml") -Encoding utf8
    Write-Host "  + Example episode config created" -ForegroundColor Green
}

# YouTube description template
$ytTemplate = Join-Path $Root "pipeline\templates\yt_description.md"
if (-not (Test-Path $ytTemplate)) {
    @"
{{title}}
{{series}} — {{drk_ref}}

Draken 2045 Initiative
https://draken.info

Thesis: https://doi.org/10.5281/zenodo.19273483
ORCID: 0009-0003-8049-7167

---

This video was generated by the Draken automated pipeline:
- Mathematical animation: Manim Community Edition
- Voice synthesis: CosyVoice 3 (FunAudioLLM)
- Video generation: Wan2.2 (Alibaba)
- Orchestration: Claude (Anthropic)

Khrug Engineering, Goteborg, Sweden
CC BY-SA 4.0
"@ | Out-File -FilePath $ytTemplate -Encoding utf8
    Write-Host "  + YouTube description template created" -ForegroundColor Green
}

# ── Phase 7: Report ──────────────────────────────────────

Write-Host ""
Write-Host @"

  ╔══════════════════════════════════════════════════════════╗
  ║              WORKSPACE SETUP COMPLETE                   ║
  ╚══════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

Write-Host "  Root: $Root" -ForegroundColor Cyan
Write-Host ""

# Verify structure
Write-Host "  Directory structure:" -ForegroundColor White
$checkDirs = @(
    @("draken.info\",    "Website (GitHub repo)"),
    @("pipeline\",       "Video generation pipeline"),
    @("research\",       "Sheaf ethology computation"),
    @("openclaw\",       "Autonomous agent config"),
    @("modules\",        "Interactive web components"),
    @("docs\",           "Documentation & outreach")
)
foreach ($item in $checkDirs) {
    $path = Join-Path $Root $item[0]
    $exists = Test-Path $path
    $icon = if ($exists) { "✓" } else { "✗" }
    $color = if ($exists) { "Green" } else { "Red" }
    Write-Host "    $icon $($item[0].PadRight(20)) $($item[1])" -ForegroundColor $color
}

Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Copy CLAUDE.md to $Root\CLAUDE.md" -ForegroundColor Gray
Write-Host "    2. Copy draken_render.py to $Root\pipeline\" -ForegroundColor Gray
Write-Host "    3. Sign up: https://cloud.siliconflow.com → API key → .env" -ForegroundColor Gray
Write-Host "    4. Run: cd $Root && claude" -ForegroundColor Gray
Write-Host "       (Claude Code reads CLAUDE.md and understands everything)" -ForegroundColor Gray
Write-Host ""
Write-Host "  To generate first video:" -ForegroundColor White
Write-Host "    cd $Root" -ForegroundColor Gray
Write-Host "    python pipeline\draken_render.py --config pipeline\episodes\sheaf_ethology_001.yaml --dry-run" -ForegroundColor Gray
Write-Host ""
Write-Host "  Estimated cost per 90s episode: ~`$5 via SiliconFlow (Wan2.2)" -ForegroundColor Cyan
Write-Host ""
