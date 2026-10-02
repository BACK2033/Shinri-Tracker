import sys
import time

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QIcon, QCursor, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QHeaderView,
    QProgressBar,
    QFrame,
    QPlainTextEdit,
    QAbstractItemView,
    QFileDialog,
    QInputDialog
)
from match_monitor import MatchMonitor, match_players
from storage import load_data, save_data
from database_utils import (
    create_empty_manager,
    get_remembered_database_path,
    load_manager_from_file,
    manager_from_dict,
    manager_to_dict,
    merge_managers,
    players_equal,
    remember_database_path,
    save_manager_to_file,
)
from cloud_groups import (
    CloudGroupError,
    GoogleSetupError,
    clear_active_group,
    connect_group,
    connect_group_from_invite,
    create_group,
    disconnect_google_account,
    get_members,
    google_setup_status,
    invite_member,
    list_available_groups,
    load_active_group,
    load_group_cache,
    make_invite_data,
    save_group_cache,
    sync_group,
)
from updater import (
    UpdateError,
    can_self_update,
    check_for_update,
    download_update,
    get_current_version,
    is_update_configured,
    launch_update_replacer,
    load_update_config,
)
from parcer import find_players


# =========================================================
# СТИЛИ
# =========================================================

STYLE = """
QMainWindow {
    background-color: #181a1f;
}

QWidget {
    color: #e6e6e6;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QLabel {
    color: #bfc3cc;
}

QLabel#title {
    color: #ffffff;
    font-size: 18pt;
    font-weight: bold;
}

QLabel#sectionTitle {
    color: #ffffff;
    font-size: 11pt;
    font-weight: bold;
}

/* =======================================================
   СПИСКИ
   ======================================================= */

QListWidget {
    background-color: #20232a;
    border: 1px solid #30343d;
    border-radius: 8px;
    padding: 5px;
    outline: none;
}

QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 0;
}

QListWidget::item:hover {
    background-color: #292d36;
}

QListWidget::item:selected {
    background-color: #3d5a80;
    color: white;
}

/* =======================================================
   ТАБЛИЦА
   ======================================================= */

QTableWidget {
    background-color: #20232a;
    alternate-background-color: #1d2026;
    border: 1px solid #30343d;
    border-radius: 8px;
    gridline-color: #30343d;
    outline: none;
    selection-background-color: #3d5a80;
    selection-color: white;
}

QTableWidget::item {
    padding: 7px;
}

QHeaderView::section {
    background-color: #292d36;
    color: #bfc3cc;
    border: none;
    border-bottom: 1px solid #3a3e48;
    padding: 9px;
    font-weight: bold;
}

/* =======================================================
   КНОПКИ
   ======================================================= */

QPushButton {
    background-color: #292d36;
    color: #e6e6e6;
    border: 1px solid #3a3e48;
    border-radius: 7px;
    padding: 8px 14px;
}

QPushButton:hover {
    background-color: #343944;
}

QPushButton:pressed {
    background-color: #252830;
}

QPushButton:disabled {
    color: #70747d;
    background-color: #22252b;
}

QPushButton#searchButton {
    background-color: #3d5a80;
    border: none;
    color: white;
    font-size: 11pt;
    font-weight: bold;
    padding: 12px;
    border-radius: 8px;
}

QPushButton#searchButton:hover {
    background-color: #496b96;
}

QPushButton#searchButton:pressed {
    background-color: #344d6e;
}

QPushButton#deleteButton:hover {
    background-color: #613c42;
}

QPushButton#addButton:hover {
    background-color: #355b4b;
}

/* =======================================================
   ПОЛЯ ВВОДА
   ======================================================= */

QLineEdit,
QPlainTextEdit {
    background-color: #20232a;
    border: 1px solid #3a3e48;
    border-radius: 7px;
    padding: 8px;
    color: #ffffff;
    selection-background-color: #3d5a80;
}

QLineEdit:focus,
QPlainTextEdit:focus {
    border: 1px solid #4f7099;
}

/* =======================================================
   ГАЛОЧКИ
   ======================================================= */

QCheckBox {
    color: #bfc3cc;
    spacing: 8px;
}

QCheckBox:hover {
    color: #ffffff;
}

/* =======================================================
   ПРОГРЕСС
   ======================================================= */

QProgressBar {
    background-color: #20232a;
    border: 1px solid #30343d;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #3d5a80;
    border-radius: 4px;
}

QFrame#separator {
    background-color: #30343d;
}

QMenuBar {
    background-color: #20232a;
    color: #e6e6e6;
    border-bottom: 1px solid #30343d;
    padding: 2px;
}

QMenuBar::item {
    padding: 5px 10px;
    background: transparent;
}

QMenuBar::item:selected {
    background-color: #343944;
    border-radius: 4px;
}

QMenu {
    background-color: #20232a;
    color: #e6e6e6;
    border: 1px solid #3a3e48;
}

QMenu::item {
    padding: 6px 28px 6px 24px;
}

QMenu::item:selected {
    background-color: #3d5a80;
}

QStatusBar {
    background-color: #181a1f;
    color: #8f95a1;
    border-top: 1px solid #30343d;
}

QStatusBar QLabel {
    color: #8f95a1;
}
"""


# =========================================================
# ИКОНКА / РЕСУРСЫ
# =========================================================

def resource_path(filename):

    import os

    if hasattr(sys, "_MEIPASS"):
        return os.path.join(
            sys._MEIPASS,
            filename
        )

    return os.path.join(
        os.path.abspath("."),
        filename
    )


# =========================================================
# ПОТОК ПОИСКА
# =========================================================

class SearchWorker(QThread):

    finished = Signal(dict, float)
    error = Signal(str)

    def __init__(
        self,
        players,
        lobby_only=False
    ):
        super().__init__()

        self.players = players
        self.lobby_only = lobby_only

    def run(self):

        try:

            start_time = time.perf_counter()

            result = find_players(
                self.players,
                self.lobby_only
            )

            elapsed_time = (
                time.perf_counter()
                - start_time
            )

            self.finished.emit(
                result,
                elapsed_time
            )

        except Exception as error:

            self.error.emit(
                str(error)
            )


# =========================================================
# ФОНОВАЯ СИНХРОНИЗАЦИЯ ОБЩЕЙ ГРУППЫ
# =========================================================

class CloudSyncWorker(QThread):

    finished = Signal(dict, int)
    error = Signal(str, int)

    def __init__(
        self,
        connection,
        local_database,
        generation,
        interactive=False,
    ):
        super().__init__()

        self.connection = dict(connection)
        self.local_database = local_database
        self.generation = generation
        self.interactive = interactive

    def run(self):
        try:
            result = sync_group(
                self.connection,
                self.local_database,
                interactive=self.interactive,
            )

            self.finished.emit(
                result,
                self.generation,
            )

        except Exception as error:
            self.error.emit(
                str(error),
                self.generation,
            )


# =========================================================
# АВТООБНОВЛЕНИЕ
# =========================================================

class UpdateCheckWorker(QThread):

    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            self.finished.emit(
                check_for_update()
            )
        except Exception as error:
            self.error.emit(
                str(error)
            )


class UpdateDownloadWorker(QThread):

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, update_info):
        super().__init__()
        self.update_info = update_info

    def run(self):
        try:
            path = download_update(
                self.update_info
            )
            self.finished.emit(path)
        except Exception as error:
            self.error.emit(str(error))


# =========================================================
# ОКНО РЕЗУЛЬТАТОВ
# =========================================================

