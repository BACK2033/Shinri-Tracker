import ctypes
from ctypes import wintypes
import difflib
import os
import sys
import re
import threading
import time
import tempfile
import unicodedata

from PySide6.QtCore import QThread, Signal

try:
    import mss
except ImportError:
    mss = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from PIL import Image
except ImportError:
    Image = None


# =========================================================
# НАСТРОЙКИ ЭКРАНА SHINRI
# Координаты интерфейса сняты с реальной области GMod 1920x1080.
# В присланном PNG был размер 1920x1200, но нижние 120 пикселей —
# пустая чёрная полоса и частью интерфейса игры не являются.
# При другом размере клиентской области координаты масштабируются.
# =========================================================

BASE_WIDTH = 1920
BASE_HEIGHT = 1080

# Проверяем экран 4 раза в секунду. Это очень лёгкая операция:
# захватываются только две небольшие области интерфейса.
POLL_INTERVAL = 0.25

# Чтобы случайный яркий кадр не считался найденной игрой.
DETECTION_CONFIRMATIONS = 2
RELEASE_CONFIRMATIONS = 3

# Надпись «КОМАНДА НАЙДЕНА».
TITLE_BOX = (600, 110, 1330, 170)
TITLE_BRIGHT_THRESHOLD = 220
TITLE_MIN_BRIGHT_RATIO = 0.04

# Жёлтый таймер под надписью.
TIMER_BOX = (900, 225, 1020, 275)
TIMER_BRIGHT_THRESHOLD = 180
TIMER_MIN_BRIGHT_RATIO = 0.04

# Красная кнопка «ГОТОВ» внизу экрана подтверждения.
# Это сильно уменьшает ложные срабатывания уже внутри катки.
READY_BOX = (850, 940, 1070, 1020)
READY_MIN_RED_RATIO = 0.20

# Центры 8 карточек по горизонтали.
NAME_CENTERS_X = (
    165,
    391,
    617,
    843,
    1069,
    1295,
    1521,
    1747,
)

# Центр строки ника в верхнем и нижнем ряду.
NAME_CENTERS_Y = (
    535,
    817,
)

# Вырезаем только строку ника, не захватывая уровень и рамку карточки.
NAME_HALF_WIDTH = 90
NAME_HALF_HEIGHT = 20

# Увеличение маленького текста перед OCR.
OCR_SCALE = 4
OCR_THRESHOLD = 145
OCR_ROW_GAP = 40

# Временная диагностика. Оставь True, пока проверяем работу монитора.
DEBUG_MONITOR = True

# F8 — принудительно просканировать текущий экран GMod.
# Не требует сворачивать игру и дополнительных библиотек.
FORCE_SCAN_VK = 0x77


# =========================================================
# WINDOWS: ИЩЕМ АКТИВНОЕ ОКНО GMOD И ЕГО CLIENT AREA
# =========================================================

user32 = ctypes.windll.user32


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


def _foreground_window_title():
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return "", None

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)

    return buffer.value, hwnd


def _is_gmod_title(title):
    # Заголовок у тебя: "Garry's Mod (64-bit)".
    # Приводим к нижнему регистру и нормализуем апостроф,
    # поэтому суффикс "(64-bit)" не мешает.
    title = (title or "").casefold().replace("’", "'")

    return "garry's mod" in title


def get_gmod_client_rect():
    """
    Возвращает client area активного окна GMod в экранных координатах:
    {left, top, width, height}.

    Если GMod сейчас не активен — None. Благодаря этому монитор почти
    ничего не делает, когда пользователь находится не в игре.
    """

    title, hwnd = _foreground_window_title()

    if hwnd is None or not _is_gmod_title(title):
        return None

    rect = wintypes.RECT()

    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None

    origin = POINT(0, 0)

    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        return None

    return {
        "left": origin.x,
        "top": origin.y,
        "width": width,
        "height": height,
    }


# =========================================================
# ОБЩИЕ УТИЛИТЫ СКРИНШОТА
# =========================================================


