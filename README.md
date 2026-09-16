# Music Site

一个极简的个人音乐在线播放站，使用 GitHub Pages 托管。

## 文件说明

- `index.html` — 网页播放页，展示全部 MP3，点击即可播放。
- `feed.xml` — RSS/Podcast 订阅源，播客类 App 可识别并在线播放。
- `songs.json` — 歌曲清单，便于其他程序读取。
- `playlists.html` — 歌单入口页，展示歌单和 HLS 广播 URL。
- `audio/` — 音乐文件夹。MP3、MP4 都放在这里，这是同步的唯一来源。
- `playlists.json` — 本机歌单数据，最多 10 个歌单。
- `generate.py` — 自动生成网页、订阅源和歌单入口页。
- `playlist_manager.py` — 本机歌单管理命令行工具。
- `hls_builder.py` — 将歌单生成为 HLS（m3u8 + TS 分片）。
- `sync_music.pyw` — 转换 MP4、缩略歌名、生成 HLS、同步 GitHub。
- `hls/` — 自动生成的 HLS 文件。

## 一键同步（推荐）

把 MP3 或 MP4 直接放入 `C:\Users\324641\Documents\website\music\audio` 后，在仓库根目录运行：

```bash
python sync_music.pyw
```

脚本会：

1. 拉取 GitHub 最新状态；
2. 把 `audio/` 里的 MP4 转换为 MP3，并删除原 MP4；
3. 缩略歌名：如果文件名中有完整的 `《...》`，只保留书名号中的内容；
4. 为每首 MP3 添加 `[秒数]` 前缀；
5. 根据 `playlists.json` 生成 HLS 广播；
6. 将本地 `audio/` 与 GitHub 同步；
7. 重新生成 `index.html`、`feed.xml`、`songs.json`、`playlists.html`；
8. 自动提交并推送。

常用参数：

```bash
python sync_music.pyw --dry-run      # 只预览，不修改、不推送
python sync_music.pyw --no-push      # 本地提交但不推送
python sync_music.pyw --no-hls       # 本次跳过 HLS 生成
python sync_music.pyw --force-hls    # 强制重建所有 HLS 分片
```

## 歌单管理

最多 10 个歌单，每个歌单对应一个独立的 HLS URL。

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

生成/更新 HLS：

```bash
python hls_builder.py
python hls_builder.py --force
python hls_builder.py --playlist "我的歌单"
```

生成后的广播 URL 格式：

```text
https://324641aliyun.github.io/music-site/hls/<歌单ID>/index.m3u8
```

HLS 默认：

- 音频编码：AAC 128k；
- TS 分片：60 秒；
- m3u8 重复引用 TS 分片：100 次，并使用 `#EXT-X-DISCONTINUITY` 分隔，达到长时间循环播放效果。

可修改配置：

```bash
python playlist_manager.py config --loop-count 50 --segment-time 30
```

禁用或删除歌单后，下次运行 `hls_builder.py` 或 `sync_music.pyw` 会清理对应的 HLS 文件。

## 网页上的“加入歌单”

GitHub Pages 是纯静态托管，网页本身不能直接写本机文件。因此网页上的“加入歌单”按钮只做入口：点击后打开 `playlists.html`，页面会显示当前歌单和对应的本机操作命令，实际加入仍在本机用 `playlist_manager.py` 完成。

## 部署地址

默认站点地址（GitHub Pages）：

```text
https://324641aliyun.github.io/music-site/
```

RSS 订阅地址：

```text
https://324641aliyun.github.io/music-site/feed.xml
```

歌单入口：

```text
https://324641aliyun.github.io/music-site/playlists.html
```
