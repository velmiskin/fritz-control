import os
import sys
import tempfile
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core.config import Config, DEFAULT_CONFIG

def test_config_defaults():
    cfg = Config()
    assert cfg.fritz_host == "192.168.178.1"
    assert cfg.fritz_port == 49000
    assert cfg.fritz_use_ssl is False
    assert cfg.get("web", "port") == 80
    assert cfg.get("system", "watchdog_timeout_sec") == 60

def test_config_load_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
        json.dump({
            "fritzbox": {
                "host": "192.168.1.1",
                "use_ssl": True,
                "ssl_port": 49443,
                "username": "admin"
            }
        }, f)
        temp_path = f.name

    try:
        cfg = Config.load(temp_path)
        assert cfg.fritz_host == "192.168.1.1"
        assert cfg.fritz_port == 49443
        assert cfg.fritz_use_ssl is True
        assert cfg.fritz_user == "admin"
        # Verify defaults are preserved for unmentioned fields
        assert cfg.get("web", "port") == 80
    finally:
        os.remove(temp_path)

def test_config_missing_file_fallback():
    cfg = Config.load("non_existent_file_xyz.json")
    assert cfg.fritz_host == "192.168.178.1"
