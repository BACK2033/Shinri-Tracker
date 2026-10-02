import uuid

from player import Player


class PlayerList:
    def __init__(
        self,
        name,
        list_id=None,
    ):
        self.id = str(list_id or uuid.uuid4())
        self.name = name
        self.players = []

    def add_player(
        self,
        steam_name,
        shinri_name="",
        note="",
    ):
        self.players.append(
            Player(
                steam_name,
                shinri_name,
                note,
            )
        )

    def remove_player(self, name):
        for player in self.players:
            if (
                player.steam_name == name
                or player.shinri_name == name
            ):
                self.players.remove(player)
                return

    def update_player(
        self,
        old_steam_name,
        new_steam_name=None,
        new_shinri_name=None,
        new_note=None,
    ):
        player = self.get_player(
            old_steam_name
        )

        if player is None:
            return

        if new_steam_name is not None:
            player.steam_name = new_steam_name

        if new_shinri_name is not None:
            player.shinri_name = new_shinri_name

        if new_note is not None:
            player.note = new_note

    def get_player(self, name):
        for player in self.players:
            if (
                player.steam_name == name
                or player.shinri_name == name
            ):
                return player

        return None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "players": [
                player.to_dict()
                for player in self.players
            ],
        }

    @classmethod
    def from_dict(cls, data):
        player_list = cls(
            data.get("name", "Без названия"),
            list_id=data.get("id"),
        )

        for player_data in data.get(
            "players",
            [],
        ):
            player_list.players.append(
                Player.from_dict(
                    player_data
                )
            )

        return player_list
