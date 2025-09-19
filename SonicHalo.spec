# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\pyqt5_audio_visualiser_optimise.py'],
    pathex=[],
    binaries=[],
    datas=[('.\\media\\Px437_IBM_VGA_8x14.ttf', 'media')],
    hiddenimports=['winsdk.windows.media.control', 'winsdk.windows.media', 'winsdk.windows'],
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
    name='SonicHalo',
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
    icon=['media\\sonic_halo_2.ico'],
    hide_console='minimize-late',
)