class ResultsDialog(QDialog):

    def __init__(
        self,
        manager,
        results,
        elapsed_time,
        show_steam_nick=False,
        parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "Результаты поиска"
        )

        self.resize(
            850,
            600
        )

        self.setModal(
            False
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        layout.setSpacing(
            12
        )

        title = QLabel(
            "Результаты поиска"
        )

        title.setObjectName(
            "title"
        )

        layout.addWidget(
            title
        )

        subtitle = QLabel(
            "Показано расположение игроков "
            "на найденных серверах."
        )

        layout.addWidget(
            subtitle
        )

        time_label = QLabel(
            f"Время поиска: "
            f"{elapsed_time:.2f} сек."
        )

        layout.addWidget(
            time_label
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            3
        )

        nickname_header = (
            "Ник Steam"
            if show_steam_nick
            else "Ник Shinri"
        )

        self.table.setHorizontalHeaderLabels([
            "Список",
            nickname_header,
            "Серверы"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch
        )

        self.table.verticalHeader().setVisible(
            False
        )

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        layout.addWidget(
            self.table
        )

        self.fill_results(
            manager,
            results,
            show_steam_nick
        )

        close_button = QPushButton(
            "Закрыть"
        )

        close_button.clicked.connect(
            self.close
        )

        layout.addWidget(
            close_button
        )

    def fill_results(
        self,
        manager,
        results,
        show_steam_nick
    ):

        self.table.setRowCount(
            0
        )

        for player_list in manager.lists:

            for player in player_list.players:

                row = (
                    self.table.rowCount()
                )

                self.table.insertRow(
                    row
                )

                # -------------------------------
                # Имя, которое показываем
                # -------------------------------

                if show_steam_nick:

                    display_name = (
                        player.steam_name
                    )

                else:

                    display_name = (
                        player.shinri_name
                        or player.steam_name
                    )

                # -------------------------------
                # Ищем серверы по обоим никам
                # -------------------------------

                found_servers = []

                names_to_check = [
                    player.steam_name,
                    player.shinri_name
                ]

                for name in names_to_check:

                    if not name:
                        continue

                    for server in results.get(
                        name,
                        []
                    ):

                        if server not in found_servers:
                            found_servers.append(
                                server
                            )

                # -------------------------------
                # Заполняем строку
                # -------------------------------

                self.table.setItem(
                    row,
                    0,
                    QTableWidgetItem(
                        player_list.name
                    )
                )

                self.table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        display_name
                    )
                )

                if found_servers:

                    server_text = "\n".join(
                        found_servers
                    )

                else:

                    server_text = "Не найден"

                self.table.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        server_text
                    )
                )


# =========================================================
# АВТОМАТИЧЕСКОЕ ОКНО НАЙДЕННОЙ КОМАНДЫ
# =========================================================

class AutoMatchDialog(QDialog):

    def __init__(
        self,
        result,
        show_steam_nick=False,
        target_screen=None,
        parent=None
    ):
        super().__init__(parent)

        self.target_screen = target_screen

        # Окно поверх игры, но стараемся не отбирать у GMod фокус.
        self.setWindowFlags(
            Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )

        self.setAttribute(
            Qt.WA_ShowWithoutActivating,
            True
        )

        self.setWindowTitle(
            "Игроки найденной команды"
        )

        self.resize(
            900,
            610
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            16,
            16,
            16,
            16
        )

        layout.setSpacing(
            9
        )

        title = QLabel(
            "КОМАНДА НАЙДЕНА — проверка списка"
        )

        title.setObjectName(
            "sectionTitle"
        )

        layout.addWidget(
            title
        )

        players = result.get(
            "players",
            []
        )

        found = [
            item
            for item in players
            if item.get("status") == "found"
        ]

        possible = [
            item
            for item in players
            if item.get("status") == "possible"
        ]

        recognized = sum(
            1
            for item in players
            if item.get("ocr_name")
        )

        if found:
            quick_names = []

            for item in found:
                player = item.get("match") or {}

                if show_steam_nick:
                    display_name = player.get(
                        "steam_name",
                        ""
                    )
                else:
                    display_name = (
                        player.get("shinri_name")
                        or player.get("steam_name")
                        or ""
                    )

                if display_name:
                    quick_names.append(
                        display_name
                    )

            quick_text = (
                "В твоих списках: "
                + ", ".join(quick_names)
            )
        else:
            quick_text = (
                "Точных совпадений с твоими списками нет."
            )

        summary = QLabel(
            quick_text
        )

        summary.setWordWrap(
            True
        )

        layout.addWidget(
            summary
        )

        info_text = (
            f"Распознано: {recognized}/16  •  "
            f"найдено: {len(found)}"
        )

        if possible:
            info_text += (
                f"  •  возможных совпадений: {len(possible)}"
            )

        ocr_time = result.get(
            "ocr_time",
            0.0
        )

        info_text += (
            f"  •  OCR: {ocr_time:.2f} сек."
        )

        info = QLabel(
            info_text
        )

        layout.addWidget(
            info
        )

        self.table = QTableWidget()

        self.table.setColumnCount(
            5
        )

        self.table.setHorizontalHeaderLabels([
            "Статус",
            "Ник на экране",
            "Игрок в базе",
            "Список",
            "Заметка"
        ])

        self.table.verticalHeader().setVisible(
            False
        )

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.table.setSelectionMode(
            QAbstractItemView.NoSelection
        )

        self.table.setWordWrap(
            True
        )

        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        self.table.setRowCount(
            len(players)
        )

        for row, item in enumerate(players):
            status = item.get(
                "status",
                "not_found"
            )

            score = item.get(
                "score",
                0.0
            )

            if status == "found":
                status_text = "✓ Есть"
            elif status == "possible":
                status_text = (
                    f"? Возможно ({score:.0%})"
                )
            elif status == "unread":
                status_text = "? OCR"
            else:
                status_text = "— Нет"

            ocr_name = (
                item.get("ocr_name")
                or "<не распознано>"
            )

            matched_player = item.get(
                "match"
            )

            display_name = ""
            list_name = ""
            note = ""

            if matched_player:
                if show_steam_nick:
                    display_name = matched_player.get(
                        "steam_name",
                        ""
                    )
                else:
                    display_name = (
                        matched_player.get("shinri_name")
                        or matched_player.get("steam_name")
                        or ""
                    )

                list_name = matched_player.get(
                    "list_name",
                    ""
                )

                note = matched_player.get(
                    "note",
                    ""
                )

            values = (
                status_text,
                ocr_name,
                display_name,
                list_name,
                note,
            )

            for column, value in enumerate(values):
                self.table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        str(value)
                    )
                )

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            4,
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.table
        )

        hint = QLabel(
            "Окно закроется автоматически, когда экран подтверждения игры исчезнет."
        )

        hint.setWordWrap(
            True
        )

        layout.addWidget(
            hint
        )

    def showEvent(self, event):
        super().showEvent(event)

        # Показываем результат на ТОМ ЖЕ мониторе, где находится
        # главное окно Shinri Tracker, а не там, где сейчас GMod/курсор.
        screen = self.target_screen

        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is None:
            return

        geometry = screen.availableGeometry()

        self.move(
            geometry.right() - self.width() - 20,
            geometry.top() + 70
        )


# =========================================================
# ОКНО ИГРОКА
# =========================================================