def _scale_box(box, client_rect):
    x1, y1, x2, y2 = box

    scale_x = client_rect["width"] / BASE_WIDTH
    scale_y = client_rect["height"] / BASE_HEIGHT

    return {
        "left": client_rect["left"] + int(round(x1 * scale_x)),
        "top": client_rect["top"] + int(round(y1 * scale_y)),
        "width": max(1, int(round((x2 - x1) * scale_x))),
        "height": max(1, int(round((y2 - y1) * scale_y))),
    }


def _mss_to_pil(screenshot):
    return Image.frombytes(
        "RGB",
        screenshot.size,
        screenshot.rgb,
    )


def _bright_ratio(image, threshold):
    """
    Считает долю ярких пикселей через histogram Pillow.
    Цикла по каждому пикселю в Python здесь нет.
    """

    gray = image.convert("L")
    histogram = gray.histogram()
    total = sum(histogram)

    if not total:
        return 0.0

    return sum(histogram[threshold:]) / total


def _red_ratio(image):
    """
    Доля красных пикселей.
    Чтобы нагрузка была мизерной, уменьшаем область до 55x20.
    """

    small = image.resize(
        (55, 20),
        Image.Resampling.BILINEAR,
    )

    pixels = list(small.getdata())

    if not pixels:
        return 0.0

    red_pixels = 0

    for red, green, blue in pixels:
        if (
            red >= 110
            and red >= green * 1.40
            and red >= blue * 1.40
        ):
            red_pixels += 1

    return red_pixels / len(pixels)


def get_detection_scores(sct, client_rect):
    """
    Возвращает три дешёвые оценки:
    - белая надпись «КОМАНДА НАЙДЕНА»;
    - жёлтый таймер;
    - красная кнопка «ГОТОВ».

    OCR здесь НЕ запускается.
    """

    title_region = _scale_box(TITLE_BOX, client_rect)
    timer_region = _scale_box(TIMER_BOX, client_rect)
    ready_region = _scale_box(READY_BOX, client_rect)

    title_image = _mss_to_pil(sct.grab(title_region))
    timer_image = _mss_to_pil(sct.grab(timer_region))
    ready_image = _mss_to_pil(sct.grab(ready_region))

    title_ratio = _bright_ratio(
        title_image,
        TITLE_BRIGHT_THRESHOLD,
    )

    timer_ratio = _bright_ratio(
        timer_image,
        TIMER_BRIGHT_THRESHOLD,
    )

    ready_ratio = _red_ratio(
        ready_image
    )

    return title_ratio, timer_ratio, ready_ratio


def detect_match_screen(sct, client_rect):
    title_ratio, timer_ratio, ready_ratio = get_detection_scores(
        sct,
        client_rect,
    )

    return (
        title_ratio >= TITLE_MIN_BRIGHT_RATIO
        and timer_ratio >= TIMER_MIN_BRIGHT_RATIO
        and ready_ratio >= READY_MIN_RED_RATIO
    )


# =========================================================
# TESSERACT
# =========================================================


def _runtime_resource_path(*parts):
    """
    Ищет ресурс и в обычном проекте, и внутри PyInstaller --onefile.
    """

    if hasattr(
        sys,
        "_MEIPASS"
    ):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(
            os.path.abspath(__file__)
        )

    return os.path.join(
        base,
        *parts
    )


