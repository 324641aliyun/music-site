# Music Site

一个极简的个人音乐在线播放站，使用 GitHub Pages 托管。

## 文件说明

- `index.html` — 网页播放页，展示全部 MP3，点击即可播放。
- `feed.xml` — RSS/Podcast 订阅源，播客类 App 可识别并在线播放。
- `songs.json` — 歌曲清单，便于其他程序读取。
- `audio/` — 音乐文件夹。MP3、MP4 都放在这里，这是同步的唯一来源。
- `playlists.json` — 本机歌单数据，最多 10 个歌单。
- `playlist_gui.pyw` — 歌单管理 GUI 软件（推荐使用）。
- `playlist_manager.py` — 本机歌单管理命令行工具。
- `hls_builder.py` — 生成静态 HLS（m3u8 + TS 分片）。
- `hls_server.py` — 本机无限循环 HLS 服务（GUI 内部调用）。
- `sync_music.pyw` — 转换 MP4、缩略歌名、清理歌单、生成 HLS、同步 GitHub。
- `generate.py` — 重新生成网页、订阅源和歌单入口页。
- `hls/` — HLS 文件目录。

## 歌单管理 GUI（推荐）

双击 `playlist_gui.pyw`，或用命令运行：

```bash
python playlist_gui.pyw
```

GUI 可以：

- 新建、重命名、删除歌单
- 启用、禁用歌单
- 从歌曲库中搜索并添加歌曲
- 从歌单中移除歌曲、调整歌曲顺序
- 生成 GitHub 静态 HLS 链接
- 启动本机无限循环 HLS 服务并生成无限循环链接

其中：

- **GitHub 静态链接**：上传到 GitHub Pages 后可以离线播放固定轮数，不能真正无限循环。
- **本机无限循环链接**：只要 GUI 软件保持运行，URL 就会无限循环播放歌单。其他软件在同一台电脑或同一局域网内可以直接访问。

## 在 Minecraft netmusic:big_megaphone 中使用

`netmusic:big_megaphone` 需要 **http/https、且以 `.m3u8` 结尾的 HLS 直播地址**。本项目的本机无限循环服务正好符合这个要求。

使用步骤：

1. 双击运行 `playlist_gui.pyw`
2. 创建一个歌单，把一首或多首歌曲加入歌单
3. 选中该歌单，点击“启动无限服务”
4. 如果 Minecraft 客户端和 GUI 在同一台电脑上，复制“大喇叭链接（Minecraft 本机客户端）”
5. 如果其他玩家也要听，复制“局域网无限链接”，并确保玩家能访问你的电脑
6. 在 Minecraft 中打开 `netmusic:big_megaphone` 界面，把链接粘贴到 m3u8 URL 输入框，设置广播范围，点击开始

链接示例：

```text
http://127.0.0.1:8765/hls/<歌单ID>/index.m3u8
http://192.168.x.x:8765/hls/<歌单ID>/index.m3u8
```

注意事项：

- GUI 软件必须保持运行，链接才会持续循环
- 如果使用局域网链接，Windows 防火墙需要放行 TCP 8765（端口被占用时 GUI 会自动换到 8766 等）
- GitHub 静态 99MB m3u8 也能填入，但它是有限长度的 VOD，播放到结尾会停止；而且文件很大，不推荐用于 Minecraft
- 真正的无限循环请使用 GUI 的“启动无限服务”

## 命令行歌单管理

```bash
# 创建歌单
python playlist_manager.py create "我的歌单"

# 加入歌曲（支持文件名、完整歌名或唯一片段）
python playlist_manager.py add "我的歌单" "朝你大胯"

# 查看歌单
python playlist_manager.py show "我的歌单"

# 从歌单移除歌曲
python playlist_manager.py remove "我的歌单" "朝你大胯"

# 启用 / 禁用
python playlist_manager.py enable "我的歌单"
python playlist_manager.py disable "我的歌单"

# 删除歌单
python playlist_manager.py delete "我的歌单"

# 列出所有歌单
python playlist_manager.py list
```

删除歌单里的音乐文件后，下次运行 `sync_music.pyw` 或重新打开 GUI 时，会自动把该音乐从所有引用它的歌单中删除。

## HLS 说明

- HLS 音频：AAC 128k
- TS 分片：默认 60 秒
- 同一个 MP3 的 TS 分片只存一份，多个歌单共用
- 静态 HLS 会自动计算循环次数，让 `index.m3u8` 尽量接近 99 MB，但不超过 GitHub 单文件限制
- 静态 HLS 地址格式：

```text
https://324641aliyun.github.io/music-site/hls/<歌单ID>/index.m3u8
```

- 无限循环地址格式（本机 GUI 服务运行时）：

```text
http://<本机局域网IP>:8765/hls/<歌单ID>/index.m3u8
```

修改静态 HLS 的大小上限和分片长度：

```bash
# 静态 m3u8 最大 50 MB
python playlist_manager.py config --max-playlist-mb 50 --segment-time 30

# 固定循环次数，关闭自动大小计算
python playlist_manager.py config --loop-count 1000

# 重新开启自动大小计算
python playlist_manager.py config --auto-loop
```

静态 99 MB 的 m3u8 会让部分播放器加载较慢，遇到兼容问题可以调低 `max_playlist_mb`。真正无限循环仍建议使用 GUI 的“本机无限循环服务”。

## 一键同步

把 MP3 或 MP4 直接放入 `audio/` 后，运行：

```bash
python sync_music.pyw
```

脚本会：

1. 拉取 GitHub 最新状态；
2. 把 MP4 转换为 MP3，并删除原 MP4；
3. 缩略歌名（保留《...》中的内容）并添加 `[秒数]` 前缀；
4. 歌曲重命名后自动更新歌单引用；
5. 删除音乐文件后，自动从引用它的歌单中移除；
6. 生成静态 HLS；
7. 同步 `audio/` 到 GitHub；
8. 重新生成网页并提交推送。

常用参数：

```bash
python sync_music.pyw --dry-run      # 只预览
python sync_music.pyw --no-push      # 本地提交不推送
python sync_music.pyw --no-hls       # 跳过 HLS
python sync_music.pyw --force-hls    # 强制重建 HLS
```

## 部署地址

- 网站首页：`https://324641aliyun.github.io/music-site/`
- RSS：`https://324641aliyun.github.io/music-site/feed.xml`
