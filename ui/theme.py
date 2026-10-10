from tkinter import ttk
from tkinter import font as tkfont

BG = "#F4F6FA"
PANEL = "#FFFFFF"
TEXT = "#202938"
MUTED = "#7B8495"
BORDER = "#E3E7EF"
ACCENT = "#4263EB"
ACCENT_DARK = "#3451CA"
SELECT = "#EDF1FF"
HEAD_BG = "#F7F8FB"

_PREFERRED = ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans",
              "Ubuntu", "DejaVu Sans")
_family = "Helvetica"  # запасной вариант: Tk подберёт системный sans


def font(size: int = 10, bold: bool = False) -> tuple:
    return (_family, size, "bold") if bold else (_family, size)


def setup_theme(root) -> None:
    """Выбирает шрифт и настраивает ttk (тема clam: цвета работают на всех ОС)."""
    global _family
    available = set(tkfont.families(root))
    _family = next((f for f in _PREFERRED if f in available), _family)

    style = ttk.Style(root)
    style.theme_use("clam")

    # Дерево
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=TEXT, rowheight=28, borderwidth=0, font=font(9))
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.map("Treeview", background=[("selected", SELECT)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=HEAD_BG, foreground=MUTED,
                    font=font(9, True), relief="flat", borderwidth=0,
                    padding=(8, 8))
    style.map("Treeview.Heading", background=[("active", "#EEF1F7")])

    # Кнопка с акцентом
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=font(10, True), borderwidth=0, focusthickness=0,
                    padding=(18, 9))
    style.map("Accent.TButton",
              background=[("pressed", ACCENT_DARK), ("active", ACCENT_DARK)])

    # Прогресс и полоса прокрутки
    style.configure("Accent.Horizontal.TProgressbar", troughcolor=BORDER,
                    background=ACCENT, borderwidth=0, thickness=6)
    style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=PANEL,
                    bordercolor=PANEL, arrowcolor=MUTED, relief="flat")