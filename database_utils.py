import copy
import json
import os
import tempfile
import unicodedata
import uuid
from pathlib import Path

from player import Player
from players_list import PlayerList


APP_NAME = "ShinriTracker"


def _normalize(value):
    value = unicodedata.normalize(
        "NFKC",
        str(value or "")
    )

    return value.strip().casefold()


def players_equal(first, second):
    """
    Считаем игроков одинаковыми, если совпадает хотя бы один
    непустой идентификатор: Steam-ник или Shinri-ник.
    """

    first_steam = _normalize(
        getattr(first, "steam_name", "")
    )

    second_steam = _normalize(
        getattr(second, "steam_name", "")
    )

    if (
        first_steam
        and second_steam
        and first_steam == second_steam
    ):
        return True

    first_shinri = _normalize(
        getattr(first, "shinri_name", "")
    )

    second_shinri = _normalize(
        getattr(second, "shinri_name", "")
    )

    return (
        bool(first_shinri)
        and bool(second_shinri)
        and first_shinri == second_shinri
    )


def _extract_lists_data(data):
    """
    Основной формат:
        {
            "lists": [...]
        }

    Дополнительно понимаем просто массив списков и несколько
    вероятных старых имён поля.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        raise ValueError(
            "Некорректный JSON: корневой элемент должен быть объектом "
            "или массивом списков."
        )

    for key in (
        "lists",
        "player_lists",
        "players_lists",
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    raise ValueError(
        "В JSON не найден массив списков игроков."
    )


def ensure_manager_ids(manager):
    """Добавляет стабильные UUID старым спискам/игрокам без изменения API проекта."""

    for player_list in getattr(manager, "lists", []):
        if not getattr(player_list, "id", None):
            player_list.id = str(uuid.uuid4())

        for player in getattr(player_list, "players", []):
            if not getattr(player, "id", None):
                player.id = str(uuid.uuid4())

    return manager


def manager_to_dict(manager):
    """
    Сериализует текущий manager независимо от реализации его класса.
    Для общей базы гарантирует наличие UUID у списков и игроков.
    """

    ensure_manager_ids(manager)

    return {
        "lists": [
            {
                "id": str(player_list.id),
                "name": player_list.name,
                "players": [
                    {
                        "id": str(player.id),
                        "steam_name": player.steam_name,
                        "shinri_name": player.shinri_name,
                        "note": player.note,
                    }
                    for player in player_list.players
                ],
            }
            for player_list in manager.lists
        ]
    }


def save_manager_to_file(
    manager,
    file_path
):
    """
    Атомарная запись JSON:
    сначала пишем временный файл, затем заменяем основной.
    """

    file_path = os.path.abspath(
        os.fspath(file_path)
    )

    parent = os.path.dirname(file_path)

    if parent:
        os.makedirs(
            parent,
            exist_ok=True
        )

    data = manager_to_dict(
        manager
    )

    fd, temporary_path = tempfile.mkstemp(
        prefix=".shinri_",
        suffix=".json.tmp",
        dir=parent or None,
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

        os.replace(
            temporary_path,
            file_path
        )

    except Exception:
        try:
            os.remove(
                temporary_path
            )
        except OSError:
            pass

        raise


def _manager_from_lists(
    template_manager,
    lists_data
):
    """
    Не требует знать имя класса менеджера.
    Делаем лёгкую копию существующего manager и заменяем только .lists.
    """

    manager = copy.copy(
        template_manager
    )

    manager.lists = []

    for raw_list in lists_data:

        if not isinstance(raw_list, dict):
            continue

        manager.lists.append(
            PlayerList.from_dict(
                raw_list
            )
        )

    return manager


def manager_from_dict(
    data,
    template_manager,
):
    """Создаёт manager из уже загруженного словаря JSON."""

    lists_data = _extract_lists_data(
        data
    )

    return _manager_from_lists(
        template_manager,
        lists_data
    )


def load_manager_from_file(
    file_path,
    template_manager
):
    file_path = os.path.abspath(
        os.fspath(file_path)
    )

    with open(
        file_path,
        "r",
        encoding="utf-8-sig"
    ) as file:
        data = json.load(
            file
        )

    lists_data = _extract_lists_data(
        data
    )

    return _manager_from_lists(
        template_manager,
        lists_data
    )


def create_empty_manager(
    template_manager,
    default_list_name="Друзья"
):
    manager = copy.copy(
        template_manager
    )

    manager.lists = []

    if default_list_name:

        create_list = getattr(
            manager,
            "create_list",
            None
        )

        if callable(create_list):

            create_list(
                default_list_name
            )

        else:

            manager.lists.append(
                PlayerList(
                    default_list_name
                )
            )

    return manager


def _clone_player(player):
    return Player.from_dict(
        player.to_dict()
    )


def _clone_list(player_list):
    return PlayerList.from_dict(
        player_list.to_dict()
    )


def merge_managers(
    base_manager,
    incoming_manager
):
    """
    Объединяет incoming_manager с base_manager.

    Правила:
    - base_manager = родная/текущая база, у неё приоритет;
    - одинаковые названия списков объединяются;
    - новые списки добавляются целиком;
    - внутри одинакового списка повторный игрок не добавляется;
    - существующая запись текущей базы никогда не перезаписывается.
    """

    stats = {
        "lists_added": 0,
        "players_added": 0,
        "duplicates_skipped": 0,
    }

    list_by_name = {
        _normalize(player_list.name): player_list
        for player_list in base_manager.lists
    }

    for incoming_list in incoming_manager.lists:

        list_key = _normalize(
            incoming_list.name
        )

        target_list = list_by_name.get(
            list_key
        )

        # Такого списка ещё нет — переносим весь список.
        if target_list is None:

            cloned = _clone_list(
                incoming_list
            )

            base_manager.lists.append(
                cloned
            )

            list_by_name[list_key] = cloned

            stats["lists_added"] += 1
            stats["players_added"] += len(
                cloned.players
            )

            continue

        # Список уже существует — добавляем только отсутствующих игроков.
        for incoming_player in incoming_list.players:

            duplicate = any(
                players_equal(
                    incoming_player,
                    existing_player
                )
                for existing_player
                in target_list.players
            )

            if duplicate:

                stats["duplicates_skipped"] += 1

                continue

            target_list.players.append(
                _clone_player(
                    incoming_player
                )
            )

            stats["players_added"] += 1

    return stats


def _settings_file_path():
    local_app_data = os.environ.get(
        "LOCALAPPDATA"
    )

    if local_app_data:
        base = Path(
            local_app_data
        )
    else:
        base = (
            Path.home()
            / ".shinri_tracker"
        )

    folder = (
        base
        / APP_NAME
    )

    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    return (
        folder
        / "database_settings.json"
    )


def remember_database_path(
    file_path
):
    settings_path = _settings_file_path()

    data = {
        "database_path": (
            os.path.abspath(
                os.fspath(file_path)
            )
            if file_path
            else None
        )
    }

    settings_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def get_remembered_database_path():
    settings_path = _settings_file_path()

    if not settings_path.exists():
        return None

    try:
        data = json.loads(
            settings_path.read_text(
                encoding="utf-8"
            )
        )

        path = data.get(
            "database_path"
        )

        if (
            path
            and os.path.isfile(path)
        ):
            return os.path.abspath(
                path
            )

    except Exception:
        return None

    return None
