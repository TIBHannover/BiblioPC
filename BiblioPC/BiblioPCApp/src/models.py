from datetime import datetime
from sqlalchemy import Column, String, Integer, Date, DateTime, Boolean, Text, func
from sqlalchemy.orm import DeclarativeBase

# Die Basisklasse für alle unsere Modelle
class Base(DeclarativeBase):
    pass

class LokalerBenutzer(Base):
    __tablename__ = "benutzer"
    
    BenNr = Column(String(50), primary_key=True)
    Pw = Column(String(255), nullable=False)  # Hashed password for authentication
    Von = Column(Date, nullable=False)
    Bis = Column(Date, nullable=False)
    Bearb = Column(String(20), nullable=False)
    Bemerkungen = Column(String(250), nullable=False)
    Host = Column(String(80), nullable=False)
    Datum = Column(DateTime, nullable=False, server_default=func.now())

class Sperrung(Base):
    __tablename__ = "sperrung"
    
    BenNr = Column(String(50), primary_key=True)
    gesperrt = Column(Boolean, nullable=True)
    Von = Column(Date, nullable=False)
    Bis = Column(Date, nullable=False)
    Bearb = Column(String(20), nullable=True)
    Bemerkungen = Column(String(250), nullable=False)
    Datum = Column(DateTime, nullable=False, server_default=func.now())

class BenutzerMax(Base):
    __tablename__ = "benutzermax"
    
    # Da BenNr auch Wildcards (z.B. '123*') enthalten kann, nutzen wir es als Key
    # Falls die Tabelle eine ID hat, müsste diese als primary_key gesetzt werden.
    BenNr = Column(String(50), primary_key=True)
    Max = Column(String(8), nullable=False) # Format "HH:MM:SS" oder "HH:MM"
    Von = Column(Date, primary_key=True)     # Kombinierter Primärschlüssel, falls keine ID existiert
    Bis = Column(Date, nullable=False)

class Zeitlimit(Base):
    __tablename__ = "zeitlimit"
    
    # Wenn es nur eine Zeile gibt, reicht ein Dummy-Key oder das primäre Feld
    StandardMax = Column(String(8), primary_key=True) # Format "HH:MM:SS"

class Aktiv(Base):
    __tablename__ = "aktiv"
    
    IP = Column(String(45), primary_key=True) # Unterstützt IPv4 und IPv6
    BenNr = Column(String(50), nullable=False, index=True)
    Login = Column(String(19), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    Host = Column(String(255), nullable=True)

class LogData(Base):
    __tablename__ = "logdata"
    
    Id = Column(Integer, primary_key=True, autoincrement=True)
    LogAkt = Column(String(10), nullable=False)
    BenNr = Column(String(50), nullable=False) 
    Datum = Column(Date, nullable=False)        
    IP = Column(String(50), nullable=False)
    Host = Column(String(80), nullable=False)
    Zeit = Column(String(20), nullable=False) # Format "HH:MM:SS"
    
class Nutzung(Base):
    __tablename__ = "nutzung"
    
    BenNr = Column(String(50), primary_key=True)
    Max = Column(String(8), nullable=False)   # z.B. "02:00:00"
    Used = Column(String(8), nullable=False)  # bereits verbrauchte Zeit, z.B. "00:30:00"
    # Bis ist primär, falls ein Benutzer über mehrere Zeiträume Einträge hat
    Bis = Column(String(8), primary_key=True)   

class Bearbeiter(Base):
    __tablename__ = "bearbeiter"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    Bearb = Column(String(250), nullable=False, unique=True)
    Passwort = Column(String(255), nullable=False) # Enthält den bcrypt/argon2-Hash

class Zugang(Base):
    __tablename__ = "zugang"
    
    BenNr = Column(String(50), primary_key=True)
    Von = Column(Date, nullable=False)
    Bis = Column(Date, nullable=False)
    Max = Column(String(20), nullable=False)   # Speichert das Format "HH:MM:SS"
    Used = Column(String(20), nullable=False)  # Speichert das Format "HH:MM:SS"
    Bearb = Column(String(20), nullable=True)
    Bemerkungen = Column(String(250), nullable=True)
    Datum = Column(DateTime, nullable=False, server_default=func.now())
