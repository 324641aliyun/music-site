#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync the local ./audio folder with the GitHub music site.

The ./audio folder is the single source of truth. Running this script will:

1. Fetch the latest remote state from GitHub.
2. Convert every MP4 in ./audio to MP3 (same as 转换.pyw), then delete the MP4.
3. Shorten MP3 names: if a file name contains a complete pair of Chinese book
   title marks 《...》, keep only the text inside the marks.
4. Add the MP3 duration in seconds as a [秒数] prefix.
5. Regenerate index.html / feed.xml / songs.json.
6. Commit and push changes to GitHub, adding new local songs and deleting songs
   that no longer exist locally.

Usage:
    python sync_music.py                # convert + normalize + push
    python sync_music.py --dry-run      # show what would happen, change nothing
    python sync_music.py --no-push      # convert/normalize/commit, do not push

Environment:
    SITE_BASE_URL  Public base URL used in feed.xml.
                   Default: https://324641aliyun.github.io/music-site/
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = REPO_ROOT / "audio"

INVALID_CHARS = r'[<>:"/\\|?*]'
DURATION_PREFIX_RE = re.compile(r'^\[\d+\]\s*')
BOOK_TITLE_RE = re.compile(r'《([^《》]+)》')

# 兼容 moviepy 不同版本的导入方式
try:
    from moviepy import AudioFileClip          # moviepy 2.x
except ImportError:
    from moviepy.editor import AudioFileClip   # moviepy 1.x

try:
    from mutagen.mp3 import MP3
except ImportError:
    MP3 = None


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def remote_main_exists() -> bool:
    result = run_git(["rev-parse", "--verify", "origin/main"], check=False)
    return result.returncode == 0


