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
    conn_arg = f"connect {sys.argv[1]}" if len(sys.argv) > 1 else ""
    
    print("Checking mpremote installation and connection...")
    try:
        subprocess.run(f"mpremote {conn_arg} version", shell=True, check=True)
    except Exception:
        print("mpremote connection failed. Ensure device is plugged into the specified port.")
        return

    print("Creating directories on ESP32 Flash...")
    dirs = ["core", "fritz", "network", "services", "api", "www", "www/css", "www/js"]
    for d in dirs:
        subprocess.run(f"mpremote {conn_arg} fs mkdir :{d}", shell=True)

    print("Deploying core and fritz modules...")
    # Copy source files
    run_cmd(f"mpremote {conn_arg} fs cp src/boot.py :boot.py")
    run_cmd(f"mpremote {conn_arg} fs cp src/main.py :main.py")
    
    # Recursively copy subdirectories
    for d in ["core", "fritz", "network", "services", "api"]:
        src_dir = os.path.join("src", d)
        if os.path.exists(src_dir):
            for f in os.listdir(src_dir):
                if f.endswith(".py"):
                    run_cmd(f"mpremote {conn_arg} fs cp {src_dir}/{f} :{d}/{f}")

    print("Deployment finished successfully!")

if __name__ == "__main__":
    main()
