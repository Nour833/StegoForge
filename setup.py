from pathlib import Path

from setuptools import setup, find_packages


def _read_version() -> str:
    namespace: dict[str, str] = {}
    version_file = Path(__file__).parent / "core" / "version.py"
    exec(version_file.read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])

setup(
    name="stegoforge",
    version=_read_version(),
    description="The most complete open-source steganography toolkit",
    author="StegoForge",
    license="MIT",
    packages=find_packages(),
    py_modules=["stegoforge"],
    python_requires=">=3.10",
    install_requires=open("requirements.txt").read().splitlines(),
    entry_points={
        "console_scripts": ["stegoforge=stegoforge:app"]
    },
)