def _configure_tesseract():
    if pytesseract is None:
        raise RuntimeError(
            "Не установлен Python-пакет pytesseract. "
            "Выполни: pip install pytesseract"
        )

    bundled_path = _runtime_resource_path(
        "tesseract",
        "tesseract.exe"
    )

    # Для onedir/ручного portable-варианта рядом с exe.
    executable_folder_path = os.path.join(
        os.path.dirname(
            os.path.abspath(sys.executable)
        ),
        "tesseract",
        "tesseract.exe"
    )

    possible_paths = (
        bundled_path,
        executable_folder_path,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    )

    # Если пользователь уже указал путь вручную — не трогаем его.
    current = getattr(
        pytesseract.pytesseract,
        "tesseract_cmd",
        "tesseract",
    )

    selected_path = None

    if (
        current
        and current != "tesseract"
        and os.path.exists(current)
    ):
        selected_path = current

    else:

        for path in possible_paths:

            if os.path.exists(path):

                pytesseract.pytesseract.tesseract_cmd = path
                selected_path = path

                break

    # Если Tesseract лежит в нашей папке, явно указываем tessdata.
    if selected_path:

        tessdata_path = os.path.join(
            os.path.dirname(selected_path),
            "tessdata"
        )

        if os.path.isdir(
            tessdata_path
        ):
            os.environ[
                "TESSDATA_PREFIX"
            ] = tessdata_path

    try:
        pytesseract.get_tesseract_version()
    except Exception as error:
        raise RuntimeError(
            "Tesseract OCR не найден. Программа поддерживает встроенную "
            "папку «tesseract» рядом с кодом/внутри EXE, либо обычную "
            "установку в C:\\Program Files\\Tesseract-OCR\\."
        ) from error

    try:
        languages = set(pytesseract.get_languages(config=""))
    except Exception:
        languages = set()

    ocr_languages = []

    # Сначала смешанный режим: он лучше всего подходит для списка,
    # где одновременно встречаются кириллица и латиница.
    if "rus" in languages and "eng" in languages:
        ocr_languages.append("rus+eng")

    # Отдельные проходы нужны не ради скорости, а ради точности:
    # смешанный режим иногда читает короткий латинский ник как кириллицу
    # (например milne -> тйпе). Все 16 картинок обрабатываются одним
    # процессом Tesseract на язык, поэтому это всё ещё быстро.
    if "eng" in languages:
        ocr_languages.append("eng")

    if "rus" in languages:
        ocr_languages.append("rus")

    if ocr_languages:
        return ocr_languages

    raise RuntimeError(
        "В Tesseract не найдено языков rus/eng. "
        "При установке добавь Russian и English language data."
    )


# =========================================================
# OCR 16 НИКОВ ЗА ОДИН ПРОХОД
# =========================================================


def _prepare_name_crop(crop):
    """
    Готовит один ник для Tesseract.

    Важный момент: каждый ник теперь является ОТДЕЛЬНОЙ страницей OCR.
    Раньше 16 строк склеивались в одну длинную картинку, и Tesseract
    иногда переносил куски одной строки в соседние. Именно это давало
    почти пустой/мусорный результат на реальном экране.
    """

    gray = crop.convert("L")

    gray = gray.resize(
        (
            gray.width * OCR_SCALE,
            gray.height * OCR_SCALE,
        ),
        Image.Resampling.LANCZOS,
    )

    # Белый текст на тёмном фоне -> чёрный текст на белом фоне.
    threshold_table = [
        255 if value < OCR_THRESHOLD else 0
        for value in range(256)
    ]

    return gray.point(threshold_table)


def _extract_name_crops(screen):
    """Возвращает ровно 16 подготовленных изображений с никами."""

    scale_x = screen.width / BASE_WIDTH
    scale_y = screen.height / BASE_HEIGHT

    crops = []

    for center_y in NAME_CENTERS_Y:
        for center_x in NAME_CENTERS_X:
            x1 = int(round((center_x - NAME_HALF_WIDTH) * scale_x))
            x2 = int(round((center_x + NAME_HALF_WIDTH) * scale_x))
            y1 = int(round((center_y - NAME_HALF_HEIGHT) * scale_y))
            y2 = int(round((center_y + NAME_HALF_HEIGHT) * scale_y))

            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(screen.width, x2)
            y2 = min(screen.height, y2)

            crop = screen.crop((x1, y1, x2, y2))
            crops.append(_prepare_name_crop(crop))

    return crops


def _clean_ocr_text(text):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip("|¦")
    return text.strip()


