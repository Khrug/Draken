#!/usr/bin/env python3
"""
Draken 2045 — Automated Generative Video Pipeline
===================================================
Generates mathematical animation videos from YAML episode configs.

Pipeline stages:
  1. Script Generation  — Anthropic Claude API → narration + Manim code
  2. Voice Synthesis     — SiliconFlow CosyVoice2 API → narration audio
  3. Animation Render    — Manim CE (local) → mathematical animation video
  4. Cinematic B-Roll    — SiliconFlow Wan2.2 API → style-transferred segments
  5. Composition         — FFmpeg (local) → final assembled video
  6. Upload (optional)   — YouTube Data API v3 → publish

Usage:
  python draken_render.py --config episodes/sheaf_ethology_001.yaml
  python draken_render.py --config episodes/sheaf_ethology_001.yaml --skip-upload
  python draken_render.py --config episodes/sheaf_ethology_001.yaml --dry-run

Requirements:
  pip install anthropic requests pyyaml manim
  API keys in .env or environment variables:
    SILICONFLOW_API_KEY, ANTHROPIC_API_KEY
"""

import os
import sys
import json
import time
import yaml
import argparse
import subprocess
import tempfile
import logging
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration & Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("draken")

SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "output"
SCENES_DIR = SCRIPT_DIR / "scenes"
OUTPUT_DIR.mkdir(exist_ok=True)
SCENES_DIR.mkdir(exist_ok=True)


