#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build HLS streams for playlists stored in ./playlists.json.

- Each unique MP3 is transcoded into AAC .ts segments once and cached under
  ./hls/_segments/<hash>/.
- Each playlist gets ./hls/<playlist-id>/index.m3u8.
- The playlist repeats the segment references N times (default 100), with
  #EXT-X-DISCONTINUITY between repeats, so the URL plays the playlist over and
  over for a very long time without storing duplicate segment files.

Usage:
    python hls_builder.py
    python hls_builder.py --force
    python hls_builder.py --playlist "我的歌单"
    python hls_builder.py --loop-count 50 --segment-time 30
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = REPO_ROOT / "audio"
HLS_DIR = REPO_ROOT / "hls"
SEGMENTS_DIR = HLS_DIR / "_segments"
PLAYLISTS_PATH = REPO_ROOT / "playlists.json"
BITRATE = "128k"
SAMPLE_RATE = "44100"
CHANNELS = "2"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def load_data() -> dict:
    import playlist_manager
    return playlist_manager.load_data()


def get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
    print(
        "ERROR: 找不到 ffmpeg。请安装 ffmpeg，或确保 Python 包 imageio-ffmpeg 可用。",
        file=sys.stderr,
    )
    sys.exit(1)


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if result.stderr.strip():
        print(result.stderr.strip()[-2000:])


