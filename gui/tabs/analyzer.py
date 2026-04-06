import os
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, 
                             QTreeWidget, QTreeWidgetItem, QLabel, 
                             QSplitter, QListWidget)
from PyQt6.QtCore import Qt

class SourceAnalyzerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scanned_data = {}
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Left: Sources Tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("<b>Source Files (Maps/QC)</b>"))
        self.tree_sources = QTreeWidget()
        self.tree_sources.setHeaderLabel("File")
        self.tree_sources.itemClicked.connect(self.on_source_selected)
        left_layout.addWidget(self.tree_sources)
        splitter.addWidget(left_widget)
        
        # Right: Resources List
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("<b>Used Resources</b>"))
        self.list_resources = QListWidget()
        right_layout.addWidget(self.list_resources)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([400, 600])

    def update_data(self, scanned_data):
        self.scanned_data = scanned_data
        self.tree_sources.clear()
        self.list_resources.clear()
        
        # Group by folder for nicer display
        dir_map = {}
        
        for path, resources in scanned_data.items():
            folder = os.path.dirname(path)
            filename = os.path.basename(path)
            
            if folder not in dir_map:
                dir_map[folder] = []
            dir_map[folder].append((filename, path, len(resources)))
            
        for folder in sorted(dir_map.keys()):
            root_item = QTreeWidgetItem(self.tree_sources)
            root_item.setText(0, folder)
            #root_item.setExpanded()
            
            for filename, full_path, res_count in sorted(dir_map[folder]):
                item = QTreeWidgetItem(root_item)
                item.setText(0, f"{filename} ({res_count})")
                item.setData(0, Qt.ItemDataRole.UserRole, full_path)

    def on_source_selected(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        self.list_resources.clear()
        
        if path and path in self.scanned_data:
            resources = self.scanned_data[path]
            for r in sorted(resources):
                self.list_resources.addItem(r)
