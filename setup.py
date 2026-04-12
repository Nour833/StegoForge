from setuptools import setup, find_packages

setup(
    name="stegoforge",
    version="1.0.0",
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