def parse_hls_playlist(playlist_path: Path) -> tuple[list[tuple[str, str]], int]:
    """Return [(EXTINF line, segment URI), ...] and target duration."""
    lines = [
        line.strip()
        for line in playlist_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries: list[tuple[str, str]] = []
    target_duration = 60
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#EXT-X-TARGETDURATION:"):
            try:
                target_duration = int(line.split(":", 1)[1])
            except ValueError:
                pass
        if line.startswith("#EXTINF"):
            next_index = index + 1
            while next_index < len(lines) and lines[next_index].startswith("#"):
                next_index += 1
            if next_index < len(lines):
                entries.append((line, lines[next_index]))
                index = next_index
        index += 1
    return entries, target_duration


def song_cache_key(song: str, segment_time: int) -> str:
    path = AUDIO_DIR / song
    stat = path.stat()
    raw = f"{song}|{stat.st_size}|{stat.st_mtime_ns}|{segment_time}|{BITRATE}|{SAMPLE_RATE}|{CHANNELS}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_song_segments(song: str, segment_time: int, force: bool = False) -> tuple[str, list[tuple[str, str]], int] | None:
    """Return (cache_key, entries, target_duration) for one MP3."""
    source = AUDIO_DIR / song
    if not source.is_file():
        print(f"  WARN: missing audio, skipped: {song}")
        return None

    key = song_cache_key(song, segment_time)
    cache_dir = SEGMENTS_DIR / key
    playlist_path = cache_dir / "index.m3u8"
    hash_path = cache_dir / ".source_hash"
    source_hash = song_cache_key(song, segment_time)

    if (
        not force
        and playlist_path.is_file()
        and hash_path.is_file()
        and hash_path.read_text(encoding="utf-8").strip() == source_hash
    ):
        entries, target_duration = parse_hls_playlist(playlist_path)
        return key, entries, target_duration

    tmp_dir = SEGMENTS_DIR / f".{key}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f"  SEGMENT {song} -> {key}")
    run_ffmpeg(
        [
            get_ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(source),
            "-vn",
            "-c:a", "aac",
            "-b:a", BITRATE,
            "-ar", SAMPLE_RATE,
            "-ac", CHANNELS,
            "-f", "hls",
            "-hls_time", str(segment_time),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(tmp_dir / "seg_%04d.ts"),
            str(tmp_dir / "index.m3u8"),
        ]
    )

    (tmp_dir / ".source_hash").write_text(source_hash + "\n", encoding="utf-8")

    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    os.rename(tmp_dir, cache_dir)

    entries, target_duration = parse_hls_playlist(playlist_path)
    return key, entries, target_duration


def remove_dir(path: Path) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    if HLS_DIR.resolve() not in resolved.parents and resolved != HLS_DIR.resolve():
        print(f"REFUSE to remove outside hls dir: {resolved}", file=sys.stderr)
        return
    shutil.rmtree(resolved, ignore_errors=True)


def find_playlist(data: dict, ident: str) -> dict | None:
    lowered = ident.casefold()
    exact = [
        p for p in data["playlists"]
        if p.get("id", "").casefold() == lowered or p.get("name", "").casefold() == lowered
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        p for p in data["playlists"]
        if lowered in p.get("id", "").casefold() or lowered in p.get("name", "").casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"“{ident}”匹配到多个歌单，请用 ID 或完整歌单名：")
        for playlist in partial:
            print(f"  - {playlist['id']}  {playlist['name']}")
    else:
        print(f"ERROR: 找不到歌单：{ident}", file=sys.stderr)
    return None


def build_playlist_hls(
    playlist: dict,
    loop_count: int,
    segment_time: int,
    force: bool = False,
) -> tuple[Path | None, set[str]]:
    """Build one playlist. Returns (index path or None, referenced cache keys)."""
    playlist_id = playlist["id"]
    out_dir = HLS_DIR / playlist_id
    index_path = out_dir / "index.m3u8"
    referenced_keys: set[str] = set()

    blocks: list[tuple[str, list[tuple[str, str]], int]] = []
    valid_songs: list[str] = []
    for song in playlist.get("songs", []):
        result = build_song_segments(song, segment_time, force=force)
        if result is None:
            continue
        key, entries, target_duration = result
        blocks.append((key, entries, target_duration))
        referenced_keys.add(key)
        valid_songs.append(song)

    if not blocks:
        remove_dir(out_dir)
        print(f"SKIP   {playlist['name']}: 没有有效歌曲")
        return None, referenced_keys

    source_hash = hashlib.sha256(
        json.dumps(
            {
                "id": playlist_id,
                "name": playlist.get("name", ""),
                "songs": valid_songs,
                "loop_count": loop_count,
                "segment_time": segment_time,
                "segment_keys": [key for key, _entries, _target in blocks],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    out_dir.mkdir(parents=True, exist_ok=True)
    hash_path = out_dir / ".source_hash"
    if (
        not force
        and index_path.is_file()
        and hash_path.is_file()
        and hash_path.read_text(encoding="utf-8").strip() == source_hash
    ):
        print(f"SKIP   {playlist['name']} (unchanged)")
        return index_path, referenced_keys

    max_target_duration = max(target for _key, _entries, target in blocks)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{max_target_duration}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]

    for loop_index in range(loop_count):
        if loop_index > 0:
            lines.append("#EXT-X-DISCONTINUITY")
        for block_index, (key, entries, _target_duration) in enumerate(blocks):
            if block_index > 0:
                lines.append("#EXT-X-DISCONTINUITY")
            for extinf, uri in entries:
                lines.append(extinf)
                suffix = f"?l={loop_index}" if loop_index > 0 else ""
                lines.append(f"../_segments/{key}/{uri}{suffix}")
    lines.append("#EXT-X-ENDLIST")

    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    hash_path.write_text(source_hash + "\n", encoding="utf-8")
    print(f"BUILD  {playlist['name']} -> hls/{playlist_id}/index.m3u8  ({loop_count} loops)")
    return index_path, referenced_keys


def cleanup(referenced_keys: set[str], keep_playlist_ids: set[str]) -> None:
    if SEGMENTS_DIR.is_dir():
        for child in SEGMENTS_DIR.iterdir():
            if child.is_dir() and child.name not in referenced_keys:
                remove_dir(child)

    if HLS_DIR.is_dir():
        for child in HLS_DIR.iterdir():
            if (
                child.is_dir()
                and child.name != "_segments"
                and not child.name.startswith(".")
                and child.name not in keep_playlist_ids
            ):
                remove_dir(child)


def build_all(
    force: bool = False,
    only_playlist: str | None = None,
    loop_count: int | None = None,
    segment_time: int | None = None,
) -> None:
    data = load_data()
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    effective_loop_count = int(loop_count if loop_count is not None else data.get("loop_count", 100))
    effective_segment_time = int(segment_time if segment_time is not None else data.get("segment_time", 60))
    if effective_loop_count < 1:
        print("ERROR: loop_count 必须大于 0", file=sys.stderr)
        sys.exit(1)
    if effective_segment_time < 1:
        print("ERROR: segment_time 必须大于 0", file=sys.stderr)
        sys.exit(1)

    playlists = data.get("playlists", [])
    if only_playlist:
        playlist = find_playlist(data, only_playlist)
        if not playlist:
            sys.exit(1)
        playlists = [playlist]

    enabled_playlists = [p for p in playlists if p.get("enabled", True)]
    all_enabled_ids = {
        p["id"] for p in data.get("playlists", []) if p.get("enabled", True)
    }

    if not enabled_playlists:
        print("没有启用的歌单。")
        if not only_playlist:
            cleanup(set(), all_enabled_ids)
        return

    referenced_keys: set[str] = set()
    for playlist in enabled_playlists:
        print(f"处理歌单：{playlist['name']} ({playlist['id']})")
        _index, keys = build_playlist_hls(
            playlist,
            loop_count=effective_loop_count,
            segment_time=effective_segment_time,
            force=force,
        )
        referenced_keys.update(keys)

    # When only one playlist is requested, do not garbage-collect shared
    # segment caches that may still be referenced by other playlists.
    if not only_playlist:
        cleanup(referenced_keys, all_enabled_ids)
    print(f"完成：{len(enabled_playlists)} 个歌单，loop_count={effective_loop_count}，segment_time={effective_segment_time}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="强制重新生成所有分片")
    parser.add_argument("--playlist", help="只处理指定歌单 (ID 或名称)")
    parser.add_argument("--loop-count", type=int, default=None, help="覆盖循环引用次数")
    parser.add_argument("--segment-time", type=int, default=None, help="覆盖 TS 分片秒数")
    args = parser.parse_args()
    build_all(
        force=args.force,
        only_playlist=args.playlist,
        loop_count=args.loop_count,
        segment_time=args.segment_time,
    )


if __name__ == "__main__":
    main()
