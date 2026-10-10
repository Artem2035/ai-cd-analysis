import itertools

from catalog import Catalog

KB = 1024
MB = 1024 * KB

# Папка = (имя, [дети]); файл = (имя, размер в байтах)
DEMO_ROOT = ("project", [
    ("src", [
        ("main.py", 4 * KB),
        ("utils.py", 12 * KB),
        ("modules", [
            ("parser.py", 8 * KB),
            ("config.py", 1 * KB),
        ]),
    ]),
    ("data", [
        ("input.json", 156 * KB),
        ("archive.zip", int(2.4 * MB)),
        ("video.mp4", 850 * MB),
    ]),
    # 2500 файлов — для проверки «Показать ещё…»
    ("logs", [(f"log_{i:04d}.txt", KB * (i % 97 + 1)) for i in range(2500)]),
    ("README.md", 3 * KB),
])


def _alloc(size: int) -> int:
    return (size + 4095) // 4096 * 4096


def _stamp(n: int) -> str:
    return f"2025-{1 + n % 12:02d}-{1 + n % 28:02d} {n % 24:02d}:{n % 60:02d}:00"


def load_demo(catalog: Catalog) -> None:
    """Кладёт демо-дерево в ту же базу, что и будущий импорт CSV."""
    rows = []
    ids = itertools.count(1)

    def add_file(name, size, parent_id, parent_path):
        fid = next(ids)
        rows.append((fid, parent_id, name, parent_path + name, 0,
                     size, _alloc(size), _stamp(fid), None, None))
        return size, _alloc(size)

    def add_folder(name, children, parent_id, parent_path):
        fid = next(ids)
        path = f"{parent_path}{name}\\"
        size = alloc = files = folders = 0
        for child_name, body in children:
            if isinstance(body, list):
                s, a, f, d = add_folder(child_name, body, fid, path)
                folders += 1 + d
                files += f
            else:
                s, a = add_file(child_name, body, fid, path)
                files += 1
            size += s
            alloc += a
        # размер папки — сумма вложенного, как в WizTree
        rows.append((fid, parent_id, name, path, 1, size, alloc,
                     _stamp(fid), files, folders))
        return size, alloc, files, folders

    add_folder(DEMO_ROOT[0], DEMO_ROOT[1], None, "D:\\")
    catalog.insert_many(rows)