def _ocr_all_pages(crops, language):
    """
    Запускает ОДИН процесс Tesseract сразу на всех 16 никах.

    Tesseract умеет принимать .txt со списком изображений как
    многостраничный документ. Поэтому мы получаем надёжность --psm 7
    для каждого отдельного ника, но без 16 тяжёлых запусков процесса.
    """

    with tempfile.TemporaryDirectory(prefix="shinri_ocr_") as temp_dir:
        temp_dir = os.path.abspath(temp_dir)
        image_paths = []

        for index, crop in enumerate(crops):
            image_path = os.path.join(
                temp_dir,
                f"nick_{index:02d}.png",
            )
            crop.save(image_path)
            image_paths.append(image_path)

        list_path = os.path.join(temp_dir, "images.txt")

        with open(list_path, "w", encoding="utf-8") as file:
            file.write("\n".join(image_paths))

        output = pytesseract.image_to_string(
            list_path,
            lang=language,
            config="--psm 7",
        )

    # Между страницами Tesseract ставит form feed (\f).
    pages = output.split("\f")

    result = []

    for index in range(16):
        page = pages[index] if index < len(pages) else ""
        result.append(_clean_ocr_text(page))

    return result


def _recognize_names(screen, languages):
    """
    Возвращает:
        names              — основной вариант для показа;
        confidences        — совместимость со старым GUI;
        candidates_by_slot — все варианты OCR для каждого из 16 мест.

    Если установлены rus+eng, eng и rus, весь экран требует всего
    ТРИ запуска Tesseract, а не 16/32/48 запусков.
    """

    crops = _extract_name_crops(screen)

    passes = []

    for language in languages:
        passes.append(
            _ocr_all_pages(
                crops,
                language,
            )
        )

    candidates_by_slot = []
    names = []
    confidences = []

    for slot in range(16):
        candidates = []

        for pass_result in passes:
            candidate = (
                pass_result[slot]
                if slot < len(pass_result)
                else ""
            )

            candidate = _clean_ocr_text(candidate)

            if (
                candidate
                and candidate.casefold()
                not in [item.casefold() for item in candidates]
            ):
                candidates.append(candidate)

        candidates_by_slot.append(candidates)

        # Первый проход — rus+eng, если он доступен. Для отображения это
        # лучший универсальный вариант. При поиске по базе ниже проверяются
        # ВСЕ кандидаты, поэтому milne/CSIRA и похожие случаи не потеряются.
        primary = candidates[0] if candidates else ""
        names.append(primary)
        confidences.append(100.0 if primary else 0.0)

    return names, confidences, candidates_by_slot


# =========================================================
# СРАВНЕНИЕ OCR С СОХРАНЁННОЙ БАЗОЙ
# =========================================================


def _normalize_for_match(value):
    value = unicodedata.normalize(
        "NFKC",
        str(value or "")
    )

    value = value.casefold()

    return "".join(
        char
        for char in value
        if char.isalnum()
    )


# Частые визуальные двойники для игрового шрифта.
# Важно: это меняет только СРАВНЕНИЕ с базой, а не сам OCR-текст.
_VISUAL_EQUIVALENTS = {
    "0": "o",
    "o": "o",
    "о": "o",

    "a": "a",
    "а": "a",

    "b": "b",
    "в": "b",
    "8": "b",

    "c": "c",
    "с": "c",

    "e": "e",
    "е": "e",

    "h": "h",
    "н": "h",

    "k": "k",
    "к": "k",

    "m": "m",
    "м": "m",

    # Особенно полезно для Noona -> Моoпа:
    # кириллическая п часто получается вместо латинской n.
    "n": "n",
    "п": "n",

    "p": "p",
    "р": "p",

    "t": "t",
    "т": "t",

    "x": "x",
    "х": "x",

    "y": "y",
    "у": "y",

    "i": "i",
    "l": "i",
    "1": "i",
    "і": "i",
    "ӏ": "i",

    "5": "s",
    "s": "s",
}


def _visual_skeleton(value):
    normalized = _normalize_for_match(
        value
    )

    return "".join(
        _VISUAL_EQUIVALENTS.get(
            char,
            char
        )
        for char in normalized
    )


def _levenshtein_distance(left, right):

    if left == right:
        return 0

    if not left:
        return len(right)

    if not right:
        return len(left)

    if len(left) > len(right):
        left, right = right, left

    previous = list(
        range(len(left) + 1)
    )

    for row_index, right_char in enumerate(
        right,
        start=1
    ):
        current = [
            row_index
        ]

        for column_index, left_char in enumerate(
            left,
            start=1
        ):
            insert_cost = (
                current[column_index - 1]
                + 1
            )

            delete_cost = (
                previous[column_index]
                + 1
            )

            replace_cost = (
                previous[column_index - 1]
                + (
                    0
                    if left_char == right_char
                    else 1
                )
            )

            current.append(
                min(
                    insert_cost,
                    delete_cost,
                    replace_cost
                )
            )

        previous = current

    return previous[-1]


