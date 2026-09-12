"""Admin authentication (pure — no I/O).

Only the Telegram user IDs in the loaded settings may use the admin panel.
``ADMIN_IDS`` comes from the environment (see ``.env``); when it is empty,
the config layer falls back to ``constants.ADMIN_TELEGRAM_IDS`` so the
panel owner (8154313073) is never locked out.

Every admin handler and every admin callback runs through :func:`is_admin`
before doing anything else; non-admins are blocked with a friendly message
and the attempt is logged server-side.
"""

from __future__ import annotations

from collections.abc import Iterable


def is_admin(telegram_user_id: object, admin_ids: Iterable[int] | None) -> bool:
    """Whether ``telegram_user_id`` is an authorized admin.

    Deliberately strict: unknown/empty IDs, an empty admin list and any
    non-integer input all mean *not* admin.
    """
    if admin_ids is None:
        return False
    try:
        user_id = int(telegram_user_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    try:
        allowed = {int(candidate) for candidate in admin_ids}
    except (TypeError, ValueError):
        return False
    return user_id in allowed
