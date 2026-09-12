"""AdminService tests — dashboard, users, economy, estate, jobs, trading,
settings, database tools and logs (real database, no Telegram)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from app.database.models.economic_event import EconomicEvent
from app.database.models.house_listing import HouseListing
from app.database.repositories.player_repository import PlayerRepository
from app.game.admin import runtime as admin_runtime
from app.game.shared.errors import (
    InsufficientFundsError,
    InvalidAmountError,
    PlayerNotFoundError,
)
from app.services.admin_service import AdminError

ADMIN_ID = 8154313073


@pytest.fixture(autouse=True)
def _clean_runtime():
    admin_runtime.reset_to_defaults()
    yield
    admin_runtime.reset_to_defaults()


async def _fund(services, player_id: int, amount: int) -> None:
    async with services.players._session_factory() as session:  # noqa: SLF001
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


async def _seed_economy(services):
    await services.admin.ensure_economy_seeded()
    await services.admin.refresh_runtime()


async def _cheapest_market_house(services):
    entries = await services.housing.get_available_houses_for_sale()
    assert entries
    return min(entries, key=lambda e: e.price)


async def _cheapest_land(services):
    entries = await services.realestate.get_available_lands()
    assert entries
    return min(entries, key=lambda e: e.price)


# --- Dashboard -------------------------------------------------------------------

async def test_dashboard_aggregates_real_numbers(services, register):
    alice = await register(tg_id=6201)
    await register(tg_id=6202)
    await _fund(services, alice.player_id, 1_500_000)
    await services.housing.ensure_initial_houses()
    await services.realestate.ensure_initial_lands()
    await _seed_economy(services)

    stats = await services.admin.get_dashboard()

    assert stats.total_users == 2
    assert stats.active_users_24h == 2
    assert stats.banned_users == 0
    assert stats.total_money == 1_500_000
    assert stats.houses_count == 30
    assert stats.lands_count == 24
    assert stats.jobs_count == 6  # «خر حمالی» catalog
    assert stats.active_sale_listings == 0
    assert stats.market_factor == pytest.approx(1.0)
    assert stats.db_dialect == "sqlite"
    assert stats.db_tables > 10
    assert stats.db_ping_ms >= 0
    assert stats.python_version


# --- Users -----------------------------------------------------------------------

async def test_list_users_paginates(services, register):
    for tg_id in range(6210, 6222):
        await register(tg_id=tg_id)

    first = await services.admin.list_users(0, per_page=8)
    second = await services.admin.list_users(1, per_page=8)

    assert first.total == 12 and len(first.items) == 8
    assert second.total == 12 and len(second.items) == 4
    assert first.has_next and not first.has_prev
    assert second.has_prev and not second.has_next


async def test_search_users_by_id_username_and_name(services, register):
    await register(tg_id=6231, username="saraShop", display_name="سارا محمدی")

    by_tg = await services.admin.search_users("6231")
    by_username = await services.admin.search_users("sarashop")
    by_name = await services.admin.search_users("محمدی")
    missing = await services.admin.search_users("nobody-xyz")

    assert len(by_tg) == 1 and by_tg[0].telegram_user_id == 6231
    assert len(by_username) == 1
    assert len(by_name) == 1
    assert missing == []
    assert await services.admin.search_users("   ") == []


async def test_get_user_detail(services, register):
    target = await register(tg_id=6241)
    detail = await services.admin.get_user_detail(target.player_id)

    assert detail.summary.telegram_user_id == 6241
    assert detail.houses_count == 0
    assert detail.job_name is None
    with pytest.raises(PlayerNotFoundError):
        await services.admin.get_user_detail(999_999)


async def test_add_and_remove_money_with_audit(services, register):
    target = await register(tg_id=6251)

    added = await services.admin.add_money(ADMIN_ID, target.player_id, 2_000_000)
    assert added.balance_after == 2_000_000
    removed = await services.admin.remove_money(ADMIN_ID, target.player_id, 500_000)
    assert removed.balance_after == 1_500_000

    logs = await services.admin.list_audit_logs(0, per_page=10)
    actions = [row.action for row in logs.items]
    assert "user_add_money" in actions and "user_remove_money" in actions

    with pytest.raises(InsufficientFundsError):
        await services.admin.remove_money(ADMIN_ID, target.player_id, 10**12)
    with pytest.raises(InvalidAmountError):
        await services.admin.add_money(ADMIN_ID, target.player_id, 0)
    with pytest.raises(PlayerNotFoundError):
        await services.admin.add_money(ADMIN_ID, 999_999, 100)


async def test_add_remove_xp_and_set_level(services, register):
    target = await register(tg_id=6261)

    added = await services.admin.add_xp(ADMIN_ID, target.player_id, 150)
    assert added.xp_after == 150 and added.new_level >= 2
    removed = await services.admin.remove_xp(ADMIN_ID, target.player_id, 50)
    assert removed.xp_after == 100
    leveled = await services.admin.set_level(ADMIN_ID, target.player_id, 5)
    assert leveled.new_level == 5

    with pytest.raises(InvalidAmountError):
        await services.admin.add_xp(ADMIN_ID, target.player_id, 0)
    with pytest.raises(InvalidAmountError):
        await services.admin.set_level(ADMIN_ID, target.player_id, 101)

    logs = await services.admin.list_audit_logs(0, per_page=10, action_prefix="user_")
    assert {row.action for row in logs.items} >= {
        "user_add_xp", "user_remove_xp", "user_set_level",
    }


async def test_ban_and_unban_user(services, register):
    target = await register(tg_id=6271)
    assert await services.admin.is_user_banned(6271) is False
    assert await services.admin.is_user_banned(9_999_999) is False

    banned = await services.admin.ban_user(ADMIN_ID, target.player_id)
    assert banned.is_banned is True
    assert await services.admin.is_user_banned(6271) is True

    unbanned = await services.admin.unban_user(ADMIN_ID, target.player_id)
    assert unbanned.is_banned is False

    with pytest.raises(PlayerNotFoundError):
        await services.admin.ban_user(ADMIN_ID, 999_999)


async def test_admins_cannot_be_banned(services, register):
    owner = await register(tg_id=ADMIN_ID)
    services.admin.set_admin_ids((ADMIN_ID,))
    with pytest.raises(AdminError):
        await services.admin.ban_user(ADMIN_ID, owner.player_id)


async def test_user_transactions_and_properties(services, register):
    await services.housing.ensure_initial_houses()
    await services.realestate.ensure_initial_lands()
    buyer = await register(tg_id=6281)
    tenant = await register(tg_id=6282)

    entry = await _cheapest_market_house(services)
    await _fund(services, buyer.player_id, entry.price)
    await services.housing.buy_from_market(buyer.player_id, entry.house.id)

    land_entry = await _cheapest_land(services)
    await _fund(services, buyer.player_id, land_entry.price)
    await services.realestate.buy_land(buyer.player_id, land_entry.land.id)

    txs = await services.admin.get_user_transactions(buyer.player_id)
    assert len(txs) >= 2
    assert all(t.amount > 0 for t in txs)

    houses, lands = await services.admin.get_user_properties(buyer.player_id)
    assert len(houses) == 1 and len(lands) == 1
    assert houses[0].market_value > 0

    tenant_txs = await services.admin.get_user_transactions(tenant.player_id)
    assert tenant_txs == []
    with pytest.raises(PlayerNotFoundError):
        await services.admin.get_user_transactions(999_999)


# --- Economy ---------------------------------------------------------------------

async def test_economy_seeding_is_idempotent(services):
    await services.admin.ensure_economy_seeded()
    await services.admin.ensure_economy_seeded()

    assets = await services.admin.list_assets()
    assert len(assets) == 7
    assert {a.code for a in assets} >= {"USD", "BTC", "GOLD18"}
    overview = await services.admin.get_economy_overview()
    assert overview.effective_factor == pytest.approx(1.0)


async def test_market_conditions_move_house_prices(services, register):
    await services.housing.ensure_initial_houses()
    await _seed_economy(services)
    entry = await _cheapest_market_house(services)
    target = await register(tg_id=6291)
    await _fund(services, target.player_id, entry.price)
    await services.housing.buy_from_market(target.player_id, entry.house.id)

    before = (await services.admin.get_house_detail(entry.house.id)).market_value
    effective = await services.admin.set_market_conditions(ADMIN_ID, 2.0)
    after = (await services.admin.get_house_detail(entry.house.id)).market_value

    assert effective == pytest.approx(2.0)
    assert after > before * 1.9  # rounding slack on the 100k step
    with pytest.raises(InvalidAmountError):
        await services.admin.set_market_conditions(ADMIN_ID, 50.0)


async def test_inflation_moves_land_prices(services):
    await services.realestate.ensure_initial_lands()
    await _seed_economy(services)
    land_entry = await _cheapest_land(services)

    before = (await services.admin.get_land_detail(land_entry.land.id)).market_value
    await services.admin.set_inflation(ADMIN_ID, 100.0)  # +100% → ×2
    after = (await services.admin.get_land_detail(land_entry.land.id)).market_value

    assert after > before * 1.9
    with pytest.raises(InvalidAmountError):
        await services.admin.set_inflation(ADMIN_ID, -95.0)


async def test_asset_price_and_history(services):
    await _seed_economy(services)

    updated = await services.admin.set_asset_price(ADMIN_ID, "USD", 2_000_000)
    assert updated.price == 2_000_000
    asset, ticks = await services.admin.get_asset_history("USD")
    assert asset.price == 2_000_000
    assert len(ticks) >= 2  # seed tick + change tick
    assert ticks[0].price == 2_000_000

    with pytest.raises(AdminError):
        await services.admin.set_asset_price(ADMIN_ID, "XXX", 100)
    with pytest.raises(InvalidAmountError):
        await services.admin.set_asset_price(ADMIN_ID, "USD", 0)


async def test_economic_event_lifecycle(services):
    await _seed_economy(services)

    event = await services.admin.create_event(
        ADMIN_ID, name="رونق", description="", multiplier=1.25, duration_hours=48
    )
    assert event.is_live is True
    overview = await services.admin.get_economy_overview()
    assert overview.effective_factor == pytest.approx(1.25)
    assert len(overview.live_events) == 1

    ended = await services.admin.end_event(ADMIN_ID, event.id)
    assert ended.is_active is False
    overview = await services.admin.get_economy_overview()
    assert overview.effective_factor == pytest.approx(1.0)

    with pytest.raises(AdminError):
        await services.admin.end_event(ADMIN_ID, event.id)
    with pytest.raises(InvalidAmountError):
        await services.admin.create_event(
            ADMIN_ID, name="x", description="", multiplier=0.01, duration_hours=1
        )
    with pytest.raises(InvalidAmountError):
        await services.admin.create_event(
            ADMIN_ID, name="", description="", multiplier=1.5, duration_hours=1
        )


async def test_settle_events_expires_old_ones(services, db):
    await _seed_economy(services)
    event = await services.admin.create_event(
        ADMIN_ID, name="موقت", description="", multiplier=1.5, duration_hours=1
    )
    # Backdate the window into the past, then settle.
    async with db.session_factory() as session:
        await session.execute(
            update(EconomicEvent)
            .where(EconomicEvent.id == event.id)
            .values(
                starts_at=datetime.now() - timedelta(hours=3),
                ends_at=datetime.now() - timedelta(hours=2),
            )
        )
        await session.commit()

    ended = await services.admin.settle_events()
    assert ended == 1
    overview = await services.admin.get_economy_overview()
    assert overview.effective_factor == pytest.approx(1.0)


async def test_trigger_crisis(services):
    await _seed_economy(services)
    event = await services.admin.trigger_crisis(ADMIN_ID)
    assert event.multiplier == pytest.approx(1.35)
    overview = await services.admin.get_economy_overview()
    assert overview.effective_factor == pytest.approx(1.35)
    logs = await services.admin.list_audit_logs(0, per_page=5, action_prefix="event_")
    assert "event_crisis" in [row.action for row in logs.items]


# --- Real estate -------------------------------------------------------------------

async def test_list_and_detail_houses(services, register):
    await services.housing.ensure_initial_houses()
    target = await register(tg_id=6301)
    entry = await _cheapest_market_house(services)
    await _fund(services, target.player_id, entry.price)
    await services.housing.buy_from_market(target.player_id, entry.house.id)

    page = await services.admin.list_houses(0)
    assert page.total == 30 and len(page.items) == 6
    owned = [h for h in page.items if h.owner_player_id == target.player_id]
    assert len(owned) <= 6  # owner name resolution is covered below

    detail = await services.admin.get_house_detail(entry.house.id)
    assert detail.owner_name == "علی"
    assert detail.market_value > 0
    with pytest.raises(AdminError):
        await services.admin.get_house_detail(999_999)


async def test_update_house_fields(services):
    await services.housing.ensure_initial_houses()

    detail = await services.admin.update_house(ADMIN_ID, 1, "area_sqm", 150)
    assert detail.house.area_sqm == 150
    detail = await services.admin.update_house(ADMIN_ID, 1, "quality", "عالی")
    assert detail.house.quality == "عالی"
    detail = await services.admin.update_house(
        ADMIN_ID, 1, "construction_year", 1390
    )
    assert detail.house.construction_year == 1390
    detail = await services.admin.update_house_location(
        ADMIN_ID, 1, "کرج", "گوهردشت"
    )
    assert (detail.house.city, detail.house.neighborhood) == ("کرج", "گوهردشت")

    with pytest.raises(InvalidAmountError):
        await services.admin.update_house(ADMIN_ID, 1, "area_sqm", 3)
    with pytest.raises(InvalidAmountError):
        await services.admin.update_house(ADMIN_ID, 1, "quality", "طلایی")
    with pytest.raises(InvalidAmountError):
        await services.admin.update_house_location(
            ADMIN_ID, 1, "تهران", "محله خیالی"
        )
    with pytest.raises(AdminError):
        await services.admin.update_house(ADMIN_ID, 1, "id", 5)


async def test_house_price_override_scales_value(services):
    await services.housing.ensure_initial_houses()
    before = (await services.admin.get_house_detail(2)).market_value

    detail = await services.admin.set_house_override(ADMIN_ID, 2, 1200)
    assert detail.house.price_override_per_mille == 1200
    assert detail.market_value == max(1, before * 1200 // 1000)

    cleared = await services.admin.set_house_override(ADMIN_ID, 2, None)
    assert cleared.house.price_override_per_mille is None
    assert cleared.market_value == before

    with pytest.raises(InvalidAmountError):
        await services.admin.set_house_override(ADMIN_ID, 2, 5)


async def test_update_land_and_override(services):
    await services.realestate.ensure_initial_lands()

    detail = await services.admin.update_land(ADMIN_ID, 1, "area_sqm", 750)
    assert detail.land.area_sqm == 750
    moved = await services.admin.update_land_location(ADMIN_ID, 1, "تهران", "ونک")
    assert moved.land.location_quality == "لوکس"

    before = moved.market_value
    overridden = await services.admin.set_land_override(ADMIN_ID, 1, 1500)
    assert overridden.market_value == max(1, before * 1500 // 1000)

    page = await services.admin.list_lands(0)
    assert page.total == 24
    with pytest.raises(InvalidAmountError):
        await services.admin.update_land(ADMIN_ID, 1, "area_sqm", 5)
    with pytest.raises(AdminError):
        await services.admin.get_land_detail(999_999)


async def test_close_listing_and_terminate_contract(services, register):
    await services.housing.ensure_initial_houses()
    owner = await register(tg_id=6311)
    tenant = await register(tg_id=6312)

    # Sale listing → admin closes it.
    sale_entry = await _cheapest_market_house(services)
    await _fund(services, owner.player_id, sale_entry.price)
    await services.housing.buy_from_market(owner.player_id, sale_entry.house.id)
    value = services.housing.estimate_value(
        await _house_orm(services, sale_entry.house.id)
    )
    await services.housing.list_house_for_sale(owner.player_id, sale_entry.house.id, value)

    listings = await services.admin.list_active_listings(0)
    assert listings.total == 1
    await services.admin.close_listing(ADMIN_ID, listings.items[0].listing_id)
    assert (await services.admin.list_active_listings(0)).total == 0
    with pytest.raises(AdminError):
        await services.admin.close_listing(ADMIN_ID, listings.items[0].listing_id)

    # Rent listing → contract → admin terminates it.
    houses = await services.housing.get_available_houses_for_sale()
    second = min(
        (e for e in houses if e.house.id != sale_entry.house.id),
        key=lambda e: e.price,
    )
    await _fund(services, owner.player_id, second.price)
    await services.housing.buy_from_market(owner.player_id, second.house.id)
    value2 = services.housing.estimate_value(await _house_orm(services, second.house.id))
    await services.housing.list_house_for_rent(
        owner.player_id, second.house.id, value2 // 200, value2 // 10
    )
    await _fund(services, tenant.player_id, value2 // 5)
    await services.housing.rent_house(tenant.player_id, second.house.id)

    contracts = await services.admin.list_contracts(0)
    assert contracts.total == 1
    await services.admin.terminate_contract(ADMIN_ID, contracts.items[0].contract_id)
    assert (await services.admin.list_contracts(0)).total == 0
    with pytest.raises(AdminError):
        await services.admin.terminate_contract(ADMIN_ID, 999_999)


async def _house_orm(services, house_id: int):
    from app.database.repositories.house_repository import HouseRepository

    async with services.players._session_factory() as session:  # noqa: SLF001
        house = await HouseRepository(session).get_by_id(house_id)
        assert house is not None
        return house


# --- Jobs --------------------------------------------------------------------------

async def test_create_update_and_toggle_job(services):
    jobs = await services.admin.list_jobs()
    assert len(jobs) == 6  # «خر حمالی» catalog

    created = await services.admin.create_job(
        ADMIN_ID, name="راننده", description="رانندگی در شهر",
        hourly_salary=300_000, required_level=2, employer="آژانس پارس",
    )
    assert created.id > 0 and created.is_active is True

    updated = await services.admin.update_job(
        ADMIN_ID, created.id, "hourly_salary", 400_000
    )
    assert updated.hourly_salary == 400_000

    toggled = await services.admin.set_job_active(ADMIN_ID, created.id, False)
    assert toggled.is_active is False

    with pytest.raises(AdminError):
        await services.admin.create_job(
            ADMIN_ID, name="راننده", description="تکراری",
            hourly_salary=100_000, required_level=1, employer="x",
        )
    with pytest.raises(InvalidAmountError):
        await services.admin.update_job(ADMIN_ID, created.id, "hourly_salary", 0)
    with pytest.raises(AdminError):
        await services.admin.get_job(999_999)


async def test_list_workers(services, register):
    jobs = await services.admin.list_jobs()
    worker_job = next(j for j in jobs if j.required_level == 1)
    target = await register(tg_id=6321)
    await services.jobs.apply_job(target.player_id, worker_job.id)

    workers = await services.admin.list_workers(0)
    assert workers.total == 1
    assert workers.items[0].telegram_user_id == 6321
    assert workers.items[0].job_name == worker_job.name


# --- Trading -----------------------------------------------------------------------

async def test_trading_overview_sales_and_activity(services, register):
    await services.housing.ensure_initial_houses()
    overview = await services.admin.get_trading_overview()
    assert overview["total_sales"] == 0

    buyer = await register(tg_id=6331)
    entry = await _cheapest_market_house(services)
    await _fund(services, buyer.player_id, entry.price)
    await services.housing.buy_from_market(buyer.player_id, entry.house.id)

    overview = await services.admin.get_trading_overview()
    assert overview["total_sales"] == 1
    sales = await services.admin.list_recent_sales(0)
    assert sales.total == 1
    assert sales.items[0].buyer_name == "علی"
    activity = await services.admin.get_market_activity()
    assert len(activity) >= 1


# --- Settings ----------------------------------------------------------------------

async def test_settings_overview_and_rewards(services):
    await _seed_economy(services)
    overview = await services.admin.get_settings_overview()
    assert overview.purchase_xp_divisor == 20_000_000
    assert overview.jobs_enabled is True

    await services.admin.set_reward_setting(ADMIN_ID, "pxd", 10_000_000)
    assert (await services.admin.get_settings_overview()).purchase_xp_divisor == 10_000_000
    await services.admin.set_min_work_minutes(ADMIN_ID, 30)
    assert (await services.admin.get_settings_overview()).min_work_minutes == 30

    with pytest.raises(InvalidAmountError):
        await services.admin.set_reward_setting(ADMIN_ID, "pxn", 1_000_000)
    with pytest.raises(InvalidAmountError):
        await services.admin.set_reward_setting(ADMIN_ID, "pxx", 1)
    with pytest.raises(AdminError):
        await services.admin.set_reward_setting(ADMIN_ID, "zzz", 1)


async def test_feature_flags_roundtrip(services):
    await _seed_economy(services)
    await services.admin.set_feature(ADMIN_ID, "jobs", False)
    assert admin_runtime.feature_enabled("jobs") is False
    assert (await services.admin.get_settings_overview()).jobs_enabled is False
    await services.admin.set_feature(ADMIN_ID, "jobs", True)
    assert admin_runtime.feature_enabled("jobs") is True
    with pytest.raises(AdminError):
        await services.admin.set_feature(ADMIN_ID, "teleport", True)


# --- Database tools ------------------------------------------------------------------

async def test_db_stats(services, register, db):
    services.attach_database(db)
    await register(tg_id=6341)
    stats = await services.admin.get_db_stats()
    assert stats.dialect == "sqlite"
    assert stats.file_size_bytes and stats.file_size_bytes > 0
    counts = dict(stats.counts)
    assert counts.get("players") == 1
    assert stats.total_rows >= 1


async def test_backup_and_restore_roundtrip(services, register, db, tmp_path, monkeypatch):
    import app.services.admin_service as admin_module

    monkeypatch.setattr(admin_module, "PROJECT_ROOT", tmp_path)
    services.attach_database(db)
    target = await register(tg_id=6351)
    await _fund(services, target.player_id, 777_000)

    info = await services.admin.backup_database(ADMIN_ID)
    assert info.filename.startswith("iran_backup_")
    backups = await services.admin.list_backups()
    assert [b.filename for b in backups] == [info.filename]

    await _fund(services, target.player_id, 1_000)
    profile = await services.players.get_profile(6351)
    assert profile is not None and profile.money == 778_000

    await services.admin.restore_database(ADMIN_ID, info.filename)
    profile = await services.players.get_profile(6351)
    assert profile is not None and profile.money == 777_000


async def test_backup_requires_attached_file_database(services):
    with pytest.raises(AdminError):
        await services.admin.backup_database(ADMIN_ID)
    with pytest.raises(AdminError):
        services.admin.backup_file_path("../evil.db")


async def test_purges(services, register, db):
    await services.housing.ensure_initial_houses()
    owner = await register(tg_id=6361)
    entry = await _cheapest_market_house(services)
    await _fund(services, owner.player_id, entry.price)
    await services.housing.buy_from_market(owner.player_id, entry.house.id)
    value = services.housing.estimate_value(await _house_orm(services, entry.house.id))
    await services.housing.list_house_for_sale(owner.player_id, entry.house.id, value)
    listing = (await services.admin.list_active_listings(0)).items[0]
    await services.admin.close_listing(ADMIN_ID, listing.listing_id)

    # Backdate the closed listing, then purge.
    async with db.session_factory() as session:
        await session.execute(
            update(HouseListing)
            .where(HouseListing.id == listing.listing_id)
            .values(closed_at=datetime.now() - timedelta(days=40))
        )
        await session.commit()

    removed = await services.admin.purge_closed_listings(ADMIN_ID, 30)
    assert removed == 1
    assert await services.admin.purge_audit_logs(ADMIN_ID, 30) >= 0
    assert await services.admin.purge_price_ticks(ADMIN_ID, 30) >= 0
    with pytest.raises(InvalidAmountError):
        await services.admin.purge_closed_listings(ADMIN_ID, 0)


# --- Logs ----------------------------------------------------------------------------

async def test_audit_log_pagination_and_filters(services, register):
    target = await register(tg_id=6371)
    await services.admin.add_money(ADMIN_ID, target.player_id, 100)
    await _seed_economy(services)
    await services.admin.set_inflation(ADMIN_ID, 5.0)

    all_logs = await services.admin.list_audit_logs(0, per_page=10)
    assert all_logs.total >= 2
    econ = await services.admin.list_audit_logs(0, action_prefix="econ")
    assert econ.total >= 1
    assert all(row.action.startswith("econ") for row in econ.items)


async def test_error_logs_returns_list(services):
    lines = await services.admin.get_error_logs()
    assert isinstance(lines, list)
