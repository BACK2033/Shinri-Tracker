import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from threading import local
import time


URLS = [
    "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa",
    "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa&page=2",
    "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa&page=3",
    "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa&page=4",
    "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa&page=5"
]


BASE_URL = "https://metricsgame.com"
thread_local = local()

def get_session():

    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()

    return thread_local.session
# =========================================================
# ЗАГРУЗКА СТРАНИЦЫ
# =========================================================

def get_page(url):

    start = time.perf_counter()

    try:

        response = requests.get(
            url,
            timeout=3
        )

        elapsed = time.perf_counter() - start

        print(
            f"{elapsed:.2f}s | {url}"
        )

        if response.status_code != 200:
            return None

        return response.text

    except requests.RequestException as error:

        elapsed = time.perf_counter() - start

        print(
            f"{elapsed:.2f}s | ERROR | {url}"
        )

        return None

# =========================================================
# ПОЛУЧЕНИЕ ССЫЛОК НА СЕРВЕРЫ
# =========================================================

def get_links(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    body = soup.find(
        "tbody",
        id="server-table-body"
    )

    if body is None:
        return []

    return body.find_all(
        "a",
        class_="font-semibold"
    )


# =========================================================
# ПАРСИНГ СПИСКА ИГРОКОВ
# =========================================================

def parse_page(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    block = soup.find(
        "ul",
        class_="space-y-1 min-w-[300px]"
    )

    if block is None:
        return []

    players_raw_list = block.find_all(
        "li",
        class_="flex items-center mx-2 md:mx-5"
    )

    players = []

    for element in players_raw_list:

        span = element.find("span")

        if span is not None:

            players.append(
                span.get_text(
                    strip=True
                )
            )

    return players


# =========================================================
# ПОЛУЧЕНИЕ ИНФОРМАЦИИ ОДНОМ СЕРВЕРЕ
# =========================================================

def parse_server(link):

    server_name = link.get_text(
        strip=True
    )

    href = link.get("href")

    if not href:
        return None

    server_url = BASE_URL + href

    server_html = get_page(
        server_url
    )

    if server_html is None:
        return None

    players = parse_page(
        server_html
    )

    return {
        "server": server_name,
        "players": players
    }


# =========================================================
# ПОЛУЧЕНИЕ ВСЕХ СЕРВЕРОВ
# =========================================================

def get_servers(lobby_only=False):
    max_workers_count = 10
    all_links = []

    # Если включён поиск только в общем лобби,
    # используем только эту страницу
    if lobby_only:

        urls = [
            "https://metricsgame.com/game/garrysmod?gamemode=shinri+trial+%7C+danganronpa&name=🚀+Общее+лобби"
        ]

    else:

        urls = URLS

    # -----------------------------------------
    # Получаем ссылки со всех нужных страниц
    # -----------------------------------------

    for url in urls:

        html = get_page(url)

        if html is None:
            continue

        links = get_links(html)

        all_links.extend(links)

    if lobby_only:
        all_links = all_links[:-4]
        max_workers_count = 13

    print(
        f"Найдено серверов: {len(all_links)}"
    )

    # -----------------------------------------
    # Загружаем серверы параллельно
    # -----------------------------------------

    servers = []

    with ThreadPoolExecutor(
        max_workers=max_workers_count
    ) as executor:

        results = executor.map(
            parse_server,
            all_links
        )

        for server in results:

            if server is not None:
                servers.append(server)

    print(
        f"Получено серверов: {len(servers)}"
    )

    return servers


# =========================================================
# ПОИСК ИГРОКОВ
# =========================================================

def find_players(
    target_players,
    lobby_only=False
):

    servers = get_servers(
        lobby_only
    )

    search_data = {}

    # -----------------------------------------
    # Приводим искомые ники к casefold
    # -----------------------------------------

    targets = {
        player.casefold(): player
        for player in target_players
    }

    # -----------------------------------------
    # Проверяем игроков на каждом сервере
    # -----------------------------------------

    for server in servers:

        server_name = server["server"]

        players = server["players"]

        for player in players:

            player_key = player.casefold()

            if player_key not in targets:
                continue

            original_name = targets[
                player_key
            ]

            if original_name not in search_data:

                search_data[
                    original_name
                ] = []

            search_data[
                original_name
            ].append(
                server_name
            )

    return search_data