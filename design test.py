
import tkinter as tk
from tkinter import ttk


BG = "#F4F6FA"
PANEL = "#FFFFFF"
TEXT = "#202938"
MUTED = "#7B8495"
BORDER = "#E3E7EF"
ACCENT = "#4263EB"


SAMPLE_TREE = [
    {
        "name": "project",
        "size": "—",
        "type": "folder",
        "children": [
            {
                "name": "src",
                "size": "—",
                "type": "folder",
                "children": [
                    {"name": "main.py", "size": "4 KB", "type": "file"},
                    {"name": "utils.py", "size": "12 KB", "type": "file"},
                    {
                        "name": "modules",
                        "size": "—",
                        "type": "folder",
                        "children": [
                            {"name": "parser.py", "size": "8 KB", "type": "file"},
                            {"name": "config.py", "size": "1 KB", "type": "file"},
                        ],
                    },
                ],
            },
            {
                "name": "data",
                "size": "—",
                "type": "folder",
                "children": [
                    {"name": "input.json", "size": "156 KB", "type": "file"},
                    {"name": "archive.zip", "size": "2.4 MB", "type": "file"},
                ],
            },
            {"name": "README.md", "size": "3 KB", "type": "file"},
        ],
    }
]


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Файловый анализатор")
        self.geometry("1100x700")
        self.minsize(760, 450)
        self.configure(bg=BG)

        self.selected_item = None
        self.answer_by_path = {}

        self._build_header()
        self._build_content()

    def _build_header(self):
        header = tk.Frame(self, bg=PANEL, height=68)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Button(
            header,
            text="▶  Анализ",
            command=self.start_analysis,
            bg=ACCENT,
            fg="white",
            activebackground="#3451CA",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=9,
            cursor="hand2",
        ).pack(side="left", padx=20, pady=14)

        self.status = tk.Label(
            header,
            text="Готов к анализу",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.status.pack(side="left", padx=12)

        self.progress = ttk.Progressbar(
            header, mode="determinate", maximum=100
        )
        self.progress.pack(
            side="right", fill="x", expand=True, padx=20
        )

    def _build_content(self):
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=16, pady=16)

        # Две панели с регулируемой шириной
        self.panes = tk.PanedWindow(
            content,
            orient="horizontal",
            sashwidth=6,
            sashrelief="flat",
            bg=BORDER,
            bd=0,
        )
        self.panes.pack(fill="both", expand=True)

        # Левая панель: дерево
        self.left_panel = tk.Frame(self.panes, bg=PANEL)
        self.panes.add(self.left_panel, minsize=280, width=440)

        # Правая панель: единый редактор
        self.right_panel = tk.Frame(self.panes, bg=PANEL)
        self.panes.add(self.right_panel, minsize=240, width=500)

        self._build_tree_panel()
        self._build_answer_panel()

    def _build_tree_panel(self):
        tk.Label(
            self.left_panel,
            text="Структура файлов",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(16, 12))

        # Заголовки с фиксированными колонками размера и вопроса
        headings = tk.Frame(self.left_panel, bg="#F7F8FB")
        headings.pack(fill="x")

        tk.Label(
            headings,
            text="Название",
            bg="#F7F8FB",
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=(12, 4), pady=10)

        tk.Label(
            headings,
            text="Размер",
            width=10,
            bg="#F7F8FB",
            fg=MUTED,
            anchor="e",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=4, pady=10)

        tk.Label(
            headings,
            text="?",
            width=4,
            bg="#F7F8FB",
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6), pady=10)

        tk.Frame(self.left_panel, bg=BORDER, height=1).pack(fill="x")

        tree_container = tk.Frame(self.left_panel, bg=PANEL)
        tree_container.pack(fill="both", expand=True)

        self.tree_canvas = tk.Canvas(
            tree_container,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
        )
        scrollbar = ttk.Scrollbar(
            tree_container,
            orient="vertical",
            command=self.tree_canvas.yview,
        )
        self.tree_canvas.configure(
            yscrollcommand=scrollbar.set
        )

        scrollbar.pack(side="right", fill="y")
        self.tree_canvas.pack(side="left", fill="both", expand=True)

        self.tree_frame = tk.Frame(self.tree_canvas, bg=PANEL)
        self.canvas_window = self.tree_canvas.create_window(
            (0, 0), window=self.tree_frame, anchor="nw"
        )

        self.tree_frame.bind(
            "<Configure>", self._update_scroll
        )
        self.tree_canvas.bind(
            "<Configure>", self._resize_tree
        )

        for item in SAMPLE_TREE:
            self._add_tree_item(self.tree_frame, item, 0, item["name"])

    def _add_tree_item(self, parent, item, depth, path):
        is_folder = item["type"] == "folder"
        children = item.get("children", [])

        row = tk.Frame(parent, bg=PANEL, height=38)
        row.pack(fill="x")
        row.pack_propagate(False)

        # Название получает всё оставшееся пространство.
        name_area = tk.Frame(row, bg=PANEL)
        name_area.pack(side="left", fill="both", expand=True)

        tk.Frame(
            name_area, bg=PANEL, width=10 + depth * 15
        ).pack(side="left")

        if children:
            toggle = tk.Button(
                name_area,
                text="▾",
                width=2,
                bd=0,
                bg=PANEL,
                fg=MUTED,
                cursor="hand2",
            )
            toggle.pack(side="left")
        else:
            tk.Label(
                name_area, text="", width=2, bg=PANEL
            ).pack(side="left")

        icon = "📁" if is_folder else "📄"

        tk.Label(
            name_area,
            text=icon,
            bg=PANEL,
            font=("Segoe UI Emoji", 10),
        ).pack(side="left", padx=(2, 5))

        name_label = tk.Label(
            name_area,
            text=item["name"],
            bg=PANEL,
            fg=TEXT,
            anchor="w",
            font=("Segoe UI", 9),
        )
        name_label.pack(side="left", fill="x", expand=True)

        # Размер всегда занимает одну и ту же ширину.
        tk.Label(
            row,
            text=item.get("size", "—"),
            width=10,
            anchor="e",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=4)

        tk.Button(
            row,
            text="?",
            width=3,
            bd=0,
            bg="#EDF1FF",
            fg=ACCENT,
            activebackground="#DCE5FF",
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            command=lambda i=item, p=path: self.ask_about(i, p),
        ).pack(side="left", padx=(0, 7), pady=5)

        def select_item(event=None):
            self.selected_item = path
            self._load_answer(path)

            for widget in self.tree_frame.winfo_children():
                pass

            row.configure(bg="#EDF1FF")
            name_area.configure(bg="#EDF1FF")
            name_label.configure(bg="#EDF1FF")

        for widget in (row, name_area, name_label):
            widget.bind("<Button-1>", select_item)

        tk.Frame(parent, bg="#F0F2F6", height=1).pack(fill="x")

        if children:
            children_frame = tk.Frame(parent, bg=PANEL)

            for child in children:
                self._add_tree_item(
                    children_frame,
                    child,
                    depth + 1,
                    f"{path}/{child['name']}",
                )

            children_frame.pack(fill="x")

            def toggle_children():
                if children_frame.winfo_manager():
                    children_frame.pack_forget()
                    toggle.configure(text="▸")
                else:
                    children_frame.pack(fill="x")
                    toggle.configure(text="▾")

                self._update_scroll()

            toggle.configure(command=toggle_children)

    def _build_answer_panel(self):
        top = tk.Frame(self.right_panel, bg=PANEL)
        top.pack(fill="x", padx=18, pady=(16, 12))

        tk.Label(
            top,
            text="Ответ / заметки",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        self.selected_label = tk.Label(
            top,
            text="Элемент не выбран",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.selected_label.pack(anchor="w", pady=(5, 0))

        editor_container = tk.Frame(self.right_panel, bg=PANEL)
        editor_container.pack(
            fill="both", expand=True, padx=18, pady=(0, 12)
        )

        self.answer_text = tk.Text(
            editor_container,
            wrap="word",
            undo=True,
            font=("Segoe UI", 10),
            bg="#FCFCFE",
            fg=TEXT,
            relief="flat",
            padx=12,
            pady=12,
            insertbackground=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.answer_text.pack(fill="both", expand=True)

        bottom = tk.Frame(self.right_panel, bg=PANEL)
        bottom.pack(fill="x", padx=18, pady=(0, 16))

        tk.Button(
            bottom,
            text="Сохранить ответ",
            command=self.save_answer,
            bg=ACCENT,
            fg="white",
            activebackground="#3451CA",
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

    def _load_answer(self, path):
        self.selected_label.configure(text=path)
        self.answer_text.delete("1.0", "end")
        self.answer_text.insert(
            "1.0", self.answer_by_path.get(path, "")
        )

    def save_answer(self):
        if self.selected_item is None:
            self.status.configure(text="Сначала выберите элемент дерева")
            return

        self.answer_by_path[self.selected_item] = (
            self.answer_text.get("1.0", "end-1c")
        )
        self.status.configure(text="Ответ сохранён")

    def ask_about(self, item, path):
        self.selected_item = path
        self._load_answer(path)

        self.answer_text.insert(
            "end",
            f"\n\nВопрос об элементе «{item['name']}»:\n",
        )
        self.answer_text.focus_set()

    def _resize_tree(self, event):
        self.tree_canvas.itemconfigure(
            self.canvas_window, width=event.width
        )

    def _update_scroll(self, event=None):
        self.tree_canvas.configure(
            scrollregion=self.tree_canvas.bbox("all")
        )

    def start_analysis(self):
        self.status.configure(text="Демонстрационный режим")
        self.progress["value"] = 100


if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
