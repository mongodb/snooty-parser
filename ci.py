#!/usr/bin/env python3
import datetime
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path
from typing import Optional, Sequence

SYSTEM_PYTHON = sys.executable
PLATFORM = f"{platform.system().lower()}_{platform.machine().lower()}"
VERSION = subprocess.check_output(
    ["git", "describe", "--tags"], encoding="utf-8"
).strip()

PACKAGE_NAME = Path(f"snooty-{VERSION}-{PLATFORM}.zip")
if "SOURCE_DATE_EPOCH" not in os.environ:
    SOURCE_DATE_EPOCH = int(
        datetime.datetime.strptime(
            subprocess.check_output(
                [
                    "git",
                    "show",
                    "-s",
                    "--format=%cd",
                    "--date=format:%Y-%m-%d %H:%M:%S",
                    "HEAD",
                ],
                encoding="utf-8",
            ).strip(),
            "%Y-%m-%d %H:%M:%S",
        ).timestamp()
    )
    os.environ["SOURCE_DATE_EPOCH"] = str(SOURCE_DATE_EPOCH)
else:
    SOURCE_DATE_EPOCH = int(os.environ["SOURCE_DATE_EPOCH"])
VENV_PATH = Path(".venv").resolve()
VENV_EXISTS_PATH = Path(".venv/.EXISTS")


def install(mode: int, source: Sequence[Path], target: Path) -> None:
    for source_path in source:
        target_path = target / source_path.name
        shutil.copyfile(source_path, target_path)
        target_path.chmod(mode)


def run_in_venv(args: Sequence[str], deterministic: bool = False) -> None:
    print("Run in environment: " + repr(args))
    environment = os.environ.copy()
    environment["VIRTUAL_ENV"] = VENV_PATH.as_posix()
    try:
        del environment["PYTHONHOME"]
    except KeyError:
        pass
    environment["PATH"] = (VENV_PATH / "bin").as_posix() + ":" + environment["PATH"]
    if deterministic:
        environment["PYTHONHASHSEED"] = str(SOURCE_DATE_EPOCH)
    subprocess.check_call(args, env=environment)


def build_zipfile(root: Path, output: Path) -> None:
    epoch = datetime.datetime.utcfromtimestamp(SOURCE_DATE_EPOCH)
    paths = sorted((path for path in root.glob("**/*") if path.is_file()))
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as myzip:
        for path in paths:
            data = path.read_bytes()
            stat = path.stat()
            zipinfo = zipfile.ZipInfo.from_file(path, arcname=path.relative_to(root))
            zipinfo.compress_type = zipfile.ZIP_DEFLATED

            # Eliminate things that prohibit reproducibility
            zipinfo.date_time = (
                epoch.year,
                epoch.month,
                epoch.day,
                epoch.hour,
                epoch.minute,
                epoch.second,
            )
            zipinfo.external_attr = (0o100000 | stat.st_mode) << 16

            myzip.writestr(zipinfo, data)


def ensure_venv() -> None:
    pyproject_stat = os.stat("pyproject.toml")
    try:
        exists_stat: Optional[os.stat_result] = VENV_EXISTS_PATH.stat()
    except FileNotFoundError:
        exists_stat = None

    if exists_stat and pyproject_stat.st_mtime <= exists_stat.st_mtime:
        return

    print("Creating venv")

    try:
        os.unlink("snootycli.py")
    except FileNotFoundError:
        pass

    try:
        shutil.rmtree(".venv")
    except FileNotFoundError:
        pass

    venv.create(".venv", with_pip=True)
    run_in_venv(["python3", "-m", "pip", "install", "--upgrade", "pip"])
    run_in_venv(["python3", "-m", "pip", "install", "flit"])
    run_in_venv(["flit", "install", "-s", "--deps=develop"])
    VENV_EXISTS_PATH.touch()


def cmd_lint() -> None:
    """Run all linting"""
    ensure_venv()
    run_in_venv(["python3", "-m", "mypy", "--strict", "snooty", "tools", "ci.py"])
    run_in_venv(["python3", "-m", "pyflakes", "snooty", "tools", "ci.py"])
    run_in_venv(["python3", "-m", "black", "snooty", "tools", "ci.py", "--check"])
    subprocess.check_call([SYSTEM_PYTHON, "tools/lint_changelog.py", "CHANGELOG.md"])


def cmd_format() -> None:
    """Format source code with black"""
    ensure_venv()
    run_in_venv(["python3", "-m", "isort", "snooty", "tools", "ci.py"])
    run_in_venv(["python3", "-m", "black", "snooty", "tools", "ci.py"])


def cmd_test() -> None:
    """Run unit tests"""
    ensure_venv()
    run_in_venv(["python3", "-X", "dev", "-m", "pytest", "--cov=snooty"])


