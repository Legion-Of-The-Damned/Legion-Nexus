from pypresence import Presence
import time


class DiscordRPCManager:
    def __init__(self, client_id=""):
        self.client_id = client_id
        self.rpc = None
        self.connected = False

    def start(self):
        if self.connected:
            return

        if not self.client_id:
            print("[RPC] Client ID не указан")
            return

        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True

            self.update_menu()

        except Exception as e:
            print(f"[RPC] ошибка start: {e}")
            self.connected = False

    def update_menu(self):
        self._update(
            state="В лаунчере Legion Nexus",
            details="Главное меню"
        )

    def update_mod(self, mod_name: str):
        self._update(
            state=f"Играет: {mod_name}",
            details="Использует моды"
        )

    def update_lobby(self, current_players: int, max_players: int, lobby_id: str):
        self._update(
            state="В лобби",
            details="Ожидание игроков",
            party_size=[current_players, max_players],
            party_max=max_players,
            join_secret=lobby_id
        )

    def update_game(self, status: str, lobby_id: str = None):
        self._update(
            state=status,
            details="В игре",
            party_size=[1, 1] if not lobby_id else None,
            party_max=1 if not lobby_id else None,
            join_secret=lobby_id
        )

    def _update(self, state="", details="", party_size=None, party_max=None, join_secret=None):
        if not self.connected:
            return

        try:
            payload = {
                "state": state,
                "details": details,
                "large_image": "logo",
                "large_text": "Legion Nexus",
                "start": time.time()
            }

            if party_size and party_max:
                payload["party_size"] = party_size
                payload["party_id"] = "legion_lobby"

            if join_secret:
                payload["join"] = join_secret

            self.rpc.update(**payload)

        except Exception as e:
            print(f"[RPC] ошибка update: {e}")
            self.connected = False

    def stop(self):
        if self.rpc:
            try:
                self.rpc.clear()
                self.rpc.close()
            except Exception as e:
                print(f"[RPC] ошибка stop: {e}")

        self.connected = False