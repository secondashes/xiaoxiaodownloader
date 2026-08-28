"""兼容别名：从项目根目录 bunkr_api 导入（避免重复实现）。

保留此文件是为了兼容 plugin/pyqt_integration.py 的旧导入方式。
新代码请直接使用项目根目录的 bunkr_api.py。
"""

import sys
from pathlib import Path

# 让 plugin 子目录也能 import 项目根目录的 bunkr_api
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bunkr_api import BunkrAPI as BunkrPlugin  # noqa: E402
from bunkr_api import extract_bunkr_url, is_bunkr_url  # noqa: E402

__all__ = ["BunkrPlugin", "is_bunkr_url", "extract_bunkr_url"]