def _similarity(left, right):
    normal_left = _normalize_for_match(
        left
    )

    normal_right = _normalize_for_match(
        right
    )

    if not normal_left or not normal_right:
        return 0.0

    if normal_left == normal_right:
        return 1.0

    normal_score = difflib.SequenceMatcher(
        None,
        normal_left,
        normal_right,
    ).ratio()

    visual_left = _visual_skeleton(
        left
    )

    visual_right = _visual_skeleton(
        right
    )

    if visual_left == visual_right:
        visual_score = 0.99

    else:
        visual_score = difflib.SequenceMatcher(
            None,
            visual_left,
            visual_right,
        ).ratio()

        distance = _levenshtein_distance(
            visual_left,
            visual_right
        )

        longest = max(
            len(visual_left),
            len(visual_right)
        )

        # Одна оставшаяся ошибка на нике 5+ символов
        # почти наверняка является OCR-ошибкой.
        if (
            longest >= 5
            and distance == 1
        ):
            visual_score = max(
                visual_score,
                0.94
            )

        elif (
            longest >= 7
            and distance == 2
        ):
            visual_score = max(
                visual_score,
                0.88
            )

    return max(
        normal_score,
        visual_score
    )


def _thresholds_for_name(name):
    length = len(_normalize_for_match(name))

    if length <= 4:
        return 0.92, 0.82

    if length <= 6:
        return 0.88, 0.78

    return 0.84, 0.74


def match_players(
    names,
    confidences,
    known_players,
    candidates_by_slot=None,
):
    """
    Сопоставляет 16 распознанных ников с текущими данными приложения.

    Теперь для каждого места может быть несколько вариантов OCR
    (rus+eng / eng / rus). При сравнении с базой проверяются все варианты
    и выбирается тот, который лучше совпал с сохранённым ником.
    """

    results = []

    for slot in range(16):
        primary_name = names[slot] if slot < len(names) else ""
        ocr_confidence = (
            confidences[slot]
            if slot < len(confidences)
            else 0.0
        )

        candidates = []

        if candidates_by_slot and slot < len(candidates_by_slot):
            for candidate in candidates_by_slot[slot]:
                if (
                    _normalize_for_match(candidate)
                    and candidate.casefold()
                    not in [item.casefold() for item in candidates]
                ):
                    candidates.append(candidate)

        if (
            _normalize_for_match(primary_name)
            and primary_name.casefold()
            not in [item.casefold() for item in candidates]
        ):
            candidates.insert(0, primary_name)

        if not candidates:
            results.append({
                "slot": slot,
                "ocr_name": "",
                "ocr_confidence": ocr_confidence,
                "status": "unread",
                "score": 0.0,
                "match": None,
                "matched_field": None,
            })
            continue

        matches = []

        for candidate in candidates:
            for player in known_players:
                aliases = (
                    ("steam_name", player.get("steam_name", "")),
                    ("shinri_name", player.get("shinri_name", "")),
                )

                for field_name, alias in aliases:
                    if not alias:
                        continue

                    score = _similarity(
                        candidate,
                        alias
                    )

                    matches.append({
                        "score": score,
                        "match": player,
                        "matched_field": field_name,
                        "ocr_name": candidate,
                    })

        matches.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        best = (
            matches[0]
            if matches
            else None
        )

        second_player_score = 0.0

        if best is not None:
            for other in matches[1:]:
                if other["match"] is not best["match"]:
                    second_player_score = other["score"]
                    break

        # Если совпадения с базой нет — просто показываем основной OCR.
        display_name = primary_name or candidates[0]

        if best is None:
            status = "not_found"
            score = 0.0
            matched_player = None
            matched_field = None

        else:
            score = best["score"]
            matched_candidate = best["ocr_name"]
            found_threshold, possible_threshold = _thresholds_for_name(
                matched_candidate
            )

            ambiguous = (
                second_player_score >= possible_threshold
                and (
                    score - second_player_score
                ) < 0.04
            )

            if (
                score >= found_threshold
                and not ambiguous
            ):
                status = "found"
                matched_player = best["match"]
                matched_field = best["matched_field"]
                display_name = matched_candidate
            elif score >= possible_threshold:
                status = "possible"
                matched_player = best["match"]
                matched_field = best["matched_field"]
                display_name = matched_candidate
            else:
                status = "not_found"
                matched_player = None
                matched_field = None

        results.append({
            "slot": slot,
            "ocr_name": display_name,
            "ocr_confidence": ocr_confidence,
            "status": status,
            "score": score,
            "match": matched_player,
            "matched_field": matched_field,
            "ocr_candidates": candidates,
        })

    return results


