# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('onnxruntime')
# Also pack StegoForge web assets
datas.append(('web/templates/*', 'web/templates'))
datas.append(('web/static/*', 'web/static'))
# Bundle offline ML model so release works without network dependency.
datas.append(('models/model_quantized.onnx', 'models'))

a = Analysis(
    ['stegoforge.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[], # Removed conflicting hidden import
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['imageio_ffmpeg'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

import sys
is_win = (sys.platform == 'win32')

kwargs = dict(
    name='stegoforge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if is_win:
    kwargs['version'] = 'version_info.txt'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    **kwargs
)
