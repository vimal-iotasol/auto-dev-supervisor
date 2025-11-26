import os
import json
from typing import Dict, Optional
from pathlib import Path

class ConfigManager:
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Default to ~/.auto-dev
            self.config_dir = Path.home() / ".auto-dev"
        
        self.config_file = self.config_dir / "config.json"
        self._ensure_config_dir()
        self.config = self._load_config()

    def _ensure_config_dir(self):
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, str]:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save_config(self):
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=4)

    def set_api_key(self, provider: str, key: str):
        self.config[f"{provider.lower()}_api_key"] = key
        self._save_config()

    def get_api_key(self, provider: str) -> Optional[str]:
        # First check env var
        env_key = os.getenv(f"{provider.upper()}_API_KEY")
        if env_key:
            return env_key
        
        # Then check config
        return self.config.get(f"{provider.lower()}_api_key")

    def get_all_keys(self) -> Dict[str, str]:
        return {k: v for k, v in self.config.items() if k.endswith("_api_key")}
