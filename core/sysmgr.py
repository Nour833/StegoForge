import os
import sys
import shutil
import urllib.request
import zipfile
import tarfile
import tempfile
import platform
import subprocess
import json
from pathlib import Path

from rich.console import Console

console = Console()

STEGOFORGE_DIR = Path.home() / ".stegoforge"
BIN_DIR = STEGOFORGE_DIR / "bin"
MODELS_DIR = STEGOFORGE_DIR / "models"

def get_ffmpeg_path() -> Path:
    if platform.system() == "Windows":
        return BIN_DIR / "ffmpeg.exe"
    return BIN_DIR / "ffmpeg"

def ffmpeg_available() -> bool:
    # If the bootstrapped version exists, it's available
    if get_ffmpeg_path().exists():
        return True
    # Otherwise check if the user has it globally
    exe = shutil.which("ffmpeg")
    if exe is not None:
        return True
    try:
        import imageio_ffmpeg # type: ignore
        if imageio_ffmpeg.get_ffmpeg_exe() is not None:
            return True
    except (ImportError, OSError):
        pass
    return False

def model_available() -> bool:
    # Just checking if the dir has some onnx file (lite model)
    return (MODELS_DIR / "srnet_lite.onnx").exists() or (MODELS_DIR / "srnet_model.onnx").exists()

def _download_with_progress(url: str, output_path: Path, desc: str):
    console.print(f"[bold cyan]Downloading {desc}...[/bold cyan]")
    try:
        from rich.progress import Progress
        with Progress() as progress:
            task = progress.add_task(f"[cyan]{desc}...", total=None)
            
            # Use a slightly custom urlretrieve to hook rich
            def reporthook(blocknum, blocksize, totalsize):
                if totalsize > 0 and progress.tasks[task].total is None:
                    progress.update(task, total=totalsize)
                progress.update(task, advance=blocksize)

            urllib.request.urlretrieve(url, output_path, reporthook=reporthook)
    except ImportError:
        # Fallback if rich fails
        urllib.request.urlretrieve(url, output_path)

def _install_ffmpeg_windows():
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "ffmpeg.zip"
        _download_with_progress(url, zip_path, "FFmpeg (Windows)")
        console.print("[dim]Extracting...[/dim]")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Gyan has a top level folder, search for ffmpeg.exe
            for member in zip_ref.namelist():
                if member.endswith("ffmpeg.exe"):
                    source = zip_ref.open(member)
                    target = open(BIN_DIR / "ffmpeg.exe", "wb")
                    with source, target:
                        shutil.copyfileobj(source, target)
                    break

def _install_ffmpeg_linux():
    # JohnVanSickle Linux Builds
    url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    with tempfile.TemporaryDirectory() as td:
        tar_path = Path(td) / "ffmpeg.tar.xz"
        _download_with_progress(url, tar_path, "FFmpeg (Linux)")
        console.print("[dim]Extracting...[/dim]")
        with tarfile.open(tar_path, "r:xz") as tar_ref:
            for member in tar_ref.getmembers():
                if member.name.endswith("/ffmpeg") or member.name == "ffmpeg":
                    f = tar_ref.extractfile(member)
                    if f:
                        target = open(BIN_DIR / "ffmpeg", "wb")
                        shutil.copyfileobj(f, target)
                        target.close()
                        break
        os.chmod(BIN_DIR / "ffmpeg", 0o755)

def _install_ffmpeg_macos():
    try:
        req = urllib.request.Request("https://evermeet.cx/ffmpeg/info/ffmpeg/release", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            url = data['download']['zip']['url']
    except Exception:
        url = "https://evermeet.cx/ffmpeg/ffmpeg-latest.zip" # Fallback
        
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "ffmpeg.zip"
        _download_with_progress(url, zip_path, "FFmpeg (macOS)")
        console.print("[dim]Extracting...[/dim]")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                if member == "ffmpeg" or member.endswith("/ffmpeg"):
                    source = zip_ref.open(member)
                    target = open(BIN_DIR / "ffmpeg", "wb")
                    with source, target:
                        shutil.copyfileobj(source, target)
                    break
        
        ffmpeg_bin = BIN_DIR / "ffmpeg"
        os.chmod(ffmpeg_bin, 0o755)
        # Strip Apple Gatekeeper Quarantine
        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(ffmpeg_bin)], capture_output=True)

def _install_models():
    # Use hf_hub_download to place it locally
    try:
        from huggingface_hub import hf_hub_download # type: ignore
        console.print("[bold cyan]Downloading ML Steganalysis Model...[/bold cyan]")
        hf_hub_download(
            repo_id="Nour833/StegoForge-Models",
            filename="srnet_lite.onnx",
            local_dir=str(MODELS_DIR)
        )
    except Exception as e:
        console.print(f"[red]Failed to download model: {e}[/red]")

def bootstrap_if_needed(require: list[str] = None, force: bool = False):
    """
    Called at CLI entrypoint. Silently provisions missing assets.
    """
    STEGOFORGE_DIR.mkdir(exist_ok=True)
    BIN_DIR.mkdir(exist_ok=True)
    MODELS_DIR.mkdir(exist_ok=True)

    missing = []
    if force or not ffmpeg_available():
        missing.append("ffmpeg")
    if force or not model_available() and (require is None or "ml" in require):
        missing.append("srnet_lite.onnx")

    if not missing:
        return

    console.print(f"[bold cyan]⚙ First run — fetching {len(missing)} asset(s)...[/bold cyan]")
    
    if "ffmpeg" in missing:
        system = platform.system()
        try:
            if system == "Windows":
                _install_ffmpeg_windows()
            elif system == "Linux":
                _install_ffmpeg_linux()
            elif system == "Darwin":
                _install_ffmpeg_macos()
            else:
                console.print(f"[yellow]Unsupported OS for FFmpeg auto-download: {system}[/yellow]")
        except Exception as e:
            console.print(f"[red]FFmpeg auto-download failed: {e}[/red]")

    if "srnet_lite.onnx" in missing:
        _install_models()
