# Music Site

一个极简的个人音乐在线播放站，使用 GitHub Pages 托管。

## 文件说明

- `index.html` — 网页播放页，展示全部 MP3，点击即可播放。
- `feed.xml` — RSS/Podcast 订阅源，播客类 App 可识别并在线播放。
- `songs.json` — 歌曲清单，便于其他程序读取。
- `audio/` — 音乐文件夹。MP3、MP4 都放在这里，这是同步的唯一来源。
- `generate.py` — 自动生成脚本：扫描 `audio/` 中的 MP3 并重新生成页面和订阅源。
- `sync_music.py` — 自动同步脚本：转换 MP4、缩略歌名、添加秒数，然后提交推送到 GitHub。

## 一键同步（推荐）

把 MP3 或 MP4 直接放入 `C:\Users\324641\Documents\website\music\audio` 后，在仓库根目录运行：

```bash
python sync_music.py
```

脚本会：

1. 拉取 GitHub 最新状态；
2. 把 `audio/` 里的 MP4 转换为 MP3，并删除原 MP4；
3. 缩略歌名：如果文件名中有完整的 `《...》`，只保留书名号中的内容；
4. 为每首 MP3 添加 `[秒数]` 前缀；
5. 将本地 `audio/` 与 GitHub 同步：新增本地有而 GitHub 没有的歌曲，删除 GitHub 有而本地已不存在的歌曲；
6. 重新生成 `index.html`、`feed.xml`、`songs.json`；
7. 自动提交并推送。

预览模式（不修改、不推送）：

```bash
python sync_music.py --dry-run
```

只提交不推送：

```bash
python sync_music.py --no-push
```

## 本地更新流程（手动）

1. 把新的 MP3/MP4 放入 `audio/`。
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
