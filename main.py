import os
import sys

from data.catalog import Catalog
from controller import Controller
from llm.client import NetworkService
from ui.main_window import MainWindow


def main() -> None:
    window = MainWindow()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    controller = Controller(Catalog(), NetworkService(window.after),
                            window.after, base_dir)
    window.attach(controller)

    def close() -> None:
        controller.shutdown()  # отменяет импорт и убирает .tmp
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)

    if "--demo" in sys.argv:
        controller.start_demo()
    else:
        controller.startup()  # только открывает готовую базу, импорт не стартует
    window.mainloop()


if __name__ == "__main__":
    main()