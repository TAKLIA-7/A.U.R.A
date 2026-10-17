"""Reset the local synthetic database only (DATABASE_URL default: ./aura.db)."""

import os

from backend.app.main import Base, engine

if __name__ == "__main__":
    if os.getenv("ALLOW_SYNTHETIC_DB_RESET") != "1":
        raise SystemExit("Set ALLOW_SYNTHETIC_DB_RESET=1 to confirm local synthetic DB reset.")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Local database schema recreated. Run seed_database to add fictional records.")
