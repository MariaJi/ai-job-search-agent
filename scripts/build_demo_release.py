"""Build an allowlisted ZIP locally; never deploy or copy the repository wholesale."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = {
    "public_demo/__init__.py": "public_demo/__init__.py",
    "public_demo/app.py": "public_demo/app.py",
    "app/api_models.py": "app/api_models.py",
    "app/fixtures/demo.json": "app/fixtures/demo.json",
    "requirements.txt": "deploy/demo/requirements.txt",
    "startup.sh": "deploy/demo/startup.sh",
}


def build_release(destination: Path) -> Path:
    destination = destination.resolve()
    # Validate all inputs before writing. No globbing or caller-selected source tree.
    contents = {}
    for target, source in RELEASE_FILES.items():
        path = ROOT / source
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("Release inputs must not be symlinks or redirected paths.")
        contents[target] = path.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects earlier release artifacts from accidental overwrite.
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as archive:
        for target, content in contents.items():
            # Linux startup script must also work when built from a Windows checkout.
            if target == "startup.sh":
                content = content.replace(b"\r\n", b"\n")
            archive.writestr(target, content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "public-demo.zip")
    args = parser.parse_args()
    build_release(args.output)
    print("Built synthetic-only release ZIP (6 allowlisted files); nothing deployed.")


if __name__ == "__main__":
    main()
