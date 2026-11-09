"""Foundation Models bridge: SystemLanguageModel only, no remote providers."""

import hashlib
import json
import os
import platform
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from sborganize.storage import ensure_private_dir


class AppleUnavailable(RuntimeError):
    pass


REASONS = {
    "model_not_ready": (
        "Apple on-device model is not ready. Check Apple Intelligence in System Settings."
    ),
    "apple_intelligence_not_enabled": "Apple Intelligence is disabled in System Settings.",
    "device_not_eligible": "This Mac is not eligible for Apple Intelligence.",
}


class AppleProvider:
    def __init__(self, root: Path):
        self.root = root

    def executable(self) -> Path:
        if platform.system() != "Darwin":
            raise AppleUnavailable("Apple on-device models require macOS 26+ and Apple silicon.")
        if int(platform.mac_ver()[0].split(".")[0]) < 26 or platform.machine() != "arm64":
            raise AppleUnavailable("Apple on-device models require macOS 26+ and Apple silicon.")
        source = files("sborganize").joinpath("data/AppleBridge.swift")
        try:
            version = subprocess.run(
                ["xcrun", "swiftc", "--version"], capture_output=True, timeout=15, check=True
            ).stdout
            tag = hashlib.sha256(
                source.read_bytes() + version + platform.mac_ver()[0].encode()
            ).hexdigest()[:20]
            cache = self.root / "cache"
            binary = cache / f"apple-bridge-{tag}"
            if binary.is_file() and os.access(binary, os.X_OK):
                return binary
            ensure_private_dir(cache)
            descriptor, name = tempfile.mkstemp(prefix=".apple-bridge-", dir=cache)
            os.close(descriptor)
            temporary = Path(name)
            try:
                subprocess.run(
                    [
                        "xcrun",
                        "swiftc",
                        "-parse-as-library",
                        "-O",
                        "-target",
                        "arm64-apple-macosx26.0",
                        "-module-cache-path",
                        str(cache / "swift-modules"),
                        str(source),
                        "-o",
                        str(temporary),
                    ],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                temporary.chmod(0o700)
                temporary.replace(binary)
            finally:
                temporary.unlink(missing_ok=True)
            return binary
        except (OSError, subprocess.SubprocessError) as exc:
            raise AppleUnavailable(
                "Apple bridge could not build. Install Xcode command-line tools."
            ) from exc

    def _run(self, *, probe=False, request=None) -> dict:
        binary = self.executable()
        try:
            result = subprocess.run(
                [str(binary), *(["--probe"] if probe else [])],
                input=json.dumps(request or {}),
                capture_output=True,
                text=True,
                timeout=15 if probe else 60,
                check=True,
            )
            if len(result.stdout) > 65536:
                raise AppleUnavailable("Apple returned an oversized response.")
            data = json.loads(result.stdout)
            if not isinstance(data, dict):
                raise AppleUnavailable("Apple returned an invalid response.")
            return data
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise AppleUnavailable("Apple bridge failed or timed out; rules are retained.") from exc

    def probe(self) -> dict:
        try:
            data = self._run(probe=True)
            available = data.get("available") is True
            code = data.get("reason", "unknown_unavailability")
            return {
                "available": available,
                "reason": "available" if available else code,
                "detail": "Apple on-device model ready."
                if available
                else REASONS.get(code, "Apple on-device model is unavailable."),
            }
        except AppleUnavailable as exc:
            return {"available": False, "reason": "bridge_unavailable", "detail": str(exc)}

    def classify(self, request: dict) -> dict:
        data = self._run(request=request)
        if data.get("available") is False or "error" in data:
            raise AppleUnavailable("Apple generation unavailable; rules are retained.")
        return data
