"""Schema-shape guards required by the game design rules."""

from __future__ import annotations

from sqlalchemy import BigInteger

from app.database.models.player import Player


def test_player_has_no_age_field():
    """The game does not use player age — it must not even exist."""
    column_names = {column.name for column in Player.__table__.columns}
    assert "age" not in column_names
    assert not hasattr(Player(telegram_user_id=1, display_name="x"), "age")


def test_telegram_user_id_is_unique():
    """One Telegram user can own exactly one profile — enforced by the DB."""
    column = Player.__table__.columns["telegram_user_id"]
    unique_index = any(
        index.unique and index.columns[0].name == "telegram_user_id"
        for index in Player.__table__.indexes
    )
    assert column.unique is True or unique_index


def test_money_column_is_exact_integer_type():
    """Money must be an exact integer column — floats are forbidden."""
    column_type = Player.__table__.columns["money"].type
    assert isinstance(column_type, BigInteger)


def test_username_is_nullable():
    """Telegram users without a username must be storable."""
    assert Player.__table__.columns["username"].nullable is True