def get_remote_audio_files() -> set[str]:
    """Return the set of audio/... paths currently tracked on origin/main."""
    if not remote_main_exists():
        return set()
    result = run_git(
        [
            "-c", "core.quotepath=false",
            "ls-tree", "-r", "--name-only", "-z", "origin/main", "--", "audio/",
        ],
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {
        line
        for line in result.stdout.split("\0")
        if line and line.startswith("audio/")
    }


def get_local_audio_files() -> set[str]:
    """Return all files currently under ./audio, as repo-root relative paths."""
    if not AUDIO_DIR.is_dir():
        return set()
    return {
        p.relative_to(REPO_ROOT).as_posix()
        for p in AUDIO_DIR.rglob("*")
        if p.is_file()
    }


def sanitize_filename(name: str) -> str:
    """Replace Windows-illegal filename characters with underscores."""
    return re.sub(INVALID_CHARS, "_", name).strip()


def get_mp3_duration(mp3_path: Path) -> float:
    """Get MP3 duration in seconds; returns 0 when unavailable."""
    if MP3 is None:
        return 0
    try:
        return float(MP3(mp3_path).info.length)
    except Exception:
        return 0


def extract_book_title(name: str) -> str | None:
    """Return text inside the first complete 《...》 pair, or None."""
    match = BOOK_TITLE_RE.search(name)
    if match:
        return match.group(1).strip()
    return None


def planned_mp3_name(mp3_path: Path) -> tuple[str, str]:
    """
    Return (new_filename, display_title) for an MP3.

    The logic is:
    - Remove any existing [秒数] prefix.
    - If a complete 《...》 pair exists, use only its content as the song name.
    - Add a fresh [秒数] prefix based on the real duration.
    """
    duration = get_mp3_duration(mp3_path)
    duration_str = str(int(duration)) if duration > 0 else "0"

    stem = mp3_path.stem
    clean_name = DURATION_PREFIX_RE.sub("", stem).strip()
    title = extract_book_title(clean_name) or clean_name
    title = sanitize_filename(title)

    new_base = f"[{duration_str}] {title}.mp3"
    if len(str(mp3_path.parent / new_base)) > 240:
        new_base = f"[{duration_str}] {title[:100]}.mp3"
    return new_base, title


def convert_mp4_to_mp3(mp4_path: Path) -> Path:
    """Convert one MP4 to MP3 beside it, using moviepy."""
    mp3_path = mp4_path.with_suffix(".mp3")
    audio = AudioFileClip(str(mp4_path))
    try:
        audio.write_audiofile(str(mp3_path), logger=None)
    finally:
        audio.close()
    return mp3_path


def process_audio(dry_run: bool) -> bool:
    """Convert MP4 -> MP3 and normalize MP3 names. Returns whether changes occur."""
    changed = False

    mp4_files = sorted(AUDIO_DIR.rglob("*.mp4"), key=lambda p: p.name.lower())
    for mp4_path in mp4_files:
        rel = mp4_path.relative_to(REPO_ROOT).as_posix()
        target_name = mp4_path.stem + ".mp3"
        if dry_run:
            print(f"WOULD CONVERT {rel} -> {target_name}")
            changed = True
            continue
        print(f"CONVERT {rel} -> {target_name}")
        try:
            convert_mp4_to_mp3(mp4_path)
            mp4_path.unlink()
            changed = True
        except Exception as exc:
            print(f"  convert failed: {exc}", file=sys.stderr)

    mp3_files = sorted(AUDIO_DIR.rglob("*.mp3"), key=lambda p: p.name.lower())
    for mp3_path in mp3_files:
        new_base, _title = planned_mp3_name(mp3_path)
        if new_base == mp3_path.name:
            continue
        rel = mp3_path.relative_to(REPO_ROOT).as_posix()
        if dry_run:
            print(f"WOULD RENAME {rel} -> {new_base}")
            changed = True
            continue

        new_path = mp3_path.with_name(new_base)
        counter = 1
        while new_path.exists():
            name_part, ext_part = os.path.splitext(new_base)
            new_base = f"{name_part}_{counter}{ext_part}"
            new_path = mp3_path.with_name(new_base)
            counter += 1

        print(f"RENAME {rel} -> {new_base}")
        mp3_path.rename(new_path)
        changed = True

    return changed


def regenerate() -> None:
    env = os.environ.copy()
    subprocess.run(
        [sys.executable, "generate.py"],
        cwd=REPO_ROOT,
        check=True,
        env=env,
    )


def commit_and_push(message: str, push: bool) -> None:
    run_git(["add", "-A"])
    status = run_git(["status", "--short"]).stdout.strip()
    if status:
        run_git(["commit", "-m", message])
        print("COMMIT", message)
    if push:
        if remote_main_exists():
            run_git(["push", "origin", "main"])
            print("PUSH   origin main")
        else:
            run_git(["push", "-u", "origin", "main"])
            print("PUSH   origin main (new branch)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show changes only")
    parser.add_argument("--no-push", action="store_true", help="commit but do not push")
    args = parser.parse_args()

    print("Fetching remote state...")
    run_git(["fetch", "origin"], check=False)

    remote_audio = get_remote_audio_files()
    audio_changed = process_audio(dry_run=args.dry_run)
    local_audio = get_local_audio_files()

    to_add = local_audio - remote_audio
    to_delete = remote_audio - local_audio

    print(f"Remote audio files: {len(remote_audio)}")
    print(f"Local audio files: {len(local_audio)}")
    print(f"Files to add: {len(to_add)}")
    print(f"Files to delete: {len(to_delete)}")

    for rel in sorted(to_add):
        print(f"  + {rel}")
    for rel in sorted(to_delete):
        print(f"  - {rel}")

    if args.dry_run:
        if not audio_changed and not to_add and not to_delete:
            print("No music changes.")
        else:
            print("Dry run: no changes were made.")
        return

    git_status = run_git(["status", "--short"]).stdout.strip()
    if not audio_changed and not to_add and not to_delete and not git_status:
        print("No music changes.")
        return

    print("Regenerating site...")
    regenerate()
    commit_and_push("Sync music library", push=not args.no_push)
    print("Done.")


if __name__ == "__main__":
    main()
