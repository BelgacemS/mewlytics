from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercase: MySQL's default collation compares case-insensitively,
    # SQLite does not, and both must agree on what counts as a duplicate
    username: Mapped[str] = mapped_column(String(32), unique=True)
    # argon2 encoded hash, with its parameters and salt
    password_hash: Mapped[str] = mapped_column(String(255))
