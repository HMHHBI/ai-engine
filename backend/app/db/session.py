from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Engine setup
# engine = create_engine(
#     settings.DATABASE_URL, 
#     connect_args={"check_same_thread": False} # SQLite ke liye zaroori hai
# )

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "options": "-c client_encoding=utf8"
    }
)

# Session factory (Laravel ke DB connection ki tarah)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Models is class ko inherit karenge
Base = declarative_base()

# Dependency: Har request par naya DB session khulega aur khatam honay par band
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()