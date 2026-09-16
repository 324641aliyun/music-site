#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the static music site.

- Scans ./audio for every .mp3
- Writes index.html, feed.xml (RSS/Podcast), songs.json, playlists.html

Usage:
    python generate.py
    SITE_BASE_URL="https://USER.github.io/music-site/" python generate.py
"""

import json
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

SITE_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = SITE_ROOT / "audio"
HLS_DIR = SITE_ROOT / "hls"
PLAYLISTS_PATH = SITE_ROOT / "playlists.json"

DEFAULT_BASE_URL = "https://324641aliyun.github.io/music-site/"

SITE_TITLE = "My Music Site"
SITE_DESCRIPTION = "Personal online music collection (MP3)."
SITE_LANGUAGE = "zh-cn"
SITE_AUTHOR = "music-site"


DURATION_PREFIX_RE = re.compile(r'^\[\d+\]\s*')


def clean_title(stem: str) -> str:
    """Use the file name as the display title."""
    return stem.strip() or "Untitled"


def clean_song_name(stem: str) -> str:
    """Return the song name without the leading [seconds] prefix."""
    name = DURATION_PREFIX_RE.sub("", stem).strip()
    return name or clean_title(stem)


def load_playlists_data() -> dict:
    """Load playlists.json for the static playlist entry page."""
    if not PLAYLISTS_PATH.exists():
        return {"max_playlists": 10, "playlists": []}
    try:
        data = json.loads(PLAYLISTS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARN: cannot read playlists.json: {exc}", file=sys.stderr)
        return {"max_playlists": 10, "playlists": []}
    data["max_playlists"] = min(int(data.get("max_playlists", 10)), 10)
    data.setdefault("playlists", [])
    return data


def file_url(rel_path: Path) -> str:
    """URL-encode a relative file path, keeping slashes for subfolders."""
    return quote(rel_path.as_posix(), safe="/")


def collect_mp3s() -> list[Path]:
    """Return all MP3 files currently under ./audio."""
    if not AUDIO_DIR.is_dir():
        print(f"ERROR: audio directory not found: {AUDIO_DIR}", file=sys.stderr)
        sys.exit(1)
    return sorted(AUDIO_DIR.rglob("*.mp3"), key=lambda p: p.name.lower())


def render_index(songs: list[dict], base_url: str) -> str:
    rows = []
    for song in songs:
        abs_url = base_url.rstrip("/") + "/" + song["url"]
        rows.append(
            f'    <li><a href="{song["url"]}">{escape(song["title"])}</a>'
            f' <span class="meta">({song["size_mb"]} MB)</span>'
            f' <button class="copy" data-url="{escape(abs_url)}">复制链接</button>'
            f' <button class="copy-name" data-name="{escape(song["name"])}">复制歌名</button></li>'
        )
    list_html = "\n".join(rows) if rows else "    <li>暂无音乐。</li>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(SITE_TITLE)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .sub {{ color: #666; margin-top: 0; }}
    audio {{ width: 100%; margin: 1rem 0; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: 0.4rem 0; }}
    .meta {{ color: #888; font-size: 0.85em; }}
    a {{ color: #0366d6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .copy, .copy-name {{ margin-left: 0.5rem; padding: 0.15rem 0.55rem; font-size: 0.85em; cursor: pointer; border: 1px solid #bbb; border-radius: 4px; background: #f6f8fa; color: #333; display: inline-block; }}
    .copy:hover, .copy-name:hover {{ background: #eaeef2; text-decoration: none; }}
    .copy.copied, .copy-name.copied {{ background: #d4edda; border-color: #28a745; color: #1e7e34; }}
    footer {{ margin-top: 2rem; color: #999; font-size: 0.85em; }}
  </style>
</head>
<body>
  <h1>{escape(SITE_TITLE)}</h1>
  <p class="sub">{escape(SITE_DESCRIPTION)}</p>
  <audio id="player" controls preload="none"></audio>
  <p>点击歌曲开始播放；点“复制链接”可复制 MP3 直链，点“复制歌名”可复制不带时间前缀的歌名。也可以订阅 <a href="feed.xml">RSS/Podcast</a>。</p>
  <ul>
{list_html}
  </ul>
  <script>
    const player = document.getElementById('player');
    document.querySelectorAll('ul a[href$=".mp3"]').forEach(a => {{
      a.addEventListener('click', (event) => {{
        event.preventDefault();
        player.src = a.href;
        player.play().catch(() => {{}});
      }});
    }});

    async function copyText(text) {{
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (err) {{
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }}
    }}

    function flashCopied(btn) {{
      const original = btn.textContent;
      btn.textContent = '已复制';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = original;
        btn.classList.remove('copied');
      }}, 1500);
    }}

    document.querySelectorAll('button.copy').forEach(btn => {{
      btn.addEventListener('click', async (event) => {{
        event.stopPropagation();
        await copyText(btn.dataset.url);
        flashCopied(btn);
      }});
    }});

    document.querySelectorAll('button.copy-name').forEach(btn => {{
      btn.addEventListener('click', async (event) => {{
        event.stopPropagation();
        await copyText(btn.dataset.name);
        flashCopied(btn);
      }});
    }});
  </script>
  <footer>共 {len(songs)} 首 · 由 generate.py 自动生成</footer>
</body>
</html>
"""


