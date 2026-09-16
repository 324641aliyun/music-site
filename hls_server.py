#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local infinite HLS server for playlists.

This server is what makes a playlist URL truly loop forever. It serves a live
m3u8 playlist whose media sequence keeps advancing; when the end of a playlist
is reached, the sequence wraps back to the first segment. The software (or
CLI) must stay running for the URL to work.

Usage:
    python hls_server.py
    python hls_server.py --port 8765 --segment-time 30
"""

import argparse
import html
import math
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import hls_builder
from playlist_manager import load_data

REPO_ROOT = Path(__file__).resolve().parent
SEGMENTS_DIR = (REPO_ROOT / "hls" / "_segments").resolve()

EXTINF_RE = re.compile(r'^#EXTINF:([0-9.]+)')
SAFE_PART_RE = re.compile(r'^[A-Za-z0-9._-]+$')


def get_lan_ip() -> str:
    """Return the LAN IP that other devices on the same network can reach."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def port_available(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def parse_extinf_duration(extinf: str) -> float:
    match = EXTINF_RE.match(extinf)
    return float(match.group(1)) if match else 0.0


def build_playlist_sequence(playlist: dict, segment_time: int) -> list[dict] | None:
    """Build an ordered segment list for one playlist."""
    segments: list[dict] = []
    valid_blocks = 0

    for song in playlist.get("songs", []):
        result = hls_builder.build_song_segments(song, segment_time)
        if result is None:
            continue
        key, entries, _target_duration = result
        for entry_index, (extinf, uri) in enumerate(entries):
            duration = parse_extinf_duration(extinf)
            if duration <= 0:
                continue
            segments.append(
                {
                    "duration": duration,
                    "uri": f"../_segments/{key}/{uri}",
                    "discontinuity": entry_index == 0 and valid_blocks > 0,
                }
            )
        valid_blocks += 1

    return segments or None


def discontinuity_count_before(entry: dict, abs_index: int) -> int:
    """Count EXT-X-DISCONTINUITY events before an absolute segment index."""
    segments = entry["segments"]
    n = len(segments)
    base_discontinuities = sum(1 for segment in segments if segment["discontinuity"])
    first_is_discontinuity = bool(segments[0]["discontinuity"])

    cycle, index = divmod(abs_index, n)
    count = cycle * base_discontinuities
    if cycle > 0 and not first_is_discontinuity:
        # loop boundary at index 0 of each completed cycle except cycle 0
        count += cycle - 1
    count += sum(1 for segment in segments[:index] if segment["discontinuity"])
    if cycle > 0 and index > 0 and not first_is_discontinuity:
        # loop boundary at index 0 of the current cycle
        count += 1
    return count


def generate_live_playlist(entry: dict, elapsed: float, window: int = 5) -> str:
    """Generate a live m3u8 for the current moment in an endless loop."""
    segments = entry["segments"]
    n = len(segments)
    total_duration = entry["total_duration"]

    cycle = int(elapsed // total_duration)
    offset = elapsed % total_duration

    current_index = n - 1
    passed = 0.0
    for index, segment in enumerate(segments):
        if offset < passed + segment["duration"]:
            current_index = index
            break
        passed += segment["duration"]

    first_abs_index = cycle * n + current_index
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{math.ceil(entry['max_duration'])}",
        f"#EXT-X-MEDIA-SEQUENCE:{first_abs_index}",
        f"#EXT-X-DISCONTINUITY-SEQUENCE:{discontinuity_count_before(entry, first_abs_index)}",
    ]

    for offset_index in range(window):
        abs_index = first_abs_index + offset_index
        segment_cycle, segment_index = divmod(abs_index, n)
        segment = segments[segment_index]
        is_discontinuity = bool(segment["discontinuity"]) or (segment_index == 0 and segment_cycle > 0)
        if offset_index > 0 and is_discontinuity:
            lines.append("#EXT-X-DISCONTINUITY")
        lines.append(f"#EXTINF:{segment['duration']:.6f},")
        lines.append(f"{segment['uri']}?v={abs_index}")

    return "\n".join(lines) + "\n"


class InfiniteHlsServer:
    """HTTP server that serves endless live HLS playlists."""

    def __init__(
        self,
        playlists: list[dict],
        segment_time: int = 60,
        host: str = "0.0.0.0",
        port: int = 8765,
    ) -> None:
        self.host = host
        self.port = port
        self.segment_time = segment_time
        self.entries: dict[str, dict] = {}
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.stream_start: float | None = None

        for playlist in playlists:
            if not playlist.get("enabled", True):
                continue
            segments = build_playlist_sequence(playlist, segment_time)
            if not segments:
                continue
            self.entries[playlist["id"]] = {
                "name": playlist.get("name", "未命名歌单"),
                "segments": segments,
                "total_duration": sum(segment["duration"] for segment in segments),
                "max_duration": max(segment["duration"] for segment in segments),
            }

    @property
    def is_running(self) -> bool:
        return self.httpd is not None

    def start(self) -> int:
        if self.httpd is not None:
            return self.port

        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "MusicInfiniteHls/1.0"

            def log_message(self, fmt, *args):  # noqa: D102
                pass

            def _headers(self, status: int, content_type: str, length: int) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(length))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = unquote(parsed.path)

                if path == "/":
                    self._serve_index()
                elif path.startswith("/hls/") and path.endswith("/index.m3u8"):
                    playlist_id = path[len("/hls/"):-len("/index.m3u8")]
                    self._serve_playlist(playlist_id)
                elif path.startswith("/hls/_segments/"):
                    self._serve_segment(path)
                else:
                    self.send_error(404)

            def _serve_index(self) -> None:
                lan_ip = get_lan_ip()
                rows = []
                for playlist_id, entry in server.entries.items():
                    url = f"http://{lan_ip}:{server.port}/hls/{playlist_id}/index.m3u8"
                    rows.append(
                        f"<li>{html.escape(entry['name'])}<br>"
                        f"<code>{html.escape(url)}</code></li>"
                    )
                body = (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<title>无限循环 HLS</title></head><body>"
                    "<h1>无限循环 HLS</h1>"
                    "<p>保持本软件运行，下面的链接才能持续播放。</p>"
                    f"<ul>{''.join(rows) or '<li>没有启用的歌单</li>'}</ul>"
                    "</body></html>"
                ).encode("utf-8")
                self._headers(200, "text/html; charset=utf-8", len(body))
                self.wfile.write(body)

            def _serve_playlist(self, playlist_id: str) -> None:
                entry = server.entries.get(playlist_id)
                if not entry:
                    self.send_error(404)
                    return
                assert server.stream_start is not None
                elapsed = time.monotonic() - server.stream_start
                body = generate_live_playlist(entry, elapsed).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def _serve_segment(self, path: str) -> None:
                relative = path[len("/hls/_segments/"):]
                parts = [part for part in relative.split("/") if part]
                if not parts or any(not SAFE_PART_RE.match(part) for part in parts):
                    self.send_error(404)
                    return
                target = SEGMENTS_DIR.joinpath(*parts).resolve()
                try:
                    target.relative_to(SEGMENTS_DIR)
                except ValueError:
                    self.send_error(404)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return

                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp2t")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(data)

        last_error: OSError | None = None
        for candidate in range(self.port, self.port + 20):
            if not port_available(self.host, candidate):
                last_error = OSError(f"port {candidate} is already in use")
                continue
            try:
                self.httpd = ThreadingHTTPServer((self.host, candidate), Handler)
                break
            except OSError as exc:
                last_error = exc
        if self.httpd is None:
            raise last_error or OSError("could not bind HLS server port")

        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.stream_start = time.monotonic()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.port

    def stop(self) -> None:
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self.thread = None
        self.stream_start = None

    def url_for(self, playlist_id: str, host: str | None = None) -> str:
        actual_host = host or get_lan_ip()
        return f"http://{actual_host}:{self.port}/hls/{playlist_id}/index.m3u8"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--segment-time", type=int, default=None)
    args = parser.parse_args()

    data = load_data()
    segment_time = int(args.segment_time if args.segment_time is not None else data.get("segment_time", 60))
    server = InfiniteHlsServer(
        data.get("playlists", []),
        segment_time=segment_time,
        host=args.host,
        port=args.port,
    )
    if not server.entries:
        print("没有启用的歌单，或歌单中没有有效歌曲。")
        return

    server.start()
    print(f"无限循环 HLS 服务已启动：{get_lan_ip()}:{server.port}")
    for playlist_id, entry in server.entries.items():
        print(f"  {entry['name']}: {server.url_for(playlist_id)}")
    print("按 Ctrl+C 停止。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
