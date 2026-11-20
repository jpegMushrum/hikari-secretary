"""Persist the deployment's immutable image references in the Compose .env."""
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


MARKER = b"# Managed by deploy/production-release.sh"
KEYS = ("BACKEND_IMAGE", "BOT_IMAGE", "MINIAPP_IMAGE")
BLOCK = re.compile(rb"(?m)^" + re.escape(MARKER) +
                   rb"\r?\nBACKEND_IMAGE=[^\r\n]*\r?\nBOT_IMAGE=[^\r\n]*\r?\nMINIAPP_IMAGE=[^\r\n]*(?:\r?\n|$)")


def pin_images(env_file, backend, bot, miniapp):
    path = Path(env_file).resolve(strict=True)
    original = path.read_bytes()
    base, matches = BLOCK.subn(b"", original)
    if matches > 1 or MARKER in base:
        raise ValueError("Malformed managed image block in .env")
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    if base and not base.endswith(b"\n"):
        base += newline
    lines = [MARKER] + [f"{k}={v}".encode() for k, v in zip(KEYS, (backend, bot, miniapp))]
    result = base + newline.join(lines) + newline
    if result == original:
        return

    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        name = Path(temporary.name)
    try:
        name.write_bytes(result)
        metadata = path.stat()
        if hasattr(os, "chown"):
            os.chown(name, metadata.st_uid, metadata.st_gid)
        name.chmod(stat.S_IMODE(metadata.st_mode))
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


if __name__ == "__main__":
    pin_images(*sys.argv[1:])
