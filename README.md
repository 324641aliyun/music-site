# Music Site

一个极简的个人音乐在线播放站，使用 GitHub Pages 托管。

## 文件说明

- `index.html` — 网页播放页，展示全部 MP3，点击即可播放。
- `feed.xml` — RSS/Podcast 订阅源，播客类 App 可识别并在线播放。
- `songs.json` — 歌曲清单，便于其他程序读取。
- `audio/` — MP3 音频文件。
- `generate.py` — 自动生成脚本：扫描 MP3、复制到 `audio/` 并重新生成页面和订阅源。
- `sync_music.py` — 自动同步脚本：扫描本地音乐目录，新增/删除 MP3，并自动提交推送到 GitHub。

## 一键同步（推荐）

把 MP3 放入 `C:\Users\324641\Music` 后，在仓库根目录运行：

```bash
python sync_music.py
```

脚本会：

1. 拉取 GitHub 最新状态；
2. 把本地音乐目录里新增或变化的 MP3 复制到 `audio/`；
3. 删除本地音乐目录中已不存在的歌曲（包括 GitHub 上仍残留的）；
4. 重新生成 `index.html`、`feed.xml`、`songs.json`；
5. 自动提交并推送。

预览模式（不修改、不推送）：

```bash
python sync_music.py --dry-run
```

## 本地更新流程

1. 把新的 MP3 放入 `C:\Users\324641\Music`（或修改脚本里的 `MUSIC_SOURCE`）。
2. 在仓库根目录运行：

   ```bash
   python generate.py
   ```

3. 提交并推送：

   ```bash
   git add -A
   git commit -m "Update music"
   git push
   ```

## 部署地址

默认站点地址（GitHub Pages）：

```text
https://324641aliyun.github.io/music-site/
```

RSS 订阅地址：

```text
https://324641aliyun.github.io/music-site/feed.xml
```

如果你的 GitHub 用户名或仓库名不同，请重新生成：

```bash
SITE_BASE_URL="https://你的用户名.github.io/你的仓库名/" python generate.py
```
