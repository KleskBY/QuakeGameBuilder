import os
import json
from copy import deepcopy

from project_config import DEFAULT_CONFIG, load_project_config

APP_STATE_FILE = "app_state.json"

class ConfigManager:
    """Manages loading and saving of builder configuration."""
    def __init__(self):
        self.config = deepcopy(DEFAULT_CONFIG)
        self.config_file = None
        self._load_app_state()

    def _load_app_state(self):
        """Load app state to find the last used config file."""
        if os.path.exists(APP_STATE_FILE):
            try:
                with open(APP_STATE_FILE, 'r') as f:
                    state = json.load(f)
                last_file = state.get("last_config_file", "")
                if last_file and os.path.exists(last_file):
                    self.load_config(last_file)
                    return
            except Exception:
                pass
        # Fallback: try legacy config in current directory
        if os.path.exists("builder_config.json"):
            self.load_config("builder_config.json")

    def _save_app_state(self):
        """Save app state with the current config file path."""
        try:
            with open(APP_STATE_FILE, 'w') as f:
                json.dump({"last_config_file": self.config_file or ""}, f, indent=4)
        except Exception:
            pass

    def load_config(self, file_path):
        """Load config from a specific JSON file."""
        try:
            self.config = load_project_config(file_path)
            self.config_file = os.path.abspath(file_path)
            self._save_app_state()
            return True
        except Exception:
            return False

    def save_config(self, file_path=None):
        """Save config to a specific file, or the current one."""
        target = file_path or self.config_file
        if not target:
            target = "builder_config.json"
        try:
            with open(target, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.config_file = os.path.abspath(target)
            self._save_app_state()
            return True
        except Exception as e:
            print(f"Failed to save config: {e}")
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def get_all(self):
        return self.config

    def set_all(self, new_config):
        self.config = new_config
