#!/usr/bin/env python3
"""仅供旧版更新器/hook 使用的路径兼容入口；实现已迁移。"""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
runpy.run_path(str(Path(__file__).resolve().parent / "command/app.py"), run_name="__main__")
