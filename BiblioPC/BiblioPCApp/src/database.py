from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event 
from config import settings

# Verbindung-URL für den asynchronen SQLite-Treiber bauen
DATABASE_URL = "sqlite+aiosqlite:////app/db/BiblioPC.db"

# Der Engine-Sitzungsverwalter
engine = create_async_engine(DATABASE_URL, echo=True)

# WAL-Modus (Fehlertolerant für aiosqlite):
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# Eine Fabrik für Datenbank-Sitzungen (Sessions)
async_session = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Hilfsfunktion (Dependency) für FastAPI-Endpunkte
async def get_db():
    async with async_session() as session:
        yield session