def load_env():
    """Load .env file if present (simple key=value parser)."""
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def require_key(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error(f"Missing API key: {name}. Set it in .env or as an environment variable.")
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Stage 1: Script Generation (Anthropic Claude API)
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM_PROMPT = """\
You are the Draken 2045 scriptwriter. You produce two outputs as JSON:

1. "narration": A narration script for a mathematical animation video.
   - Written for text-to-speech (no markdown, no special characters).
   - Academic but accessible tone.
   - Duration should match the target when read at ~150 words/minute.

2. "manim_code": A complete Manim Community Edition scene file (Python).
   - The scene class must be named "DrakenScene".
   - Use standard Manim objects: Graph, MathTex, Text, Arrow, etc.
   - Animate the mathematical concepts described in the topic.
   - Include self.wait() calls that roughly sync with narration pacing.
   - Resolution: 1920x1080 (default -qh).

Respond ONLY with valid JSON, no markdown fences, no preamble:
{"narration": "...", "manim_code": "..."}
"""


def generate_script(config: dict, api_key: str) -> dict:
    """Call Claude API to generate narration + Manim code."""
    import anthropic

    log.info("Stage 1: Generating script via Claude API...")

    content = config["content"]
    prompt = (
        f"Create a {content['duration_target_seconds']}-second video about:\n"
        f"Topic: {content['topic']}\n"
        f"Key equations: {', '.join(content.get('key_equations', []))}\n"
        f"Narration style: {content.get('narration_style', 'Academic but accessible')}\n"
        f"Series: {config['episode'].get('series', 'Draken 2045')}\n"
        f"Episode: {config['episode'].get('title', 'Untitled')}\n"
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SCRIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    result = json.loads(text)
    log.info(f"  Narration: {len(result['narration'])} chars")
    log.info(f"  Manim code: {len(result['manim_code'])} chars")
    return result


# ---------------------------------------------------------------------------
# Stage 2: Voice Synthesis (SiliconFlow CosyVoice2 API)
# ---------------------------------------------------------------------------

def synthesize_voice(narration: str, config: dict, sf_key: str) -> Path:
    """Call SiliconFlow CosyVoice2 API to generate narration audio."""
    import requests

    log.info("Stage 2: Synthesizing narration via CosyVoice2...")

    voice_cfg = config.get("voice", {})
    model = voice_cfg.get("model", "FunAudioLLM/CosyVoice2-0.5B")

    # SiliconFlow TTS endpoint
    url = "https://api.siliconflow.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {sf_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": narration,
        "voice": voice_cfg.get("voice_id", ""),  # default voice if empty
        "response_format": "mp3",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        log.error(f"  CosyVoice API error {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)

    audio_path = OUTPUT_DIR / "narration.mp3"
    audio_path.write_bytes(resp.content)
    log.info(f"  Audio saved: {audio_path} ({len(resp.content)} bytes)")
    return audio_path


# ---------------------------------------------------------------------------
# Stage 3: Manim Animation Render (local)
# ---------------------------------------------------------------------------

def render_manim(manim_code: str) -> Path:
    """Write Manim scene to file and render locally."""
    log.info("Stage 3: Rendering Manim animation...")

    scene_file = SCENES_DIR / "draken_scene.py"
    scene_file.write_text(manim_code, encoding="utf-8")
    log.info(f"  Scene written: {scene_file}")

    # Render at high quality
    cmd = [
        "manim", "-qh",
        "--media_dir", str(OUTPUT_DIR / "manim_media"),
        str(scene_file),
        "DrakenScene",
    ]
    log.info(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"  Manim render failed:\n{result.stderr[-2000:]}")
        sys.exit(1)

    # Find the rendered video
    media_dir = OUTPUT_DIR / "manim_media" / "videos" / "draken_scene" / "1080p60"
    videos = list(media_dir.glob("*.mp4"))
    if not videos:
        log.error(f"  No video found in {media_dir}")
        sys.exit(1)

    video_path = videos[0]
    log.info(f"  Animation rendered: {video_path}")
    return video_path


# ---------------------------------------------------------------------------
# Stage 4: Cinematic B-Roll (SiliconFlow Wan2.2 API)
# ---------------------------------------------------------------------------

def generate_broll(config: dict, sf_key: str, num_clips: int = 3) -> list[Path]:
    """Generate cinematic B-roll clips via Wan2.2 text-to-video."""
    import requests

    log.info(f"Stage 4: Generating {num_clips} B-roll clips via Wan2.2...")

    video_cfg = config.get("video", {})
    model = video_cfg.get("model", "Wan-AI/Wan2.2-T2V-A14B")
    style = video_cfg.get("style_prompt", "abstract mathematical topology visualization")
    resolution = video_cfg.get("resolution", "1280x720")

    url = "https://api.siliconflow.com/v1/video/submit"
    headers = {
        "Authorization": f"Bearer {sf_key}",
        "Content-Type": "application/json",
    }

    clip_paths = []
    for i in range(num_clips):
        # Vary the prompt slightly for each clip
        prompts = [
            f"{style}, slow camera pan, cinematic lighting",
            f"{style}, zooming into node structure, particle effects",
            f"{style}, morphing between graph states, ethereal glow",
        ]
        prompt = prompts[i % len(prompts)]

        payload = {
            "model": model,
            "prompt": prompt,
            "image_size": resolution,
        }

        log.info(f"  Submitting clip {i+1}/{num_clips}: {prompt[:60]}...")
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            log.warning(f"  Clip {i+1} submission failed: {resp.text[:300]}")
            continue

        task = resp.json()
        task_id = task.get("requestId") or task.get("id")
        if not task_id:
            log.warning(f"  No task ID returned for clip {i+1}")
            continue

        # Poll for completion
        status_url = f"https://api.siliconflow.com/v1/video/status/{task_id}"
        for attempt in range(60):  # up to 5 minutes
            time.sleep(5)
            status_resp = requests.get(status_url, headers=headers, timeout=30)
            status_data = status_resp.json()
            state = status_data.get("status", "")
            if state == "Succeed":
                video_url = status_data.get("results", {}).get("videos", [{}])[0].get("url", "")
                if video_url:
                    video_resp = requests.get(video_url, timeout=120)
                    clip_path = OUTPUT_DIR / f"broll_{i:02d}.mp4"
                    clip_path.write_bytes(video_resp.content)
                    clip_paths.append(clip_path)
                    log.info(f"  Clip {i+1} saved: {clip_path}")
                break
            elif state == "Failed":
                log.warning(f"  Clip {i+1} generation failed")
                break
        else:
            log.warning(f"  Clip {i+1} timed out")

    return clip_paths


# ---------------------------------------------------------------------------
# Stage 5: FFmpeg Composition
# ---------------------------------------------------------------------------

def compose_video(
    manim_video: Path,
    narration_audio: Path,
    broll_clips: list[Path],
    config: dict,
) -> Path:
    """Assemble final video: Manim animation + narration audio + B-roll intro/outro."""
    log.info("Stage 5: Composing final video with FFmpeg...")

    episode = config["episode"]
    final_path = OUTPUT_DIR / f"{episode.get('drk_ref', 'DRK-000')}_{datetime.now():%Y%m%d}.mp4"

    # Strategy: B-roll intro (clip 0) → Manim with narration → B-roll outro (last clip)
    # For MVP: just overlay narration audio on Manim video
    # B-roll clips are appended as intro/outro

    parts_file = OUTPUT_DIR / "parts.txt"
    parts = []

    # Add B-roll intro if available
    if broll_clips:
        parts.append(f"file '{broll_clips[0]}'")

    # Manim with audio overlay
    manim_with_audio = OUTPUT_DIR / "manim_narrated.mp4"
    cmd_audio = [
        "ffmpeg", "-y",
        "-i", str(manim_video),
        "-i", str(narration_audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(manim_with_audio),
    ]
    subprocess.run(cmd_audio, capture_output=True)
    parts.append(f"file '{manim_with_audio}'")

    # Add B-roll outro if available
    if len(broll_clips) > 1:
        parts.append(f"file '{broll_clips[-1]}'")

    parts_file.write_text("\n".join(parts), encoding="utf-8")

    # Concatenate all parts
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(parts_file),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(final_path),
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"  Concat failed, falling back to narrated Manim only")
        # Fallback: just use the narrated Manim video
        import shutil
        shutil.copy2(manim_with_audio, final_path)

    log.info(f"  Final video: {final_path}")
    return final_path


# ---------------------------------------------------------------------------
# Stage 6: YouTube Upload (optional)
# ---------------------------------------------------------------------------

def upload_youtube(video_path: Path, config: dict):
    """Upload to YouTube via Data API v3 (requires OAuth setup)."""
    log.info("Stage 6: Uploading to YouTube...")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        log.warning("  Google API libraries not installed. Skipping upload.")
        return

    secrets_file = SCRIPT_DIR / "client_secrets.json"
    if not secrets_file.exists():
        log.warning(f"  {secrets_file} not found. Skipping upload.")
        log.info("  Set up OAuth at https://console.cloud.google.com")
        return

    episode = config["episode"]
    publish = config.get("publish", {})

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes)
    credentials = flow.run_local_server(port=0)
    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": episode.get("title", "Draken 2045 Episode"),
            "description": f"Draken 2045 Initiative — {episode.get('series', '')}\n"
                           f"Ref: {episode.get('drk_ref', '')}\n\n"
                           f"https://draken.info\n\n"
                           f"Thesis: https://doi.org/10.5281/zenodo.19273483",
            "tags": publish.get("tags", ["Draken 2045"]),
            "categoryId": publish.get("category", "28"),
        },
        "status": {
            "privacyStatus": publish.get("youtube_privacy", "unlisted"),
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"  Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    log.info(f"  Uploaded! https://youtube.com/watch?v={video_id}")
    return video_id


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Draken 2045 Generative Pipeline")
    parser.add_argument("--config", required=True, help="Path to episode YAML config")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--skip-broll", action="store_true", help="Skip B-roll generation (saves cost)")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit")
    args = parser.parse_args()

    load_env()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = SCRIPT_DIR / config_path

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if args.dry_run:
        print(yaml.dump(config, default_flow_style=False))
        print(f"\nEstimated cost:")
        print(f"  TTS:   ~$0.01")
        print(f"  Video: ~$0.87 (3 B-roll clips × $0.29)")
        print(f"  Total: ~$0.88 (without B-roll: ~$0.01)")
        return

    # Load API keys
    anthropic_key = require_key("ANTHROPIC_API_KEY")
    sf_key = require_key("SILICONFLOW_API_KEY")

    log.info(f"Episode: {config['episode'].get('title', '?')}")
    log.info(f"DRK ref: {config['episode'].get('drk_ref', '?')}")
    log.info("=" * 60)

    # Stage 1: Generate script
    script = generate_script(config, anthropic_key)

    # Stage 2: Synthesize narration
    audio_path = synthesize_voice(script["narration"], config, sf_key)

    # Stage 3: Render Manim animation
    manim_path = render_manim(script["manim_code"])

    # Stage 4: Generate B-roll (optional)
    broll_clips = []
    if not args.skip_broll:
        broll_clips = generate_broll(config, sf_key, num_clips=3)

    # Stage 5: Compose final video
    final_video = compose_video(manim_path, audio_path, broll_clips, config)

    # Stage 6: Upload to YouTube (optional)
    if not args.skip_upload:
        upload_youtube(final_video, config)

    log.info("=" * 60)
    log.info("Pipeline complete.")
    log.info(f"Output: {final_video}")


if __name__ == "__main__":
    main()