# =========================================================
# ФОНОВЫЙ МОНИТОР
# =========================================================


class MatchMonitor(QThread):
    """
    Фоновый монитор.

    Автоматически обнаруживает окно подтверждения матча.
    Дополнительно F8 принудительно запускает OCR текущего экрана GMod —
    это удобно для проверки, если автоматическое обнаружение не сработало.
    """

    match_found = Signal(object)
    match_ended = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._error_reported = False

        self._last_gmod_state = None
        self._last_debug_print = 0.0
        self._force_key_was_down = False

        # Автоматическая проверка включена по умолчанию.
        # F8 остаётся доступной даже когда автопроверка выключена.
        self._auto_enabled = threading.Event()
        self._auto_enabled.set()

    def stop(self):
        self._stop_event.set()

    def set_auto_enabled(self, enabled):
        if enabled:
            self._auto_enabled.set()
            self._debug("Автоматическая проверка включена.")
        else:
            self._auto_enabled.clear()
            self._debug(
                "Автоматическая проверка выключена. "
                "F8 для ручной проверки продолжает работать."
            )

    def _debug(self, message):
        if DEBUG_MONITOR:
            print(f"[MatchMonitor] {message}", flush=True)

    def _force_scan_pressed(self):
        """
        Проверяем F8 через WinAPI, поэтому никакой keyboard/pynput не нужен.
        Возвращаем True только в момент нажатия, а не пока клавиша удерживается.
        """
        key_down = bool(user32.GetAsyncKeyState(FORCE_SCAN_VK) & 0x8000)
        pressed = key_down and not self._force_key_was_down
        self._force_key_was_down = key_down
        return pressed

    def _scan_match(self, sct, client_rect, languages, reason):
        analysis_started = time.perf_counter()

        self._debug(
            f"Запускаю OCR ({reason}), client="
            f"{client_rect['width']}x{client_rect['height']}"
        )

        screenshot = _mss_to_pil(
            sct.grab(client_rect)
        )

        # Если захват по какой-то причине почти полностью чёрный,
        # сразу сообщаем об этом. Такое иногда бывает в exclusive fullscreen.
        sample = screenshot.resize((64, 40)).convert("L")
        avg_brightness = sum(sample.getdata()) / (64 * 40)

        if avg_brightness < 3:
            raise RuntimeError(
                "Скриншот GMod получается почти полностью чёрным. "
                "Если игра запущена в эксклюзивном полноэкранном режиме, "
                "переключи её в «Оконный без рамки»."
            )

        ocr_started = time.perf_counter()

        names, confidences, candidates = _recognize_names(
            screenshot,
            languages,
        )

        ocr_time = time.perf_counter() - ocr_started
        total_time = time.perf_counter() - analysis_started

        recognized = [name for name in names if name]

        self._debug(
            f"OCR завершён за {ocr_time:.2f} сек. "
            f"Распознано {len(recognized)}/16: {recognized}"
        )

        # Короткий системный сигнал — позволяет понять, что сканирование
        # действительно произошло, даже если оверлей не виден поверх fullscreen.
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

        self.match_found.emit({
            "names": names,
            "confidences": confidences,
            "ocr_time": ocr_time,
            "total_time": total_time,
            "languages": languages,
            "candidates": candidates,
            "reason": reason,
        })

    def run(self):
        if mss is None:
            self.error.emit(
                "Не установлен пакет mss. Выполни: pip install mss"
            )
            return

        if Image is None:
            self.error.emit(
                "Не установлен Pillow. Выполни: pip install pillow"
            )
            return

        try:
            languages = _configure_tesseract()
        except Exception as error:
            self.error.emit(str(error))
            return

        self._debug(
            f"Монитор запущен. OCR-режимы: {', '.join(languages)}. "
            "F8 = принудительное сканирование."
        )

        positive_frames = 0
        negative_frames = 0
        match_active = False

        with mss.mss() as sct:
            while not self._stop_event.is_set():
                cycle_started = time.perf_counter()

                try:
                    client_rect = get_gmod_client_rect()

                    in_gmod = client_rect is not None

                    if in_gmod != self._last_gmod_state:
                        self._last_gmod_state = in_gmod

                        if in_gmod:
                            title, _ = _foreground_window_title()
                            self._debug(
                                f"GMod обнаружен. Заголовок окна: {title!r}; "
                                f"client={client_rect}"
                            )
                        else:
                            title, _ = _foreground_window_title()
                            self._debug(
                                f"GMod НЕ активен. Активное окно: {title!r}"
                            )

                    if client_rect is None:
                        positive_frames = 0
                        self._force_key_was_down = False
                        self._sleep_remaining(cycle_started)
                        continue

                    # F8 запускает OCR независимо от автоматического режима.
                    force_scan = self._force_scan_pressed()

                    if force_scan:
                        self._scan_match(
                            sct,
                            client_rect,
                            languages,
                            reason="F8",
                        )

                    # Если автопроверка выключена — даже области детектора
                    # не захватываем. Остаётся только очень лёгкая проверка F8.
                    if not self._auto_enabled.is_set():
                        positive_frames = 0
                        negative_frames = 0

                        if match_active:
                            match_active = False
                            self.match_ended.emit()

                        self._sleep_remaining(cycle_started)
                        continue

                    title_ratio, timer_ratio, ready_ratio = get_detection_scores(
                        sct,
                        client_rect,
                    )

                    detected = (
                        title_ratio >= TITLE_MIN_BRIGHT_RATIO
                        and timer_ratio >= TIMER_MIN_BRIGHT_RATIO
                        and ready_ratio >= READY_MIN_RED_RATIO
                    )

                    now = time.perf_counter()
                    if DEBUG_MONITOR and now - self._last_debug_print >= 1.0:
                        self._last_debug_print = now
                        self._debug(
                            f"detector: title={title_ratio:.3f} "
                            f"(нужно {TITLE_MIN_BRIGHT_RATIO:.3f}), "
                            f"timer={timer_ratio:.3f} "
                            f"(нужно {TIMER_MIN_BRIGHT_RATIO:.3f}), "
                            f"ready={ready_ratio:.3f} "
                            f"(нужно {READY_MIN_RED_RATIO:.3f}), "
                            f"detected={detected}"
                        )

                    if detected:
                        negative_frames = 0
                        positive_frames += 1

                        if (
                            not match_active
                            and positive_frames >= DETECTION_CONFIRMATIONS
                        ):
                            match_active = True

                            self._debug(
                                "Экран подтверждения обнаружен автоматически."
                            )

                            self._scan_match(
                                sct,
                                client_rect,
                                languages,
                                reason="auto",
                            )

                    else:
                        positive_frames = 0

                        if match_active:
                            negative_frames += 1

                            if (
                                negative_frames
                                >= RELEASE_CONFIRMATIONS
                            ):
                                match_active = False
                                negative_frames = 0
                                self._debug(
                                    "Экран подтверждения исчез."
                                )
                                self.match_ended.emit()

                    self._sleep_remaining(cycle_started)

                except Exception as error:
                    if not self._error_reported:
                        self._error_reported = True
                        self.error.emit(
                            "Ошибка автоматического распознавания: "
                            f"{error}"
                        )

                    self._debug(f"Ошибка: {error}")
                    self._stop_event.wait(1.0)

    def _sleep_remaining(self, cycle_started):
        elapsed = time.perf_counter() - cycle_started
        remaining = max(0.0, POLL_INTERVAL - elapsed)
        self._stop_event.wait(remaining)
