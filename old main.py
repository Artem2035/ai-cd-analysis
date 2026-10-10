import subprocess
import csv
from pathlib import Path

WIZTREE = r"D:\programms\WizTree\WizTree64.exe"
DISK = r"C:"
CSV_FILE = Path(__file__).parent / "wiztree_result.csv"
cmd = [
    WIZTREE,
    DISK,
    f"/export={CSV_FILE}",
    "/admin=1",
    "/sortby=1",
]

def scan_disk():
    try:
        print("⏳ WizTree сканирует диск...")

        subprocess.run(
            cmd,
            check=True
        )

        if Path(CSV_FILE).exists():
            print("✅ WizTree завершил сканирование.")
            print(f"📄 Результат: {CSV_FILE}")
        else:
            print("⚠️ WizTree завершился, но CSV-файл не найден.")

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка WizTree. Код завершения: {e.returncode}")

    except FileNotFoundError:
        print(f"❌ WizTree не найден: {WIZTREE}")

    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")


def read_result():
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        next(f)

        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            print(row)


if __name__ == "__main__":
    scan_disk()
    #read_result()