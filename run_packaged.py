"""
EXE 打包专用启动入口：图形化界面（tkinter）。
导入 gui 模块并启动。
"""
from gui import AIsChatGUI

if __name__ == "__main__":
    gui = AIsChatGUI()
    gui.run()
