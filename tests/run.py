#!/usr/bin/env python3
"""Create a local test venv, prepare pinned wheels, and run every test."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

sys.dont_write_bytecode = True
from support import ROOT, WORK, isolated_env
from workspace import requirements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Never download dependencies")
    parser.add_argument("--wheel-dir", type=Path, help="Use an existing wheel directory")
    parser.add_argument("--pattern", default="test_*.py", help="unittest discovery pattern")
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("Tests require macOS or Linux")
    wheels = (args.wheel_dir or WORK / "wheels").resolve()
    if args.wheel_dir and not wheels.is_dir():
        parser.error("--wheel-dir must be an existing directory")
    wheels.mkdir(parents=True, exist_ok=True)
    prefix = WORK / "venv"
    py = prefix / "bin/python"
    if not py.is_file():
        venv.EnvBuilder(with_pip=True).create(prefix)
    env = isolated_env(WORK, AGENTDEV_TEST_WHEELS=str(wheels))
    deps = requirements(ROOT)
    if not args.offline:
        download_env = dict(env)
        download_env.pop("PIP_NO_INDEX")
        download_env.pop("PIP_FIND_LINKS")
        subprocess.run([str(py), "-m", "pip", "--isolated", "download", "--disable-pip-version-check",
                        "--cache-dir", str(WORK / "pip-cache"), "--only-binary=:all:",
                        "--dest", str(wheels), *deps], env=download_env, check=True)
    subprocess.run([str(py), "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
                    "--cache-dir", str(WORK / "pip-cache"), "--no-index", "--find-links", str(wheels), *deps], env=env, check=True)
    return subprocess.run([str(py), "-B", "-m", "unittest", "discover", "-s", str(ROOT / "tests"),
                           "-p", args.pattern, "-v"], cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
