"""
EXE 打包专用启动入口：图形化界面（tkinter）。
支持 --minimized 参数启动时最小化到托盘。
"""
import sys
from gui import AIsChatGUI

if __name__ == "__main__":
    start_minimized = "--minimized" in sys.argv
    gui = AIsChatGUI(start_minimized=start_minimized)
    gui.run()
