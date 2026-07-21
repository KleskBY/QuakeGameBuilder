import os
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QFormLayout, QLineEdit, QPushButton,
                             QHBoxLayout, QFileDialog, QTabWidget, QVBoxLayout,
                             QPlainTextEdit, QLabel, QMessageBox, QComboBox,
                             QGroupBox, QScrollArea, QCheckBox)

class SettingsTab(QWidget):
    project_changed = pyqtSignal()
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Project File Toolbar ---
        project_bar = QHBoxLayout()

        self.lbl_project_file = QLabel("No project loaded")
        self.lbl_project_file.setStyleSheet("color: gray;")
        project_bar.addWidget(self.lbl_project_file)
        project_bar.addStretch()

        btn_load = QPushButton("Load Project")
        btn_load.clicked.connect(self.load_project_file)
        project_bar.addWidget(btn_load)

        btn_save_as = QPushButton("Save Project As...")
        btn_save_as.clicked.connect(self.save_project_as)
        project_bar.addWidget(btn_save_as)

        main_layout.addLayout(project_bar)

        # --- Settings Tabs ---
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- General Tab ---
        tab_general = QWidget()
        layout_gen = QFormLayout(tab_general)

        self.edit_fs_basepath = QLineEdit()
        btn_browse_game = QPushButton("...")
        btn_browse_game.setFixedWidth(30)
        btn_browse_game.clicked.connect(self.browse_fs_basepath)

        row_game = QHBoxLayout()
        row_game.addWidget(self.edit_fs_basepath)
        row_game.addWidget(btn_browse_game)
        layout_gen.addRow("Project Directory:", row_game)

        self.edit_fs_game = QLineEdit()
        btn_browse_fs_game = QPushButton("...")
        btn_browse_fs_game.setFixedWidth(30)
        btn_browse_fs_game.clicked.connect(self.browse_fs_game)

        row_fs_game = QHBoxLayout()
        row_fs_game.addWidget(self.edit_fs_game)
        row_fs_game.addWidget(btn_browse_fs_game)
        layout_gen.addRow("Game (Mod) Directory:", row_fs_game)

        self.edit_qc_dir = QLineEdit()
        self.edit_qc_dir.setPlaceholderText("Relative to project dir (e.g. qc)")
        btn_browse_qc = QPushButton("...")
        btn_browse_qc.setFixedWidth(30)
        btn_browse_qc.clicked.connect(self.browse_qc_dir)

        row_qc = QHBoxLayout()
        row_qc.addWidget(self.edit_qc_dir)
        row_qc.addWidget(btn_browse_qc)
        layout_gen.addRow("Source Code (QC) Directory:", row_qc)

        self.edit_output_path = QLineEdit()
        self.edit_output_path.setPlaceholderText("Leave empty to build in current directory")
        btn_browse_output = QPushButton("...")
        btn_browse_output.setFixedWidth(30)
        btn_browse_output.clicked.connect(self.browse_output_path)

        self.combo_naming = QComboBox()
        self.combo_naming.addItem("Date (build20260328)", "date")
        self.combo_naming.addItem("Numeric (build9623)", "numeric")
        layout_gen.addRow("Build Naming:", self.combo_naming)

        row_output = QHBoxLayout()
        row_output.addWidget(self.edit_output_path)
        row_output.addWidget(btn_browse_output)
        layout_gen.addRow("Output Path:", row_output)

        self.chk_open_after_build = QCheckBox("")
        layout_gen.addRow("Open location after build:", self.chk_open_after_build)

        self.tabs.addTab(tab_general, "General")

        # --- Includes Tab ---
        self.edit_includes = self.create_list_editor("Includes (files or dirs, one per line):")

        tab_includes = QWidget()
        layout_inc = QVBoxLayout(tab_includes)
        layout_inc.addWidget(QLabel("Unconditionally Included Paths (relative to Game Directory):"))

        inc_buttons = QHBoxLayout()
        btn_add_file = QPushButton("Add File...")
        btn_add_file.clicked.connect(self.browse_include_file)
        btn_add_folder = QPushButton("Add Folder...")
        btn_add_folder.clicked.connect(self.browse_include_folder)
        inc_buttons.addWidget(btn_add_file)
        inc_buttons.addWidget(btn_add_folder)
        inc_buttons.addStretch()
        layout_inc.addLayout(inc_buttons)

        layout_inc.addWidget(self.edit_includes)
        self.tabs.addTab(tab_includes, "Includes")

        # --- Excludes Tab ---
        self.edit_rem_paths = self.create_list_editor("Remove Paths (after build):")

        tab_excludes = QWidget()
        layout_exc = QVBoxLayout(tab_excludes)
        layout_exc.addWidget(QLabel("Files/Dirs to Remove (relative to data dir, use ../ for outside):"))
        layout_exc.addWidget(self.edit_rem_paths)
        self.tabs.addTab(tab_excludes, "Excludes")

        # --- Ignore / External Assets Tab ---
        self.edit_ignore_patterns = self.create_list_editor("Ignore Patterns:")

        tab_ignore = QWidget()
        layout_ign = QVBoxLayout(tab_ignore)
        layout_ign.addWidget(QLabel(
            "External / stock assets to exclude from the MISSING check.\n"
            "One glob pattern per line (e.g. sound/vox/*, maps/c2a2*.bsp).\n"
            "These are original Q1/HL1 assets the mod doesn't bundle; the end "
            "user supplies them."))
        layout_ign.addWidget(self.edit_ignore_patterns)
        self.tabs.addTab(tab_ignore, "Ignore")

        # --- PK3 Packs Tab ---
        tab_pk3 = QWidget()
        layout_pk3_outer = QVBoxLayout(tab_pk3)
        layout_pk3_outer.addWidget(QLabel("Pack directories into PK3 files. Each pack has a name and a list of paths to include."))

        self.pk3_scroll_area = QScrollArea()
        self.pk3_scroll_area.setWidgetResizable(True)
        self.pk3_container = QWidget()
        self.pk3_layout = QVBoxLayout(self.pk3_container)
        self.pk3_layout.addStretch()
        self.pk3_scroll_area.setWidget(self.pk3_container)
        layout_pk3_outer.addWidget(self.pk3_scroll_area)

        self.pk3_entries = []

        btn_add_pk3 = QPushButton("+ Add PK3 Pack")
        btn_add_pk3.clicked.connect(lambda: self._add_pk3_entry())
        layout_pk3_outer.addWidget(btn_add_pk3)

        self.tabs.addTab(tab_pk3, "Packs")

        # Save Button
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        main_layout.addWidget(btn_save)

    def create_list_editor(self, label):
        edit = QPlainTextEdit()
        return edit

    def _safe_relpath(self, path, base):
        """Compute relative path, falling back to absolute if on different drives."""
        try:
            return os.path.relpath(path, base).replace("\\", "/")
        except ValueError:
            return os.path.abspath(path).replace("\\", "/")

    def browse_fs_basepath(self):
        d = QFileDialog.getExistingDirectory(self, "Select Base Path (fs_basepath)", self.edit_fs_basepath.text())
        if d:
            self.edit_fs_basepath.setText(os.path.abspath(d))

    def browse_fs_game(self):
        start = self.edit_fs_basepath.text() or ""
        d = QFileDialog.getExistingDirectory(self, "Select Game (Mod) Directory", start)
        if d:
            base = self.edit_fs_basepath.text()
            if base:
                self.edit_fs_game.setText(self._safe_relpath(d, base))
            else:
                self.edit_fs_game.setText(os.path.basename(d))

    def browse_output_path(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.edit_output_path.text())
        if d:
            self.edit_output_path.setText(os.path.abspath(d))

    def browse_qc_dir(self):
        start = self.edit_fs_basepath.text() or ""
        d = QFileDialog.getExistingDirectory(self, "Select QC Source Directory", start)
        if d:
            base = self.edit_fs_basepath.text()
            if base:
                self.edit_qc_dir.setText(self._safe_relpath(d, base))
            else:
                self.edit_qc_dir.setText(os.path.abspath(d))

    def _get_data_dir(self):
        return os.path.join(self.edit_fs_basepath.text(), self.edit_fs_game.text())

    def _append_include(self, rel_path):
        text = self.edit_includes.toPlainText()
        if text and not text.endswith("\n"):
            text += "\n"
        text += rel_path
        self.edit_includes.setPlainText(text)

    def browse_include_file(self):
        data_dir = self._get_data_dir()
        files, _ = QFileDialog.getOpenFileNames(self, "Add File to Includes", data_dir)
        for f in files:
            self._append_include(self._safe_relpath(f, data_dir))

    def browse_include_folder(self):
        data_dir = self._get_data_dir()
        d = QFileDialog.getExistingDirectory(self, "Add Folder to Includes", data_dir)
        if d:
            self._append_include(self._safe_relpath(d, data_dir))

    def load_settings(self):
        config = self.config_manager.get_all()
        self.edit_fs_basepath.setText(config.get("fs_basepath", ""))
        self.edit_fs_game.setText(config.get("fs_game", "data"))
        self.edit_qc_dir.setText(config.get("qc_dir", "qc"))
        self.edit_output_path.setText(config.get("output_path", ""))

        naming = config.get("build_naming", "date")
        idx = self.combo_naming.findData(naming)
        self.combo_naming.setCurrentIndex(idx if idx >= 0 else 0)

        self.chk_open_after_build.setChecked(config.get("open_after_build", True))

        includes = config.get("includes", [])
        self.edit_includes.setPlainText("\n".join(includes))

        removes = config.get("remove_paths", [])
        self.edit_rem_paths.setPlainText("\n".join(removes))

        ignores = config.get("ignore_patterns", [])
        self.edit_ignore_patterns.setPlainText("\n".join(ignores))

        self._load_pk3_entries(config.get("pk3_packs", []))

        self._update_project_label()

    def sync_to_config(self):
        """Push current UI state into config manager (without saving to disk)."""
        self.config_manager.set_all(self._collect_config())

    def _collect_config(self):
        return {
            "fs_basepath": self.edit_fs_basepath.text(),
            "fs_game": self.edit_fs_game.text(),
            "qc_dir": self.edit_qc_dir.text(),
            "output_path": self.edit_output_path.text(),
            "build_naming": self.combo_naming.currentData(),
            "open_after_build": self.chk_open_after_build.isChecked(),
            "includes": self.get_list_from_editor(self.edit_includes),
            "remove_paths": self.get_list_from_editor(self.edit_rem_paths),
            "ignore_patterns": self.get_list_from_editor(self.edit_ignore_patterns),
            "pk3_packs": self._get_pk3_packs()
        }

    def save_settings(self):
        new_config = self._collect_config()

        self.config_manager.set_all(new_config)
        self.config_manager.save_config()
        QMessageBox.information(self, "Settings Saved", "Settings updated successfully.")

    def load_project_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Project Config", "",
            "JSON Files (*.json);;All Files (*)")
        if file_path:
            if self.config_manager.load_config(file_path):
                self.load_settings()
                self.project_changed.emit()
                QMessageBox.information(self, "Project Loaded",
                    f"Loaded: {os.path.basename(file_path)}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to load: {file_path}")

    def save_project_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project Config As", "",
            "JSON Files (*.json);;All Files (*)")
        if file_path:
            new_config = self._collect_config()
            self.config_manager.set_all(new_config)
            if self.config_manager.save_config(file_path):
                self._update_project_label()
                self.project_changed.emit()
                QMessageBox.information(self, "Project Saved",
                    f"Saved: {os.path.basename(file_path)}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to save: {file_path}")

    def _update_project_label(self):
        path = self.config_manager.config_file
        if path:
            self.lbl_project_file.setText(f"Project: {os.path.basename(path)}")
            self.lbl_project_file.setStyleSheet("")
        else:
            self.lbl_project_file.setText("No project loaded")
            self.lbl_project_file.setStyleSheet("color: gray;")

    def get_list_from_editor(self, editor):
        text = editor.toPlainText()
        return [line.strip() for line in text.split('\n') if line.strip()]

    def add_ignore_pattern(self, pattern):
        """Append a pattern to the ignore-patterns editor (deduped).
        Returns the updated list. Does NOT persist to disk — the user still
        clicks Save Settings for that."""
        patterns = self.get_list_from_editor(self.edit_ignore_patterns)
        if pattern not in patterns:
            patterns.append(pattern)
            self.edit_ignore_patterns.setPlainText("\n".join(patterns))
        return patterns

    # --- PK3 Packs ---

    def _add_pk3_entry(self, name="", paths_text=""):
        group = QGroupBox()
        layout = QVBoxLayout(group)

        row_top = QHBoxLayout()
        edit_name = QLineEdit(name)
        edit_name.setPlaceholderText("e.g. textures.pk3")
        row_top.addWidget(QLabel("PK3 Name:"))
        row_top.addWidget(edit_name)

        btn_remove = QPushButton("Remove")
        btn_remove.setFixedWidth(70)
        row_top.addWidget(btn_remove)
        layout.addLayout(row_top)

        edit_paths = QPlainTextEdit()
        edit_paths.setPlaceholderText("Paths to pack, one per line (e.g. textures, env, sound/ambient)")
        edit_paths.setPlainText(paths_text)
        edit_paths.setMaximumHeight(100)
        layout.addWidget(edit_paths)

        entry = {"group": group, "name": edit_name, "paths": edit_paths}
        self.pk3_entries.append(entry)

        btn_remove.clicked.connect(lambda: self._remove_pk3_entry(entry))

        # Insert before the stretch
        self.pk3_layout.insertWidget(self.pk3_layout.count() - 1, group)

    def _remove_pk3_entry(self, entry):
        self.pk3_entries.remove(entry)
        entry["group"].deleteLater()

    def _load_pk3_entries(self, pk3_packs):
        # Clear existing
        for entry in self.pk3_entries:
            entry["group"].deleteLater()
        self.pk3_entries.clear()

        for pack in pk3_packs:
            name = pack.get("name", "")
            paths = pack.get("paths", [])
            self._add_pk3_entry(name, "\n".join(paths))

    def _get_pk3_packs(self):
        packs = []
        for entry in self.pk3_entries:
            name = entry["name"].text().strip()
            paths_text = entry["paths"].toPlainText()
            paths = [p.strip() for p in paths_text.split('\n') if p.strip()]
            if name and paths:
                packs.append({"name": name, "paths": paths})
        return packs
