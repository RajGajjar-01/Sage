from rich.console import Console
from rich.text import Text

_LINES = (
    "  ██████╗  ██████╗ ████████╗  █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
    "  ██╔══██╗██╔═══██╗╚══██╔══╝ ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    "  ██║  ██║██║   ██║   ██║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
    "  ██║  ██║██║   ██║   ██║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
    "  ██████╔╝╚██████╔╝   ██║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
    "  ╚═════╝  ╚═════╝    ╚═╝    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝  ",
)
_GRADIENT = (
    (255, 255, 255),
    (255, 240, 180),
    (255, 220, 120),
    (255, 200, 60),
    (240, 170, 0),
    (210, 140, 0),
)


def print_banner(console: Console) -> None:
    console.print()
    for line, (r, g, b) in zip(_LINES, _GRADIENT, strict=True):
        console.print(Text(line, style=f"rgb({r},{g},{b})"))
    console.print()
    console.print(
        "  [dim]DotAgent Core [/][bold #F0AA00]●[/][dim] Sandboxed Workspace · Multi-Provider · Resumable Sessions[/]"
    )
    console.print()
