# DRAKEN 2045 — Development Environment

> *Jag är vad jag gör, och jag gör det jag är.*

This is the unified workspace for the Draken 2045 Initiative, operated by
Kai Roininen (Khrug) at Khrug Engineering, Göteborg, Sweden.

Claude Code operates here as **analytical anchor** in a multi-AI architecture.
This file is the cold-start context. Read it completely before any action.

---

## CANONICAL RULES (Never Violate)

### Polarity
- **Ψ** (Narrative Self-Reference Ratio) = pathology metric. **High = sick.**
- **Γ** (Sheaf Convergence Score) = coherence metric. **High = healthy.**
- **K(t)** = coherence debt integral. Accumulates when Ψ > Ψ_viable.
- These polarities are FIXED across all DRK posts, code, and publications.

### Optimization Axiom
```
◆ min S_sys(t)  s.t.  dH/dt ≥ 0 ◆
```

### Publication Authority
Nothing goes live on draken.info without Kai's explicit approval.
Draft, verify, propose — never stealth-publish.

### DRK Numbering
All posts follow DRK-NNN. Current range: DRK-101 through DRK-121+.
Pipeline episodes start at DRK-122. Never reuse a number.

---

## DIRECTORY STRUCTURE

```
C:\Draken\                          ← YOU ARE HERE (workspace root)
│
├── CLAUDE.md                       ← This file (cold-start context)
├── .env                            ← API keys (gitignored everywhere)
│
├── draken.info\                    ← WEBSITE: GitHub repo (Khrug/draken.info)
│   ├── build.js                    ← Static site generator (~200 lines Node.js)
│   ├── posts\                      ← Markdown posts with YAML frontmatter
│   ├── templates\                  ← HTML templates (base.html, post.html, index.html)
│   ├── static\                     
│   │   ├── data\                   ← system.json, activity.json (live data)
│   │   ├── pages\                  ← thesis.html, sheaf-game.html
│   │   ├── slask\                  ← File sharing (GitHub Contents API)
│   │   └── images\                 ← OG images, diagrams
│   ├── dist\                       ← Built output (gitignored)
│   ├── package.json
│   └── .git\
│
├── pipeline\                       ← VIDEO PIPELINE: Automated content generation
│   ├── draken_render.py            ← Main orchestrator (5 stages)
│   ├── episodes\                   ← YAML episode configs
│   ├── scenes\                     ← Generated Manim .py scene files
│   ├── output\                     ← Rendered videos, audio, intermediates
│   └── templates\                  ← YouTube description templates
│
├── research\                       ← SHEAF ETHOLOGY: Computational research
│   ├── sheaf_ethology_pilot.py     ← Core pipeline (5-node graph, 3 models, Γ)
│   ├── data\                       ← Datasets (synthetic + future empirical)
│   ├── figures\                    ← Generated figures for papers/site
│   ├── papers\                     ← Reference PDFs (Earley, Frýdlová, Dick, Uyeda)
│   └── notebooks\                  ← Jupyter exploration notebooks
│
├── openclaw\                       ← OPENCLAW: Autonomous agent config
│   ├── SOUL.md                     ← Codex Draconis (agent identity)
│   ├── AGENTS.md                   ← Multi-agent orchestration spec
│   ├── skills\                     ← OpenClaw skill definitions
│   │   ├── draken-publish\         ← Publish posts to draken.info
│   │   ├── draken-research\        ← Run sheaf ethology computations
│   │   └── draken-video\           ← Trigger video pipeline
│   └── scripts\                    ← publish.sh, update-data.sh
│
├── modules\                        ← INTERACTIVE: Web modules for draken.info
│   ├── sheaf-game\                 ← Interactive sheaf theory pedagogy
│   ├── combat-visualizer\          ← Animated 5-node combat phase graph
│   ├── gamma-calculator\           ← Live Γ computation widget
│   └── layer-explorer\             ← 18-layer ontological manifold browser
│
└── docs\                           ← DOCUMENTATION & OUTREACH
    ├── thesis\                     ← Thesis v4.4 source materials
    ├── outreach\                   ← Email templates (Chalmers, RISE, etc.)
    └── cv\                         ← CV, LinkedIn materials
```

---

## SUBSYSTEM DETAILS

