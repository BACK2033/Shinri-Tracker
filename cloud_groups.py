import copy
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from database_utils import APP_NAME


SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]

GROUP_SCHEMA = 1
DATABASE_SCHEMA = 2
GROUP_META_NAME = "shinri_group.json"
DATABASE_NAME = "database.json"


class GoogleSetupError(RuntimeError):
    pass


class CloudGroupError(RuntimeError):
    pass


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _resource_path(name):
    # Сначала внешний файл рядом с exe: его можно заменить без пересборки.
    executable_dir = Path(sys.executable).resolve().parent
    external = executable_dir / name

    if external.exists():
        return external

    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / name
        if bundled.exists():
            return bundled

    local = Path(__file__).resolve().parent / name
    if local.exists():
        return local

    return external


def app_data_dir():
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / ".shinri_tracker"

    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def credentials_path():
    return _resource_path("google_credentials.json")


def token_path():
    return app_data_dir() / "google_token.json"


def active_group_path():
    return app_data_dir() / "active_cloud_group.json"


def group_cache_path(group_id):
    folder = app_data_dir() / "cloud_groups"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{group_id}.database.json"


def group_baseline_path(group_id):
    folder = app_data_dir() / "cloud_groups"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{group_id}.baseline.json"


def has_google_dependencies():
    try:
        import google.auth  # noqa: F401
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        return True
    except Exception:
        return False


def google_setup_status():
    if not has_google_dependencies():
        return False, (
            "Не установлены библиотеки Google Drive. "
            "Запусти install_dependencies.bat или установи requirements.txt."
        )

    path = credentials_path()

    if not path.exists():
        return False, (
            "Не найден google_credentials.json. Это OAuth-файл разработчика "
            "из Google Cloud Console. После его добавления обычным пользователям "
            "ничего настраивать вручную не понадобится."
        )

    return True, "OK"


def _require_google():
    ok, message = google_setup_status()

    if not ok:
        raise GoogleSetupError(message)

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

    return (
        Request,
        Credentials,
        InstalledAppFlow,
        build,
        MediaIoBaseDownload,
        MediaIoBaseUpload,
    )


def get_drive_service(interactive=True):
    (
        Request,
        Credentials,
        InstalledAppFlow,
        build,
        _MediaIoBaseDownload,
        _MediaIoBaseUpload,
    ) = _require_google()

    creds = None
    token = token_path()

    if token.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(token),
                SCOPES,
            )
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            raise GoogleSetupError(
                "Нужна повторная авторизация Google. Открой «Общая группа» "
                "и запусти синхронизацию вручную."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path()),
            SCOPES,
        )

        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            authorization_prompt_message=(
                "Открылось окно Google. Разреши Shinri Tracker доступ "
                "к файлам общей базы."
            ),
            success_message=(
                "Авторизация завершена. Это окно можно закрыть и вернуться "
                "в Shinri Tracker."
            ),
        )

        token.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False,
    )


def disconnect_google_account():
    try:
        token_path().unlink()
    except FileNotFoundError:
        pass


def _is_drive_access_error(error):
    """
    404 is also returned by Drive when the user has access to a shared file,
    but drive.file has not yet authorized this app for that specific file.
    403 can be returned as appNotAuthorizedToFile.
    """
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    return status in (403, 404)


def authorize_drive_files(file_ids):
    """
    Grants Shinri Tracker per-file access under the narrow drive.file scope.

    Sharing a Drive folder with another Google account gives that *user* access,
    but drive.file intentionally does not automatically give the *app* access to
    those shared files. Google Picker is the supported way for the recipient to
    explicitly allow this app to use an invited file.
    """
    file_ids = [
        str(file_id).strip()
        for file_id in file_ids
        if str(file_id).strip()
    ]

    if not file_ids:
        raise CloudGroupError(
            "В приглашении нет файлов Google Drive для подключения."
        )

    (
        _Request,
        _Credentials,
        InstalledAppFlow,
        _build,
        _MediaIoBaseDownload,
        _MediaIoBaseUpload,
    ) = _require_google()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path()),
        SCOPES,
    )

    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        authorization_prompt_message=(
            "Открылся Google Drive. Подтверди доступ Shinri Tracker "
            "к файлу общей группы."
        ),
        success_message=(
            "Доступ к общей группе выдан. Это окно можно закрыть и "
            "вернуться в Shinri Tracker."
        ),
        prompt="consent select_account",
        trigger_onepick="true",
        file_ids=",".join(file_ids),
        allow_multiple="true" if len(file_ids) > 1 else "false",
    )

    token_path().write_text(
        creds.to_json(),
        encoding="utf-8",
    )

    return creds


