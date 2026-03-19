import os

from PySide6.QtWidgets import QApplication
from app.gui.main_window import MainWindow
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    base_dir = os.path.dirname(__file__)
    style_path = os.path.join(base_dir, "app", "gui", "styles", "styles.qss")

    with open(style_path, "r") as f:
        app.setStyleSheet(f.read())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
