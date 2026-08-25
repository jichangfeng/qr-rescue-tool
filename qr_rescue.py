from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageGrab, ImageTk

from qr_rescue_core import DecodeResult, decode_image, decode_path, load_image


APP_TITLE = "二维码救援工具"


def _console_print(message: str, stream) -> bool:
    """Write CLI output when a console exists.

    PyInstaller's ``--windowed`` executable intentionally has no real stdout
    or stderr.  Writing to those placeholder streams can raise ``OSError(22)``
    on Windows, so CLI diagnostics must never depend on them being available.
    """
    if stream is None:
        return False
    try:
        stream.write(f"{message}\n")
        stream.flush()
    except (OSError, ValueError, UnicodeError, AttributeError):
        return False
    return True


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _save_clean_qr(text: str, path: str) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(path)


class QRRescueApp:
    def __init__(self, root) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x680")
        self.root.minsize(680, 560)
        self.image: np.ndarray | None = None
        self.image_path: str | None = None
        self.result: DecodeResult | None = None
        self.preview_photo = None

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        title = ttk.Label(main, text=APP_TITLE, font=("Microsoft YaHei UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(
            main,
            text="读取二维码原始内容，不访问网址；普通识别失败时自动纠偏和重建。",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 12))

        content = ttk.Panedwindow(main, orient="horizontal")
        content.grid(row=2, column=0, sticky="nsew")

        preview_frame = ttk.LabelFrame(content, text="图片", padding=10)
        result_frame = ttk.LabelFrame(content, text="二维码原始内容", padding=10)
        content.add(preview_frame, weight=1)
        content.add(result_frame, weight=2)

        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview = ttk.Label(
            preview_frame,
            text="请选择图片\n或从剪贴板粘贴",
            anchor="center",
            justify="center",
        )
        self.preview.grid(row=0, column=0, sticky="nsew")

        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(
            result_frame,
            wrap="word",
            font=("Consolas", 10),
            padx=8,
            pady=8,
            undo=False,
        )
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.details = ttk.Label(result_frame, text="", foreground="#555555")
        self.details.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=0, sticky="ew", pady=(14, 8))
        self.open_button = ttk.Button(buttons, text="选择图片", command=self.choose_image)
        self.open_button.pack(side="left")
        self.paste_button = ttk.Button(buttons, text="粘贴图片", command=self.paste_image)
        self.paste_button.pack(side="left", padx=(8, 0))
        self.decode_button = ttk.Button(buttons, text="重新识别", command=self.start_decode)
        self.decode_button.pack(side="left", padx=(8, 0))
        self.copy_button = ttk.Button(
            buttons, text="复制原始内容", command=self.copy_result, state="disabled"
        )
        self.copy_button.pack(side="left", padx=(18, 0))
        self.browser_button = ttk.Button(
            buttons, text="浏览器打开", command=self.open_in_browser, state="disabled"
        )
        self.browser_button.pack(side="left", padx=(8, 0))
        self.save_button = ttk.Button(
            buttons, text="另存干净二维码", command=self.save_clean_qr, state="disabled"
        )
        self.save_button.pack(side="left", padx=(8, 0))

        status_frame = ttk.Frame(main)
        status_frame.grid(row=4, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status = ttk.Label(status_frame, text="就绪")
        self.status.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=150)
        self.progress.grid(row=0, column=1, sticky="e")

        root.bind("<Control-v>", lambda _event: self.paste_image())

    def choose_image(self) -> None:
        from tkinter import filedialog, messagebox

        path = filedialog.askopenfilename(
            title="选择二维码图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.image = load_image(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.image_path = path
        self.show_preview(self.image)
        self.start_decode()

    def paste_image(self) -> None:
        from tkinter import messagebox

        try:
            clipboard = ImageGrab.grabclipboard()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"无法读取剪贴板：{exc}")
            return
        if isinstance(clipboard, Image.Image):
            self.image = _pil_to_cv(clipboard)
            self.image_path = None
        elif isinstance(clipboard, list) and clipboard:
            try:
                self.image_path = str(clipboard[0])
                self.image = load_image(self.image_path)
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc))
                return
        else:
            messagebox.showinfo(APP_TITLE, "剪贴板中没有图片或图片文件。")
            return
        self.show_preview(self.image)
        self.start_decode()

    def show_preview(self, image: np.ndarray) -> None:
        if image.ndim == 2:
            pil = Image.fromarray(image)
        else:
            pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        pil.thumbnail((300, 390), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(pil)
        self.preview.configure(image=self.preview_photo, text="")

    def start_decode(self) -> None:
        if self.image is None:
            return
        self.set_busy(True)
        self.result = None
        self.text.delete("1.0", "end")
        self.details.configure(text="")
        image = self.image.copy()
        threading.Thread(target=self._decode_worker, args=(image,), daemon=True).start()

    def _decode_worker(self, image: np.ndarray) -> None:
        try:
            result = decode_image(
                image,
                progress=lambda message: self.root.after(
                    0, lambda value=message: self.status.configure(text=value)
                ),
            )
            self.root.after(0, lambda: self.finish_decode(result, None))
        except Exception as exc:
            self.root.after(0, lambda: self.finish_decode(None, exc))

    def finish_decode(self, result: DecodeResult | None, error: Exception | None) -> None:
        from tkinter import messagebox

        self.set_busy(False)
        if error is not None:
            self.status.configure(text="识别出错")
            messagebox.showerror(APP_TITLE, str(error))
            return
        if result is None:
            self.status.configure(text="未能识别；可尝试裁掉无关背景后再试")
            self.text.insert(
                "1.0",
                "没有恢复出有效内容。\n\n建议：让二维码尽量占满图片、保留完整三个定位框，"
                "并避免严重反光或遮挡。",
            )
            return

        self.result = result
        self.text.insert("1.0", result.text)
        detail_parts = [f"方式：{result.method}"]
        if result.version is not None:
            detail_parts.append(f"Version {result.version}")
        if result.error_correction:
            detail_parts.append(f"纠错等级 {result.error_correction}")
        if result.timing_score is not None:
            detail_parts.append(f"时序匹配 {result.timing_score:.3f}")
        self.details.configure(text=" ｜ ".join(detail_parts))
        self.status.configure(text="识别成功；未访问该地址")
        self.copy_button.configure(state="normal")
        self.save_button.configure(state="normal")
        parsed = urlparse(result.text)
        if parsed.scheme in {"http", "https"}:
            self.browser_button.configure(state="normal")

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in (self.open_button, self.paste_button, self.decode_button):
            button.configure(state=state)
        self.copy_button.configure(state="disabled")
        self.browser_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def copy_result(self) -> None:
        if self.result is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.result.text)
        self.status.configure(text="已复制原始内容")

    def open_in_browser(self) -> None:
        from tkinter import messagebox

        if self.result is None:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "即将在默认浏览器打开二维码中的地址。\n\n只打开你信任的二维码，是否继续？",
        ):
            return
        webbrowser.open(self.result.text)

    def save_clean_qr(self) -> None:
        from tkinter import filedialog, messagebox

        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            title="另存干净二维码",
            defaultextension=".png",
            initialfile="clean-qrcode.png",
            filetypes=[("PNG 图片", "*.png")],
        )
        if not path:
            return
        try:
            _save_clean_qr(self.result.text, path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"保存失败：{exc}")
            return
        self.status.configure(text=f"已保存：{path}")


def _run_cli(path: str) -> int:
    try:
        result = decode_path(
            path,
            progress=lambda message: _console_print(message, sys.stderr),
        )
    except Exception as exc:
        _console_print(f"识别出错：{exc}", sys.stderr)
        return 1
    if result is None:
        _console_print("未识别出二维码内容。", sys.stderr)
        return 2
    _console_print(result.text, sys.stdout)
    details = [result.method]
    if result.version is not None:
        details.append(f"Version {result.version}")
    if result.error_correction:
        details.append(f"EC {result.error_correction}")
    _console_print(" | ".join(details), sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("image", nargs="?", help="启动后自动载入的二维码图片")
    parser.add_argument("--cli", action="store_true", help="使用命令行模式")
    arguments = parser.parse_args()
    if arguments.cli:
        if not arguments.image:
            _console_print("--cli 需要提供图片路径", sys.stderr)
            return 2
        return _run_cli(arguments.image)

    import tkinter as tk

    root = tk.Tk()
    app = QRRescueApp(root)
    if arguments.image:
        try:
            app.image_path = arguments.image
            app.image = load_image(arguments.image)
            app.show_preview(app.image)
            root.after(100, app.start_decode)
        except Exception:
            pass
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
