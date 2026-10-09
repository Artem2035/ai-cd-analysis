import csv
import os
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox


# ============================================================
# НАСТРОЙКИ
# ============================================================

WIZTREE = r"D:\programms\WizTree\WizTree64.exe"
DISK = r"C:"

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "wiztree_result.csv"
DB_FILE = BASE_DIR / "wiztree.db"


# ============================================================
# УТИЛИТЫ
# ============================================================

def normalize_path(path: str) -> str:
    """
    Приводит путь к единому виду.

    Для дерева:
        C:\
        C:\Windows\
        C:\Windows\System32\
    """
    path = path.strip().strip('"').replace("/", "\\")

    if len(path) == 2 and path[1] == ":":
        path += "\\"

    return path


def is_folder(path: str) -> bool:
    return path.endswith("\\")


def parent_path(path: str):
    """
    Возвращает родительскую папку.

    C:\Windows\System32\cmd.exe
        -> C:\Windows\System32\

    C:\Windows\
        -> C:\
    """

    path = normalize_path(path)

    if path.endswith("\\"):
        without_last = path[:-1]
    else:
        without_last = path

    pos = without_last.rfind("\\")

    if pos < 0:
        return None

    parent = without_last[:pos + 1]

    # C:\Windows -> C:\
    if len(parent) == 3 and parent[1] == ":":
        return parent

    return parent


def display_name(path: str) -> str:
    """
    Только имя для отображения в Treeview.
    """

    path = normalize_path(path)

    if len(path) == 3 and path[1:] == ":\\":
        return path

    tmp = path.rstrip("\\")

    pos = tmp.rfind("\\")

    if pos >= 0:
        return tmp[pos + 1:]

    return tmp


def format_size(value):
    if value is None:
        return ""

    try:
        value = int(value)
    except Exception:
        return str(value)

    units = ["B", "KB", "MB", "GB", "TB", "PB"]

    size = float(value)

    for unit in units:
        if size < 1024:
            if unit == "B":
                return f"{int(size):,} {unit}".replace(",", " ")
            return f"{size:,.1f} {unit}".replace(",", " ")

        size /= 1024

    return f"{size:,.1f} EB".replace(",", " ")


# ============================================================
# DATABASE
# ============================================================

class Database:
    """
    SQLite используется вместо хранения сотен тысяч
    элементов непосредственно в Tkinter Treeview.

    Treeview показывает только открытые ветки.
    """

    def __init__(self, filename):
        self.filename = str(filename)
        self.conn = None

    def open(self):
        self.conn = sqlite3.connect(
            self.filename,
            check_same_thread=False
        )

        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")

        # Проверяем, существует ли таблица items.
        row = self.conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'items'
        """).fetchone()

        if row is None:
            self.create()

    def close(self):
        if self.conn:
            self.conn.close()

    def create(self):
        cur = self.conn.cursor()

        cur.execute("DROP TABLE IF EXISTS items")

        cur.execute("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                parent TEXT,
                name TEXT NOT NULL,
                is_folder INTEGER NOT NULL,
                size INTEGER DEFAULT 0,
                allocated INTEGER DEFAULT 0,
                modified TEXT DEFAULT '',
                attributes INTEGER DEFAULT 0,
                files INTEGER DEFAULT 0,
                folders INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE INDEX idx_parent
            ON items(parent)
        """)

        cur.execute("""
            CREATE INDEX idx_parent_folder
            ON items(parent, is_folder)
        """)

        cur.execute("""
            CREATE INDEX idx_path
            ON items(path)
        """)

        self.conn.commit()

    def insert_many(self, rows):
        self.conn.executemany("""
            INSERT OR REPLACE INTO items
            (
                path,
                parent,
                name,
                is_folder,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

    def commit(self):
        self.conn.commit()

    def get_root(self):
        """
        Возвращает C:\.
        """

        row = self.conn.execute("""
            SELECT
                id,
                path,
                name,
                is_folder,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            FROM items
            WHERE path = ?
            LIMIT 1
        """, (DISK + "\\",)).fetchone()

        if row:
            return row

        # Иногда WizTree может экспортировать C: без \
        row = self.conn.execute("""
            SELECT
                id,
                path,
                name,
                is_folder,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            FROM items
            WHERE path = ?
            LIMIT 1
        """, (DISK,)).fetchone()

        return row

    def has_children(self, parent):
        row = self.conn.execute("""
            SELECT 1
            FROM items
            WHERE parent = ?
            LIMIT 1
        """, (parent,)).fetchone()

        return row is not None

    def get_children(self, parent, sort_column, descending):
        """
        Получить только непосредственных детей.

        Никаких рекурсивных запросов.
        """

        allowed = {
            "name": "name COLLATE NOCASE",
            "size": "size",
            "allocated": "allocated",
            "modified": "modified",
            "type": "is_folder",
        }

        order = allowed.get(sort_column, "name COLLATE NOCASE")

        direction = "DESC" if descending else "ASC"

        # ВАЖНО:
        #
        # Никакого:
        #
        #   ORDER BY is_folder DESC
        #
        # Поэтому файлы и папки сортируются ВМЕСТЕ.
        #
        # Если сортируем по имени:
        #   aaa.txt
        #   Documents
        #   photo.jpg
        #   Windows
        #
        # Если сортируем по размеру:
        #   100 GB folder
        #   80 GB file
        #   50 GB folder
        #   2 GB file
        #
        # То есть именно то, что требуется.

        query = f"""
            SELECT
                id,
                path,
                name,
                is_folder,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            FROM items
            WHERE parent = ?
            ORDER BY {order} {direction},
                     name COLLATE NOCASE ASC
        """

        return self.conn.execute(query, (parent,)).fetchall()

    def count(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM items"
        ).fetchone()[0]


# ============================================================
# IMPORT CSV
# ============================================================

def parse_int(value):
    if value is None:
        return 0

    value = str(value).strip()

    if not value:
        return 0

    # Удаляем возможные разделители тысяч.
    value = value.replace(",", "")

    try:
        return int(value)
    except ValueError:
        return 0


def import_csv_to_database(db: Database, csv_file: Path, progress_callback):
    """
    Импортирует CSV WizTree в SQLite.

    ВАЖНО:
    SQLite строится в отдельном потоке.
    GUI при этом не зависает.
    """

    db.create()

    rows = []
    count = 0

    with open(
        csv_file,
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace"
    ) as f:

        reader = csv.reader(f)

        header = next(reader, None)

        if not header:
            raise RuntimeError("CSV-файл пустой.")

        # WizTree:
        #
        # File Name
        # Size
        # Allocated
        # Modified
        # Attributes
        # Files
        # Folders

        for row in reader:

            if not row:
                continue

            # Иногда новые версии WizTree могут добавлять
            # дополнительные колонки. Нас интересуют первые 7.
            if len(row) < 7:
                continue

            path = normalize_path(row[0])

            if not path:
                continue

            size = parse_int(row[1])
            allocated = parse_int(row[2])
            modified = row[3].strip()
            attributes = parse_int(row[4])
            files = parse_int(row[5])
            folders = parse_int(row[6])

            folder = is_folder(path)

            parent = parent_path(path)

            name = display_name(path)

            rows.append((
                path,
                parent,
                name,
                1 if folder else 0,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            ))

            count += 1

            if len(rows) >= 5000:
                db.insert_many(rows)
                rows.clear()

                if count % 50000 == 0:
                    progress_callback(
                        f"Импорт CSV: {count:,} записей".replace(",", " ")
                    )

        if rows:
            db.insert_many(rows)

    db.commit()

    progress_callback(
        f"Индекс построен: {count:,} записей".replace(",", " ")
    )


# ============================================================
# ОСНОВНОЙ GUI
# ============================================================

class WizTreeGUI:

    def __init__(self, root):
        self.root = root

        self.root.title("WizTree Lazy Explorer")
        self.root.geometry("1100x700")
        self.root.minsize(800, 500)

        self.db = Database(DB_FILE)
        self.db.open()

        self.sort_column = "size"
        self.sort_descending = True

        # Чтобы один и тот же каталог не грузился несколько раз.
        self.loaded_nodes = set()

        self.scanning = False

        self.create_ui()

        self.load_existing_database()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def create_ui(self):

        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=8)

        self.scan_button = ttk.Button(
            top,
            text="Сканировать C:",
            command=self.start_scan
        )

        self.scan_button.pack(side="left")

        self.status = ttk.Label(
            top,
            text="Готово"
        )

        self.status.pack(
            side="left",
            padx=15
        )

        # ----------------------------------------------------
        # TREE
        # ----------------------------------------------------

        frame = ttk.Frame(self.root)
        frame.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=(0, 8)
        )

        columns = (
            "size",
            "allocated",
            "modified",
            "type"
        )

        self.tree = ttk.Treeview(
            frame,
            columns=columns,
            show="tree headings",
            selectmode="browse"
        )

        self.tree.heading(
            "#0",
            text="Имя",
            command=lambda: self.change_sort("name")
        )

        self.tree.heading(
            "size",
            text="Размер",
            command=lambda: self.change_sort("size")
        )

        self.tree.heading(
            "allocated",
            text="Выделено",
            command=lambda: self.change_sort("allocated")
        )

        self.tree.heading(
            "modified",
            text="Изменён",
            command=lambda: self.change_sort("modified")
        )

        self.tree.heading(
            "type",
            text="Тип",
            command=lambda: self.change_sort("type")
        )

        self.tree.column("#0", width=500)

        self.tree.column(
            "size",
            width=130,
            anchor="e"
        )

        self.tree.column(
            "allocated",
            width=130,
            anchor="e"
        )

        self.tree.column(
            "modified",
            width=160
        )

        self.tree.column(
            "type",
            width=90
        )

        vsb = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tree.yview
        )

        hsb = ttk.Scrollbar(
            frame,
            orient="horizontal",
            command=self.tree.xview
        )

        self.tree.configure(
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        vsb.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        hsb.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # ----------------------------------------------------
        # События
        # ----------------------------------------------------

        self.tree.bind(
            "<<TreeviewOpen>>",
            self.on_open
        )

        self.tree.bind(
            "<Double-1>",
            self.on_double_click
        )

    # --------------------------------------------------------
    # EXISTING DB
    # --------------------------------------------------------

    def load_existing_database(self):

        root_row = self.db.get_root()

        if root_row:
            self.show_root(root_row)
            self.status.config(
                text=f"Индекс готов: {self.db.count():,} записей".replace(",", " ")
            )

    # --------------------------------------------------------
    # ROOT
    # --------------------------------------------------------

    def show_root(self, row):

        self.tree.delete(*self.tree.get_children())

        self.loaded_nodes.clear()

        (
            item_id,
            path,
            name,
            is_folder_item,
            size,
            allocated,
            modified,
            attributes,
            files,
            folders
        ) = row

        iid = self.tree.insert(
            "",
            "end",
            text=path,
            values=(
                format_size(size),
                format_size(allocated),
                modified,
                "Папка" if is_folder_item else "Файл"
            ),
            open=False
        )

        # Не добавляем "Загрузка".
        #
        # Вместо этого Treeview сам получает признак
        # has_children.
        #
        # Пользователь видит только C:\.
        if self.db.has_children(path):
            self.tree.item(
                iid,
                open=False
            )

            # Tkinter Treeview не имеет штатного has_children
            # для item, поэтому используем пустой dummy node.
            #
            # Он НЕ является надписью "Загрузка".
            #
            # Он будет мгновенно удалён при раскрытии.
            self.tree.insert(
                iid,
                "end",
                text="",
                values=("", "", "", ""),
                tags=("dummy",)
            )

        self.root_node = iid

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    def change_sort(self, column):

        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column

            # Размер обычно хочется видеть от большого к маленькому.
            if column in ("size", "allocated"):
                self.sort_descending = True
            else:
                self.sort_descending = False

        # Обновляем только уже раскрытые папки.
        self.refresh_open_nodes()

        direction = "↓" if self.sort_descending else "↑"

        names = {
            "name": "Имя",
            "size": "Размер",
            "allocated": "Выделено",
            "modified": "Изменён",
            "type": "Тип"
        }

        self.status.config(
            text=f"Сортировка: {names[column]} {direction}"
        )

    def refresh_open_nodes(self):

        # Сохраняем открытые пути.
        open_paths = []

        def collect(parent=""):
            for iid in self.tree.get_children(parent):

                values = self.tree.item(iid)

                text = values.get("text", "")

                if self.tree.item(iid, "open"):
                    open_paths.append(text)
                    collect(iid)

        collect()

        # Для каждого уже загруженного каталога
        # заново запрашиваем его детей.
        #
        # Но дерево не пересоздаётся целиком.

        for iid in list(self.tree.get_children("")):

            self.refresh_node_recursive(iid)

    def refresh_node_recursive(self, iid):

        text = self.tree.item(iid, "text")

        # dummy
        if not text:
            return

        is_open = self.tree.item(iid, "open")

        if not is_open:
            return

        # Не трогаем dummy.
        children = [
            child
            for child in self.tree.get_children(iid)
            if self.tree.item(child, "tags") != ("dummy",)
        ]

        if children:
            self.populate_node(iid, text, replace=True)

            for child in self.tree.get_children(iid):
                self.refresh_node_recursive(child)

    # --------------------------------------------------------
    # OPEN
    # --------------------------------------------------------

    def on_open(self, event):

        selection = self.tree.selection()

        if not selection:
            return

        iid = selection[0]

        path = self.tree.item(
            iid,
            "text"
        )

        if not path:
            return

        # Уже загружали?
        if iid in self.loaded_nodes:
            return

        self.populate_node(
            iid,
            path,
            replace=False
        )

    # --------------------------------------------------------
    # POPULATE NODE
    # --------------------------------------------------------

    def populate_node(
        self,
        iid,
        parent_path_value,
        replace=False
    ):

        # Удаляем dummy.
        for child in self.tree.get_children(iid):

            tags = self.tree.item(
                child,
                "tags"
            )

            if "dummy" in tags:
                self.tree.delete(child)

        rows = self.db.get_children(
            parent_path_value,
            self.sort_column,
            self.sort_descending
        )

        # Если детей нет — всё.
        if not rows:
            self.loaded_nodes.add(iid)
            return

        # При сортировке удаляем старые элементы.
        if replace:

            for child in self.tree.get_children(iid):
                self.tree.delete(child)

        for row in rows:

            (
                item_id,
                path,
                name,
                is_folder_item,
                size,
                allocated,
                modified,
                attributes,
                files,
                folders
            ) = row

            child_iid = self.tree.insert(
                iid,
                "end",
                text=name,
                values=(
                    format_size(size),
                    format_size(allocated),
                    modified,
                    "Папка" if is_folder_item else "Файл"
                )
            )

            # Только папки получают dummy.
            #
            # Файлы вообще не имеют дочернего элемента.
            if is_folder_item and self.db.has_children(path):

                self.tree.insert(
                    child_iid,
                    "end",
                    text="",
                    values=("", "", "", ""),
                    tags=("dummy",)
                )

        self.loaded_nodes.add(iid)

    # --------------------------------------------------------
    # DOUBLE CLICK
    # --------------------------------------------------------

    def on_double_click(self, event):

        iid = self.tree.identify_row(event.y)

        if not iid:
            return

        path = self.tree.item(
            iid,
            "text"
        )

        if not path:
            return

        # Если папка — не открываем Windows Explorer,
        # а даём Treeview раскрыться.
        if path.endswith("\\"):
            return

        # Файл можно открыть.
        try:
            os.startfile(path)
        except Exception:
            pass

    # --------------------------------------------------------
    # SCAN
    # --------------------------------------------------------

    def start_scan(self):

        if self.scanning:
            return

        if not Path(WIZTREE).exists():
            messagebox.showerror(
                "Ошибка",
                f"WizTree не найден:\n\n{WIZTREE}"
            )
            return

        self.scanning = True

        self.scan_button.config(
            state="disabled"
        )

        self.status.config(
            text="Запуск WizTree..."
        )

        # Удаляем старую базу после успешного нового CSV,
        # поэтому существующее дерево пока остаётся.
        thread = threading.Thread(
            target=self.scan_worker,
            daemon=True
        )

        thread.start()

    def scan_worker(self):

        try:

            # ------------------------------------------------
            # Удаляем старый CSV
            # ------------------------------------------------

            try:
                CSV_FILE.unlink()
            except FileNotFoundError:
                pass

            # ------------------------------------------------
            # WizTree
            # ------------------------------------------------

            cmd = [
                WIZTREE,
                DISK,
                f"/export={CSV_FILE}",
                "/admin=1",
                "/sortby=1",
            ]

            self.gui_status(
                "WizTree сканирует C:..."
            )

            # ВАЖНО:
            #
            # subprocess.run() сам по себе не всегда достаточен,
            # потому что WizTree может завершить один процесс,
            # а экспорт CSV закончить немного позже.
            #
            # Поэтому после завершения процесса дополнительно
            # ждём появления и стабилизации CSV.

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            process.wait()

            # ------------------------------------------------
            # Ждём CSV
            # ------------------------------------------------

            self.gui_status(
                "Ожидание завершения экспорта CSV..."
            )

            if not self.wait_for_csv():
                raise RuntimeError(
                    "WizTree не создал CSV-файл."
                )

            # ------------------------------------------------
            # Создаём временную БД
            # ------------------------------------------------

            temp_db = BASE_DIR / "wiztree_new.db"

            try:
                temp_db.unlink()
            except FileNotFoundError:
                pass

            new_db = Database(temp_db)
            new_db.open()

            try:

                import_csv_to_database(
                    new_db,
                    CSV_FILE,
                    self.gui_status
                )

            finally:
                new_db.close()

            # ------------------------------------------------
            # Меняем БД
            # ------------------------------------------------

            self.root.after(
                0,
                lambda: self.finish_scan(temp_db)
            )

        except Exception as e:

            self.root.after(
                0,
                lambda err=str(e): self.scan_error(err)
            )

    # --------------------------------------------------------
    # WAIT CSV
    # --------------------------------------------------------

    def wait_for_csv(self):

        timeout = 60 * 30

        started = time.time()

        previous_size = -1
        stable_count = 0

        while time.time() - started < timeout:

            try:

                if CSV_FILE.exists():

                    size = CSV_FILE.stat().st_size

                    if size > 0:

                        if size == previous_size:

                            stable_count += 1

                        else:

                            stable_count = 0

                        previous_size = size

                        # CSV не меняется минимум ~1.5 сек.
                        if stable_count >= 3:
                            return True

            except OSError:
                pass

            time.sleep(0.5)

        return False

    # --------------------------------------------------------
    # FINISH SCAN
    # --------------------------------------------------------

    def finish_scan(self, temp_db):

        try:

            self.db.close()

            # Старую БД удаляем.
            try:
                DB_FILE.unlink()
            except FileNotFoundError:
                pass

            # Новую БД переименовываем.
            temp_db.replace(DB_FILE)

            self.db = Database(DB_FILE)
            self.db.open()

            self.show_root(
                self.db.get_root()
            )

            self.status.config(
                text=(
                    f"Готово: "
                    f"{self.db.count():,} записей"
                ).replace(",", " ")
            )

        except Exception as e:

            messagebox.showerror(
                "Ошибка",
                str(e)
            )

        finally:

            self.scanning = False

            self.scan_button.config(
                state="normal"
            )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    def scan_error(self, error):

        self.scanning = False

        self.scan_button.config(
            state="normal"
        )

        self.status.config(
            text="Ошибка"
        )

        messagebox.showerror(
            "Ошибка сканирования",
            error
        )

    # --------------------------------------------------------
    # STATUS FROM THREAD
    # --------------------------------------------------------

    def gui_status(self, text):

        self.root.after(
            0,
            lambda msg=text: self.status.config(
                text=msg
            )
        )

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    def close(self):

        try:
            self.db.close()
        except Exception:
            pass

        self.root.destroy()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = WizTreeGUI(root)

    root.protocol(
        "WM_DELETE_WINDOW",
        app.close
    )

    root.mainloop()