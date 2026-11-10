"""
src/core/config.py - Configuration manager for FritzControl
Loads JSON configuration from Flash storage with safe fallbacks.
"""

import json
from core.logger import log

DEFAULT_CONFIG = {
    "wifi": {
        "ssid": "",
        "password": ""
    },
    "fritzbox": {
        "host": "192.168.178.1",
        "port": 49000,
        "ssl_port": 49443,
        "use_ssl": False,
        "username": "",
        "password": ""
    },
    "web": {
        "port": 80,
        "admin_password": ""
    },
    "ntp": {
        "server": "pool.ntp.org",
        "timezone_offset_hours": 1
    },
    "system": {
        "watchdog_timeout_sec": 60,
        "log_level": "INFO"
    }
}

def _copy_dict(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _copy_dict(v)
        else:
            out[k] = v
    return out

class Config:
    def __init__(self, config_dict=None):
        self._data = config_dict if config_dict is not None else _copy_dict(DEFAULT_CONFIG)

    @classmethod
    def load(cls, path="config.json"):
        cfg_data = _copy_dict(DEFAULT_CONFIG)
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
                for sec, val in loaded.items():
                    if isinstance(val, dict) and sec in cfg_data and isinstance(cfg_data[sec], dict):
                        cfg_data[sec].update(val)
                    else:
                        cfg_data[sec] = val
            log.info(f"Loaded config from {path}")
        except OSError:
            log.warn(f"Config file {path} not found. Using defaults.")
        except Exception as e:
            log.error(f"Error parsing config {path}: {e}. Using defaults.")

        return cls(cfg_data)

    def get(self, section, key=None, default=None):
        sec_val = self._data.get(section)
        if sec_val is None:
            return default
        if key is None:
            return sec_val
        if isinstance(sec_val, dict):
            return sec_val.get(key, default)
        return default

    @property
    def fritz_host(self):
        return self.get("fritzbox", "host", "192.168.178.1")

    @property
    def fritz_port(self):
        use_ssl = self.get("fritzbox", "use_ssl", False)
        return self.get("fritzbox", "ssl_port", 49443) if use_ssl else self.get("fritzbox", "port", 49000)

    @property
    def fritz_user(self):
        return self.get("fritzbox", "username", "")

    @property
    def fritz_password(self):
        return self.get("fritzbox", "password", "")

    @property
    def fritz_use_ssl(self):
        return self.get("fritzbox", "use_ssl", False)

    @property
    def web_port(self):
        return self.get("web", "port", 80)

    @property
    def web_password(self):
        return self.get("web", "admin_password", "")