class PlayerDialog(QDialog):

    def __init__(
        self,
        parent=None,
        steam_name="",
        shinri_name="",
        note=""
    ):
        super().__init__(
            parent
        )

        self.setWindowTitle(
            "Игрок"
        )

        self.resize(
            450,
            300
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        layout.setSpacing(
            10
        )

        # =================================================
        # STEAM
        # =================================================

        layout.addWidget(
            QLabel("Steam-ник")
        )

        self.steam_edit = QLineEdit()

        self.steam_edit.setText(
            steam_name
        )

        self.steam_edit.setPlaceholderText(
            "Steam nickname..."
        )

        layout.addWidget(
            self.steam_edit
        )

        # =================================================
        # SHINRI
        # =================================================

        layout.addWidget(
            QLabel("Shinri-ник")
        )

        self.shinri_edit = QLineEdit()

        self.shinri_edit.setText(
            shinri_name
        )

        self.shinri_edit.setPlaceholderText(
            "Ник персонажа в Shinri..."
        )

        layout.addWidget(
            self.shinri_edit
        )

        # =================================================
        # ЗАМЕТКА
        # =================================================

        layout.addWidget(
            QLabel("Заметка")
        )

        self.note_edit = QPlainTextEdit()

        self.note_edit.setPlainText(
            note
        )

        self.note_edit.setPlaceholderText(
            "Любая дополнительная информация..."
        )

        self.note_edit.setMinimumHeight(
            80
        )

        layout.addWidget(
            self.note_edit
        )

        # =================================================
        # КНОПКИ
        # =================================================

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def get_data(self):

        return (
            self.steam_edit.text().strip(),
            self.shinri_edit.text().strip(),
            self.note_edit.toPlainText().strip()
        )


# =========================================================
# ГЛАВНОЕ ОКНО
# =========================================================

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()


        self.setWindowTitle(
            "Shinri Tracker"
        )

        self.setWindowIcon(
            QIcon(
                resource_path(
                    "icon.png"
                )
            )
        )

        self.resize(
            1100,
            700
        )

        self.setMinimumSize(
            850,
            550
        )

        # Источник базы может быть:
        # 1) стандартный storage.py;
        # 2) пользовательский JSON;
        # 3) общая Google Drive группа с локальным кэшем.
        self.current_db_path = None
        self.cloud_group = None
        self.cloud_sync_worker = None
        self.cloud_generation = 0
        self.cloud_sync_pending = False
        self.update_check_worker = None
        self.update_download_worker = None
        self.update_check_manual = False

        default_manager = load_data()
        self.manager = default_manager

        remembered_group = load_active_group()

        if remembered_group:
            cached_database = load_group_cache(
                remembered_group["group_id"]
            )

            if cached_database:
                try:
                    self.manager = manager_from_dict(
                        cached_database,
                        default_manager
                    )
                    self.cloud_group = remembered_group
                except Exception as error:
                    print(
                        "[Cloud] Не удалось открыть локальный кэш группы:",
                        error
                    )

        # Если общей группы нет, восстанавливаем обычный локальный JSON.
        if self.cloud_group is None:
            remembered_db = get_remembered_database_path()

            if remembered_db:
                try:
                    self.manager = load_manager_from_file(
                        remembered_db,
                        default_manager
                    )
                    self.current_db_path = remembered_db
                except Exception as error:
                    print(
                        "[Database] Не удалось открыть последнюю базу:",
                        error
                    )
                    remember_database_path(None)

        if not self.manager.lists:
            self.manager.create_list(
                "Друзья"
            )

            if self.cloud_group:
                save_group_cache(
                    self.cloud_group["group_id"],
                    manager_to_dict(self.manager)
                )
            elif self.current_db_path:
                save_manager_to_file(
                    self.manager,
                    self.current_db_path
                )
            else:
                save_data(
                    self.manager
                )

        self.search_worker = None
        self.results_window = None

        self.create_interface()

        self.update_lists()

        self.update_database_label()

        # Автоматический монитор экрана подтверждения матча.
        # Сам OCR работает в отдельном QThread, поэтому интерфейс не зависает.
        self.auto_match_window = None

        self.match_monitor = MatchMonitor()

        self.match_monitor.set_auto_enabled(
            self.auto_match_action.isChecked()
        )

        self.match_monitor.match_found.connect(
            self.on_auto_match
        )

        self.match_monitor.match_ended.connect(
            self.on_auto_match_ended
        )

        self.match_monitor.error.connect(
            self.on_match_monitor_error
        )

        self.match_monitor.start()

        # Синхронизация общей базы: небольшая задержка после локальных правок
        # + периодическая проверка изменений других участников.
        self.cloud_debounce_timer = QTimer(self)
        self.cloud_debounce_timer.setSingleShot(True)
        self.cloud_debounce_timer.setInterval(1800)
        self.cloud_debounce_timer.timeout.connect(
            lambda: self.sync_cloud_group(silent=True)
        )

        self.cloud_periodic_timer = QTimer(self)
        self.cloud_periodic_timer.setInterval(45000)
        self.cloud_periodic_timer.timeout.connect(
            lambda: self.sync_cloud_group(silent=True)
        )
        self.cloud_periodic_timer.start()

        if self.cloud_group:
            QTimer.singleShot(
                2500,
                lambda: self.sync_cloud_group(silent=True)
            )

        # Автопроверка GitHub Release не блокирует запуск окна.
        if (
            load_update_config().get("auto_check", True)
            and is_update_configured()
        ):
            QTimer.singleShot(
                4000,
                lambda: self.check_updates(manual=False)
            )

    # =====================================================
    # СОЗДАНИЕ ИНТЕРФЕЙСА
    # =====================================================

    def get_all_saved_players(self):
        """
        Делает лёгкий снимок текущей локальной базы игроков.
        Здесь используется реальная структура проекта: self.manager.lists
        -> player_list.players.
        """

        players = []

        for player_list in self.manager.lists:
            for player in player_list.players:
                players.append({
                    "steam_name": player.steam_name,
                    "shinri_name": player.shinri_name,
                    "note": player.note,
                    "list_name": player_list.name,
                })

        return players

    def on_auto_match(self, ocr_result):
        """
        Вызывается Qt-сигналом уже в GUI-потоке.
        Сопоставление 16 OCR-ников с базой происходит мгновенно.
        """

        matched_rows = match_players(
            ocr_result.get("names", []),
            ocr_result.get("confidences", []),
            self.get_all_saved_players(),
            candidates_by_slot=ocr_result.get("candidates"),
        )

        result = dict(ocr_result)
        result["players"] = matched_rows

        self.show_auto_match_result(result)

    def on_auto_match_ended(self):
        """
        Экран подтверждения исчез.

        Если включена галочка автоматического закрытия —
        закрываем окно результатов. Иначе оставляем его открытым.
        """

        if not self.auto_close_analysis_action.isChecked():
            return

        if self.auto_match_window is not None:
            self.auto_match_window.close()
            self.auto_match_window = None

    def on_match_monitor_error(self, message):
        print(f"[MatchMonitor] {message}")

        QMessageBox.warning(
            self,
            "Автопроверка найденной игры",
            message
        )

    def auto_match_enabled_changed(self):
        """
        Включает/выключает автоматическое распознавание.
        F8 остаётся рабочей для ручной проверки.
        """

        enabled = self.auto_match_action.isChecked()

        monitor = getattr(
            self,
            "match_monitor",
            None
        )

        if monitor is not None:
            monitor.set_auto_enabled(
                enabled
            )

        if not enabled and self.auto_match_window is not None:
            self.auto_match_window.close()
            self.auto_match_window = None

    def create_menus(self):
        """
        Классическое верхнее меню вместо постоянно видимых
        кнопок базы и галочек настроек.
        """

        menu_bar = self.menuBar()

        # =================================================
        # ФАЙЛ
        # =================================================

        file_menu = menu_bar.addMenu(
            "Файл"
        )

        new_database_action = QAction(
            "Новая база...",
            self
        )
        new_database_action.setShortcut(
            "Ctrl+N"
        )
        new_database_action.triggered.connect(
            self.create_new_database
        )

        open_database_action = QAction(
            "Открыть базу...",
            self
        )
        open_database_action.setShortcut(
            "Ctrl+O"
        )
        open_database_action.triggered.connect(
            self.open_database
        )

        merge_database_action = QAction(
            "Объединить с другой базой...",
            self
        )
        merge_database_action.triggered.connect(
            self.merge_database
        )

        default_database_action = QAction(
            "Открыть стандартную базу",
            self
        )
        default_database_action.triggered.connect(
            self.use_default_database
        )

        file_menu.addAction(
            new_database_action
        )
        file_menu.addAction(
            open_database_action
        )
        file_menu.addAction(
            merge_database_action
        )
        file_menu.addSeparator()
        file_menu.addAction(
            default_database_action
        )
        file_menu.addSeparator()

        exit_action = QAction(
            "Выход",
            self
        )
        exit_action.triggered.connect(
            self.close
        )
        file_menu.addAction(
            exit_action
        )

        # =================================================
        # ОБЩАЯ ГРУППА
        # =================================================

        group_menu = menu_bar.addMenu(
            "Общая группа"
        )

        self.group_create_action = QAction(
            "Создать группу из текущей базы...",
            self
        )
        self.group_create_action.triggered.connect(
            self.create_cloud_group
        )

        self.group_connect_action = QAction(
            "Подключиться к группе...",
            self
        )
        self.group_connect_action.triggered.connect(
            self.connect_cloud_group
        )

        self.group_import_invite_action = QAction(
            "Открыть файл приглашения...",
            self
        )
        self.group_import_invite_action.triggered.connect(
            self.import_cloud_invite
        )

        self.group_sync_action = QAction(
            "Синхронизировать сейчас",
            self
        )
        self.group_sync_action.setShortcut(
            "Ctrl+Shift+S"
        )
        self.group_sync_action.triggered.connect(
            lambda: self.sync_cloud_group(silent=False, interactive=True)
        )

        self.group_invite_action = QAction(
            "Пригласить участника...",
            self
        )
        self.group_invite_action.triggered.connect(
            self.invite_cloud_member
        )

        self.group_members_action = QAction(
            "Участники...",
            self
        )
        self.group_members_action.triggered.connect(
            self.show_cloud_members
        )

        self.group_export_invite_action = QAction(
            "Сохранить файл приглашения...",
            self
        )
        self.group_export_invite_action.triggered.connect(
            self.export_cloud_invite
        )

        self.group_disconnect_action = QAction(
            "Отключиться от группы",
            self
        )
        self.group_disconnect_action.triggered.connect(
            self.disconnect_cloud_group
        )

        self.google_logout_action = QAction(
            "Выйти из Google-аккаунта на этом ПК",
            self
        )
        self.google_logout_action.triggered.connect(
            self.logout_google_account
        )

        group_menu.addAction(
            self.group_create_action
        )
        group_menu.addAction(
            self.group_connect_action
        )
        group_menu.addAction(
            self.group_import_invite_action
        )
        group_menu.addSeparator()
        group_menu.addAction(
            self.group_sync_action
        )
        group_menu.addAction(
            self.group_invite_action
        )
        group_menu.addAction(
            self.group_members_action
        )
        group_menu.addAction(
            self.group_export_invite_action
        )
        group_menu.addSeparator()
        group_menu.addAction(
            self.group_disconnect_action
        )
        group_menu.addAction(
            self.google_logout_action
        )

        # =================================================
        # НАСТРОЙКИ
        # =================================================

        settings_menu = menu_bar.addMenu(
            "Настройки"
        )

        self.show_steam_action = QAction(
            "Показывать Steam-ник",
            self
        )
        self.show_steam_action.setCheckable(
            True
        )
        self.show_steam_action.setChecked(
            False
        )
        self.show_steam_action.toggled.connect(
            lambda _checked: self.nickname_display_changed()
        )

        self.lobby_only_action = QAction(
            "Искать только в общем лобби",
            self
        )
        self.lobby_only_action.setCheckable(
            True
        )
        self.lobby_only_action.setChecked(
            False
        )

        self.auto_match_action = QAction(
            "Автоматически анализировать найденную игру",
            self
        )
        self.auto_match_action.setCheckable(
            True
        )
        self.auto_match_action.setChecked(
            True
        )
        self.auto_match_action.toggled.connect(
            lambda _checked: self.auto_match_enabled_changed()
        )

        self.auto_close_analysis_action = QAction(
            "Автоматически закрывать окно анализа",
            self
        )
        self.auto_close_analysis_action.setCheckable(
            True
        )
        self.auto_close_analysis_action.setChecked(
            True
        )

        settings_menu.addAction(
            self.show_steam_action
        )
        settings_menu.addAction(
            self.lobby_only_action
        )
        settings_menu.addSeparator()
        settings_menu.addAction(
            self.auto_match_action
        )
        settings_menu.addAction(
            self.auto_close_analysis_action
        )

        # =================================================
        # ПОМОЩЬ / ОБНОВЛЕНИЯ
        # =================================================

        help_menu = menu_bar.addMenu(
            "Помощь"
        )

        update_action = QAction(
            "Проверить обновления...",
            self
        )
        update_action.triggered.connect(
            lambda: self.check_updates(manual=True)
        )

        version_action = QAction(
            f"Версия {get_current_version()}",
            self
        )
        version_action.setEnabled(False)

        help_menu.addAction(
            update_action
        )
        help_menu.addSeparator()
        help_menu.addAction(
            version_action
        )

        self.update_group_actions()

    def create_interface(self):

        self.create_menus()

        central_widget = QWidget()

        self.setCentralWidget(
            central_widget
        )

        main_layout = QVBoxLayout()

        main_layout.setContentsMargins(
            12,
            10,
            12,
            10
        )

        main_layout.setSpacing(
            8
        )

        central_widget.setLayout(
            main_layout
        )

        # Текущая база больше не занимает целую строку.
        # Показываем её компактно внизу окна.
        self.database_label = QLabel(
            "База: стандартная"
        )

        self.statusBar().addPermanentWidget(
            self.database_label
        )

        self.statusBar().showMessage(
            "F8 — ручной анализ экрана",
            0
        )

        # =================================================
        # ОСНОВНОЙ КОНТЕНТ
        # =================================================

        content_layout = QHBoxLayout()

        content_layout.setSpacing(
            10
        )

        # =================================================
        # ЛЕВАЯ ПАНЕЛЬ — СПИСКИ
        # =================================================

        left_layout = QVBoxLayout()

        left_layout.setSpacing(
            6
        )

        list_title = QLabel(
            "Списки"
        )

        list_title.setObjectName(
            "sectionTitle"
        )

        left_layout.addWidget(
            list_title
        )

        self.list_widget = QListWidget()

        self.list_widget.currentRowChanged.connect(
            self.on_list_selected
        )

        left_layout.addWidget(
            self.list_widget
        )

        list_buttons = QHBoxLayout()

        list_buttons.setSpacing(
            5
        )

        add_list_button = QPushButton(
            "＋"
        )
        add_list_button.setToolTip(
            "Добавить список"
        )

        delete_list_button = QPushButton(
            "－"
        )
        delete_list_button.setToolTip(
            "Удалить список"
        )

        rename_list_button = QPushButton(
            "Переименовать"
        )

        add_list_button.setObjectName(
            "addButton"
        )

        delete_list_button.setObjectName(
            "deleteButton"
        )

        add_list_button.clicked.connect(
            self.add_list
        )

        delete_list_button.clicked.connect(
            self.delete_list
        )

        rename_list_button.clicked.connect(
            self.rename_list
        )

        list_buttons.addWidget(
            add_list_button
        )

        list_buttons.addWidget(
            delete_list_button
        )

        list_buttons.addWidget(
            rename_list_button,
            1
        )

        left_layout.addLayout(
            list_buttons
        )

        # =================================================
        # ПРАВАЯ ПАНЕЛЬ — ИГРОКИ
        # =================================================

        right_layout = QVBoxLayout()

        right_layout.setSpacing(
            6
        )

        title_row = QHBoxLayout()

        self.players_label = QLabel(
            "Игроки (0)"
        )

        self.players_label.setObjectName(
            "sectionTitle"
        )

        title_row.addWidget(
            self.players_label
        )

        title_row.addStretch()

        # Поиск переехал в ту же строку, что и заголовок.
        self.player_search = QLineEdit()

        self.player_search.setPlaceholderText(
            "Поиск игрока..."
        )

        self.player_search.setClearButtonEnabled(
            True
        )

        self.player_search.setMaximumWidth(
            320
        )

        self.player_search.textChanged.connect(
            self.filter_players
        )

        title_row.addWidget(
            self.player_search
        )

        right_layout.addLayout(
            title_row
        )

        # =================================================
        # ТАБЛИЦА
        # =================================================

        self.player_table = QTableWidget()

        self.player_table.setColumnCount(
            2
        )

        self.player_table.setHorizontalHeaderLabels([
            "Ник Shinri",
            "Заметка"
        ])

        self.player_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        self.player_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        self.player_table.horizontalHeader().setMinimumSectionSize(
            160
        )

        self.player_table.setWordWrap(
            True
        )

        self.player_table.verticalHeader().setVisible(
            False
        )

        self.player_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        self.player_table.setAlternatingRowColors(
            True
        )

        self.player_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.player_table.cellDoubleClicked.connect(
            self.edit_player
        )

        right_layout.addWidget(
            self.player_table,
            1
        )

        # =================================================
        # КНОПКИ ИГРОКОВ
        # =================================================

        player_buttons = QHBoxLayout()

        player_buttons.setSpacing(
            6
        )

        add_player_button = QPushButton(
            "＋ Добавить"
        )

        delete_player_button = QPushButton(
            "－ Удалить"
        )

        edit_player_button = QPushButton(
            "Изменить"
        )

        move_player_button = QPushButton(
            "Перенести"
        )

        add_player_button.setObjectName(
            "addButton"
        )

        delete_player_button.setObjectName(
            "deleteButton"
        )

        add_player_button.clicked.connect(
            self.add_player
        )

        delete_player_button.clicked.connect(
            self.delete_player
        )

        edit_player_button.clicked.connect(
            lambda: self.edit_player()
        )

        move_player_button.clicked.connect(
            lambda: self.move_player()
        )

        player_buttons.addWidget(
            add_player_button
        )

        player_buttons.addWidget(
            delete_player_button
        )

        player_buttons.addWidget(
            edit_player_button
        )

        player_buttons.addWidget(
            move_player_button
        )

        right_layout.addLayout(
            player_buttons
        )

        content_layout.addLayout(
            left_layout,
            1
        )

        content_layout.addLayout(
            right_layout,
            4
        )

        main_layout.addLayout(
            content_layout,
            1
        )

        # =================================================
        # ПОИСК ПО СЕРВЕРАМ
        # =================================================

        self.search_button = QPushButton(
            "ПОИСК ИГРОКОВ"
        )

        self.search_button.setObjectName(
            "searchButton"
        )

        self.search_button.setMinimumHeight(
            40
        )

        self.search_button.clicked.connect(
            self.start_search
        )

        main_layout.addWidget(
            self.search_button
        )

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            0
        )

        self.progress.setMaximumHeight(
            8
        )

        self.progress.hide()

        main_layout.addWidget(
            self.progress
        )

    # =====================================================
    # СПИСКИ
    # =====================================================
    def show_auto_match_result(self, result):
        # Закрываем прошлое окно, если по какой-то причине оно осталось.
        if self.auto_match_window is not None:
            self.auto_match_window.close()

        show_steam = (
            self.show_steam_action.isChecked()
        )

        # Запоминаем монитор главного окна программы. Даже если Shinri Tracker
        # сейчас не активен, результат появится именно на этом мониторе.
        target_screen = self.screen()

        # parent=None намеренно: если главное окно программы свёрнуто,
        # окно результата всё равно сможет показаться.
        self.auto_match_window = AutoMatchDialog(
            result,
            show_steam_nick=show_steam,
            target_screen=target_screen,
            parent=None
        )

        self.auto_match_window.show()

    # =====================================================
    # ОБЩИЕ ГРУППЫ / GOOGLE DRIVE
    # =====================================================

    def update_group_actions(self):
        active = bool(
            getattr(self, "cloud_group", None)
        )

        for action_name in (
            "group_sync_action",
            "group_invite_action",
            "group_members_action",
            "group_export_invite_action",
            "group_disconnect_action",
        ):
            action = getattr(
                self,
                action_name,
                None
            )

            if action is not None:
                action.setEnabled(
                    active
                )

    def _show_google_setup_error(self, message=None):
        if not message:
            _ok, message = google_setup_status()

        QMessageBox.warning(
            self,
            "Google Drive не настроен",
            message
            + "\n\nДля владельца программы это настраивается один раз. "
              "После сборки EXE обычный пользователь только входит "
              "в свой Google-аккаунт в браузере."
        )

    def _activate_cloud_group(
        self,
        connection,
        database,
    ):
        self.cloud_group = connection
        self.current_db_path = None

        remember_database_path(
            None
        )

        self.manager = manager_from_dict(
            database,
            self.manager
        )

        self.cloud_generation += 1
        self.cloud_sync_pending = False

        self._refresh_after_database_change()
        self.update_group_actions()
        self.update_database_label(
            sync_text="синхронизировано"
        )

    def create_cloud_group(self):
        ok, message = google_setup_status()

        if not ok:
            self._show_google_setup_error(
                message
            )
            return

        name, accepted = QInputDialog.getText(
            self,
            "Создать общую группу",
            "Название группы:"
        )

        name = name.strip()

        if not accepted or not name:
            return

        answer = QMessageBox.question(
            self,
            "Создание группы",
            "Текущая база будет загружена в новую общую группу Google Drive.\n\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            self.statusBar().showMessage(
                "Создаю общую группу в Google Drive..."
            )
            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            database = manager_to_dict(
                self.manager
            )

            connection = create_group(
                name,
                database,
            )

            self._activate_cloud_group(
                connection,
                database,
            )

            QMessageBox.information(
                self,
                "Группа создана",
                f"Общая группа «{name}» создана.\n\n"
                "Теперь можно открыть «Общая группа → Пригласить участника»."
            )

        except GoogleSetupError as error:
            self._show_google_setup_error(
                str(error)
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка Google Drive",
                f"Не удалось создать группу:\n{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage(
                "F8 — ручной анализ экрана",
                5000
            )

    def connect_cloud_group(self):
        ok, message = google_setup_status()

        if not ok:
            self._show_google_setup_error(
                message
            )
            return

        try:
            self.statusBar().showMessage(
                "Ищу доступные общие группы в Google Drive..."
            )
            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            groups = list_available_groups()

        except GoogleSetupError as error:
            self._show_google_setup_error(
                str(error)
            )
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка Google Drive",
                f"Не удалось получить список групп:\n{error}"
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not groups:
            answer = QMessageBox.question(
                self,
                "Группы не найдены",
                "Shinri Tracker не нашёл доступных групп.\n\n"
                "Если тебе прислали файл .shinrigroup, открыть его сейчас?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )

            if answer == QMessageBox.Yes:
                self.import_cloud_invite()

            return

        labels = []
        by_label = {}

        for group in groups:
            short_id = str(
                group.get("group_id", "")
            )[:8]

            label = (
                f"{group.get('name', 'Без названия')}"
                f"  [{short_id}]"
            )

            labels.append(label)
            by_label[label] = group

        selected, accepted = QInputDialog.getItem(
            self,
            "Подключиться к группе",
            "Доступные группы:",
            labels,
            0,
            False,
        )

        if not accepted or not selected:
            return

        try:
            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            connection, database = connect_group(
                by_label[selected]
            )

            self._activate_cloud_group(
                connection,
                database,
            )

            QMessageBox.information(
                self,
                "Группа подключена",
                f"Теперь используется общая база «{connection.get('name', '')}»."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка подключения",
                f"Не удалось подключить группу:\n{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def import_cloud_invite(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть приглашение Shinri Tracker",
            "",
            "Shinri Group (*.shinrigroup);;JSON (*.json);;Все файлы (*.*)"
        )

        if not file_path:
            return

        try:
            import json

            with open(
                file_path,
                "r",
                encoding="utf-8-sig"
            ) as file:
                invite = json.load(file)

            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            connection, database = connect_group_from_invite(
                invite
            )

            self._activate_cloud_group(
                connection,
                database,
            )

            QMessageBox.information(
                self,
                "Группа подключена",
                f"Подключена группа «{connection.get('name', '')}»."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка приглашения",
                "Не удалось открыть общую группу. Проверь, что владелец "
                "пригласил именно этот Google-аккаунт. Если открылось окно "
                "Google Drive, выбери предложенный файл базы и подтверди "
                "доступ Shinri Tracker.\n\n"
                f"{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def invite_cloud_member(self):
        if not self.cloud_group:
            return

        email, accepted = QInputDialog.getText(
            self,
            "Пригласить участника",
            "Google-аккаунт участника (email):"
        )

        email = email.strip()

        if not accepted or not email:
            return

        if "@" not in email:
            QMessageBox.warning(
                self,
                "Некорректный email",
                "Укажи email Google-аккаунта."
            )
            return

        try:
            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            invite_member(
                self.cloud_group,
                email,
            )

            answer = QMessageBox.question(
                self,
                "Доступ выдан",
                f"Google Drive отправил приглашение на {email}.\n\n"
                "Сохранить ещё и маленький файл .shinrigroup, который можно "
                "передать через Discord на случай, если группа не появится "
                "в списке автоматически?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if answer == QMessageBox.Yes:
                self.export_cloud_invite()

        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка приглашения",
                f"Не удалось выдать доступ:\n{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def export_cloud_invite(self):
        if not self.cloud_group:
            return

        safe_name = "".join(
            char
            if char.isalnum() or char in " _-"
            else "_"
            for char in self.cloud_group.get("name", "Shinri Group")
        ).strip()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить приглашение",
            f"{safe_name}.shinrigroup",
            "Shinri Group (*.shinrigroup)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(
            ".shinrigroup"
        ):
            file_path += ".shinrigroup"

        try:
            import json

            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    make_invite_data(
                        self.cloud_group
                    ),
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            QMessageBox.information(
                self,
                "Приглашение сохранено",
                "Файл не содержит пароля или Google-токена. Передать его "
                "нужно только человеку, которому уже выдан доступ через "
                "«Пригласить участника»."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить приглашение:\n{error}"
            )

    def show_cloud_members(self):
        if not self.cloud_group:
            return

        try:
            QApplication.setOverrideCursor(
                Qt.WaitCursor
            )

            members = get_members(
                self.cloud_group
            )

            lines = []

            for member in members:
                name = (
                    member.get("displayName")
                    or member.get("emailAddress")
                    or member.get("type", "участник")
                )

                email = member.get("emailAddress", "")
                role = member.get("role", "")

                if email and email != name:
                    name = f"{name} — {email}"

                lines.append(
                    f"• {name} ({role})"
                )

            QMessageBox.information(
                self,
                "Участники общей группы",
                "\n".join(lines)
                if lines
                else "Участники не найдены."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось получить участников:\n{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_cloud_group(self):
        if not self.cloud_group:
            return

        answer = QMessageBox.question(
            self,
            "Отключиться от группы",
            "Отключить эту общую базу на данном ПК?\n\n"
            "Файлы группы в Google Drive НЕ удаляются. После отключения "
            "откроется стандартная локальная база.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        clear_active_group()
        self.cloud_group = None
        self.cloud_generation += 1
        self.cloud_sync_pending = False
        self.update_group_actions()

        self.manager = load_data()
        self.current_db_path = None
        remember_database_path(None)

        if not self.manager.lists:
            self.manager.create_list("Друзья")
            save_data(self.manager)

        self._refresh_after_database_change()

    def logout_google_account(self):
        answer = QMessageBox.question(
            self,
            "Выйти из Google",
            "Удалить сохранённый OAuth-токен Google с этого ПК?\n\n"
            "При следующей синхронизации браузер снова попросит войти.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        disconnect_google_account()

        QMessageBox.information(
            self,
            "Google",
            "Локальный токен удалён. Данные общей группы в Google Drive не изменены."
        )

    def sync_cloud_group(
        self,
        silent=True,
        interactive=False,
    ):
        if not self.cloud_group:
            if not silent:
                QMessageBox.information(
                    self,
                    "Общая группа",
                    "Сейчас общая группа не подключена."
                )
            return

        if self.cloud_sync_worker is not None:
            self.cloud_sync_pending = True
            return

        ok, message = google_setup_status()

        if not ok:
            self.update_database_label(
                sync_text="Google Drive не настроен"
            )

            if not silent:
                self._show_google_setup_error(message)
            return

        generation = self.cloud_generation
        local_database = manager_to_dict(
            self.manager
        )

        worker = CloudSyncWorker(
            self.cloud_group,
            local_database,
            generation,
            interactive=interactive,
        )

        worker.silent = silent
        self.cloud_sync_worker = worker

        self.update_database_label(
            sync_text="синхронизация..."
        )

        worker.finished.connect(
            self.on_cloud_sync_finished
        )
        worker.error.connect(
            self.on_cloud_sync_error
        )
        worker.start()

    def on_cloud_sync_finished(
        self,
        result,
        generation,
    ):
        worker = self.cloud_sync_worker
        self.cloud_sync_worker = None

        if not self.cloud_group:
            return

        if (
            worker is not None
            and self.cloud_group.get("group_id")
            != worker.connection.get("group_id")
        ):
            return

        conflicts = int(
            result.get("conflicts", 0)
        )

        # Пока шёл интернет-запрос, пользователь мог успеть что-то изменить.
        # В таком случае его свежие данные НЕ перетираем результатом потока.
        if generation == self.cloud_generation:
            self.manager = manager_from_dict(
                result["database"],
                self.manager
            )
            self.update_lists()
        else:
            save_group_cache(
                self.cloud_group["group_id"],
                manager_to_dict(self.manager)
            )
            self.cloud_sync_pending = True

        if conflicts:
            self.update_database_label(
                sync_text=f"синхронизировано, конфликтов: {conflicts}"
            )
        else:
            self.update_database_label(
                sync_text="синхронизировано"
            )

        if worker is not None and not getattr(worker, "silent", True):
            message = "Общая база синхронизирована."

            if conflicts:
                message += (
                    f"\n\nОбнаружено конфликтов полей: {conflicts}. "
                    "В спорных местах сохранён вариант с этого ПК."
                )

            QMessageBox.information(
                self,
                "Синхронизация",
                message
            )

        if self.cloud_sync_pending:
            self.cloud_sync_pending = False
            QTimer.singleShot(
                500,
                lambda: self.sync_cloud_group(silent=True)
            )

    def on_cloud_sync_error(
        self,
        message,
        generation,
    ):
        worker = self.cloud_sync_worker
        self.cloud_sync_worker = None

        if (
            worker is not None
            and self.cloud_group
            and self.cloud_group.get("group_id")
            != worker.connection.get("group_id")
        ):
            return

        self.update_database_label(
            sync_text="офлайн / ожидает синхронизации"
        )

        # Локальная работа продолжается даже без Google Drive.
        if self.cloud_group:
            save_group_cache(
                self.cloud_group["group_id"],
                manager_to_dict(self.manager)
            )

        if worker is not None and not getattr(worker, "silent", True):
            QMessageBox.warning(
                self,
                "Синхронизация не выполнена",
                message
                + "\n\nЛокальные изменения не потеряны и будут отправлены позже."
            )

    # =====================================================
    # АВТООБНОВЛЕНИЕ
    # =====================================================

    def check_updates(self, manual=True):
        if self.update_check_worker is not None:
            if manual:
                QMessageBox.information(
                    self,
                    "Обновление",
                    "Проверка уже выполняется."
                )
            return

        if not is_update_configured():
            if manual:
                QMessageBox.information(
                    self,
                    "Автообновление",
                    "GitHub-репозиторий ещё не указан в update_config.json.\n\n"
                    "Если собирать Release через приложенный workflow, "
                    "он заполнит github_owner/github_repo автоматически."
                )
            return

        self.update_check_manual = manual
        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.finished.connect(
            self.on_update_checked
        )
        self.update_check_worker.error.connect(
            self.on_update_check_error
        )

        if manual:
            self.statusBar().showMessage(
                "Проверяю GitHub Releases..."
            )

        self.update_check_worker.start()

    def on_update_checked(self, info):
        manual = self.update_check_manual
        self.update_check_worker = None

        if not info.get("available"):
            if manual:
                reason = info.get("reason")
                text = (
                    "В репозитории пока нет опубликованных Release."
                    if reason == "no_release"
                    else f"Установлена актуальная версия {get_current_version()}."
                )

                QMessageBox.information(
                    self,
                    "Обновление",
                    text
                )
            return

        notes = str(
            info.get("notes", "")
        ).strip()

        if len(notes) > 1200:
            notes = notes[:1200] + "\n..."

        message = (
            f"Доступна версия {info.get('version')}\n"
            f"Текущая версия: {get_current_version()}\n\n"
        )

        if notes:
            message += notes + "\n\n"

        if can_self_update():
            message += "Скачать и установить обновление?"
        else:
            message += (
                "Программа запущена не как собранный EXE, поэтому "
                "автозамена недоступна. Открыть страницу Release?"
            )

        answer = QMessageBox.question(
            self,
            "Доступно обновление",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        if not can_self_update():
            import webbrowser
            page = info.get("page_url")
            if page:
                webbrowser.open(page)
            return

        self.download_update_and_restart(
            info
        )

    def on_update_check_error(self, message):
        manual = self.update_check_manual
        self.update_check_worker = None

        if manual:
            QMessageBox.warning(
                self,
                "Не удалось проверить обновление",
                message
            )

    def download_update_and_restart(self, info):
        if self.update_download_worker is not None:
            return

        self.statusBar().showMessage(
            f"Скачиваю Shinri Tracker {info.get('version')}..."
        )

        worker = UpdateDownloadWorker(
            info
        )
        self.update_download_worker = worker
        worker.finished.connect(
            self.on_update_downloaded
        )
        worker.error.connect(
            self.on_update_download_error
        )
        worker.start()

    def on_update_downloaded(self, file_path):
        self.update_download_worker = None

        try:
            launch_update_replacer(
                file_path
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Ошибка обновления",
                str(error)
            )
            return

        QApplication.quit()

    def on_update_download_error(self, message):
        self.update_download_worker = None

        QMessageBox.critical(
            self,
            "Не удалось скачать обновление",
            message
        )

    # =====================================================
    # БАЗА ДАННЫХ
    # =====================================================

    def save_current_database(self):
        """
        Сохраняет активный источник данных. Для общей группы сначала пишем
        локальный кэш мгновенно, а Google Drive синхронизируем с debounce.
        """

        if self.cloud_group:
            database = manager_to_dict(
                self.manager
            )

            save_group_cache(
                self.cloud_group["group_id"],
                database
            )

            self.cloud_generation += 1

            if hasattr(self, "cloud_debounce_timer"):
                self.cloud_debounce_timer.start()

            self.update_database_label(
                sync_text="есть локальные изменения"
            )

        elif self.current_db_path:
            save_manager_to_file(
                self.manager,
                self.current_db_path
            )

        else:
            save_data(
                self.manager
            )

    def update_database_label(self, sync_text=None):

        if self.cloud_group:
            group_name = self.cloud_group.get(
                "name",
                "Общая группа"
            )

            text = f"База: ☁ {group_name}"

            if sync_text:
                text += f" • {sync_text}"

            self.database_label.setText(
                text
            )

            self.database_label.setToolTip(
                "Общая база Google Drive. "
                "Изменения всегда сначала сохраняются локально."
            )

        elif self.current_db_path:

            import os

            file_name = os.path.basename(
                self.current_db_path
            )

            self.database_label.setText(
                f"База: {file_name}"
            )

            self.database_label.setToolTip(
                self.current_db_path
            )

        else:

            self.database_label.setText(
                "База: стандартная"
            )

            self.database_label.setToolTip(
                "Стандартная база программы"
            )

    def _refresh_after_database_change(self):

        self.player_search.clear()

        self.update_lists()

        self.update_database_label()

    def _switch_from_cloud_to_local(self):
        """Отключает активную группу, не удаляя ничего из Google Drive."""

        if self.cloud_group:
            clear_active_group()
            self.cloud_group = None
            self.cloud_generation += 1
            self.cloud_sync_pending = False
            self.update_group_actions()

    def create_new_database(self):

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Создать новую базу",
            "shinri_players.json",
            "JSON (*.json)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(
            ".json"
        ):
            file_path += ".json"

        try:

            new_manager = create_empty_manager(
                self.manager,
                default_list_name="Друзья"
            )

            save_manager_to_file(
                new_manager,
                file_path
            )

            self._switch_from_cloud_to_local()
            self.manager = new_manager
            self.current_db_path = file_path

            remember_database_path(
                file_path
            )

            self._refresh_after_database_change()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать базу:\n{error}"
            )

    def open_database(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Подключить JSON-базу",
            "",
            "JSON (*.json);;Все файлы (*.*)"
        )

        if not file_path:
            return

        try:

            new_manager = load_manager_from_file(
                file_path,
                self.manager
            )

            self._switch_from_cloud_to_local()
            self.manager = new_manager
            self.current_db_path = file_path

            remember_database_path(
                file_path
            )

            self._refresh_after_database_change()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Ошибка базы",
                f"Не удалось открыть JSON:\n{error}"
            )

    def use_default_database(self):

        try:

            self._switch_from_cloud_to_local()
            self.manager = load_data()
            self.current_db_path = None

            remember_database_path(
                None
            )

            if not self.manager.lists:

                self.manager.create_list(
                    "Друзья"
                )

                save_data(
                    self.manager
                )

            self._refresh_after_database_change()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Ошибка базы",
                f"Не удалось открыть стандартную базу:\n{error}"
            )

    def merge_database(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Добавить данные из другой базы",
            "",
            "JSON (*.json);;Все файлы (*.*)"
        )

        if not file_path:
            return

        try:

            import os

            if (
                self.current_db_path
                and os.path.abspath(file_path)
                == os.path.abspath(self.current_db_path)
            ):

                QMessageBox.information(
                    self,
                    "Объединение",
                    "Это уже текущая база."
                )

                return

            incoming_manager = load_manager_from_file(
                file_path,
                self.manager
            )

            stats = merge_managers(
                self.manager,
                incoming_manager
            )

            self.save_current_database()

            self.update_lists()

            QMessageBox.information(
                self,
                "Объединение завершено",
                "Данные добавлены в текущую базу.\n\n"
                f"Новых списков: {stats['lists_added']}\n"
                f"Новых игроков: {stats['players_added']}\n"
                f"Повторов пропущено: {stats['duplicates_skipped']}\n\n"
                "При совпадениях сохранены записи текущей базы."
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Ошибка объединения",
                f"Не удалось объединить базы:\n{error}"
            )

    def update_lists(self):

        current_index = (
            self.list_widget.currentRow()
        )

        self.list_widget.clear()

        for player_list in self.manager.lists:

            self.list_widget.addItem(
                player_list.name
            )

        if self.manager.lists:

            if current_index < 0:
                current_index = 0

            if current_index >= len(
                self.manager.lists
            ):
                current_index = (
                    len(self.manager.lists) - 1
                )

            self.list_widget.setCurrentRow(
                current_index
            )

        else:

            self.player_table.setRowCount(
                0
            )

            self.players_label.setText(
                "Игроки (0)"
            )

    def on_list_selected(
        self,
        index
    ):

        if index < 0:

            self.player_table.setRowCount(
                0
            )

            self.players_label.setText(
                "Игроки (0)"
            )

            return

        player_list = (
            self.manager.lists[index]
        )

        self.update_players(
            player_list
        )

    # =====================================================
    # ПЕРЕКЛЮЧЕНИЕ STEAM / SHINRI
    # =====================================================

    def nickname_display_changed(
        self
    ):

        index = (
            self.list_widget.currentRow()
        )

        if index < 0:
            return

        player_list = (
            self.manager.lists[index]
        )

        self.update_players(
            player_list
        )

    # =====================================================
    # ИГРОКИ
    # =====================================================

    def update_players(
        self,
        player_list
    ):

        self.players_label.setText(
            f"Игроки — {player_list.name} ({len(player_list.players)})"
        )

        show_steam = (
            self.show_steam_action.isChecked()
        )

        if show_steam:

            self.player_table.setHorizontalHeaderLabels([
                "Ник Steam",
                "Заметка"
            ])

        else:

            self.player_table.setHorizontalHeaderLabels([
                "Ник Shinri",
                "Заметка"
            ])

        self.player_table.setRowCount(
            0
        )

        for player in player_list.players:

            row = (
                self.player_table.rowCount()
            )

            self.player_table.insertRow(
                row
            )

            if show_steam:

                display_name = (
                    player.steam_name
                )

            else:

                # Для старых записей Shinri-ник ещё не заполнен.
                # В таком случае показываем старый Steam-ник,
                # чтобы существующие записи не исчезли из вида.
                display_name = (
                    player.shinri_name
                    or player.steam_name
                )

            self.player_table.setItem(
                row,
                0,
                QTableWidgetItem(
                    display_name
                )
            )

            note_item = QTableWidgetItem(
                player.note
            )

            note_item.setTextAlignment(
                Qt.AlignLeft | Qt.AlignTop
            )

            self.player_table.setItem(
                row,
                1,
                note_item
            )

        self.player_table.resizeRowsToContents()

        self.filter_players()

    # =====================================================
    # ЖИВОЙ ПОИСК ПО ТЕКУЩЕМУ СПИСКУ
    # =====================================================

    def filter_players(
        self
    ):

        search_text = (
            self.player_search.text()
            .strip()
            .casefold()
        )

        index = (
            self.list_widget.currentRow()
        )

        if index < 0:
            return

        player_list = (
            self.manager.lists[index]
        )

        for row, player in enumerate(
            player_list.players
        ):

            searchable_text = " ".join([
                player.steam_name,
                player.shinri_name,
                player.note
            ]).casefold()

            visible = (
                not search_text
                or search_text in searchable_text
            )

            self.player_table.setRowHidden(
                row,
                not visible
            )

    # =====================================================
    # ДОБАВЛЕНИЕ СПИСКА
    # =====================================================

    def add_list(self):

        name, ok = self.get_text(
            "Новый список",
            "Введите название списка:"
        )

        if not ok or not name:
            return

        self.manager.create_list(
            name
        )

        self.save_current_database()

        self.update_lists()

    # =====================================================
    # УДАЛЕНИЕ СПИСКА
    # =====================================================

    def delete_list(self):

        index = (
            self.list_widget.currentRow()
        )

        if index < 0:
            return

        player_list = (
            self.manager.lists[index]
        )

        answer = QMessageBox.question(
            self,
            "Удаление списка",
            f"Удалить список «{player_list.name}»?"
        )

        if answer != QMessageBox.Yes:
            return

        self.manager.delete_list(
            player_list.name
        )

        self.save_current_database()

        self.update_lists()

    # =====================================================
    # ПЕРЕИМЕНОВАНИЕ СПИСКА
    # =====================================================

    def rename_list(self):

        index = (
            self.list_widget.currentRow()
        )

        if index < 0:
            return

        player_list = (
            self.manager.lists[index]
        )

        new_name, ok = self.get_text(
            "Переименование списка",
            "Новое название:",
            player_list.name
        )

        if not ok or not new_name:
            return

        self.manager.rename_list(
            player_list.name,
            new_name
        )

        self.save_current_database()

        self.update_lists()

    # =====================================================
    # ДОБАВЛЕНИЕ ИГРОКА
    # =====================================================

    def add_player(self):

        index = (
            self.list_widget.currentRow()
        )

        if index < 0:

            QMessageBox.warning(
                self,
                "Ошибка",
                "Сначала выберите список."
            )

            return

        player_list = (
            self.manager.lists[index]
        )

        dialog = PlayerDialog(
            self
        )

        if dialog.exec() != QDialog.Accepted:
            return

        (
            steam_name,
            shinri_name,
            note
        ) = dialog.get_data()

        if not steam_name and not shinri_name:

            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно указать хотя бы один ник."
            )

            return

        player_list.add_player(
            steam_name,
            shinri_name,
            note
        )

        self.save_current_database()

        self.update_players(
            player_list
        )

    # =====================================================
    # УДАЛЕНИЕ ИГРОКА
    # =====================================================

    def delete_player(self):

        list_index = (
            self.list_widget.currentRow()
        )

        player_row = (
            self.player_table.currentRow()
        )

        if (
            list_index < 0
            or player_row < 0
        ):
            return

        player_list = (
            self.manager.lists[list_index]
        )

        player = (
            player_list.players[player_row]
        )

        answer = QMessageBox.question(
            self,
            "Удаление игрока",
            f"Удалить игрока "
            f"«{self.get_display_name(player)}»?"
        )

        if answer != QMessageBox.Yes:
            return

        player_list.players.remove(
            player
        )

        self.save_current_database()

        self.update_players(
            player_list
        )

    # =====================================================
    # ПЕРЕНОС ИГРОКА В ДРУГОЙ СПИСОК
    # =====================================================

    def move_player(self):

        source_index = (
            self.list_widget.currentRow()
        )

        player_row = (
            self.player_table.currentRow()
        )

        if (
            source_index < 0
            or player_row < 0
        ):

            QMessageBox.information(
                self,
                "Перенос игрока",
                "Сначала выберите игрока."
            )

            return

        if len(self.manager.lists) < 2:

            QMessageBox.information(
                self,
                "Перенос игрока",
                "Для переноса нужен хотя бы ещё один список."
            )

            return

        source_list = (
            self.manager.lists[source_index]
        )

        if player_row >= len(
            source_list.players
        ):
            return

        player = (
            source_list.players[player_row]
        )

        destinations = [
            player_list.name
            for index, player_list
            in enumerate(self.manager.lists)
            if index != source_index
        ]

        destination_name, ok = QInputDialog.getItem(
            self,
            "Перенести игрока",
            f"Куда перенести «{self.get_display_name(player)}»?",
            destinations,
            0,
            False
        )

        if not ok or not destination_name:
            return

        destination_list = next(
            (
                player_list
                for index, player_list
                in enumerate(self.manager.lists)
                if (
                    index != source_index
                    and player_list.name == destination_name
                )
            ),
            None
        )

        if destination_list is None:
            return

        duplicate = any(
            players_equal(
                player,
                existing_player
            )
            for existing_player
            in destination_list.players
        )

        if duplicate:

            QMessageBox.warning(
                self,
                "Перенос игрока",
                "В выбранном списке уже есть игрок "
                "с таким Steam- или Shinri-ником."
            )

            return

        source_list.players.remove(
            player
        )

        destination_list.players.append(
            player
        )

        self.save_current_database()

        self.update_players(
            source_list
        )

    # =====================================================
    # РЕДАКТИРОВАНИЕ ИГРОКА
    # =====================================================

    def edit_player(
        self,
        row=None,
        column=None
    ):

        list_index = (
            self.list_widget.currentRow()
        )

        if list_index < 0:
            return

        if row is None:

            row = (
                self.player_table.currentRow()
            )

        if row < 0:
            return

        player_list = (
            self.manager.lists[list_index]
        )

        if row >= len(
            player_list.players
        ):
            return

        player = (
            player_list.players[row]
        )

        dialog = PlayerDialog(
            self,
            player.steam_name,
            player.shinri_name,
            player.note
        )

        if dialog.exec() != QDialog.Accepted:
            return

        (
            new_steam_name,
            new_shinri_name,
            new_note
        ) = dialog.get_data()

        if (
            not new_steam_name
            and not new_shinri_name
        ):

            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно указать хотя бы один ник."
            )

            return

        player.steam_name = (
            new_steam_name
        )

        player.shinri_name = (
            new_shinri_name
        )

        player.note = (
            new_note
        )

        self.save_current_database()

        self.update_players(
            player_list
        )

    # =====================================================
    # ПОЛУЧЕНИЕ ОТОБРАЖАЕМОГО НИКА
    # =====================================================

    def get_display_name(
        self,
        player
    ):

        if self.show_steam_action.isChecked():

            return player.steam_name

        return (
            player.shinri_name
            or player.steam_name
        )

    # =====================================================
    # ПОИСК
    # =====================================================

    def start_search(self):

        players = []

        for player_list in self.manager.lists:

            for player in player_list.players:

                names = [
                    player.steam_name,
                    player.shinri_name
                ]

                for name in names:

                    if not name:
                        continue

                    if name.casefold() not in [
                        x.casefold()
                        for x in players
                    ]:

                        players.append(
                            name
                        )

        if not players:

            QMessageBox.information(
                self,
                "Поиск",
                "Нет игроков для поиска."
            )

            return

        self.search_button.setEnabled(
            False
        )

        self.search_button.setText(
            "ПОИСК ВЫПОЛНЯЕТСЯ..."
        )

        self.progress.show()

        lobby_only = (
            self.lobby_only_action.isChecked()
        )

        self.search_worker = SearchWorker(
            players,
            lobby_only
        )

        self.search_worker.finished.connect(
            self.search_finished
        )

        self.search_worker.error.connect(
            self.search_error
        )

        self.search_worker.finished.connect(
            self.search_worker.deleteLater
        )

        self.search_worker.error.connect(
            self.search_worker.deleteLater
        )

        self.search_worker.start()

    # =====================================================
    # ПОИСК ЗАВЕРШЁН
    # =====================================================

    def search_finished(
        self,
        results,
        elapsed_time
    ):

        self.search_button.setEnabled(
            True
        )

        self.search_button.setText(
            "ПОИСК ИГРОКОВ"
        )

        self.progress.hide()

        show_steam = (
            self.show_steam_action.isChecked()
        )

        self.results_window = ResultsDialog(
            self.manager,
            results,
            elapsed_time,
            show_steam,
            self
        )

        self.results_window.show()

        self.search_worker = None

    # =====================================================
    # ОШИБКА ПОИСКА
    # =====================================================

    def search_error(
        self,
        message
    ):

        self.search_button.setEnabled(
            True
        )

        self.search_button.setText(
            "ПОИСК ИГРОКОВ"
        )

        self.progress.hide()

        QMessageBox.critical(
            self,
            "Ошибка поиска",
            message
        )

        self.search_worker = None

    # =====================================================
    # ПРОСТОЙ ВВОД ТЕКСТА
    # =====================================================

    def get_text(
        self,
        title,
        label,
        default=""
    ):

        dialog = QDialog(
            self
        )

        dialog.setWindowTitle(
            title
        )

        dialog.resize(
            400,
            150
        )

        layout = QVBoxLayout(
            dialog
        )

        layout.setContentsMargins(
            20,
            20,
            20,
            20
        )

        layout.addWidget(
            QLabel(label)
        )

        line_edit = QLineEdit()

        line_edit.setText(
            default
        )

        layout.addWidget(
            line_edit
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            dialog.accept
        )

        buttons.rejected.connect(
            dialog.reject
        )

        layout.addWidget(
            buttons
        )

        if (
            dialog.exec()
            == QDialog.Accepted
        ):

            return (
                line_edit.text().strip(),
                True
            )

        return "", False


    # =====================================================
    # ЗАКРЫТИЕ ПРИЛОЖЕНИЯ
    # =====================================================

    def closeEvent(self, event):
        if self.auto_match_window is not None:
            self.auto_match_window.close()
            self.auto_match_window = None

        if getattr(self, "match_monitor", None) is not None:
            self.match_monitor.stop()
            self.match_monitor.wait(2000)

        # Не оставляем QThread живым в момент уничтожения Qt-объектов.
        for worker_name in (
            "cloud_sync_worker",
            "update_check_worker",
            "update_download_worker",
        ):
            worker = getattr(
                self,
                worker_name,
                None
            )

            if worker is not None and worker.isRunning():
                worker.wait(2500)

                if worker.isRunning():
                    worker.terminate()
                    worker.wait(500)

        super().closeEvent(event)


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )

    app.setWindowIcon(
        QIcon(
            resource_path(
                "icon.png"
            )
        )
    )

    app.setStyleSheet(
        STYLE
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )