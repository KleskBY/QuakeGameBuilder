import os
import fnmatch
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QLabel,
                             QSplitter, QListWidget, QListWidgetItem, QMenu)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices

class ResourceTreeTab(QWidget):
    # Emitted when the user marks a MISSING resource as an external asset.
    # Payload is the exact resource path (e.g. "sound/vox/foo.wav").
    ignore_pattern_added = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reverse_map = {}
        self.missing_files = set()
        self.archived_files = {}   # res_path -> archive basename
        self.ignored_files = set()
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
        self.tree_build.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_build.customContextMenuRequested.connect(self.on_tree_context_menu)
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

    def update_data(self, scanned_data, data_root="", archive_index=None, ignore_patterns=None):
        self.tree_build.clear()
        self.list_referrers.clear()
        self.reverse_map = {}
        self.missing_files = set()
        self.archived_files = {}
        self.ignored_files = set()

        archive_index = archive_index or {}
        ignore_patterns = ignore_patterns or []

        # 1. Build Reverse Map
        for src_path, resources in scanned_data.items():
            for res in resources:
                if res not in self.reverse_map:
                    self.reverse_map[res] = set()
                self.reverse_map[res].add(src_path)

        # 2. Classify each resource: on-disk / in-archive / ignored / missing
        if data_root:
            for res_path in self.reverse_map:
                full_path = os.path.join(data_root, res_path)
                if os.path.isfile(full_path):
                    continue  # present as a loose file — fine
                key = res_path.replace("\\", "/").lower()
                archive = archive_index.get(key)
                if archive:
                    self.archived_files[res_path] = archive
                elif self._matches_ignore(key, ignore_patterns):
                    self.ignored_files.add(res_path)
                else:
                    self.missing_files.add(res_path)

        # 3. Build Tree Nodes
        self.tree_nodes = {}
        red = QColor(220, 60, 60)
        amber = QColor(210, 150, 40)
        gray = QColor(140, 140, 140)

        for res_path in sorted(self.reverse_map.keys()):
            parts = res_path.split('/')
            parent_item = self.tree_build.invisibleRootItem()
            current_path = ""
            is_missing = res_path in self.missing_files
            is_archived = res_path in self.archived_files
            is_ignored = res_path in self.ignored_files

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
                        if is_missing:
                            new_item.setForeground(0, red)
                            new_item.setText(0, f"{part} [{ref_count}] (MISSING)")
                        elif is_archived:
                            new_item.setForeground(0, amber)
                            new_item.setText(0, f"{part} [{ref_count}] (in {self.archived_files[res_path]})")
                        elif is_ignored:
                            new_item.setForeground(0, gray)
                            new_item.setText(0, f"{part} [{ref_count}] (external, not bundled)")
                        else:
                            new_item.setForeground(0, Qt.GlobalColor.lightGray)
                            new_item.setText(0, f"{part} [{ref_count}]")
                    else:
                        new_item.setForeground(0, Qt.GlobalColor.darkGray)

                    self.tree_nodes[current_path] = new_item
                else:
                    # Propagate red to parent folders that contain missing files.
                    # (archived/ignored are non-problems — don't color parents.)
                    if is_missing and i < len(parts) - 1:
                        existing = self.tree_nodes[current_path]
                        existing.setForeground(0, red)

                parent_item = self.tree_nodes[current_path]

        # 4. Update status label
        total = len(self.reverse_map)
        missing = len(self.missing_files)
        archived = len(self.archived_files)
        ignored = len(self.ignored_files)
        if not data_root:
            self.lbl_missing_count.setText(f"{total} resources")
        else:
            parts = []
            if missing:
                parts.append(f"<span style='color: #dc3c3c;'>{missing} missing</span>")
            if archived:
                parts.append(f"<span style='color: #d2963c;'>{archived} in archives</span>")
            if ignored:
                parts.append(f"<span style='color: #8c8c8c;'>{ignored} external</span>")
            if parts:
                self.lbl_missing_count.setText(", ".join(parts) + f" out of {total} resources")
            else:
                self.lbl_missing_count.setText(f"All {total} resources found on disk")

    def _matches_ignore(self, key, patterns):
        for pat in patterns:
            if fnmatch.fnmatch(key, pat.lower()):
                return True
        return False

    def on_resource_node_selected(self, item, column):
        res_path = item.data(0, Qt.ItemDataRole.UserRole)
        self.list_referrers.clear()

        if res_path and res_path in self.reverse_map:
            # Show classification status at top
            if res_path in self.missing_files:
                warning = QListWidgetItem(f"FILE NOT FOUND: {res_path}")
                warning.setForeground(QColor(220, 60, 60))
                self.list_referrers.addItem(warning)
            elif res_path in self.archived_files:
                info = QListWidgetItem(f"FOUND IN ARCHIVE: {self.archived_files[res_path]}")
                info.setForeground(QColor(210, 150, 40))
                self.list_referrers.addItem(info)
            elif res_path in self.ignored_files:
                info = QListWidgetItem("IGNORED (external asset, not bundled)")
                info.setForeground(QColor(140, 140, 140))
                self.list_referrers.addItem(info)

            sources = self.reverse_map[res_path]
            for s in sorted(sources):
                label = os.path.basename(s) + " (" + os.path.dirname(s) + ")"
                list_item = QListWidgetItem(label)
                list_item.setData(Qt.ItemDataRole.UserRole, s)
                self.list_referrers.addItem(list_item)

    def on_tree_context_menu(self, pos):
        item = self.tree_build.itemAt(pos)
        if not item:
            return
        res_path = item.data(0, Qt.ItemDataRole.UserRole)
        # Only offer the action on a MISSING leaf.
        if not res_path or res_path not in self.missing_files:
            return
        menu = QMenu(self)
        act = menu.addAction("Mark as external asset (ignore)")
        chosen = menu.exec(self.tree_build.viewport().mapToGlobal(pos))
        if chosen == act:
            self.ignore_pattern_added.emit(res_path)

    def on_referrer_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
