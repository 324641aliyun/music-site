#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync the local music source directory with the GitHub music site.

The local music source directory is the single source of truth. Running this
script will:

1. Fetch the latest remote state from GitHub.
2. Copy any new/changed MP3 files from MUSIC_SOURCE into ./audio.
3. Delete audio files that exist locally/remotely but no longer exist in
   MUSIC_SOURCE.
4. Regenerate index.html / feed.xml / songs.json.
5. Commit and push the changes to GitHub.

Usage:
    python sync_music.py                # scan + push
    python sync_music.py --dry-run      # show what would happen, change nothing
    python sync_music.py --no-push      # commit locally, do not push

Environment:
    MUSIC_SOURCE   Path to the folder that contains your MP3 library.
                   Default: C:\\Users\\324641\\Music
    SITE_BASE_URL  Public base URL used in feed.xml.
                   Default: https://324641aliyun.github.io/music-site/
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = REPO_ROOT / "audio"
DEFAULT_MUSIC_SOURCE = r"C:\Users\324641\Music"


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


def get_source_mp3s(source: Path) -> dict[str, Path]:
    """Return {relative_posix_path: absolute_source_path} for every MP3."""
    if not source.is_dir():
        print(f"ERROR: music source directory not found: {source}", file=sys.stderr)
        sys.exit(1)
    return {
        p.relative_to(source).as_posix(): p
        for p in sorted(source.rglob("*.mp3"))
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


def plan_sync(source: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (to_copy_relative, to_delete_relative, remote_audio_files)."""
    desired = get_source_mp3s(source)
    local_audio = get_local_audio_files()
    remote_audio = get_remote_audio_files()

    desired_paths = {f"audio/{rel}" for rel in desired}
    to_copy = {
        f"audio/{rel}"
        for rel, src in desired.items()
        if not (AUDIO_DIR / rel).exists()
        or (AUDIO_DIR / rel).stat().st_size != src.stat().st_size
    }
    to_delete = (local_audio | remote_audio) - desired_paths
    return to_copy, to_delete, remote_audio


def apply_sync(source: Path, to_copy: set[str], to_delete: set[str]) -> None:
    desired = get_source_mp3s(source)

    # Delete stale files first so renamed/removed songs do not stay on GitHub.
    for rel in sorted(to_delete):
        target = REPO_ROOT / rel
        if target.exists():
            target.unlink()
            print(f"DELETE {rel}")
        else:
            print(f"DELETE (remote only) {rel}")

    # Copy new/changed MP3 files.
    for rel in sorted(to_copy):
        src = desired[rel.removeprefix("audio/")]
        dst = REPO_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"COPY   {rel}")


def regenerate(source: Path) -> None:
    env = os.environ.copy()
    env.setdefault("MUSIC_SOURCE", str(source))
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

    source = Path(os.environ.get("MUSIC_SOURCE", DEFAULT_MUSIC_SOURCE))

    print("Fetching remote state...")
    run_git(["fetch", "origin"], check=False)

    to_copy, to_delete, remote_audio = plan_sync(source)

    print(f"Source directory: {source}")
    print(f"Remote audio files: {len(remote_audio)}")
    print(f"Files to copy: {len(to_copy)}")
    print(f"Files to delete: {len(to_delete)}")

    for rel in sorted(to_copy):
        print(f"  + {rel}")
    for rel in sorted(to_delete):
        print(f"  - {rel}")

    if not to_copy and not to_delete:
        print("No music changes.")
        return

    if args.dry_run:
        print("Dry run: no changes were made.")
        return

    apply_sync(source, to_copy, to_delete)
    print("Regenerating site...")
    regenerate(source)
    commit_and_push("Sync music library", push=not args.no_push)
    print("Done.")


if __name__ == "__main__":
    main()
