"""安卓慢速采集/OCR 的等待预算；桌面沿用原值，不增加固定休眠。"""
import os
import sys


def is_android() -> bool:
    return sys.platform == "android" or os.environ.get("MAAFGO_PLATFORM") == "android"


def platform_timeout(desktop: float, android: float) -> float:
    return android if is_android() else desktop
