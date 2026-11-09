"""Render the actual, synthetic CLI demo as a self-contained README terminal SVG."""

import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import TerminalTheme

from sborganize.terminal import styled_text


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="sborganize-artwork-") as temporary:
        result = subprocess.run(
            [sys.executable, "-m", "sborganize", "--data-dir", temporary, "demo"],
            capture_output=True,
            text=True,
            check=True,
            env=dict(os.environ, NO_COLOR="1"),
        )
    palette = [
        (59, 66, 82),
        (191, 97, 106),
        (163, 190, 140),
        (235, 203, 139),
        (129, 161, 193),
        (180, 142, 173),
        (136, 192, 208),
        (216, 222, 233),
    ]
    theme = TerminalTheme((32, 39, 51), (229, 233, 240), palette, palette)
    terminal = Console(
        record=True,
        width=88,
        force_terminal=True,
        no_color=False,
        color_system="truecolor",
        file=io.StringIO(),
    )
    terminal.print(styled_text(result.stdout.rstrip()))
    svg = terminal.export_svg(title="$ sborganize demo", theme=theme, unique_id="sborganize-demo")
    svg = re.sub(r"@font-face\s*\{.*?\}", "", svg, flags=re.S)
    svg = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
    assert 'url("https:' not in svg and "<script" not in svg
    path = root / "docs/assets/terminal-demo.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    print("Rendered synthetic CLI output:", path.relative_to(root))


if __name__ == "__main__":
    main()
