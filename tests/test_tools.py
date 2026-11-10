from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import deploy, flash, hardware_discovery, hardware_ntp, hardware_smoke


def test_deploy_manifest_includes_source_and_static_files(tmp_path):
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "www").mkdir()
    (tmp_path / "src" / "boot.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "core" / "config.py").write_text("", encoding="utf-8")
    (tmp_path / "www" / "index.html").write_text("", encoding="utf-8")
    (tmp_path / "www" / "css").mkdir()
    (tmp_path / "www" / "css" / "style.css").write_text("", encoding="utf-8")
    manifest = deploy.collect_deploy_files(tmp_path)
    remotes = {str(remote) for _, remote in manifest}
    assert remotes == {
        "boot.py", "core/config.py", "www/index.html", "www/css/style.css"
    }
    assert deploy.collect_remote_directories(manifest) == ["core", "www", "www/css"]


def test_deploy_commands_are_argument_lists(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    deploy.deploy("COM3 & echo unsafe", project_root=tmp_path)
    assert calls
    assert all(isinstance(command, list) for command, _ in calls)
    assert all("shell" not in kwargs for _, kwargs in calls)
    assert calls[0][0][:3] == ["mpremote", "connect", "COM3 & echo unsafe"]


def test_flash_commands_are_argument_lists(monkeypatch, tmp_path):
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(b"firmware")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(flash.subprocess, "run", fake_run)
    flash.flash("COM3 & echo unsafe", firmware, confirmed=True)
    assert len(calls) == 2
    assert all(isinstance(command, list) for command, _ in calls)
    assert all("shell" not in kwargs for _, kwargs in calls)
    assert "COM3 & echo unsafe" in calls[0][0]


def test_hardware_smoke_uses_isolated_staging_and_always_cleans(monkeypatch, tmp_path):
    for local_name, _ in hardware_smoke.FILES:
        path = tmp_path / local_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    script = tmp_path / "tests" / "hardware" / "phase25_smoke.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        returncode = 1 if len(calls) == 1 else 0
        stdout = "phase25_import_smoke PASS\n" if "run" in command else ""
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    monkeypatch.setattr(hardware_smoke.subprocess, "run", fake_run)
    output = hardware_smoke.run_hardware_smoke("COM3", project_root=tmp_path)
    assert "PASS" in output
    assert calls[-1][0][-4:] == ["fs", "rm", "-r", ":phase25_smoke"]
    assert all(isinstance(command, list) for command, _ in calls)
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_hardware_discovery_stages_config_and_always_cleans(monkeypatch, tmp_path):
    for local_name, _ in hardware_discovery.FILES:
        path = tmp_path / local_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    script = tmp_path / "tests" / "hardware" / "phase1_discovery.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        '{"wifi":{"ssid":"test","password":"secret"},'
        '"fritzbox":{"host":"192.0.2.1","username":"user",'
        '"password":"secret","use_ssl":false}}',
        encoding="utf-8",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        returncode = 1 if len(calls) == 1 else 0
        stdout = "phase1_discovery PASS\n" if "run" in command else ""
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    monkeypatch.setattr(hardware_discovery.subprocess, "run", fake_run)
    output = hardware_discovery.run_hardware_discovery(
        "COM3", config, project_root=tmp_path
    )
    assert "PASS" in output
    assert any(command[-1] == ":phase1_discovery/config.json"
               for command, _ in calls)
    assert calls[-1][0][-4:] == ["fs", "rm", "-r", ":phase1_discovery"]
    assert all(isinstance(command, list) for command, _ in calls)
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_hardware_discovery_rejects_placeholder_config(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        '{"wifi":{"ssid":"YOUR_WIFI_SSID","password":"secret"},'
        '"fritzbox":{"host":"192.0.2.1","username":"user",'
        '"password":"secret"}}',
        encoding="utf-8",
    )
    try:
        hardware_discovery.run_hardware_discovery("COM3", config, tmp_path)
    except RuntimeError as exc:
        assert "non-placeholder wifi.ssid" in str(exc)
    else:
        raise AssertionError("placeholder configuration was accepted")


def test_hardware_ntp_stages_config_and_always_cleans(monkeypatch, tmp_path):
    for local_name, _ in hardware_ntp.FILES:
        path = tmp_path / local_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    script = tmp_path / "tests" / "hardware" / "phase3_ntp.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        '{"wifi":{"ssid":"test","password":"secret"},'
        '"ntp":{"server":"pool.example"}}',
        encoding="utf-8",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        returncode = 1 if len(calls) == 1 else 0
        stdout = "phase3_ntp PASS\n" if "run" in command else ""
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    monkeypatch.setattr(hardware_ntp.subprocess, "run", fake_run)
    output = hardware_ntp.run_hardware_ntp("COM3", config, project_root=tmp_path)
    assert "PASS" in output
    assert any(command[-1] == ":phase3_ntp/config.json"
               for command, _ in calls)
    assert calls[-1][0][-4:] == ["fs", "rm", "-r", ":phase3_ntp"]
    assert all(isinstance(command, list) for command, _ in calls)
    assert all("shell" not in kwargs for _, kwargs in calls)
