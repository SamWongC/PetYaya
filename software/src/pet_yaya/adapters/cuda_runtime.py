"""Discover NVIDIA wheel DLLs only inside the active Python environment."""
import os
from pathlib import Path
import sys


def configure_cuda_dlls():
    if os.name != "nt":
        return []
    root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    folders = [root / package / location for package in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime")
               for location in ("bin", "lib") if (root / package / location).is_dir()]
    handles = [os.add_dll_directory(str(folder)) for folder in folders]
    os.environ["PATH"] = os.pathsep.join([*(str(folder) for folder in folders), os.environ.get("PATH", "")])
    return handles

