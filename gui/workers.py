import os
from PyQt6.QtCore import QThread, pyqtSignal
import scanner
import builder

class ScanWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, fs_basepath, fs_game, qc_dir):
        super().__init__()
        self.fs_basepath = fs_basepath
        self.fs_game = fs_game
        self.qc_dir = qc_dir

    def run(self):
        data_path = os.path.join(self.fs_basepath, self.fs_game)
        qc_path = os.path.join(self.fs_basepath, self.qc_dir) if self.qc_dir else ""
        bsp_path = os.path.join(data_path, "maps")

        errors = []
        if not os.path.isdir(self.fs_basepath):
            errors.append(f"Project directory does not exist:\n{self.fs_basepath}")
        if not os.path.isdir(data_path):
            errors.append(f"Game data directory does not exist:\n{data_path}")
        if qc_path and not os.path.isdir(qc_path):
            errors.append(f"QC source directory does not exist:\n{qc_path}")

        if errors:
            self.error.emit("\n\n".join(errors))
            self.finished.emit({})
            return

        results = scanner.scan_all(qc_dir=qc_path, bsp_dir=bsp_path)
        self.finished.emit(results)

class BuildWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)
    
    def __init__(self, assets, config):
        super().__init__()
        self.assets = assets
        self.config = config
        self.fs_basepath = config["fs_basepath"]
        self.fs_game = config["fs_game"]
        
    def run(self):
        if self.config.get("build_mode") == "manifest":
            self.error.emit("Manifest release builds must use quakebuild.py so they can be verified.")
            return
        b = builder.Builder()
        b.log_callback = self.log_signal.emit
        b.set_paths(self.fs_basepath, self.fs_game)
        b.output_path = self.config.get("output_path", "")
        b.build_naming = self.config.get("build_naming", "date")
        b.pk3_packs = self.config.get("pk3_packs", [])
        b.ignore_patterns = self.config.get("ignore_patterns", [])
        b.set_config(
            self.config.get("includes", []),
            self.config.get("remove_paths", [])
        )
        
        try:
            build_name = b.run_build(custom_assets=self.assets)
            self.finished.emit(build_name)
        except Exception as e:
            self.log_signal.emit(f"FATAL ERROR: {str(e)}")
            self.finished.emit("")
