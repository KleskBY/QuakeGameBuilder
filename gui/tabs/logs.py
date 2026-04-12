from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit)

class BuildLogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def append(self, text):
        self.log_view.append(text)

    def clear(self):
        self.log_view.clear()
