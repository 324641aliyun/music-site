#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 歌单管理器。

运行后可以直接管理歌单、添加/删除歌曲、调整顺序，并生成：

- GitHub 静态 HLS 链接（需要同步到 GitHub 后使用）
- 本机无限循环 HLS 链接（保持本软件运行即可持续播放）

直接双击本文件即可运行，也可以用：
    python playlist_gui.pyw
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import playlist_manager as pm

BASE_URL = os.environ.get(
    "SITE_BASE_URL", "https://324641aliyun.github.io/music-site/"
).rstrip("/") + "/"


class PlaylistGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("音乐歌单管理器")
        self.root.geometry("1180x760")
        self.root.minsize(900, 600)

        self.data = pm.load_data()
        pm.remove_missing_songs()
        self.data = pm.load_data()
        self.all_songs = pm.audio_relative_names()

        self.current_id: str | None = None
        self.server = None
        self.filtered_songs: list[str] = []
        self.status_var = tk.StringVar(value="就绪")
        self.static_url_var = tk.StringVar()
        self.infinite_url_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.result_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self.refresh_playlists()
        self.refresh_library()
        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="新建歌单", command=self.new_playlist).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="重命名", command=self.rename_playlist).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="删除歌单", command=self.delete_playlist).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="启用/禁用", command=self.toggle_enabled).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="刷新", command=self.reload_data).pack(side=tk.LEFT, padx=3)

        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # 歌单列表
        left = ttk.Frame(main, padding=4)
        main.add(left, weight=1)
        ttk.Label(left, text="歌单").pack(anchor=tk.W)
        self.playlist_list = self._listbox(left)
        self.playlist_list.bind("<<ListboxSelect>>", self.on_playlist_select)

        # 歌单歌曲
        middle = ttk.Frame(main, padding=4)
        main.add(middle, weight=2)
        ttk.Label(middle, text="当前歌单歌曲").pack(anchor=tk.W)
        self.song_list = self._listbox(middle, selectmode=tk.EXTENDED)
        song_buttons = ttk.Frame(middle)
        song_buttons.pack(fill=tk.X, pady=4)
        ttk.Button(song_buttons, text="上移", command=lambda: self.move_song(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(song_buttons, text="下移", command=lambda: self.move_song(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(song_buttons, text="从歌单移除", command=self.remove_selected_songs).pack(side=tk.LEFT, padx=2)

        # 歌曲库
        right = ttk.Frame(main, padding=4)
        main.add(right, weight=2)
        ttk.Label(right, text="歌曲库").pack(anchor=tk.W)
        search_entry = ttk.Entry(right, textvariable=self.search_var)
        search_entry.pack(fill=tk.X, pady=3)
        self.search_var.trace_add("write", lambda *_: self.refresh_library())
        self.library_list = self._listbox(right, selectmode=tk.EXTENDED)
        ttk.Button(right, text="添加到当前歌单", command=self.add_selected_songs).pack(fill=tk.X, pady=4)

        # 链接
        link_frame = ttk.LabelFrame(self.root, text="广播链接", padding=8)
        link_frame.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(link_frame, text="GitHub 静态链接（自动填充到大小上限）").grid(row=0, column=0, sticky=tk.W)
        static_entry = ttk.Entry(link_frame, textvariable=self.static_url_var, width=80)
        static_entry.grid(row=0, column=1, sticky=tk.EW, padx=6)
        ttk.Button(link_frame, text="生成静态 HLS", command=self.generate_static_link).grid(row=0, column=2, padx=3)
        ttk.Button(link_frame, text="复制", command=lambda: self.copy_var(self.static_url_var)).grid(row=0, column=3, padx=3)

        ttk.Label(link_frame, text="本机无限循环链接（保持软件运行）").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        infinite_entry = ttk.Entry(link_frame, textvariable=self.infinite_url_var, width=80)
        infinite_entry.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=(6, 0))
        ttk.Button(link_frame, text="启动无限服务", command=self.start_infinite_server).grid(row=1, column=2, padx=3, pady=(6, 0))
        ttk.Button(link_frame, text="停止服务", command=self.stop_infinite_server).grid(row=1, column=3, padx=3, pady=(6, 0))
        ttk.Button(link_frame, text="复制", command=lambda: self.copy_var(self.infinite_url_var)).grid(row=1, column=4, padx=3, pady=(6, 0))

        link_frame.columnconfigure(1, weight=1)

        status = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _listbox(self, parent: tk.Widget, selectmode=tk.BROWSE) -> tk.Listbox:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        listbox = tk.Listbox(frame, selectmode=selectmode, exportselection=False)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return listbox

    # -------------------------------------------------------------- helpers
    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def current_playlist(self) -> dict | None:
        if not self.current_id:
            return None
        for playlist in self.data["playlists"]:
            if playlist["id"] == self.current_id:
                return playlist
        return None

    def selected_playlist(self) -> dict | None:
        indexes = self.playlist_list.curselection()
        if not indexes:
            return None
        return self.data["playlists"][indexes[0]]

    def save(self) -> None:
        pm.save_data(self.data)

    def reload_data(self) -> None:
        self.data = pm.load_data()
        removed = pm.remove_missing_songs()
        self.data = pm.load_data()
        self.all_songs = pm.audio_relative_names()
        self.current_id = None
        self.refresh_playlists()
        self.refresh_songs()
        self.refresh_library()
        if removed:
            self.set_status(f"已清理 {len(removed)} 首无效歌单引用")

    # -------------------------------------------------------------- refresh
    def refresh_playlists(self) -> None:
        self.playlist_list.delete(0, tk.END)
        for playlist in self.data["playlists"]:
            status = "启用" if playlist.get("enabled", True) else "禁用"
            self.playlist_list.insert(
                tk.END,
                f"{playlist['name']}  [{status}]  {len(playlist.get('songs', []))} 首",
            )
        if self.current_id:
            for index, playlist in enumerate(self.data["playlists"]):
                if playlist["id"] == self.current_id:
                    self.playlist_list.selection_set(index)
                    self.playlist_list.activate(index)
                    break
        self.refresh_songs()

    def refresh_songs(self) -> None:
        self.song_list.delete(0, tk.END)
        playlist = self.current_playlist()
        if not playlist:
            return
        for index, song in enumerate(playlist.get("songs", []), 1):
            self.song_list.insert(tk.END, f"{index:>3}. {song}")

    def refresh_library(self) -> None:
        self.library_list.delete(0, tk.END)
        query = self.search_var.get().strip().casefold()
        self.filtered_songs = [
            song for song in self.all_songs
            if not query or query in song.casefold()
        ]
        for song in self.filtered_songs:
            self.library_list.insert(tk.END, song)

    def on_playlist_select(self, _event=None) -> None:
        playlist = self.selected_playlist()
        if playlist:
            self.current_id = playlist["id"]
            self.refresh_songs()
            self.refresh_infinite_url()

    # -------------------------------------------------------------- actions
    def new_playlist(self) -> None:
        if len(self.data["playlists"]) >= int(self.data["max_playlists"]):
            messagebox.showwarning("提示", f"最多只能创建 {self.data['max_playlists']} 个歌单。")
            return
        name = simpledialog.askstring("新建歌单", "请输入歌单名：", parent=self.root)
        if not name:
            return
        name = name.strip()
        if any(p["name"].casefold() == name.casefold() for p in self.data["playlists"]):
            messagebox.showwarning("提示", "已存在同名歌单。")
            return
        playlist = {
            "id": pm.new_playlist_id(),
            "name": name,
            "enabled": True,
            "songs": [],
        }
        self.data["playlists"].append(playlist)
        self.current_id = playlist["id"]
        self.save()
        self.refresh_playlists()
        self.set_status(f"已创建歌单：{name}")

    def rename_playlist(self) -> None:
        playlist = self.selected_playlist()
        if not playlist:
            return
        name = simpledialog.askstring("重命名歌单", "请输入新名称：", initialvalue=playlist["name"], parent=self.root)
        if not name:
            return
        name = name.strip()
        if any(p is not playlist and p["name"].casefold() == name.casefold() for p in self.data["playlists"]):
            messagebox.showwarning("提示", "已存在同名歌单。")
            return
        playlist["name"] = name
        self.save()
        self.refresh_playlists()
        self.set_status(f"已重命名为：{name}")

    def delete_playlist(self) -> None:
        playlist = self.selected_playlist()
        if not playlist:
            return
        if not messagebox.askyesno("确认删除", f"确定要删除歌单“{playlist['name']}”吗？"):
            return
        self.data["playlists"].remove(playlist)
        self.current_id = None
        self.save()
        self.refresh_playlists()
        self.set_status(f"已删除歌单：{playlist['name']}")

    def toggle_enabled(self) -> None:
        playlist = self.selected_playlist()
        if not playlist:
            return
        playlist["enabled"] = not playlist.get("enabled", True)
        self.save()
        self.refresh_playlists()
        state = "启用" if playlist["enabled"] else "禁用"
        self.set_status(f"已{state}歌单：{playlist['name']}")

    def add_selected_songs(self) -> None:
        playlist = self.current_playlist()
        if not playlist:
            messagebox.showinfo("提示", "请先选择一个歌单。")
            return
        indexes = self.library_list.curselection()
        if not indexes:
            return
        added = 0
        for index in indexes:
            song = self.filtered_songs[index]
            if song not in playlist["songs"]:
                playlist["songs"].append(song)
                added += 1
        if added:
            self.save()
            self.refresh_playlists()
            self.set_status(f"已添加 {added} 首歌曲到歌单：{playlist['name']}")
        else:
            self.set_status("所选歌曲已经在歌单中。")

    def remove_selected_songs(self) -> None:
        playlist = self.current_playlist()
        if not playlist:
            return
        indexes = list(self.song_list.curselection())
        if not indexes:
            return
        for index in sorted(indexes, reverse=True):
            del playlist["songs"][index]
        self.save()
        self.refresh_playlists()
        self.set_status(f"已从歌单移除 {len(indexes)} 首歌曲。")

    def move_song(self, direction: int) -> None:
        playlist = self.current_playlist()
        if not playlist:
            return
        indexes = list(self.song_list.curselection())
        if len(indexes) != 1:
            return
        index = indexes[0]
        new_index = index + direction
        if new_index < 0 or new_index >= len(playlist["songs"]):
            return
        playlist["songs"][index], playlist["songs"][new_index] = (
            playlist["songs"][new_index],
            playlist["songs"][index],
        )
        self.save()
        self.refresh_playlists()
        self.song_list.selection_set(new_index)

    # --------------------------------------------------------------- links
    def copy_var(self, var: tk.StringVar) -> None:
        value = var.get().strip()
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.set_status("已复制到剪贴板")

    def refresh_infinite_url(self) -> None:
        playlist = self.current_playlist()
        if not self.server or not playlist:
            self.infinite_url_var.set("")
            return
        if playlist["id"] in self.server.entries:
            self.infinite_url_var.set(self.server.url_for(playlist["id"]))
        else:
            self.infinite_url_var.set("")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, callback, payload = self.result_queue.get_nowait()
                if kind == "ok":
                    callback(payload)
                else:
                    self.set_status(f"失败：{payload}")
                    messagebox.showerror("错误", str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def run_in_thread(self, work, done) -> None:
        def wrapper():
            try:
                result = work()
            except SystemExit as exc:
                self.result_queue.put(("error", None, str(exc)))
            except Exception as exc:
                self.result_queue.put(("error", None, str(exc)))
            else:
                self.result_queue.put(("ok", done, result))

        threading.Thread(target=wrapper, daemon=True).start()

    def generate_static_link(self) -> None:
        playlist = self.current_playlist()
        if not playlist:
            messagebox.showinfo("提示", "请先选择一个歌单。")
            return
        self.save()
        playlist_id = playlist["id"]
        self.set_status("正在生成静态 HLS，请稍候...")

        def work():
            import hls_builder
            hls_builder.build_all(only_playlist=playlist_id)
            return f"{BASE_URL}hls/{playlist_id}/index.m3u8"

        def done(url: str):
            self.static_url_var.set(url)
            self.set_status("静态 HLS 链接已生成")

        self.run_in_thread(work, done)

    def start_infinite_server(self) -> None:
        if self.server:
            self.set_status("无限服务已经在运行")
            return
        self.save()
        self.set_status("正在准备无限循环 HLS，请稍候...")

        def work():
            import hls_server
            server = hls_server.InfiniteHlsServer(
                self.data["playlists"],
                segment_time=int(self.data.get("segment_time", 60)),
                port=8765,
            )
            if not server.entries:
                raise RuntimeError("没有启用的歌单，或歌单中没有有效歌曲。")
            server.start()
            return server

        def done(server):
            self.server = server
            self.refresh_infinite_url()
            self.set_status(
                f"无限循环服务已启动，端口 {server.port}；保持本软件运行，链接才有效。"
            )

        self.run_in_thread(work, done)

    def stop_infinite_server(self) -> None:
        if not self.server:
            self.set_status("无限服务未运行")
            return
        self.server.stop()
        self.server = None
        self.infinite_url_var.set("")
        self.set_status("无限循环服务已停止")

    def on_close(self) -> None:
        if self.server:
            self.server.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    PlaylistGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
