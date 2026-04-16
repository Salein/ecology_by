from __future__ import annotations

from pathlib import Path

from app.services.auth_users import USERS_PATH, import_users_from_json


def main() -> None:
    imported = import_users_from_json(USERS_PATH)
    print(f"Imported users: {imported}")


if __name__ == "__main__":
    main()