def _json_bytes(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


class DriveGroupClient:
    def __init__(self, interactive=True):
        self.service = get_drive_service(
            interactive=interactive
        )

        (
            _Request,
            _Credentials,
            _InstalledAppFlow,
            _build,
            self.MediaIoBaseDownload,
            self.MediaIoBaseUpload,
        ) = _require_google()

    def create_json_file(
        self,
        name,
        data,
        parent_id,
        app_properties=None,
    ):
        metadata = {
            "name": name,
            "mimeType": "application/json",
            "parents": [parent_id],
        }

        if app_properties:
            metadata["appProperties"] = app_properties

        media = self.MediaIoBaseUpload(
            io.BytesIO(_json_bytes(data)),
            mimetype="application/json",
            resumable=False,
        )

        result = self.service.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink,modifiedTime",
        ).execute()

        return result

    def update_json_file(self, file_id, data):
        media = self.MediaIoBaseUpload(
            io.BytesIO(_json_bytes(data)),
            mimetype="application/json",
            resumable=False,
        )

        return self.service.files().update(
            fileId=file_id,
            media_body=media,
            fields="id,name,modifiedTime,md5Checksum",
        ).execute()

    def download_json(self, file_id):
        request = self.service.files().get_media(
            fileId=file_id
        )

        stream = io.BytesIO()
        downloader = self.MediaIoBaseDownload(
            stream,
            request,
        )

        done = False

        while not done:
            _status, done = downloader.next_chunk()

        stream.seek(0)

        return json.loads(
            stream.read().decode("utf-8-sig")
        )

    def create_group(self, name, database):
        group_id = str(uuid.uuid4())

        folder = self.service.files().create(
            body={
                "name": f"Shinri Tracker - {name}",
                "mimeType": "application/vnd.google-apps.folder",
                "appProperties": {
                    "shinri_tracker_type": "group_folder",
                    "shinri_tracker_group_id": group_id,
                },
            },
            fields="id,name,webViewLink",
        ).execute()

        folder_id = folder["id"]

        remote_document = {
            "schema": DATABASE_SCHEMA,
            "group_id": group_id,
            "revision": 1,
            "updated_at": _utc_now(),
            "updated_by": device_id(),
            "database": database,
        }

        database_file = self.create_json_file(
            DATABASE_NAME,
            remote_document,
            folder_id,
            app_properties={
                "shinri_tracker_type": "database",
                "shinri_tracker_group_id": group_id,
            },
        )

        group_meta = {
            "schema": GROUP_SCHEMA,
            "app": "Shinri Tracker",
            "group_id": group_id,
            "name": name,
            "folder_id": folder_id,
            "database_file_id": database_file["id"],
            "created_at": _utc_now(),
        }

        group_file = self.create_json_file(
            GROUP_META_NAME,
            group_meta,
            folder_id,
            app_properties={
                "shinri_tracker_type": "group",
                "shinri_tracker_group_id": group_id,
            },
        )

        group_meta["group_file_id"] = group_file["id"]
        group_meta["folder_web_link"] = folder.get("webViewLink", "")

        # Дописываем собственный file id внутрь метаданных, чтобы invite был
        # самодостаточным даже после ручного копирования файла.
        self.update_json_file(
            group_file["id"],
            group_meta,
        )

        return group_meta, remote_document

    def list_groups(self):
        query = (
            "trashed = false and "
            "appProperties has { key='shinri_tracker_type' and value='group' }"
        )

        result = self.service.files().list(
            q=query,
            spaces="drive",
            pageSize=100,
            fields="files(id,name,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()

        groups = []

        for item in result.get("files", []):
            try:
                meta = self.download_json(
                    item["id"]
                )

                meta["group_file_id"] = item["id"]
                groups.append(meta)
            except Exception:
                continue

        return groups

    def connect_by_group_file(self, group_file_id):
        meta = self.download_json(
            group_file_id
        )

        meta["group_file_id"] = group_file_id

        if not meta.get("database_file_id"):
            raise CloudGroupError(
                "В группе не указан файл database.json."
            )

        remote = self.download_json(
            meta["database_file_id"]
        )

        return meta, remote

    def invite_member(self, folder_id, email):
        body = {
            "type": "user",
            "role": "writer",
            "emailAddress": email,
        }

        return self.service.permissions().create(
            fileId=folder_id,
            body=body,
            sendNotificationEmail=True,
            emailMessage=(
                "Тебе открыт доступ к общей базе Shinri Tracker. "
                "Открой Shinri Tracker → Общая группа → Подключиться к группе."
            ),
            fields="id,emailAddress,role",
        ).execute()

    def list_members(self, folder_id):
        result = self.service.permissions().list(
            fileId=folder_id,
            fields="permissions(id,type,emailAddress,displayName,role)",
        ).execute()

        return result.get("permissions", [])


def device_id():
    path = app_data_dir() / "device_id.txt"

    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value

    value = str(uuid.uuid4())
    path.write_text(value, encoding="utf-8")
    return value


def save_active_group(connection):
    active_group_path().write_text(
        json.dumps(
            connection,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_active_group():
    path = active_group_path()

    if not path.exists():
        return None

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        if data.get("group_id") and data.get("database_file_id"):
            return data
    except Exception:
        return None

    return None


def clear_active_group():
    try:
        active_group_path().unlink()
    except FileNotFoundError:
        pass


def save_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".shinri_",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def save_group_cache(group_id, database):
    save_json_atomic(
        group_cache_path(group_id),
        database,
    )


def load_group_cache(group_id):
    path = group_cache_path(group_id)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except Exception:
        return None


def save_group_baseline(group_id, database):
    save_json_atomic(
        group_baseline_path(group_id),
        database,
    )


def load_group_baseline(group_id):
    path = group_baseline_path(group_id)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except Exception:
        return None


def create_group(name, database):
    client = DriveGroupClient(interactive=True)
    connection, remote = client.create_group(
        name,
        database,
    )

    save_active_group(connection)
    save_group_cache(
        connection["group_id"],
        remote["database"],
    )
    save_group_baseline(
        connection["group_id"],
        remote["database"],
    )

    return connection


def list_available_groups():
    return DriveGroupClient(
        interactive=True
    ).list_groups()


def connect_group(group_meta):
    client = DriveGroupClient(interactive=True)
    connection, remote = client.connect_by_group_file(
        group_meta["group_file_id"]
    )

    save_active_group(connection)
    save_group_cache(
        connection["group_id"],
        remote["database"],
    )
    save_group_baseline(
        connection["group_id"],
        remote["database"],
    )

    return connection, remote["database"]


def connect_group_from_invite(invite_data):
    group_file_id = str(
        invite_data.get("group_file_id") or ""
    ).strip()
    database_file_id = str(
        invite_data.get("database_file_id") or ""
    ).strip()

    client = DriveGroupClient(interactive=True)

    # New invitations contain everything needed to connect without reading
    # shinri_group.json first. Only database.json must be explicitly approved
    # for this app through Google Picker on the recipient's account.
    if database_file_id:
        connection = {
            "schema": invite_data.get("schema", GROUP_SCHEMA),
            "app": "Shinri Tracker",
            "group_id": invite_data.get("group_id"),
            "name": invite_data.get("name", "Shinri group"),
            "folder_id": invite_data.get("folder_id"),
            "database_file_id": database_file_id,
            "group_file_id": group_file_id,
        }

        if not connection.get("group_id"):
            raise CloudGroupError(
                "Некорректный файл приглашения: нет group_id."
            )

        try:
            remote = client.download_json(database_file_id)
        except Exception as error:
            if not _is_drive_access_error(error):
                raise

            authorize_drive_files([database_file_id])
            client = DriveGroupClient(interactive=False)
            remote = client.download_json(database_file_id)

    else:
        # Compatibility with invitation files created by v9.0. They contain
        # only group_file_id, so first authorize/read shinri_group.json, then
        # authorize database.json. This may show Google Picker twice, but only
        # for old invitation files.
        if not group_file_id:
            raise CloudGroupError(
                "Некорректный файл приглашения: нет group_file_id."
            )

        try:
            meta = client.download_json(group_file_id)
        except Exception as error:
            if not _is_drive_access_error(error):
                raise

            authorize_drive_files([group_file_id])
            client = DriveGroupClient(interactive=False)
            meta = client.download_json(group_file_id)

        meta["group_file_id"] = group_file_id
        database_file_id = str(
            meta.get("database_file_id") or ""
        ).strip()

        if not database_file_id:
            raise CloudGroupError(
                "В группе не указан файл database.json."
            )

        try:
            remote = client.download_json(database_file_id)
        except Exception as error:
            if not _is_drive_access_error(error):
                raise

            authorize_drive_files([database_file_id])
            client = DriveGroupClient(interactive=False)
            remote = client.download_json(database_file_id)

        connection = meta

    if not isinstance(remote, dict):
        raise CloudGroupError(
            "Файл общей базы имеет некорректный формат."
        )

    remote_group_id = remote.get("group_id")
    connection_group_id = connection.get("group_id")

    if (
        remote_group_id
        and connection_group_id
        and str(remote_group_id) != str(connection_group_id)
    ):
        raise CloudGroupError(
            "Приглашение не соответствует выбранной общей базе."
        )

    database = remote.get("database", {"lists": []})

    save_active_group(connection)
    save_group_cache(
        connection["group_id"],
        database,
    )
    save_group_baseline(
        connection["group_id"],
        database,
    )

    return connection, database


def invite_member(connection, email):
    client = DriveGroupClient(interactive=True)
    return client.invite_member(
        connection["folder_id"],
        email,
    )


def get_members(connection):
    client = DriveGroupClient(interactive=True)
    return client.list_members(
        connection["folder_id"]
    )


def make_invite_data(connection):
    return {
        "format": "shinri-group-invite",
        "version": 2,
        "name": connection.get("name", "Shinri group"),
        "group_id": connection.get("group_id"),
        "group_file_id": connection.get("group_file_id"),
        "database_file_id": connection.get("database_file_id"),
        "folder_id": connection.get("folder_id"),
    }


def _index_lists(database):
    return {
        str(item.get("id")): copy.deepcopy(item)
        for item in database.get("lists", [])
        if item.get("id")
    }


def _flatten_players(database):
    players = {}

    for player_list in database.get("lists", []):
        list_id = str(player_list.get("id", ""))

        for player in player_list.get("players", []):
            player_id = str(player.get("id", ""))

            if not player_id:
                continue

            item = copy.deepcopy(player)
            item["list_id"] = list_id
            players[player_id] = item

    return players


def _three_way_value(base, local, remote):
    if local == remote:
        return copy.deepcopy(local), 0

    if local == base:
        return copy.deepcopy(remote), 0

    if remote == base:
        return copy.deepcopy(local), 0

    # Оба изменили одно и то же поле по-разному.
    # Локальная правка остаётся видимой пользователю, но считаем конфликт.
    return copy.deepcopy(local), 1


def _merge_object(base, local, remote, fields):
    # Новая запись.
    if base is None:
        if local is None:
            return copy.deepcopy(remote), 0
        if remote is None:
            return copy.deepcopy(local), 0

        result = copy.deepcopy(local)
        conflicts = 0

        for field in fields:
            value, conflict = _three_way_value(
                None,
                local.get(field),
                remote.get(field),
            )
            result[field] = value
            conflicts += conflict

        return result, conflicts

    # Удалили оба.
    if local is None and remote is None:
        return None, 0

    # Удалили локально, удалённый пользователь ничего не менял -> удаление.
    if local is None:
        if remote == base:
            return None, 0

        # На другом ПК запись редактировали одновременно — безопаснее сохранить.
        return copy.deepcopy(remote), 1

    # Удалили удалённо.
    if remote is None:
        if local == base:
            return None, 0

        return copy.deepcopy(local), 1

    result = copy.deepcopy(local)
    conflicts = 0

    for field in fields:
        value, conflict = _three_way_value(
            base.get(field),
            local.get(field),
            remote.get(field),
        )
        result[field] = value
        conflicts += conflict

    return result, conflicts


def three_way_merge(base, local, remote):
    """
    Трёхстороннее объединение общей базы.

    Благодаря UUID одновременно можно, например, добавить игрока на одном ПК
    и отредактировать другого на втором. Для одной и той же записи поля тоже
    объединяются отдельно. Только настоящая одновременная правка одного поля
    считается конфликтом; в таком случае остаётся локальное значение.
    """

    base = copy.deepcopy(base or {"lists": []})
    local = copy.deepcopy(local or {"lists": []})
    remote = copy.deepcopy(remote or {"lists": []})

    base_lists = _index_lists(base)
    local_lists = _index_lists(local)
    remote_lists = _index_lists(remote)

    list_ids = set(base_lists) | set(local_lists) | set(remote_lists)
    merged_lists = {}
    conflicts = 0

    for list_id in list_ids:
        merged, count = _merge_object(
            base_lists.get(list_id),
            local_lists.get(list_id),
            remote_lists.get(list_id),
            fields=["name"],
        )

        if merged is not None:
            merged["id"] = list_id
            merged["players"] = []
            merged_lists[list_id] = merged

        conflicts += count

    base_players = _flatten_players(base)
    local_players = _flatten_players(local)
    remote_players = _flatten_players(remote)

    player_ids = set(base_players) | set(local_players) | set(remote_players)
    merged_players = {}

    for player_id in player_ids:
        merged, count = _merge_object(
            base_players.get(player_id),
            local_players.get(player_id),
            remote_players.get(player_id),
            fields=[
                "steam_name",
                "shinri_name",
                "note",
                "list_id",
            ],
        )

        if merged is not None:
            merged["id"] = player_id
            merged_players[player_id] = merged

        conflicts += count

    # Если из-за конфликта сохранился игрок из удалённого списка — возвращаем
    # сам список по данным одной из сторон, чтобы игрок не потерялся.
    for player in merged_players.values():
        list_id = player.get("list_id")

        if list_id and list_id not in merged_lists:
            source = (
                local_lists.get(list_id)
                or remote_lists.get(list_id)
                or base_lists.get(list_id)
            )

            merged_lists[list_id] = {
                "id": list_id,
                "name": (
                    source.get("name", "Восстановленный список")
                    if source
                    else "Восстановленный список"
                ),
                "players": [],
            }

            conflicts += 1

    # Сохраняем привычный порядок: локальный -> удалённые новые -> остальные.
    list_order = []

    for source in (local, remote, base):
        for item in source.get("lists", []):
            list_id = str(item.get("id", ""))
            if list_id in merged_lists and list_id not in list_order:
                list_order.append(list_id)

    player_order_by_list = {}

    for source in (local, remote, base):
        for item in source.get("lists", []):
            list_id = str(item.get("id", ""))
            order = player_order_by_list.setdefault(list_id, [])

            for player in item.get("players", []):
                player_id = str(player.get("id", ""))
                if player_id in merged_players and player_id not in order:
                    order.append(player_id)

    for player_id, player in merged_players.items():
        list_id = player.get("list_id")
        order = player_order_by_list.setdefault(list_id, [])
        if player_id not in order:
            order.append(player_id)

    result_lists = []

    for list_id in list_order:
        item = merged_lists[list_id]
        item["players"] = []

        for player_id in player_order_by_list.get(list_id, []):
            player = merged_players.get(player_id)

            if not player or player.get("list_id") != list_id:
                continue

            clean_player = {
                "id": player_id,
                "steam_name": player.get("steam_name", ""),
                "shinri_name": player.get("shinri_name", ""),
                "note": player.get("note", ""),
            }

            item["players"].append(clean_player)

        result_lists.append(item)

    return {
        "lists": result_lists,
    }, conflicts


def sync_group(connection, local_database, interactive=False):
    client = DriveGroupClient(
        interactive=interactive
    )

    remote_document = client.download_json(
        connection["database_file_id"]
    )

    remote_database = remote_document.get(
        "database",
        {"lists": []},
    )

    baseline = load_group_baseline(
        connection["group_id"]
    )

    if baseline is None:
        baseline = copy.deepcopy(remote_database)

    merged, conflicts = three_way_merge(
        baseline,
        local_database,
        remote_database,
    )

    uploaded = merged != remote_database
    revision = int(
        remote_document.get("revision", 0)
    )

    if uploaded:
        revision += 1

        new_document = {
            "schema": DATABASE_SCHEMA,
            "group_id": connection["group_id"],
            "revision": revision,
            "updated_at": _utc_now(),
            "updated_by": device_id(),
            "database": merged,
        }

        client.update_json_file(
            connection["database_file_id"],
            new_document,
        )

    save_group_baseline(
        connection["group_id"],
        merged,
    )

    save_group_cache(
        connection["group_id"],
        merged,
    )

    return {
        "database": merged,
        "conflicts": conflicts,
        "uploaded": uploaded,
        "revision": revision,
        "synced_at": _utc_now(),
    }