def cmd_clean() -> None:
    """Remove all build artifacts"""
    try:
        os.unlink("snootycli.py")
    except FileNotFoundError:
        pass

    for path in glob.glob("snooty.tar.zip*"):
        os.unlink(path)

    try:
        shutil.rmtree(".venv")
    except FileNotFoundError:
        pass

    try:
        shutil.rmtree("dist")
    except FileNotFoundError:
        pass

    try:
        shutil.rmtree(".docs")
    except FileNotFoundError:
        pass


def cmd_help() -> None:
    """Print help strings"""
    for name, value in globals().items():
        if name.startswith("cmd_"):
            print(f"{name[4:]}: {value.__doc__}")


DOCS_COMMIT = "1c6dfe71fd45fbdcdf5c7b73f050f615f4279064"


def cmd_performance_report() -> None:
    """Fetch a sample corpus, and generate a timing report for each part of the parse"""
    if not Path(".docs").exists():
        subprocess.check_call(
            ["git", "clone", "https://github.com/mongodb/docs.git", ".docs"]
        )

    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=".docs", encoding="utf-8"
        )
        != DOCS_COMMIT
    ):
        subprocess.check_call(["git", "fetch"], cwd=".docs")
        subprocess.check_call(["git", "reset", "--hard", DOCS_COMMIT], cwd=".docs")

    run_in_venv(["python3", "-m", "snooty.performance_report", ".docs"])


def cmd_package(sign: bool = False) -> None:
    """Generate a binary package"""

    ensure_venv()

    try:
        shutil.rmtree("snooty.dist")
    except FileNotFoundError:
        pass

    try:
        shutil.rmtree("dist")
    except FileNotFoundError:
        pass

    os.mkdir("dist")
    with open("snootycli.py", "w") as f:
        f.write("from snooty import main; main.main()\n")

    run_in_venv(
        ["python3", "-m", "PyInstaller", "-n", "snooty", "snootycli.py"],
        deterministic=True,
    )
    os.unlink("snootycli.py")

    install(
        0o644,
        [
            Path("snooty/config.toml"),
            Path("snooty/rstspec.toml"),
            *(Path(p) for p in glob.glob("LICENSE*")),
        ],
        Path("dist/snooty/"),
    )
    Path("dist/snooty/.EXISTS").touch()

    # Normalize the mtime, and zip in sorted order
    build_zipfile(Path("dist"), PACKAGE_NAME)

    # Ensure that the generated binary runs
    subprocess.check_call(["./dist/snooty/snooty", "--help"])
    print(f"::set-output name=package_filename::${PACKAGE_NAME.name}")

    if sign:
        subprocess.check_call(
            ["gpg", "--armor", "--detach-sig", (Path("dist") / PACKAGE_NAME).as_posix()]
        )


def cmd_cut_release() -> None:
    """Release a new version of snooty. Must provide BUMP_TO_VERSION"""
    BUMP_TO_VERSION = os.environ["BUMP_TO_VERSION"]

    if re.match(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[\w_-]+)?$", BUMP_TO_VERSION) is None:
        print(
            "Must specify a valid BUMP_TO_VERSION (e.g. 'ci.py cut-release BUMP_TO_VERSION=0.1.15')"
        )
        sys.exit(1)

    try:
        subprocess.check_call(["git", "diff-index", "--quiet", "HEAD", "--"])
    except subprocess.CalledProcessError:
        print("Uncommitted changes found: aborting release")
        sys.exit(1)

    cmd_clean()
    subprocess.check_call([SYSTEM_PYTHON, "tools/bump_version.py", BUMP_TO_VERSION])
    subprocess.check_call(["git", "add", "snooty/__init__.py", "CHANGELOG.md"])
    subprocess.check_call(["git", "commit", "-m", f"Bump to v{BUMP_TO_VERSION}"])
    cmd_test()
    subprocess.check_call(
        [
            "git",
            "tag",
            "-s",
            "-m",
            f"Release v${BUMP_TO_VERSION}" f"v${BUMP_TO_VERSION}",
        ]
    )

    push_to = re.search(
        r"^(\w+).+github.com(?::|/)mongodb/snooty-parser.git \(push\)$",
        subprocess.check_output(["git", "remote", "-v"], encoding="utf-8"),
        re.M,
    )
    if push_to:
        subprocess.check_call(["git", "push", push_to[1], f"v${BUMP_TO_VERSION}"])

    # Make a post-release version bump
    subprocess.check_call([SYSTEM_PYTHON, "tools/bump_version.py", "dev"])
    subprocess.check_call(["git", "add", "snooty/__init__.py"])
    subprocess.check_call(["git", "commit", "-m", "Post-release bump"])

    print()
    print(
        "Creating the release may now take several minutes. Check https://github.com/mongodb/snooty-parser/actions for status."
    )
    print(
        "Release will be created at: https://github.com/mongodb/snooty-parser/releases/tag/v${BUMP_TO_VERSION}"
    )


def main() -> None:
    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(1)

    commands = sys.argv[1:]
    for command in commands:
        globals()[f"cmd_{command}"]()


if __name__ == "__main__":
    main()