def render_playlists_page(data: dict, base_url: str) -> str:
    playlists = data.get("playlists", [])
    max_playlists = data.get("max_playlists", 10)
    cards = []
    for playlist in playlists:
        pid = playlist.get("id", "")
        name = playlist.get("name", "未命名歌单")
        enabled = bool(playlist.get("enabled", True))
        songs = playlist.get("songs", [])
        status = "已启用" if enabled else "已禁用"
        status_class = "on" if enabled else "off"
        hls_path = HLS_DIR / pid / "index.m3u8"
        hls_url = base_url.rstrip("/") + f"/hls/{pid}/index.m3u8"

        if not enabled:
            url_html = '<div class="url muted">已禁用；重新启用并运行本机同步脚本后会恢复。</div>'
        elif hls_path.is_file():
            url_html = (
                f'<div class="url"><code>{escape(hls_url)}</code> '
                f'<button class="copy" data-url="{escape(hls_url)}">复制 URL</button></div>'
            )
        else:
            url_html = '<div class="url muted">HLS 尚未生成；运行本机 hls_builder.py 或 sync_music.pyw 后会生成。</div>'

        song_items = "".join(f"<li>{escape(song)}</li>" for song in songs) or "<li>（空歌单）</li>"
        cards.append(
            f"""    <div class="card">
      <h2>{escape(name)} <span class="badge {status_class}">{status}</span></h2>
      <div class="meta">ID: {escape(pid)} · {len(songs)} 首歌曲</div>
      {url_html}
      <details><summary>查看歌曲列表</summary><ul>{song_items}</ul></details>
    </div>"""
        )

    cards_html = "\n".join(cards) if cards else '<p class="muted">暂无歌单。请在本机使用 playlist_manager.py 创建。</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>歌单入口 - {escape(SITE_TITLE)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
    h1 {{ margin-bottom: 0.25rem; }}
    h2 {{ margin-bottom: 0.25rem; }}
    .muted {{ color: #888; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.8rem 1rem; margin: 1rem 0; }}
    .badge {{ font-size: 0.75em; padding: 0.1rem 0.4rem; border-radius: 4px; vertical-align: middle; }}
    .badge.on {{ background: #d4edda; color: #1e7e34; }}
    .badge.off {{ background: #eee; color: #666; }}
    .url {{ background: #f6f8fa; border-radius: 6px; padding: 0.5rem 0.6rem; margin: 0.6rem 0; word-break: break-all; }}
    .copy {{ margin-left: 0.5rem; padding: 0.15rem 0.55rem; font-size: 0.85em; cursor: pointer; border: 1px solid #bbb; border-radius: 4px; background: #fff; }}
    .copy.copied {{ background: #d4edda; border-color: #28a745; color: #1e7e34; }}
    .notice {{ display: none; border: 1px solid #f0c36d; background: #fff8e5; border-radius: 8px; padding: 0.7rem 0.9rem; margin: 1rem 0; }}
    pre, code {{ font-family: Consolas, "Courier New", monospace; }}
    pre {{ background: #f6f8fa; padding: 0.5rem; border-radius: 6px; overflow-x: auto; }}
    a {{ color: #0366d6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    details {{ margin-top: 0.5rem; }}
    li {{ margin: 0.2rem 0; }}
  </style>
</head>
<body>
  <h1>歌单入口</h1>
  <p>当前共 {len(playlists)} / 最多 {max_playlists} 个歌单。网页只展示歌单和 HLS 广播地址，歌单的创建、删除、启用、禁用和加减歌曲都在本机完成。</p>
  <div id="song-help" class="notice">
    要把 <strong id="song-name"></strong> 加入歌单，请在本机运行：
    <pre id="song-command"></pre>
  </div>
  {cards_html}
  <h2>本机操作方式</h2>
  <ol>
    <li>创建歌单：<code>python playlist_manager.py create "歌单名"</code></li>
    <li>加入歌曲：<code>python playlist_manager.py add "歌单名" "歌曲文件名"</code></li>
    <li>查看歌单：<code>python playlist_manager.py show "歌单名"</code></li>
    <li>生成 HLS：<code>python hls_builder.py</code></li>
    <li>同步 GitHub：<code>python sync_music.pyw</code></li>
  </ol>
  <p><a href="index.html">返回歌曲列表</a></p>
  <script>
    async function copyText(text) {{
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (err) {{
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }}
    }}

    function flashCopied(btn) {{
      const original = btn.textContent;
      btn.textContent = '已复制';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = original;
        btn.classList.remove('copied');
      }}, 1500);
    }}

    document.querySelectorAll('button.copy').forEach(btn => {{
      btn.addEventListener('click', async (event) => {{
        event.stopPropagation();
        await copyText(btn.dataset.url);
        flashCopied(btn);
      }});
    }});

    const params = new URLSearchParams(location.search);
    const song = params.get('song');
    if (song) {{
      const box = document.getElementById('song-help');
      box.style.display = 'block';
      document.getElementById('song-name').textContent = song;
      document.getElementById('song-command').textContent =
        'python playlist_manager.py add "歌单名" "' + song + '"';
    }}
  </script>
</body>
</html>
"""


def render_feed(songs: list[dict], base_url: str) -> str:
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for song in songs:
        abs_url = base_url.rstrip("/") + "/" + song["url"]
        items.append(
            "  <item>\n"
            f"    <title>{xml_escape(song['title'])}</title>\n"
            f"    <link>{xml_escape(abs_url)}</link>\n"
            f"    <guid isPermaLink=\"false\">{xml_escape(abs_url)}</guid>\n"
            f"    <pubDate>{now}</pubDate>\n"
            f"    <enclosure url=\"{xml_escape(abs_url)}\" type=\"audio/mpeg\" length=\"{song['size']}\"/>\n"
            "  </item>"
        )
    items_xml = "\n".join(items) if items else "  <!-- no songs -->"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{xml_escape(SITE_TITLE)}</title>
    <link>{xml_escape(base_url.rstrip("/"))}</link>
    <description>{xml_escape(SITE_DESCRIPTION)}</description>
    <language>{SITE_LANGUAGE}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>{xml_escape(SITE_AUTHOR)}</itunes:author>
{items_xml}
  </channel>
</rss>
"""


def main() -> None:
    base_url = os.environ.get("SITE_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"

    mp3_files = collect_mp3s()
    if not mp3_files:
        print("No MP3 files found in ./audio.", file=sys.stderr)
        sys.exit(1)

    songs = []
    for mp3_path in mp3_files:
        rel_path = mp3_path.relative_to(SITE_ROOT)
        title = clean_title(mp3_path.stem)
        name = clean_song_name(mp3_path.stem)
        song_file = mp3_path.relative_to(AUDIO_DIR).as_posix()
        size = mp3_path.stat().st_size
        songs.append(
            {
                "title": title,
                "name": name,
                "file": song_file,
                "url": file_url(rel_path),
                "size": size,
                "size_mb": f"{size / 1024 / 1024:.1f}",
            }
        )
    songs.sort(key=lambda s: s["title"].lower())

    (SITE_ROOT / "index.html").write_text(render_index(songs, base_url), encoding="utf-8")
    (SITE_ROOT / "feed.xml").write_text(render_feed(songs, base_url), encoding="utf-8")
    (SITE_ROOT / "songs.json").write_text(
        json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    playlists_data = load_playlists_data()
    (SITE_ROOT / "playlists.html").write_text(
        render_playlists_page(playlists_data, base_url), encoding="utf-8"
    )

    print(f"Generated {len(songs)} songs:")
    for song in songs:
        print(f"  - {song['title']} ({song['size_mb']} MB) {song['url']}")
    print(f"Base URL: {base_url}")


if __name__ == "__main__":
    main()
