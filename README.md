# 二维码救援工具（QR Rescue）

一个面向 Windows 的离线二维码识别工具，专门处理普通扫码器难以识别的低质量图片，例如光照不均、静区不足、透视或曲面变形、低对比度和反复缩放后的二维码。

工具只读取二维码中实际编码的原始内容，识别阶段不会访问网址。因此，即使二维码网址打开后会发生 HTTP 重定向，也可以先复制跳转前的原始地址。

## 功能特点

- 完全本地识别，默认不发送图片、不访问二维码网址；
- 选择本地图片，或直接从剪贴板粘贴截图；
- 普通解码失败后，自动进行对比度增强、定位、纠偏与模块重建；
- 显示并复制二维码中未经跳转的原始内容；
- 将恢复出的内容重新生成清晰、规范的新二维码；
- 同时提供桌面界面和命令行模式；
- 支持包含中文字符的 Windows 文件路径。

## 快速使用

### 直接运行 EXE

从 GitHub Releases 下载 `qr-rescue-tool-v0.1.0-windows-x64.exe`，双击运行，无需安装 Python。

1. 点击“选择图片”，或者截图后点击“粘贴图片”（支持 `Ctrl+V`）；
2. 等待识别完成；
3. 点击“复制原始内容”；
4. 如需制作通用版本，点击“另存干净二维码”。

程序只有在你主动点击“浏览器打开”并再次确认后，才会访问二维码中的网址。

> PyInstaller 生成的程序没有商业数字签名，Windows SmartScreen 可能显示“未知发布者”。你可以从源码自行构建并核对行为。

### 从源码运行

