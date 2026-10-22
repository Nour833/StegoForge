from pathlib import Path

from setuptools import setup, find_packages


def _read_version() -> str:
    namespace: dict[str, str] = {}
    version_file = Path(__file__).parent / "core" / "version.py"
    exec(version_file.read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def _read_reqs(name: str) -> list[str]:
    p = Path(__file__).parent / name
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


setup(
    name="stegoforge",
    version=_read_version(),
    description="The most complete open-source steganography toolkit",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="StegoForge",
    license="MIT",
    packages=find_packages(exclude=["tests*"]),
    include_package_data=True,
    package_data={
        "models": ["*.onnx", "*.sha256"],
        "stegoforge_ops": ["schemas/*"],
        "web": ["templates/*", "static/*", "static/**/*"],
    },
    py_modules=["stegoforge"],
    python_requires=">=3.10",
    keywords="steganography forensics ctf cryptography lsb dct covert-channel steganalysis",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Security",
        "Topic :: Security :: Cryptography",
        "Topic :: Multimedia :: Graphics",
    ],
    install_requires=_read_reqs("requirements.txt"),
    extras_require={
        "web": _read_reqs("requirements-web.txt"),
    },
    project_urls={
        "Source": "https://github.com/nour833/StegoForge",
        "Bug Tracker": "https://github.com/nour833/StegoForge/issues",
        "Changelog": "https://github.com/nour833/StegoForge/blob/main/CHANGELOG.md",
    },
    entry_points={
        "console_scripts": ["stegoforge=stegoforge:app"]
    },
)
