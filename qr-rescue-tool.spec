# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy

from PyInstaller.utils.hooks import collect_all


# PyInstaller injects SPECPATH when executing this file.  Resolving the entry
# script from it keeps the build reproducible after the repository is cloned
# to a different directory.
project_root = Path(SPECPATH)
app_version = runpy.run_path(str(project_root / 'version.py'))['__version__']
release_name = f'qr-rescue-tool-v{app_version}-windows-x64'

datas = []
binaries = []
hiddenimports = ['PIL._tkinter_finder']
tmp_ret = collect_all('zxingcpp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(project_root / 'qr_rescue.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=release_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    # GUI errors are reported by the application itself.  Suppress the raw
    # PyInstaller traceback dialog that a windowed build would otherwise show.
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
