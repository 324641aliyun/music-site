#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local playlist manager for the music site.

Playlists are stored in ./playlists.json and can later be converted into HLS
streams by hls_builder.py.

Examples:
    python playlist_manager.py list
    python playlist_manager.py create "我的歌单"
    python playlist_manager.py add "我的歌单" "[166] 朝你大胯捏一把.mp3"
    python playlist_manager.py show "我的歌单"
    python playlist_manager.py remove "我的歌单" "朝你大胯捏一把"
    python playlist_manager.py disable "我的歌单"
    python playlist_manager.py enable "我的歌单"
    python playlist_manager.py delete "我的歌单"
    python playlist_manager.py config --loop-count 50 --segment-time 30
"""

import argparse
import copy
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = REPO_ROOT / "audio"
PLAYLISTS_PATH = REPO_ROOT / "playlists.json"

MAX_PLAYLISTS = 10
DEFAULT_LOOP_COUNT = 100
DEFAULT_SEGMENT_TIME = 60

DEFAULT_DATA = {
    "max_playlists": MAX_PLAYLISTS,
    "loop_count": DEFAULT_LOOP_COUNT,
    "segment_time": DEFAULT_SEGMENT_TIME,
    "playlists": [],
}


def default_data() -> dict:
    return copy.deepcopy(DEFAULT_DATA)


def load_data() -> dict:
    if not PLAYLISTS_PATH.exists():
        return default_data()
    try:
        data = json.loads(PLAYLISTS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: cannot read {PLAYLISTS_PATH}: {exc}", file=sys.stderr)
        sys.exit(1)

    data.setdefault("max_playlists", MAX_PLAYLISTS)
    data.setdefault("loop_count", DEFAULT_LOOP_COUNT)
    data.setdefault("segment_time", DEFAULT_SEGMENT_TIME)
    data.setdefault("playlists", [])
    if not isinstance(data["playlists"], list):
        print("ERROR: playlists.json: 'playlists' must be a list", file=sys.stderr)
        sys.exit(1)

    for playlist in data["playlists"]:
        playlist.setdefault("id", new_playlist_id())
        playlist.setdefault("name", "未命名歌单")
        playlist.setdefault("enabled", True)
        playlist.setdefault("songs", [])
        if not isinstance(playlist["songs"], list):
            playlist["songs"] = []
    return data


def save_data(data: dict) -> None:
    PLAYLISTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def new_playlist_id() -> str:
    return "pl_" + uuid.uuid4().hex[:8]


def audio_relative_names() -> list[str]:
    if not AUDIO_DIR.is_dir():
        return []
    return sorted(
        p.relative_to(AUDIO_DIR).as_posix()
        for p in AUDIO_DIR.rglob("*.mp3")
    )


def resolve_audio_song(query: str) -> str | None:
    """Resolve an exact name, stem, or unique substring to an audio/ filename."""
    songs = audio_relative_names()
    if not songs:
        print("ERROR: ./audio has no MP3 files.", file=sys.stderr)
        return None

    lowered = query.casefold()
    exact = [s for s in songs if s.casefold() == lowered or Path(s).name.casefold() == lowered]
    if len(exact) == 1:
        return exact[0]

    stems = [s for s in songs if Path(s).stem.casefold() == lowered]
    if len(stems) == 1:
        return stems[0]

    partial = [s for s in songs if lowered in s.casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"“{query}”匹配到多首歌曲，请用更精确的文件名：")
        for song in partial:
            print(f"  - {song}")
        return None

    print(f"ERROR: 找不到歌曲：{query}", file=sys.stderr)
    return None


def resolve_playlist_song(playlist: dict, query: str) -> str | None:
    """Resolve a song already inside a playlist, even if the audio file is gone."""
    songs = playlist.get("songs", [])
    lowered = query.casefold()

    exact = [s for s in songs if s.casefold() == lowered or Path(s).name.casefold() == lowered]
    if len(exact) == 1:
        return exact[0]

    stems = [s for s in songs if Path(s).stem.casefold() == lowered]
    if len(stems) == 1:
        return stems[0]

    partial = [s for s in songs if lowered in s.casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"“{query}”在歌单中匹配到多首歌曲，请用更精确的文件名：")
        for song in partial:
            print(f"  - {song}")
        return None

    print(f"ERROR: 歌单中找不到歌曲：{query}", file=sys.stderr)
    return None


def find_playlist(data: dict, ident: str) -> dict | None:
    ident_cf = ident.casefold()

    exact = [
        p for p in data["playlists"]
        if p.get("id", "").casefold() == ident_cf or p.get("name", "").casefold() == ident_cf
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [
        p for p in data["playlists"]
        if ident_cf in p.get("id", "").casefold() or ident_cf in p.get("name", "").casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"“{ident}”匹配到多个歌单，请用 ID 或完整歌单名：")
        for playlist in partial:
            print(f"  - {playlist['id']}  {playlist['name']}")
        return None

    print(f"ERROR: 找不到歌单：{ident}", file=sys.stderr)
    return None


def cmd_list(data: dict, args: argparse.Namespace) -> None:
    playlists = data["playlists"]
    if not playlists:
        print("暂无歌单。")
        return
    print(f"歌单数量：{len(playlists)}/{data['max_playlists']}")
    for playlist in playlists:
        status = "启用" if playlist.get("enabled", True) else "禁用"
        print(f"- {playlist['id']}  [{status}]  {playlist['name']}  ({len(playlist['songs'])} 首)")


def cmd_create(data: dict, args: argparse.Namespace) -> None:
    if len(data["playlists"]) >= int(data["max_playlists"]):
        print(f"ERROR: 最多只能创建 {data['max_playlists']} 个歌单。", file=sys.stderr)
        sys.exit(1)

    name = args.name.strip()
    if any(p.get("name", "").casefold() == name.casefold() for p in data["playlists"]):
        print(f"ERROR: 已存在同名歌单：{name}", file=sys.stderr)
        sys.exit(1)

    playlist = {
        "id": new_playlist_id(),
        "name": name,
        "enabled": True,
        "songs": [],
    }
    data["playlists"].append(playlist)
    save_data(data)
    print(f"已创建歌单：{playlist['id']}  {playlist['name']}")


def cmd_delete(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)
    data["playlists"].remove(playlist)
    save_data(data)
    print(f"已删除歌单：{playlist['name']}")


def cmd_enable(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)
    playlist["enabled"] = True
    save_data(data)
    print(f"已启用歌单：{playlist['name']}")


def cmd_disable(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)
    playlist["enabled"] = False
    save_data(data)
    print(f"已禁用歌单：{playlist['name']}")


def cmd_rename(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)
    new_name = args.new_name.strip()
    if any(
        p is not playlist and p.get("name", "").casefold() == new_name.casefold()
        for p in data["playlists"]
    ):
        print(f"ERROR: 已存在同名歌单：{new_name}", file=sys.stderr)
        sys.exit(1)
    old_name = playlist["name"]
    playlist["name"] = new_name
    save_data(data)
    print(f"已重命名：{old_name} -> {new_name}")


def cmd_add(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)

    added = []
    for query in args.songs:
        song = resolve_audio_song(query)
        if not song:
            sys.exit(1)
        if song not in playlist["songs"]:
            playlist["songs"].append(song)
            added.append(song)

    save_data(data)
    if added:
        print(f"已加入 {playlist['name']}：")
        for song in added:
            print(f"  + {song}")
    else:
        print("没有新增歌曲（可能已存在）。")


def cmd_remove(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)

    removed = []
    for query in args.songs:
        song = resolve_playlist_song(playlist, query)
        if not song:
            sys.exit(1)
        if song in playlist["songs"]:
            playlist["songs"].remove(song)
            removed.append(song)

    save_data(data)
    if removed:
        print(f"已从 {playlist['name']} 移除：")
        for song in removed:
            print(f"  - {song}")
    else:
        print("没有移除任何歌曲。")


def cmd_show(data: dict, args: argparse.Namespace) -> None:
    playlist = find_playlist(data, args.playlist)
    if not playlist:
        sys.exit(1)
    status = "启用" if playlist.get("enabled", True) else "禁用"
    print(f"{playlist['name']}  [{status}]  ID: {playlist['id']}")
    if not playlist["songs"]:
        print("  （空歌单）")
        return
    for index, song in enumerate(playlist["songs"], 1):
        print(f"  {index:>2}. {song}")


def cmd_config(data: dict, args: argparse.Namespace) -> None:
    if args.loop_count is not None:
        if args.loop_count < 1:
            print("ERROR: --loop-count 必须大于 0", file=sys.stderr)
            sys.exit(1)
        data["loop_count"] = args.loop_count
    if args.segment_time is not None:
        if args.segment_time < 1:
            print("ERROR: --segment-time 必须大于 0", file=sys.stderr)
            sys.exit(1)
        data["segment_time"] = args.segment_time
    save_data(data)
    print(f"loop_count={data['loop_count']}  segment_time={data['segment_time']}")


def update_song_paths(mapping: dict[str, str]) -> bool:
    """Update playlist song references after sync renames audio files."""
    if not mapping:
        return False
    data = load_data()
    changed = False
    for playlist in data["playlists"]:
        songs = []
        for song in playlist["songs"]:
            new_song = mapping.get(song, song)
            songs.append(new_song)
            if new_song != song:
                changed = True
        playlist["songs"] = songs
    if changed:
        save_data(data)
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="列出所有歌单")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("create", help="创建歌单")
    p.add_argument("name", help="歌单名")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("delete", help="删除歌单")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("enable", help="启用歌单")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("disable", help="禁用歌单")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("rename", help="重命名歌单")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.add_argument("new_name", help="新歌单名")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("add", help="把歌曲加入歌单")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.add_argument("songs", nargs="+", help="歌曲文件名、完整歌名或唯一片段")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="从歌单移除歌曲")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.add_argument("songs", nargs="+", help="歌曲文件名、完整歌名或唯一片段")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("show", help="查看歌单内容")
    p.add_argument("playlist", help="歌单 ID 或名称")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("config", help="修改 HLS 配置")
    p.add_argument("--loop-count", type=int, default=None, help="m3u8 重复引用 TS 的次数，默认 100")
    p.add_argument("--segment-time", type=int, default=None, help="每个 TS 分片的秒数，默认 60")
    p.set_defaults(func=cmd_config)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    data = load_data()
    args.func(data, args)


if __name__ == "__main__":
    main()
