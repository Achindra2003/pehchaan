"""Download the ONNX models Pehchaan uses into api/models/ (git-ignored).

Usage: uv run python scripts/download_models.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = {
    # OpenCV Zoo, MIT
    "face_detection_yunet_2023mar.onnx": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    # OpenCV Zoo, Apache-2.0
    "face_recognition_sface_2021dec.onnx": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
    # MiniFASNet-V2 anti-spoofing (from minivision Silent-Face-Anti-Spoofing), Apache-2.0
    "minifasnet_v2.onnx": "https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx/resolve/main/minifasnet_v2.onnx",
    # OpenCV WeChat QR detector + super-resolution (opencv_3rdparty), Apache-2.0
    **{
        f"wechat/{name}": f"https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/{name}"
        for name in ("detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel")
    },
}

TARGET = Path(__file__).resolve().parents[1] / "models"


def main() -> int:
    TARGET.mkdir(exist_ok=True)
    for name, url in MODELS.items():
        path = TARGET / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            print(f"skip     {name}")
            continue
        print(f"fetch    {name}")
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed https URLs
            path.write_bytes(response.read())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"sha256   {digest}  {name}")
    print(f"models in {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