源码运行需要 Windows 和 [uv](https://docs.astral.sh/uv/)。项目统一使用 uv 管理 Python 3.13 和虚拟环境，不依赖系统中预先安装的 `python`、`python3`、`py` 或 Conda。

例如，可以使用 Scoop 安装 uv：

```powershell
scoop install uv
```

安装 uv 后无需另外安装 Python；创建环境时，如果本机没有合适的 Python 3.13，uv 会自动下载并管理它。

最简单的方式是双击：

```text
run-qr-rescue-tool.bat
```

首次运行会用 Python 3.13 创建项目目录下的 `.venv`，并从 `requirements.txt` 安装依赖。运行依赖锁定为经过疑难二维码样本验证的版本，保证源码运行和 Release 构建使用一致的解码环境。后续运行也会快速检查依赖，避免首次安装中断后留下不完整环境。

也可以手动执行：

```powershell
uv venv --python 3.13
uv pip install -r requirements.txt
.\.venv\Scripts\python.exe qr_rescue.py
```

命令行解码：

```powershell
.\.venv\Scripts\python.exe qr_rescue.py --cli "D:\path\to\qrcode.png"
```

识别成功时，原始内容写入标准输出，识别方式和二维码信息写入标准错误；失败时退出码为 `2`。

> GitHub Release 中的 EXE 是无控制台窗口的桌面版本。需要在终端中读取输出时，请使用上面的 Python 源码命令；窗口版 EXE 的 `--cli` 参数主要用于自动化自检，只提供退出码。

## 它是如何工作的

工具使用分层策略，清晰二维码不会进入耗时的高级流程：

1. 使用 ZXing-C++ 和 OpenCV 进行普通解码；
2. 补充静区，尝试局部对比度增强、Otsu 和自适应二值化；
3. 搜索三个定位框并建立二维码坐标系；
4. 根据黑白交替的时序线判断二维码 Version；
5. 搜索内部校正点，拟合透视、拍摄和轻微曲面形变；
6. 将原图重新采样为标准模块网格；
7. 使用多组局部阈值和逐模块重建结果再次纠错解码。

这不是绕过加密或访问控制。它恢复的只是图片中原本就存在的二维码数据。

## 适用范围与限制

适合尝试：

- 微信等少数应用能识别、通用扫码器失败的图片；
- 拍摄后有颜色偏移、亮度渐变或轻度模糊的二维码；
- 四周留白不足、被非纯色背景包围的二维码；
- 发生透视、旋转或轻微曲面变形的二维码。

无法保证恢复：

- 三个大定位框被完全裁掉或严重遮挡；
- 大量模块已经缺失，超过二维码纠错能力；
- 二维码在图片中太小，每个模块不足约 2 像素；
- 图片并非标准 QR Code，例如某些平台专用的小程序码。

识别困难时，建议先裁掉无关背景，让二维码占据图片主体，并保留完整定位框。

## 隐私与安全

- 图片与识别结果仅在本机内存中处理；
- 识别过程不上传图片，也不请求二维码网址；
- “浏览器打开”需要用户主动点击和确认；
- 不建议打开来源不明的二维码网址；
- 二维码可能包含登录令牌、发票参数或其他敏感信息，请谨慎分享识别结果。

## 项目结构

```text
qr-rescue-tool/
├─ qr_rescue.py              # Tkinter 桌面界面、命令行入口与新二维码生成
├─ qr_rescue_core.py         # 解码、定位、Version 判断和网格重建
├─ version.py                # 发布版本号，决定 EXE 文件名
├─ requirements.txt          # Python 运行依赖
├─ qr-rescue-tool.spec       # PyInstaller 可复现打包配置
├─ run-qr-rescue-tool.bat    # Windows 源码启动器（纯 ASCII，避免代码页乱码）
└─ README.md
```

## 构建 Windows EXE

安装依赖和 PyInstaller：

```powershell
uv venv --python 3.13
uv pip install -r requirements.txt
uv pip install pyinstaller
```

使用仓库中的 `.spec` 配置构建：

```powershell
uv run pyinstaller --noconfirm --clean "qr-rescue-tool.spec"
```

输出文件位于：

```text
dist/qr-rescue-tool-v0.1.0-windows-x64.exe
```

`.spec` 是 PyInstaller 的构建配方，定义了入口脚本、需要额外收集的 ZXing/Pillow 组件、单文件输出和无控制台窗口等设置。仓库中的配置使用相对项目目录解析入口脚本，可以在不同路径下克隆后复现构建。

EXE 文件名由 `version.py` 中的 `__version__` 自动生成，格式固定为：

```text
qr-rescue-tool-v{version}-windows-x64.exe
```

准备新版本时，只需先修改 `version.py`，例如将 `0.1.0` 改为 `0.2.0`，再重新执行构建命令。

`build/` 和 `dist/` 默认被 Git 忽略。建议将 EXE 作为 GitHub Release 附件发布，不要直接提交到 Git 历史中。

## 发布 GitHub Release

1. 从干净的 Git 工作区执行上面的构建命令；
2. 本地测试 `dist/qr-rescue-tool-v0.1.0-windows-x64.exe`；
3. 在 GitHub 仓库中创建版本标签和 Release；
4. 将 EXE 上传为 Release 附件；
5. 在 Release Notes 中记录主要变化和 SHA-256 校验值。

生成校验值：

```powershell
Get-FileHash -Algorithm SHA256 ".\dist\qr-rescue-tool-v0.1.0-windows-x64.exe"
```

Release 标题和附件 Label 可以使用中文，但实际上传的附件文件名建议始终使用上述 ASCII 格式，避免 GitHub 将特殊字符规范化为 `default.exe`。

## 参与改进

欢迎提交 Issue，最好附上：

- 操作系统与工具版本；
- 原图尺寸、格式以及是否经过截图或压缩；
- 是否有其他扫码器能够识别；
- 在不泄露敏感信息的前提下提供脱敏样本。

提交包含新识别算法的 Pull Request 时，请同时提供可复现的测试样本或生成方法，并避免将真实票据、登录令牌等敏感二维码提交到公开仓库。

## 主要依赖

- [ZXing-C++](https://github.com/zxing-cpp/zxing-cpp)：二维码纠错解码；
- [OpenCV](https://opencv.org/)：图像增强、模板匹配与几何纠偏；
- [NumPy](https://numpy.org/)：模块网格与数值计算；
- [Pillow](https://python-pillow.org/)：图片预览和剪贴板处理；
- [python-qrcode](https://github.com/lincolnloop/python-qrcode)：生成干净二维码；
- [PyInstaller](https://pyinstaller.org/)：构建单文件 Windows 程序。

## 免责声明

本项目仅用于恢复和读取用户有权处理的二维码图片。它不会绕过网页权限、登录、防伪验证或服务端访问控制。请勿使用本工具处理或传播未经授权的敏感数据。
