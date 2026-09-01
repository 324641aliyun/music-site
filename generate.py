#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the static music site.

- Copies every .mp3 from MUSIC_SOURCE into ./audio
- Writes index.html, feed.xml (RSS/Podcast), songs.json

Usage:
    python generate.py
    MUSIC_SOURCE="C:/Users/324641/Music" SITE_BASE_URL="https://USER.github.io/music-site/" python generate.py
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

SITE_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = SITE_ROOT / "audio"

DEFAULT_MUSIC_SOURCE = r"C:\Users\324641\Music"
DEFAULT_BASE_URL = "https://324641aliyun.github.io/music-site/"

SITE_TITLE = "My Music Site"
SITE_DESCRIPTION = "Personal online music collection (MP3)."
SITE_LANGUAGE = "zh-cn"
SITE_AUTHOR = "music-site"


def clean_title(stem: str) -> str:
    """Use the file name as the display title."""
    return stem.strip() or "Untitled"


def file_url(rel_path: Path) -> str:
    """URL-encode a relative file path, keeping slashes for subfolders."""
    return quote(rel_path.as_posix(), safe="/")


def collect_mp3s(source: Path) -> list[Path]:
    if not source.is_dir():
        print(f"ERROR: music source directory not found: {source}", file=sys.stderr)
        sys.exit(1)
    return sorted(source.rglob("*.mp3"), key=lambda p: p.name.lower())


def copy_mp3s(source: Path) -> list[tuple[Path, Path]]:
    """Copy MP3 files into ./audio, preserving relative subfolders when present."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in collect_mp3s(source):
        rel = src.relative_to(source)
        dst = AUDIO_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            print(f"SKIP  {rel}")
        else:
            shutil.copy2(src, dst)
            print(f"COPY  {rel}")
        copied.append((src, dst))
    return copied


def render_index(songs: list[dict], base_url: str) -> str:
    rows = []
    for song in songs:
        abs_url = base_url.rstrip("/") + "/" + song["url"]
        rows.append(
            f'    <li><a href="{song["url"]}">{escape(song["title"])}</a>'
            f' <span class="meta">({song["size_mb"]} MB)</span>'
            f' <button class="copy" data-url="{escape(abs_url)}">复制链接</button></li>'
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
    .copy {{ margin-left: 0.5rem; padding: 0.15rem 0.55rem; font-size: 0.85em; cursor: pointer; border: 1px solid #bbb; border-radius: 4px; background: #f6f8fa; color: #333; }}
    .copy:hover {{ background: #eaeef2; }}
    .copy.copied {{ background: #d4edda; border-color: #28a745; color: #1e7e34; }}
    footer {{ margin-top: 2rem; color: #999; font-size: 0.85em; }}
  </style>
</head>
<body>
  <h1>{escape(SITE_TITLE)}</h1>
  <p class="sub">{escape(SITE_DESCRIPTION)}</p>
  <audio id="player" controls preload="none"></audio>
  <p>点击歌曲开始播放；点“复制链接”可复制 MP3 直链供其他软件播放。也可以订阅 <a href="feed.xml">RSS/Podcast</a>。</p>
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

    document.querySelectorAll('button.copy').forEach(btn => {{
      btn.addEventListener('click', async (event) => {{
        event.stopPropagation();
        const url = btn.dataset.url;
        try {{
          await navigator.clipboard.writeText(url);
        }} catch (err) {{
          const textarea = document.createElement('textarea');
          textarea.value = url;
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand('copy');
          textarea.remove();
        }}
        const original = btn.textContent;
        btn.textContent = '已复制';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.textContent = original;
          btn.classList.remove('copied');
        }}, 1500);
      }});
    }});
  </script>
  <footer>共 {len(songs)} 首 · 由 generate.py 自动生成</footer>
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
    music_source = Path(os.environ.get("MUSIC_SOURCE", DEFAULT_MUSIC_SOURCE))
    base_url = os.environ.get("SITE_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"

    copied = copy_mp3s(music_source)
    if not copied:
        print("No MP3 files found.", file=sys.stderr)
        sys.exit(1)

    songs = []
    for _src, dst in copied:
        rel_path = dst.relative_to(SITE_ROOT)
        title = clean_title(dst.stem)
        size = dst.stat().st_size
        songs.append(
            {
                "title": title,
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

    print(f"Generated {len(songs)} songs:")
    for song in songs:
        print(f"  - {song['title']} ({song['size_mb']} MB) {song['url']}")
    print(f"Base URL: {base_url}")


if __name__ == "__main__":
    main()
