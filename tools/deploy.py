"""Upload FritzControl source and static assets with mpremote."""

import argparse
from pathlib import Path, PurePosixPath
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("core", "fritz", "net", "services", "api")


def mpremote_prefix(port=None):
    command = ["mpremote"]
    if port:
        command.extend(("connect", port))
    return command


def collect_deploy_files(project_root=PROJECT_ROOT):
    files = []
    src_root = project_root / "src"
    for directory in SOURCE_DIRS:
        source_dir = src_root / directory
        if source_dir.is_dir():
            for path in sorted(source_dir.rglob("*.py")):
                relative = path.relative_to(src_root)
                files.append((path, PurePosixPath(relative.as_posix())))
    www_root = project_root / "www"
    if www_root.is_dir():
        for path in sorted(item for item in www_root.rglob("*") if item.is_file()):
            relative = path.relative_to(project_root)
            files.append((path, PurePosixPath(relative.as_posix())))
    # Entrypoints are uploaded last so an automatic reset cannot start a new
    # application against a partially updated module set or dashboard.
    for name in ("boot.py", "main.py"):
        path = src_root / name
        if path.is_file():
            files.append((path, PurePosixPath(name)))
    return files


def collect_remote_directories(files):
    directories = set()
    for _, remote in files:
        parent = remote.parent
        while str(parent) != ".":
            directories.add(str(parent))
            parent = parent.parent
    return sorted(directories, key=lambda value: (value.count("/"), value))


def run_command(command, check=True, capture_output=False):
    print("->", subprocess.list2cmdline([str(item) for item in command]))
    return subprocess.run(
        [str(item) for item in command],
        check=check,
        capture_output=capture_output,
        text=capture_output,
    )


def ensure_remote_directory(prefix, remote_dir):
    target = ":{}".format(remote_dir)
    result = run_command(prefix + ["fs", "mkdir", target], check=False,
                         capture_output=True)
    if result.returncode == 0:
        return
    # mkdir also fails when the directory exists; verify that case explicitly.
    run_command(prefix + ["fs", "ls", target], check=True, capture_output=True)


def deploy(port=None, project_root=PROJECT_ROOT, dry_run=False):
    files = collect_deploy_files(project_root)
    if not files:
        raise RuntimeError("No deployable files found")
    prefix = mpremote_prefix(port)
    directories = collect_remote_directories(files)
    if dry_run:
        for directory in directories:
            print("mkdir :{}".format(directory))
        for local, remote in files:
            print("copy {} -> :{}".format(local, remote))
        return files

    run_command(prefix + ["version"])
    for directory in directories:
        ensure_remote_directory(prefix, directory)
    for local, remote in files:
        target = ":{}".format(remote)
        run_command(prefix + ["fs", "cp", str(local), target])
        run_command(prefix + ["fs", "ls", target], capture_output=True)
    print("Deployment verified: {} files uploaded.".format(len(files)))
    return files


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", help="serial port, for example COM3")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the deployment manifest without connecting")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        deploy(port=args.port, dry_run=args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Deployment failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
