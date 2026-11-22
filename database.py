import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

url = os.environ["DATABASE_URL"]
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
elif url.startswith("postgresql://") and "+asyncpg" not in url:
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    added_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class CheckLog(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(100), index=True)
    requester_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("voter_id", "target_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voter_id: Mapped[int] = mapped_column(BigInteger)
    target_key: Mapped[str] = mapped_column(String(100))
    value: Mapped[int] = mapped_column(Integer)

class AdminAction(Base):
    __tablename__ = "admin_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

@asynccontextmanager
async def session_scope():
    async with Session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db():
    await engine.dispose()

def normalize_query(raw: str):
    value = raw.strip()
    if value.startswith("@"):
        value = value[1:]
    if value.isdigit():
        return f"id:{value}", None, int(value)
    if not value or len(value) > 64:
        raise ValueError("Неверный username или ID")
    username = value.lower()
    return f"user:{username}", username, None

async def lookup(session, raw: str):
    try:
        key, _, _ = normalize_query(raw)
    except ValueError:
        return None
    return await session.scalar(select(Person).where(Person.key == key))

async def log_check(session, raw: str, requester_id: int):
    normalized = raw.strip().lower()[:100]
    session.add(CheckLog(query=normalized, requester_id=requester_id))
    await session.flush()
    count = await session.scalar(select(func.count(CheckLog.id)).where(CheckLog.query == normalized))
    await session.commit()
    return int(count or 0)