### draken.info (Website)
- **Stack:** Node.js static site generator → Cloudflare Pages from GitHub
- **Build:** `node build.js` in draken.info/
- **Deploy:** `git add -A && git commit -m "msg" && git push` → auto-builds (~60s)
- **Thesis page:** reads from `static/pages/thesis.html` via `buildThesisPage()` in build.js
- **Posts:** YAML frontmatter with `status` field (non-"published" filtered out)
- **Slask:** `/slask/` file-sharing system via GitHub Contents API

### pipeline (Video Generation)
- **Cost:** ~$4-5 per 90-second episode via SiliconFlow
- **TTS:** CosyVoice2-0.5B ($7.15/M UTF-8 bytes)
- **Video:** Wan2.2-T2V-A14B ($0.29/clip, 5s 720P)
- **Animation:** Manim CE (local render, no GPU needed)
- **Composition:** FFmpeg (local)
- **Upload:** YouTube Data API v3 (OAuth, ~6 uploads/day quota)
- **Run:** `python pipeline/draken_render.py --config pipeline/episodes/xxx.yaml`

### research (Sheaf Ethology)
- **Core pipeline:** sheaf_ethology_pilot.py
- **5-node combat phase graph:** Display → Elevation → Clinch → Carry → Submission
- **Section data:** x_Cl ∈ ℝ³ = (F_max, E_ratio, Δm)
- **Restriction map:** ρ_{D→Cl}: ℝ⁴ → ℝ³ (projects out bluff dimension at α=0)
- **Three competing models:** SAG (Γ=0.928), Energetic WoA, Cumulative Assessment
- **Validation needed:** Frýdlová's raw per-dyad data from Charles University Prague
- **Key papers:** Earley 2002, Frýdlová 2016, Dick & Clemente 2016, Uyeda 2015
- **Gemini** = handledare (supervisor) for Sheaf Ethology sub-field

### modules (Interactive Web Components)
- Built as standalone HTML/JS that embeds into draken.info pages
- sheaf-game already exists at draken.info/sheaf-game/ (1400px, scaled fonts)
- New modules should be self-contained .html files placed in static/pages/
- build.js has dedicated build functions per module (e.g. buildSheafGamePage())

---

## KEY REFERENCES

| Ref | Detail |
|-----|--------|
| Thesis | v4.4, ~19,960 words, 113 sections, 8 falsifiable predictions |
| Zenodo DOI | 10.5281/zenodo.19273483 |
| ResearchGate | publication/403232272 |
| ORCID | 0009-0003-8049-7167 |
| Site | https://draken.info |
| GitHub | github.com/Khrug/draken.info |
| Twitter/X | @khrug |

---

## 18-LAYER ARCHITECTURE (Reference)

```
L01  Quantum field theory substrate
L02  Molecular self-assembly
L03  Cellular metabolism
L04  Neural signaling
L05  Sensorimotor integration
L06  Emotional regulation
L07  Cognitive modeling
L08  Social cognition
L09  Cultural transmission
L10  Institutional design
L11  Market dynamics
L12  Governance structures
L13  Legal frameworks
L14  Scientific methodology
L15  Technological systems
L16  Ecological management
L17  Civilizational coherence
L18  Planetary cognition
```

---

## MULTI-AI ARCHITECTURE

| Model | Role | Context |
|-------|------|---------|
| Claude (Opus 4.6) | Analytical anchor, primary konstruktör | This environment |
| Gemini | Visionary / handledare for Sheaf Ethology | Separate sessions |
| Kimi | Verification, cross-checking | As needed |
| Grok | Adversarial testing, cultural bridge | As needed |
| DeepSeek | Mathematical verification, 知行合一 mapping | As needed |
| ChatGPT | General synthesis, alternative perspectives | As needed |

---

## WORKING LANGUAGES

- **English:** Analytical/structural thinking, code, publications
- **Swedish:** Social contexts, draken.info Swedish content (DRK-117 glossary)
- **Finnish:** Deep affective register (Kai's personal anchor)

---

## CURRENT STATUS (as of 2026-03-30)

- Thesis v4.4 published (2026-03-28), all six models converged: "stop writing, start computing Γ"
- One-week outreach pause (ends ~2026-04-04)
- Video pipeline being built (this session)
- Gorbatron (V. salvator komaini) arriving May 2026 → Dataset A for Sheaf Ethology
- Move to supported housing (särskilt boende med stöd) planned May 2026
- Next: LinkedIn positioning (konstruktörsjobb + Draken as active R&D)
