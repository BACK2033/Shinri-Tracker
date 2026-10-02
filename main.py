from PySide6.QtWidgets import QApplication
from gui import MainWindow

import sys
from gui import STYLE, resource_path
from PySide6.QtGui import QIcon


if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )

    app.setWindowIcon(
        QIcon(resource_path("icon.png"))
    )

    app.setStyleSheet(
        STYLE
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )