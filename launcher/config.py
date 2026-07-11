import json
import os


class ConfigManager:
    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, "config.json")
        self.data = {
            "ram": 4,
            "resolution": "1280x720"
        }
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except:
            self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)