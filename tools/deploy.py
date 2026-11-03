"""
tools/deploy.py - Upload source files to ESP32 using mpremote

Usage:
    python tools/deploy.py [PORT]
    e.g. python tools/deploy.py COM3
"""

import sys
import subprocess
import os

def run_cmd(cmd):
    print(f"-> {cmd}")
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"Command failed with code {res.returncode}")
        return False
    return True

def main():
    port_arg = f"--port {sys.argv[1]}" if len(sys.argv) > 1 else ""
    
    print("Checking mpremote installation...")
    try:
        subprocess.run(f"mpremote {port_arg} version", shell=True, check=True)
    except Exception:
        print("mpremote not found or device not connected. Install via: pip install mpremote")
        return

    print("Syncing src/ and www/ to ESP32 Flash...")
    # Create target directories on device
    dirs = ["core", "fritz", "network", "services", "api", "www", "www/css", "www/js"]
    for d in dirs:
        subprocess.run(f"mpremote {port_arg} fs mkdir :{d}", shell=True)

    # Sync files
    run_cmd(f"mpremote {port_arg} fs cp -r src/* :")
    run_cmd(f"mpremote {port_arg} fs cp -r www :")
    print("Deployment finished successfully!")

if __name__ == "__main__":
    main()
