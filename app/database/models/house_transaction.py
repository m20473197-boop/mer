"""HouseTransaction ORM model — the money audit trail of the housing system."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

# Transaction types
TX_MARKET_PURCHASE: str = "market_purchase"   # player buys from system market
TX_PLAYER_PURCHASE: str = "player_purchase"   # player buys from player
TX_RENT_DEPOSIT: str = "rent_deposit"         # tenant pays the deposit (رهن)
TX_RENT_PAYMENT: str = "rent_payment"         # tenant pays monthly rent


class HouseTransaction(Base):
    """One money movement caused by the housing system.

    Written inside the same transaction as the balance changes themselves,
    so the audit trail can never drift from the wallets.

    Fields:
        id: Primary key.
        house_id: Related house (nullable for robustness).
        contract_id: Related rental contract (rent payments/deposits).
        payer_player_id: Who paid (FK players).
        payee_player_id: Who received (FK players; ``None`` → system market).
        amount: Amount moved (Toman, exact integer).
        transaction_type: One of the ``TX_*`` constants.
        note: Short human-readable note for history screens.
        created_at: When the money moved.
    """

    __tablename__ = "house_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    house_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contract_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("rental_contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    payer_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payee_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HouseTransaction id={self.id} type={self.transaction_type!r} "
            f"amount={self.amount} payer={self.payer_player_id} "
            f"payee={self.payee_player_id}>"
        )
