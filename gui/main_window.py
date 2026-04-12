import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTabWidget,
                             QLabel, QMessageBox, QDialog, QDialogButtonBox)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from .config import ConfigManager
from .workers import ScanWorker, BuildWorker
from .tabs.analyzer import SourceAnalyzerTab
from .tabs.resources import ResourceTreeTab
from .tabs.logs import BuildLogTab
from .tabs.settings import SettingsTab
from .tabs.about import AboutTab

APP_VERSION = "0.1.0"
APP_AUTHOR = "KleskBY"
APP_REPO = "https://github.com/KleskBY/QuakeGameBuilder"
APP_WEBSITE = "https://quake.by"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quake Resource Builder")
        self.resize(1000, 700)
        
        self.config_manager = ConfigManager()
        self._update_title()

        # Data
        self.scanned_data = {} # { source_path: [resources] }

        # Menu Bar
        menu_bar = self.menuBar()
        
        self.scan_action = QAction("&Scan project", self)
        self.scan_action.triggered.connect(self.start_scan)
        menu_bar.addAction(self.scan_action)

        self.build_action = QAction("&Build", self)
        self.build_action.triggered.connect(self.start_build)
        menu_bar.addAction(self.build_action)

        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Toolbar / Header
        # toolbar = QHBoxLayout()
        
        # self.btn_scan = QPushButton("Scan Project")
        # self.btn_scan.clicked.connect(self.start_scan)
        
        # self.btn_build = QPushButton("Build Release")
        # self.btn_build.clicked.connect(self.start_build)
        
        # # Removed Modal Settings Button
        
        # toolbar.addWidget(self.btn_scan)
        # toolbar.addStretch()
        # toolbar.addWidget(self.btn_build)
        # main_layout.addLayout(toolbar)

        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Settings
        self.tab_settings = SettingsTab(config_manager=self.config_manager)
        self.tab_settings.project_changed.connect(self._update_title)
        self.tabs.addTab(self.tab_settings, "Settings")

        # Tab 2: Analyzer
        self.tab_analyzer = SourceAnalyzerTab()
        self.tabs.addTab(self.tab_analyzer, "Source Analyzer")

        # Tab 3: Resource Tree
        self.tab_res_tree = ResourceTreeTab()
        self.tabs.addTab(self.tab_res_tree, "Resource Tree")

        # Tab 4: Build Log
        self.tab_log = BuildLogTab()
        self.tabs.addTab(self.tab_log, "Build Log")

        self.tab_help = AboutTab()
        self.tabs.addTab(self.tab_help, "Help")
        
        # Menu Bar
        # menu_bar = self.menuBar()
        # help_menu = menu_bar.addMenu("&Help")

        # about_action = QAction("&About", self)
        # about_action.triggered.connect(self.show_about)
        # help_menu.addAction(about_action)

        # Status Bar
        self.status = QLabel("Ready")
        self.statusBar().addWidget(self.status)

    def _update_title(self):
        base = "Quake Resource Builder"
        config_file = self.config_manager.config_file
        if config_file:
            base += f" - {os.path.basename(config_file)}"
        self.setWindowTitle(base)

    # --- Scanning ---
    def start_scan(self):
        self.tab_settings.sync_to_config()
        self.scan_action.setEnabled(False)
        self.status.setText("Scanning resources...")
        config = self.config_manager.get_all()
        self.worker = ScanWorker(config["fs_basepath"], config["fs_game"], config.get("qc_dir", "qc"))
        self.worker.error.connect(self.on_scan_error)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.start()
        self.tabs.setCurrentWidget(self.tab_res_tree)

        
    def on_scan_error(self, message):
        self.scan_action.setEnabled(True)
        self.status.setText("Scan failed — invalid paths")
        QMessageBox.critical(self, "Scan Error", message)

    def on_scan_finished(self, results):
        self.scanned_data = results
        config = self.config_manager.get_all()
        data_root = os.path.join(config["fs_basepath"], config["fs_game"])

        self.tab_analyzer.update_data(results)
        self.tab_res_tree.update_data(results, data_root=data_root)

        missing = len(self.tab_res_tree.missing_files)
        total = sum(len(r) for r in results.values())
        status = f"Scan complete. Found {len(results)} source files, {total} resources."
        if missing:
            status += f" ({missing} missing files)"
        self.status.setText(status)
        # self.btn_scan.setEnabled(True)
        self.scan_action.setEnabled(True)

    # --- Building ---
    def start_build(self):
        self.tab_settings.sync_to_config()
        # Gather all scanned assets
        all_assets = set()
        for resources in self.scanned_data.values():
            all_assets.update(resources)

        if not all_assets:
            QMessageBox.warning(self, "No Assets", "No assets identified. Run a scan first.")
            return

        self.tabs.setCurrentWidget(self.tab_log)
        self.tab_log.clear()
        self.build_action.setEnabled(False)
        # self.btn_build.setEnabled(False)
        self.status.setText("Building...")
        
        config = self.config_manager.get_all()
        self.build_worker = BuildWorker(list(all_assets), config)
        self.build_worker.log_signal.connect(self.tab_log.append)
        self.build_worker.finished.connect(self.on_build_finished)
        self.build_worker.start()
        
    def on_build_finished(self, build_name):
        self.build_action.setEnabled(True)
        if build_name:
            self.status.setText(f"Build Success: {build_name}")
            self.tab_log.append(f"\nSUCCESS: Build saved to {build_name}")
            if self.config_manager.get("open_after_build", True):
                abs_path = os.path.abspath(build_name)
                QDesktopServices.openUrl(QUrl.fromLocalFile(abs_path))
        else:
            self.status.setText("Build Failed")

    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("About Quake Game Builder")
        dlg.setFixedSize(400, 250)
        layout = QVBoxLayout(dlg)

        title = QLabel(f"<h2>Quake Game Builder</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f"<b>Version:</b> {APP_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        author = QLabel(f"<b>Author:</b> {APP_AUTHOR}")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        info = QLabel(
            f'<p>Standalone build tool for DarkPlaces engine games.</p>'
            f'<p><b>Repository:</b> <a href="{APP_REPO}">{APP_REPO}</a></p>'
            f'<p><b>Website:</b> <a href="{APP_WEBSITE}">{APP_WEBSITE}</a></p>'
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)

        dlg.exec()
