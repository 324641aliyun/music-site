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
- 生成 Minecraft 大喇叭专用的 GitHub Pages 公网 m3u8 链接

## 在 Minecraft netmusic:big_megaphone 中使用

`netmusic:big_megaphone` 需要 **http/https、且以 `.m3u8` 结尾的直播地址**。本项目使用 GitHub Pages 提供公网静态 m3u8，不需要局域网，也不需要让本机软件一直运行。

### 原理

NetMusic 1.5.1 的 `M3U8InputStream` 会把 m3u8 中的 TS URI 逐个下载，遇到 `#EXT-X-ENDLIST` 后标记 `noMoreSegments`，当前流播放结束。随后 `BigMegaphoneClientManager` 检测到声音已经不在 `tickingSounds` 中，会在约 40 tick 后重新创建声音并再次播放。

所以：

- 单遍 m3u8 播完后，大喇叭会自动重新播放
- 每轮之间约有 **2-3 秒空档**
- 如果 m3u8 里重复写相同的 TS URI，NetMusic 内部会通过 `processedUrls` 去重，不会按重复次数播放
- 99MB 的重复 m3u8 会被完整下载和解析，不适合大喇叭

### 使用步骤

1. 双击运行 `playlist_gui.pyw`
2. 新建歌单，把一首或多首歌曲加入歌单
3. 选中该歌单，点击“生成大喇叭链接”
4. 运行同步脚本，把 m3u8 和 TS 分片推送到 GitHub：

```bash
python sync_music.pyw
```

5. GUI 中会显示公网链接，例如：

```text
https://324641aliyun.github.io/music-site/hls/<歌单ID>/index.m3u8
```

6. 在 Minecraft 中打开 `netmusic:big_megaphone` 界面，把链接粘贴到 m3u8 URL 输入框，设置广播范围，点击开始

之后即使玩家不在同一局域网，只要能访问 GitHub Pages，就可以听到音乐。

### 当前默认配置

`playlists.json` 默认是单遍模式：

```json
{
  "auto_loop": false,
  "loop_count": 1,
  "segment_time": 60
}
```

即每个歌单只生成一遍 m3u8，然后依靠大喇叭自动重播。

修改分片长度：

```bash
python playlist_manager.py config --segment-time 30
```

如果改成自动大小模式（不推荐用于大喇叭）：

```bash
python playlist_manager.py config --auto-loop --max-playlist-mb 99
```

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

## HLS 与同步

HLS 默认：

- 音频编码：AAC 128k
- TS 分片：默认 60 秒
- 同一个 MP3 的 TS 分片只存一份，多个歌单共用
- 当前为单遍 m3u8，体积很小，适合公网大喇叭使用

一键同步：

```bash
python sync_music.pyw
```

脚本会：

1. 拉取 GitHub 最新状态
2. 把 MP4 转换为 MP3，并删除原 MP4
3. 缩略歌名并添加 `[秒数]` 前缀
4. 歌曲重命名后自动更新歌单引用
5. 删除音乐文件后自动从歌单移除
6. 生成/更新静态 HLS
7. 同步 `audio/`、`hls/` 到 GitHub
8. 重新生成网页并提交推送

常用参数：

```bash
python sync_music.pyw --dry-run
python sync_music.pyw --no-push
python sync_music.pyw --no-hls
python sync_music.pyw --force-hls
```

## 部署地址

- 网站首页：`https://324641aliyun.github.io/music-site/`
- RSS：`https://324641aliyun.github.io/music-site/feed.xml`
- 大喇叭链接格式：`https://324641aliyun.github.io/music-site/hls/<歌单ID>/index.m3u8`
