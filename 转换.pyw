import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# 兼容 moviepy 不同版本的导入方式（只读音频轨，适用于无视频流的纯音频 MP4）
try:
    from moviepy import AudioFileClip          # moviepy 2.x
except ImportError:
    from moviepy.editor import AudioFileClip   # moviepy 1.x

try:
    from mutagen.mp3 import MP3
except ImportError:
    MP3 = None

# Windows 非法字符
INVALID_CHARS = r'[<>:"/\\|?*]'

# 已有时长前缀，例如 [210]
DURATION_PREFIX_RE = re.compile(r'^\[\d+\]')


def sanitize_filename(name):
    """清洗文件名中的非法字符，替换为下划线"""
    return re.sub(INVALID_CHARS, '_', name)


def get_mp3_duration(mp3_path):
    """获取 MP3 时长（秒），失败返回 0"""
    if MP3 is not None:
        try:
            audio = MP3(mp3_path)
            return audio.info.length
        except Exception:
            return 0
    return 0


def convert_mp4_to_mp3(mp4_path, mp3_path):
    """使用 moviepy 提取音频并保存为 MP3"""
    audio = AudioFileClip(mp4_path)
    try:
        audio.write_audiofile(mp3_path, logger=None)
    finally:
        audio.close()


def rename_mp3_with_duration(mp3_path):
    """为 MP3 文件重命名，添加时长（秒）前缀 [秒数]"""
    if not os.path.exists(mp3_path):
        return None, "源文件不存在"

    dir_name = os.path.dirname(mp3_path)
    base_name = os.path.basename(mp3_path)

    # 分离文件名和扩展名
    name_without_ext, ext = os.path.splitext(base_name)

    # 已有时长前缀则跳过
    if DURATION_PREFIX_RE.match(name_without_ext):
        return None, "SKIP"

    duration = get_mp3_duration(mp3_path)
    duration_str = str(int(duration)) if duration > 0 else "0"

    # 清洗原文件名（去掉非法字符）
    clean_name = sanitize_filename(name_without_ext)

    # 生成新文件名，使用 [秒数] 前缀
    new_base = f"[{duration_str}] {clean_name}{ext}"

    # 检查路径长度，若超过 240 字符则截断 clean_name
    max_len = 240
    if len(os.path.join(dir_name, new_base)) > max_len:
        new_base = f"[{duration_str}] {clean_name[:100]}{ext}"

    new_path = os.path.join(dir_name, new_base)

    # 如果新文件名与原文件名相同（理论上不会，但避免死循环）
    if new_path == mp3_path:
        return None, "文件名已符合格式"

    # 处理重名冲突
    counter = 1
    while os.path.exists(new_path):
        name_part, ext_part = os.path.splitext(new_base)
        new_base = f"{name_part}_{counter}{ext_part}"
        new_path = os.path.join(dir_name, new_base)
        counter += 1

    try:
        os.rename(mp3_path, new_path)
        return new_path, None
    except Exception as e:
        return None, str(e)


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP4 → MP3 批量转换器")
        self.root.geometry("600x450")

        self.folder_path = tk.StringVar()
        self.status_var = tk.StringVar()
        self.status_var.set("请选择文件夹")

        self.create_widgets()

    def create_widgets(self):
        btn_select = tk.Button(
            self.root,
            text="选择文件夹并开始转换",
            command=self.select_folder,
            height=2,
            font=("Arial", 12)
        )
        btn_select.pack(pady=20)

        label_status = tk.Label(
            self.root,
            textvariable=self.status_var,
            wraplength=500,
            font=("Arial", 10)
        )
        label_status.pack(pady=10)

        self.log_text = scrolledtext.ScrolledText(
            self.root,
            width=70,
            height=18,
            state='disabled',
            font=("Consolas", 9)
        )
        self.log_text.pack(pady=10, padx=10)

    def log(self, message):
        """线程安全地向日志区域添加一行"""
        self.root.after(0, self._log_sync, message)

    def _log_sync(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def select_folder(self):
        folder = filedialog.askdirectory(title="选择包含 MP4 文件的文件夹")
        if not folder:
            return
        self.folder_path.set(folder)
        self.status_var.set(f"正在处理：{folder}")
        self.log(f"开始处理文件夹：{folder}")

        threading.Thread(target=self.process_folder, args=(folder,), daemon=True).start()

    def process_folder(self, folder):
        try:
            # 1. 查找所有 MP4 文件
            mp4_files = [f for f in os.listdir(folder) if f.lower().endswith('.mp4')]
            self.log(f"发现 {len(mp4_files)} 个 MP4 文件")

            # 2. 转换 MP4 → MP3，然后删除 MP4
            for i, filename in enumerate(mp4_files, 1):
                mp4_path = os.path.join(folder, filename)
                mp3_name = os.path.splitext(filename)[0] + ".mp3"
                mp3_path = os.path.join(folder, mp3_name)

                self.log(f"[{i}/{len(mp4_files)}] 转换：{filename}")
                try:
                    convert_mp4_to_mp3(mp4_path, mp3_path)
                    os.remove(mp4_path)
                    self.log(f"  完成并删除 MP4：{filename}")
                except Exception as e:
                    self.log(f"  转换失败：{filename}，错误：{e}")

            # 3. 重命名所有 MP3 文件（包括原有的）
            mp3_files = [f for f in os.listdir(folder) if f.lower().endswith('.mp3')]
            self.log(f"\n开始重命名 {len(mp3_files)} 个 MP3 文件")
            for filename in mp3_files:
                mp3_path = os.path.join(folder, filename)
                new_path, error = rename_mp3_with_duration(mp3_path)
                if new_path:
                    self.log(f"  重命名：{filename} → {os.path.basename(new_path)}")
                elif error == "SKIP":
                    self.log(f"  跳过（已有时长前缀）：{filename}")
                else:
                    self.log(f"  重命名失败：{filename}，错误：{error}")

            self.status_var.set("处理完成！")
            self.log("\n全部操作完成。")
            self.root.after(0, messagebox.showinfo, "完成", "所有文件处理完毕！")
        except Exception as e:
            self.status_var.set("处理出错")
            self.log(f"发生错误：{e}")
            self.root.after(0, messagebox.showerror, "错误", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()