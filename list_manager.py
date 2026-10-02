from players_list import PlayerList


class ListManager:
    def __init__(self):
        self.lists = []

    def create_list(self, name):
        self.lists.append(PlayerList(name))

    def delete_list(self, name):
        for list in self.lists:
            if list.name == name:
                self.lists.remove(list)

    def get_list(self, name):
        for list_ in self.lists:
            if list_.name == name:
                return list_
        return None

    def rename_list(self, name, new_name):
        for list_ in self.lists:
            if list_.name == name:
                list_.update_name(new_name)

    def to_dict(self):
        return {
            "lists": [
                player_list.to_dict()
                for player_list in self.lists
            ]
        }

    @classmethod
    def from_dict(cls, data):
        manager = cls()

        for list_data in data["lists"]:
            manager.lists.append(
                PlayerList.from_dict(list_data)
            )

        return manager