from catalog import Catalog
from controller import Controller
from services import NetworkService
from ui.main_window import MainWindow


def main() -> None:
    window = MainWindow()
    controller = Controller(Catalog(), NetworkService(window.after))
    controller.load_demo()
    window.attach(controller)
    window.mainloop()


if __name__ == "__main__":
    main()