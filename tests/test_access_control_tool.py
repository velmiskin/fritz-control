import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import access_control


def test_access_control_requires_exact_confirmation(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    result = access_control.main([
        "--config", str(config),
        "--block", "192.168.178.30",
        "--confirm-block", "192.168.178.31",
    ])
    assert result == 1


def test_access_control_rejects_invalid_ip_before_config_read(tmp_path):
    result = access_control.main([
        "--config", str(tmp_path / "missing.json"),
        "--block", "192.168.178.999",
        "--confirm-block", "192.168.178.999",
    ])
    assert result == 1
