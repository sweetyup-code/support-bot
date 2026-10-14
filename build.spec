# build.spec — PyInstaller конфиг
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# ---- скрытые импорты, которые PyInstaller не находит сам ----
hidden = []
hidden += collect_submodules("sentence_transformers")
hidden += collect_submodules("transformers")
hidden += collect_submodules("sklearn")
hidden += collect_submodules("joblib")
hidden += collect_submodules("playwright")
hidden += collect_submodules("PyQt6")
hidden += [
    "torch",
    "numpy",
    "scipy",
    "tokenizers",
    "huggingface_hub",
    "safetensors",
    "tqdm",
    "requests",
    "openai",
    "ui_selectors",
]

a = Analysis(
    ["gui.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        # только то, что должно быть вшито в exe (bat не нужен — вынесем наружу)
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # ускоряет сборку и уменьшает размер
        "tkinter",
        "matplotlib",
        "IPython",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SupportBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # без консольного окна
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # если есть иконка — укажи "icon.ico"
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SupportBot",
)