import uuid


class Player:
    def __init__(
        self,
        steam_name,
        shinri_name="",
        note="",
        player_id=None,
    ):
        self.id = str(player_id or uuid.uuid4())
        self.steam_name = steam_name
        self.shinri_name = shinri_name
        self.note = note

    def to_dict(self):
        return {
            "id": self.id,
            "steam_name": self.steam_name,
            "shinri_name": self.shinri_name,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data):
        # Поддержка старого формата: раньше имя могло храниться в "name".
        steam_name = data.get(
            "steam_name",
            data.get("name", ""),
        )

        return cls(
            steam_name,
            data.get("shinri_name", ""),
            data.get("note", ""),
            player_id=data.get("id"),
        )
