"""Restrained terminal styling; redirected output and JSON stay plain."""

import sys
from contextvars import ContextVar

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

_plain = ContextVar("plain_terminal", default=False)


def set_plain(value: bool) -> None:
    _plain.set(value)


def console(*, err=False) -> Console:
    return Console(
        file=sys.stderr if err else sys.stdout,
        no_color=_plain.get() or None,
        highlight=False,
        markup=False,
        emoji=False,
    )


def styled_text(message) -> Text:
    message = "".join(
        char for char in str(message) if char in "\n\t" or (ord(char) >= 32 and ord(char) != 127)
    )
    text = Text(message)
    offset = 0
    for line in message.splitlines(keepends=True):
        if line.startswith(("Error:", "Stopped:")):
            text.stylize("bold red", offset, offset + len(line.rstrip()))
        elif line.startswith(("Preview", "sborganize", "Organization review", "Restore preview")):
            text.stylize("bold cyan", offset, offset + len(line.rstrip()))
        elif line.startswith(("Phone layout verified", "Simulation verified", "Read access ready")):
            text.stylize("green", offset, offset + len(line.rstrip()))
        elif line.startswith(("Plan saved:", "Backup saved:", "Review saved:", "Next:")):
            text.stylize("dim", offset, offset + len(line.rstrip()))
        elif line.startswith(("move ", "rename ", "folder ", "compact ", "into ")):
            text.stylize("cyan", offset, offset + len(line.split()[0]))
        offset += len(line)
    return text


def write_text(message="", *, err=False) -> None:
    console(err=err).print(styled_text(message))


def write_guide(markdown: str) -> None:
    output = console()
    if output.is_terminal:
        output.print(Markdown(markdown, code_theme="ansi_dark"))
    else:
        output.print(Text(markdown.rstrip()))
