import tkinter as tk

from ui import theme
from ui.file_tree import FileTree
from ui.header import Header
from ui.query_panel import QueryPanel


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Файловый анализатор")
        self.geometry("1100x700")
        self.minsize(760, 450)
        self.configure(bg=theme.BG)
        theme.setup_theme(self)

    def attach(self, controller) -> None:
        """Строит интерфейс и подключает колбэки контроллера."""
        header = Header(self, controller)
        header.pack(fill="x")

        # Поле итога: хранит последний результат загрузки
        result_box = tk.Frame(self, bg=theme.BG)
        result_box.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(result_box, text="Итог", bg=theme.BG, fg=theme.MUTED,
                 font=theme.font(9, True)).pack(anchor="w", pady=(0, 4))
        self.result = tk.Text(
            result_box, height=1, wrap="word", font=theme.font(10),
            bg=theme.PANEL, fg=theme.TEXT, relief="flat", padx=12, pady=8,
            highlightthickness=1, highlightbackground=theme.BORDER,
            state="disabled")
        self.result.tag_configure("error", foreground=theme.ERROR)
        self.result.pack(fill="x")

        content = tk.Frame(self, bg=theme.BG)
        content.pack(fill="both", expand=True, padx=16, pady=(12, 16))

        panes = tk.PanedWindow(content, orient="horizontal", sashwidth=6,
                               sashrelief="flat", bg=theme.BORDER, bd=0)
        panes.pack(fill="both", expand=True)

        tree = FileTree(panes, controller)
        query = QueryPanel(panes, controller)
        panes.add(tree, minsize=280, width=440)
        panes.add(query, minsize=240, width=500)

        controller.on_status = header.set_status
        controller.on_progress = header.set_progress
        controller.on_busy = header.set_busy
        controller.on_result = self.set_result
        controller.on_data_reset = tree.reload
        controller.on_query_opened = query.show_query
        controller.on_answer = query.show_answer

        tree.reload()

    def set_result(self, text: str, is_error: bool = False) -> None:
        """Колбэк контроллера on_result: ошибки выводятся красным."""
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text, ("error",) if is_error else ())
        self.result.configure(state="disabled")