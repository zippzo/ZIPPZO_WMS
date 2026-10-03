from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Zippzo WMS database
DATABASE_URL = "sqlite:///./zippzo_wms.db"

# Create database connection
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Create database sessions
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

# Base class for database models
Base = declarative_base()


# Database session
def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()