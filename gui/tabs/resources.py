import os
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QLabel,
                             QSplitter, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices

class ResourceTreeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.reverse_map = {}
        self.missing_files = set()
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left: Resource Directory Tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("<b>Build Resource Tree</b>"))
        self.tree_build = QTreeWidget()
        self.tree_build.setHeaderLabel("Resource Path")
        self.tree_build.itemClicked.connect(self.on_resource_node_selected)
        left_layout.addWidget(self.tree_build)

        self.lbl_missing_count = QLabel("")
        left_layout.addWidget(self.lbl_missing_count)

        splitter.addWidget(left_widget)

        # Right: Referrers List
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("<b>Referenced By (Source Files)</b>"))
        self.list_referrers = QListWidget()
        self.list_referrers.itemDoubleClicked.connect(self.on_referrer_double_clicked)
        right_layout.addWidget(self.list_referrers)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 500])

    def update_data(self, scanned_data, data_root=""):
        self.tree_build.clear()
        self.list_referrers.clear()
        self.reverse_map = {}
        self.missing_files = set()

        # 1. Build Reverse Map
        for src_path, resources in scanned_data.items():
            for res in resources:
                if res not in self.reverse_map:
                    self.reverse_map[res] = set()
                self.reverse_map[res].add(src_path)

        # 2. Check which files exist on disk
        if data_root:
            for res_path in self.reverse_map:
                full_path = os.path.join(data_root, res_path)
                if not os.path.isfile(full_path):
                    self.missing_files.add(res_path)

        # 3. Build Tree Nodes
        self.tree_nodes = {}
        red = QColor(220, 60, 60)

        for res_path in sorted(self.reverse_map.keys()):
            parts = res_path.split('/')
            parent_item = self.tree_build.invisibleRootItem()
            current_path = ""
            is_missing = res_path in self.missing_files

            for i, part in enumerate(parts):
                if current_path:
                    current_path += "/" + part
                else:
                    current_path = part

                if current_path not in self.tree_nodes:
                    new_item = QTreeWidgetItem(parent_item)
                    new_item.setText(0, part)
                    # If it's the leaf (file), store data
                    if i == len(parts) - 1:
                        new_item.setData(0, Qt.ItemDataRole.UserRole, res_path)
                        ref_count = len(self.reverse_map[res_path])
                        new_item.setText(0, f"{part} [{ref_count}]")
                        if is_missing:
                            new_item.setForeground(0, red)
                            new_item.setText(0, f"{part} [{ref_count}] (MISSING)")
                        else:
                            new_item.setForeground(0, Qt.GlobalColor.lightGray)
                    else:
                        new_item.setForeground(0, Qt.GlobalColor.darkGray)

                    self.tree_nodes[current_path] = new_item
                else:
                    # Propagate red to parent folders that contain missing files
                    if is_missing and i < len(parts) - 1:
                        existing = self.tree_nodes[current_path]
                        existing.setForeground(0, red)

                parent_item = self.tree_nodes[current_path]

        # 4. Update missing count label
        total = len(self.reverse_map)
        missing = len(self.missing_files)
        if missing > 0:
            self.lbl_missing_count.setText(
                f"<span style='color: #dc3c3c;'>{missing} missing</span> out of {total} resources")
        elif data_root:
            self.lbl_missing_count.setText(f"All {total} resources found on disk")
        else:
            self.lbl_missing_count.setText(f"{total} resources")

    def on_resource_node_selected(self, item, column):
        res_path = item.data(0, Qt.ItemDataRole.UserRole)
        self.list_referrers.clear()

        if res_path and res_path in self.reverse_map:
            # Show missing file warning at top
            if res_path in self.missing_files:
                warning = QListWidgetItem(f"FILE NOT FOUND: {res_path}")
                warning.setForeground(QColor(220, 60, 60))
                self.list_referrers.addItem(warning)

            sources = self.reverse_map[res_path]
            for s in sorted(sources):
                label = os.path.basename(s) + " (" + os.path.dirname(s) + ")"
                list_item = QListWidgetItem(label)
                list_item.setData(Qt.ItemDataRole.UserRole, s)
                self.list_referrers.addItem(list_item)

    def on_referrer_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
