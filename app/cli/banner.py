from rich.text import Text

_LINES = (
    "   ██████╗  █████╗  ██████╗ ███████╗",
    "  ██╔════╝ ██╔══██╗██╔════╝ ██╔════╝",
    "  ╚█████╗  ███████║██║  ███╗█████╗  ",
    "   ╚═══██╗ ██╔══██║██║   ██║██╔══╝  ",
    "  ██████╔╝ ██║  ██║╚██████╔╝███████╗",
    "  ╚═════╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝",
)
_GRADIENT = (
    (255, 255, 255),
    (255, 240, 180),
    (255, 220, 120),
    (255, 200, 60),
    (240, 170, 0),
    (210, 140, 0),
)


def banner() -> Text:
    text = Text()
    for line, (r, g, b) in zip(_LINES, _GRADIENT, strict=True):
        text.append(line + "\n", style=f"rgb({r},{g},{b})")
    text.append("\n  Sage Core ", style="dim")
    text.append("●", style="bold #F0AA00")
    text.append(
        " Sandboxed Workspace · Multi-Provider · Resumable Sessions", style="dim"
    )
    return text
