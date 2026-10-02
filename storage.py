import json

from list_manager import ListManager


FILE_NAME = "data.json"


def save_data(manager):

    with open(
        FILE_NAME,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            manager.to_dict(),
            file,
            ensure_ascii=False,
            indent=4
        )


def load_data():

    try:

        with open(
            FILE_NAME,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return ListManager.from_dict(
            data
        )

    except FileNotFoundError:

        return ListManager()

    except json.JSONDecodeError:

        print(
            "Ошибка: data.json повреждён."
        )

        return ListManager()