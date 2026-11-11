from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# hide_parameters keeps payment names, amounts and emails out of error logs.
engine_options = {"pool_pre_ping": True, "hide_parameters": True}
if not settings.database_url.startswith("sqlite"):
    # Keep each Render instance inside a predictable connection budget. Two
    # bounded Gmail scans still leave eight slots for interactive requests.
    engine_options.update(
        {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_timeout": settings.database_pool_timeout,
            "pool_recycle": 300,
            "connect_args": {"connect_timeout": settings.database_connect_timeout},
        }
    )

engine = create_engine(
    settings.database_url,
    **engine_options,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
