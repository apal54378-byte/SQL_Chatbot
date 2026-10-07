import os
from functools import lru_cache
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()
_REQUIRED = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")

def missing_database_settings():
    return [name for name in _REQUIRED if not os.getenv(name)]

@lru_cache(maxsize=1)
def get_engine():
    missing = missing_database_settings()
    if missing:
        raise ValueError(f"Missing database settings: {', '.join(missing)}. Add them to your .env file.")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
