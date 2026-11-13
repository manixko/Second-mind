
import json
from pathlib import Path


class ConfigManager:

    def __init__(self):
        self.database_path = (
            Path(__file__).resolve().parent.parent / "Database"
        )

        if not self.database_path.is_dir():
            raise FileNotFoundError(
                f"Database folder does not exist: {self.database_path}"
            )

    def _get_vendor_path(self, vendor):
        for folder in self.database_path.iterdir():
            if folder.is_dir() and folder.name.lower() == vendor.lower():
                return folder

        raise FileNotFoundError(f"Vendor '{vendor}' not found")

    def get_configs(self, vendor):
        vendor_path = self._get_vendor_path(vendor)
        configs = []

        for file in sorted(vendor_path.glob("*.json")):
            try:
                config = self._read_json(file)

                configs.append({
                    "id": config.get("id", file.stem),
                    "name": config.get("name", file.stem),
                    "description": config.get("description", ""),
                    "file": file.stem
                })

            except (ValueError, OSError):
                continue

        return configs

    def load_config(self, vendor, config_id):
        vendor_path = self._get_vendor_path(vendor)
        config_path = vendor_path / f"{config_id}.json"

        if not config_path.is_file():
            raise FileNotFoundError(
                f"Config not found: {config_path}"
            )

        config = self._read_json(config_path)

        if config.get("id", config_id) != config_id:
            raise ValueError("Config ID mismatch")

        return config

    def build_commands(self, config, values):
        inputs = config.get("inputs", [])
        commands = config.get("commands", [])

        if not isinstance(inputs, list) or not isinstance(commands, list):
            raise ValueError("Invalid config structure")

        if not all(isinstance(command, str) for command in commands):
            raise ValueError("Commands must be strings")

        validated_values = {}

        for field in inputs:
            name = field["name"]
            value = values.get(name, field.get("default"))

            if value is None:
                if field.get("required", True):
                    raise ValueError(f"Missing required input: {name}")
                continue

            field_type = field.get("type", "string")

            if field_type == "integer":
                if isinstance(value, bool):
                    raise ValueError(f"{name} must be an integer")

                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"{name} must be an integer")

                if "min" in field and value < field["min"]:
                    raise ValueError(f"{name} is below minimum")

                if "max" in field and value > field["max"]:
                    raise ValueError(f"{name} exceeds maximum")

            elif field_type in ("string", "interface"):
                if not isinstance(value, str):
                    raise ValueError(f"{name} must be a string")

                if not value and field.get("required", True):
                    raise ValueError(f"{name} cannot be empty")

                if any(char in value for char in ("\n", "\r", "\x00")):
                    raise ValueError(f"Invalid characters in {name}")

            else:
                raise ValueError(f"Unsupported input type: {field_type}")

            if "choices" in field and value not in field["choices"]:
                raise ValueError(f"Invalid choice for {name}")

            validated_values[name] = value

        try:
            return [
                command.format_map(validated_values)
                for command in commands
            ]
        except (KeyError, ValueError):
            raise ValueError("Invalid command template")

    @staticmethod
    def _read_json(path):
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
