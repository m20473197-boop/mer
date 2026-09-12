"""Registers all Telegram handlers — the single routing map of the bot."""

from __future__ import annotations

import re

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.handlers import (
    admin,
    admin_panel,
    bank,
    business,
    crime,
    divar,
    family,
    housing,
    iran_market,
    job,
    main_menu,
    vehicle,
    realestate,
    start,
)
from app.bot.handlers.errors import error_handler
from app.bot.keyboards import callbacks
from app.core import constants


def register_handlers(application: Application) -> None:
    """Wire all routes.

    Order matters: specific callbacks come first and the unknown-callback
    fallback must be registered last (first match wins inside a group).
    """
    # Public commands
    application.add_handler(CommandHandler("start", start.start_handler))

    # Admin dev commands (protected by ADMIN_IDS inside handlers)
    application.add_handler(CommandHandler("admin_add_xp", admin.admin_add_xp))
    application.add_handler(CommandHandler("admin_remove_xp", admin.admin_remove_xp))
    application.add_handler(CommandHandler("admin_set_level", admin.admin_set_level))
    application.add_handler(CommandHandler("admin_status", admin.admin_status))
    application.add_handler(CommandHandler("admin_xp_history", admin.admin_xp_history))

    # Admin panel: the "پنل" message opens it; one conversation carries every
    # typed admin value (amounts, names, settings). Registered FIRST in
    # group 0 so a pending admin input always wins over the feature text
    # triggers.
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.Regex(f"^{admin_panel.ADMIN_PANEL_TEXT_TRIGGER}$"),
            admin_panel.admin_command,
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    admin_panel.admin_input_entry,
                    pattern=rf"^{callbacks.ADM_IN_PREFIX}",
                )
            ],
            states={
                admin_panel.ADMIN_INPUT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        admin_panel.admin_input_received,
                    ),
                    # Tapping any admin button mid-input cancels the input.
                    CallbackQueryHandler(
                        admin_panel.admin_callback, pattern=r"^adm_"
                    ),
                ],
            },
            fallbacks=[
                # No text fallback: "پنل" is plain TEXT, so mid-conversation
                # it is (correctly) treated as the pending input value.
                CallbackQueryHandler(
                    admin_panel.admin_input_cancel,
                    pattern=rf"^{callbacks.ADM_IN_CANCEL}$",
                ),
            ],
            name="admin_input",
            persistent=False,
            allow_reentry=True,
        )
    )

    # Jobs («خر حمالی») — text messages; old «مشاغل»/«شغل من» still accepted
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(job.JOBS_TEXT_PATTERN), job.jobs_text_handler)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(job.MY_JOB_TEXT_PATTERN), job.my_job_text_handler)
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(job.LEAVE_JOB_TEXT_PATTERN), job.leave_job_text_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(job.APPLY_JOB_TEXT_PATTERN), job.apply_job_text_handler
        )
    )

    # Business System — only the predefined catalog is reachable.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(business.BUSINESS_TEXT_PATTERN),
            business.business_text_handler,
        )
    )

    # 📈 بازار ایران — read-only screens; the scheduler is not a handler.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(iran_market.IRAN_MARKET_TEXT_PATTERN),
            iran_market.iran_market_text_handler,
        )
    )

    # 🧱 دیوار ایران — the input conversation is registered before generic
    # text/callback fallbacks so typed prices/searches stay inside the flow.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(divar.DIVAR_TEXT_PATTERN),
            divar.divar_text_handler,
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    divar.start_search_input,
                    pattern=rf"^{callbacks.DIVAR_SEARCH}$",
                ),
                CallbackQueryHandler(
                    divar.start_price_filter_input,
                    pattern=rf"^{callbacks.DIVAR_FILTER_PRICE}$",
                ),
                CallbackQueryHandler(
                    divar.start_area_filter_input,
                    pattern=rf"^{callbacks.DIVAR_FILTER_AREA}$",
                ),
                CallbackQueryHandler(
                    divar.start_neighborhood_input,
                    pattern=rf"^{callbacks.DIVAR_FILTER_NEIGHBORHOOD}$",
                ),
                CallbackQueryHandler(
                    divar.start_listing_price,
                    pattern=rf"^(?:{callbacks.DIVAR_SELL_HOUSE_PREFIX}|{callbacks.DIVAR_SELL_LAND_PREFIX}|{callbacks.DIVAR_SELL_CAR_PREFIX})\d+$",
                ),
            ],
            states={
                divar.DIVAR_INPUT_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        divar.input_received,
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    divar.cancel_input,
                    pattern=rf"^{callbacks.DIVAR_INPUT_CANCEL}$",
                )
            ],
            name="divar_input",
            persistent=False,
            allow_reentry=True,
        )
    )

    # 🏦 بانک ایران — amounts and transfer confirmation stay in the
    # ConversationHandler; handlers only call BankService, never the database.
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    bank.start_deposit, pattern=rf"^{callbacks.BANK_DEPOSIT}$"
                ),
                CallbackQueryHandler(
                    bank.start_withdrawal, pattern=rf"^{callbacks.BANK_WITHDRAW}$"
                ),
                CallbackQueryHandler(
                    bank.start_transfer, pattern=rf"^{callbacks.BANK_TRANSFER}$"
                ),
            ],
            states={
                bank.BANK_AMOUNT_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        bank.amount_input_received,
                    )
                ],
                bank.BANK_TRANSFER_CARD_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        bank.transfer_card_input_received,
                    )
                ],
                bank.BANK_TRANSFER_RECIPIENT_STATE: [
                    CallbackQueryHandler(
                        bank.transfer_recipient_continue,
                        pattern=rf"^{callbacks.BANK_TRANSFER_RECIPIENT_OK}$",
                    )
                ],
                bank.BANK_TRANSFER_AMOUNT_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        bank.transfer_amount_input_received,
                    )
                ],
                bank.BANK_TRANSFER_CONFIRM_STATE: [
                    CallbackQueryHandler(
                        bank.confirm_transfer,
                        pattern=rf"^{callbacks.BANK_TRANSFER_CONFIRM}$",
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(
                    bank.cancel_bank_input,
                    pattern=rf"^{callbacks.BANK_CANCEL}$",
                )
            ],
            name="iran_bank_input",
            persistent=False,
            allow_reentry=True,
        )
    )

    # 🕳️ خلاف — target replies and laundering amounts are translated here;
    # every rule, cooldown and money mutation remains in CrimeService.
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    crime.start_information,
                    pattern=rf"^{callbacks.CRIME_INFORMATION}$",
                ),
                CallbackQueryHandler(
                    crime.start_bank_hack,
                    pattern=rf"^{callbacks.CRIME_BANK_HACK}$",
                ),
                CallbackQueryHandler(
                    crime.start_laundering,
                    pattern=rf"^{callbacks.CRIME_LAUNDERING}$",
                ),
            ],
            states={
                crime.CRIME_TARGET_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        crime.target_input_received,
                    )
                ],
                crime.CRIME_AMOUNT_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        crime.amount_input_received,
                    )
                ],
            },
            fallbacks=[
                CallbackQueryHandler(
                    crime.cancel_crime_input,
                    pattern=rf"^{callbacks.CRIME_CANCEL}$",
                )
            ],
            name="crime_input",
            persistent=False,
            allow_reentry=True,
        )
    )

    # 🏦 بانک ایران — text entry opens the persistent bank menu. It is
    # registered after the input conversation so pending amounts/cards win.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(bank.BANK_TEXT_PATTERN),
            bank.bank_text_handler,
        )
    )

    # 🕳️ خلاف — شوتی is not exposed by a separate text/main-menu route.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(crime.CRIME_TEXT_PATTERN),
            crime.crime_text_handler,
        )
    )

    # 🚗 نمایشگاه ماشین حاج ممد — fixed catalog, purchase and owned cars.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(vehicle.VEHICLE_TEXT_PATTERN),
            vehicle.vehicle_text_handler,
        )
    )

    # Iran Market purchase input and direct Persian purchase commands.
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    iran_market.start_purchase_input,
                    pattern=rf"^{callbacks.MARKET_BUY_PREFIX}[A-Z_]+$",
                )
            ],
            states={
                iran_market.IRAN_MARKET_INPUT_STATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        iran_market.purchase_input_received,
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    iran_market.cancel_purchase_input,
                    pattern=rf"^{callbacks.MARKET_INPUT_CANCEL}$",
                )
            ],
            name="iran_market_purchase_input",
            persistent=False,
            allow_reentry=True,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(iran_market.MARKET_PURCHASE_PATTERN),
            iran_market.purchase_command_handler,
        )
    )

    # Housing system — text messages («خانه» / «مسکن» open the housing menu)
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.Regex(
                f"^({housing.HOUSING_TEXT_TRIGGER}|{housing.HOUSING_MENU_TEXT_TRIGGER})$"
            ),
            housing.housing_text_handler,
        )
    )

    # Land / Construction / Renovation — text messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{realestate.LANDS_MY_TEXT_TRIGGER}$"),
            realestate.lands_my_text_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{realestate.LANDS_MARKET_TEXT_TRIGGER}$"),
            realestate.lands_market_text_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{realestate.BUILD_TEXT_TRIGGER}$"),
            realestate.build_text_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{realestate.STATUS_TEXT_TRIGGER}$"),
            realestate.status_text_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{realestate.RENOVATE_TEXT_TRIGGER}$"),
            realestate.renovate_text_handler,
        )
    )

    # Marriage and Family system — text commands ONLY (no menus, no buttons).
    # Registered after the admin input conversation on purpose: while an admin
    # has a pending typed value, that conversation must keep winning, and
    # before the unknown-callback fallback (first match wins inside group 0).
    application.add_handler(
        MessageHandler(
            filters.TEXT
            # DOTALL: the optional note after the trigger may span lines.
            & filters.Regex(re.compile(rf"^{constants.MARRIAGE_TRIGGER}(\s+.*)?$", re.DOTALL)),
            family.marriage_text_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.MARRIAGE_ACCEPT_TRIGGER}$"),
            family.accept_marriage_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.MARRIAGE_REJECT_TRIGGER}$"),
            family.reject_marriage_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.MARRIAGE_CANCEL_TRIGGER}$"),
            family.cancel_marriage_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.DIVORCE_TRIGGER}$"),
            family.divorce_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.CHEATING_TRIGGER}$"),
            family.cheating_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.RELATIONSHIP_TRIGGER}$"),
            family.relationship_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.FAMILY_TRIGGER}$"),
            family.family_info_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.CHILDREN_TRIGGER}$"),
            family.children_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.FAMILY_HISTORY_TRIGGER}$"),
            family.family_history_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{constants.FAMILY_HELP_TRIGGER}$"),
            family.family_help_handler,
        )
    )

    # Job callbacks
    application.add_handler(
        CallbackQueryHandler(job.show_jobs_menu, pattern=rf"^{callbacks.JOBS_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(job.show_jobs_list, pattern=rf"^{callbacks.JOBS_LIST}$")
    )
    application.add_handler(
        CallbackQueryHandler(job.show_my_job, pattern=rf"^{callbacks.JOBS_MY_JOB}$")
    )
    application.add_handler(
        CallbackQueryHandler(job.settle_job_callback, pattern=rf"^{callbacks.JOBS_SETTLE}$")
    )
    application.add_handler(
        CallbackQueryHandler(job.leave_job_callback, pattern=rf"^{callbacks.JOBS_LEAVE}$")
    )
    application.add_handler(
        CallbackQueryHandler(job.show_job_history, pattern=rf"^{callbacks.JOBS_HISTORY}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            job.apply_job_callback, pattern=rf"^{callbacks.JOBS_APPLY_PREFIX}\d+$"
        )
    )

    # Business callbacks — all must be registered BEFORE the unknown fallback.
    application.add_handler(
        CallbackQueryHandler(
            business.show_business_menu, pattern=rf"^{callbacks.BUSINESS_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            business.show_business_list, pattern=rf"^{callbacks.BUSINESS_LIST}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            business.show_owned_businesses, pattern=rf"^{callbacks.BUSINESS_MY}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            business.generate_business_income,
            pattern=rf"^{callbacks.BUSINESS_INCOME}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            business.start_business_callback,
            pattern=rf"^{callbacks.BUSINESS_START_PREFIX}[a-z_]+$",
        )
    )

    # 🏦 بانک ایران callbacks — operation entry callbacks are owned by the
    # ConversationHandler above; read-only screens live here.
    application.add_handler(
        CallbackQueryHandler(
            bank.show_bank_menu, pattern=rf"^{callbacks.BANK_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bank.show_bank_balance, pattern=rf"^{callbacks.BANK_BALANCE}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bank.show_bank_card, pattern=rf"^{callbacks.BANK_CARD}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bank.show_bank_history, pattern=rf"^{callbacks.BANK_HISTORY}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bank.show_bank_history_page,
            pattern=rf"^{callbacks.BANK_HISTORY_PAGE_PREFIX}\d+$",
        )
    )

    # 🕳️ خلاف callbacks — all specific routes are before the unknown fallback.
    application.add_handler(
        CallbackQueryHandler(crime.show_crime_menu, pattern=rf"^{callbacks.CRIME_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(crime.show_documents, pattern=rf"^{callbacks.CRIME_DOCUMENTS}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            crime.issue_document,
            pattern=rf"^{callbacks.CRIME_DOCUMENT_PREFIX}[a-z_]+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(crime.show_shoti, pattern=rf"^{callbacks.CRIME_SHOTI}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            crime.start_shoti_vehicle,
            pattern=rf"^{callbacks.CRIME_SHOTI_VEHICLE_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            crime.show_shoti_history,
            pattern=rf"^{callbacks.CRIME_SHOTI_HISTORY}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            crime.show_laundering_history,
            pattern=rf"^{callbacks.CRIME_LAUNDERING_HISTORY}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(crime.show_crime_history, pattern=rf"^{callbacks.CRIME_HISTORY}$")
    )

    # Iran Market callbacks — read stored prices only.
    application.add_handler(
        CallbackQueryHandler(
            iran_market.show_iran_market_menu,
            pattern=rf"^{callbacks.MARKET_MENU}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            iran_market.show_iran_market_asset,
            pattern=rf"^{callbacks.MARKET_ASSET_PREFIX}[A-Z_]+$",
        )
    )

    # 🧱 دیوار ایران callbacks.
    application.add_handler(
        CallbackQueryHandler(divar.show_divar_menu, pattern=rf"^{callbacks.DIVAR_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_categories, pattern=rf"^{callbacks.DIVAR_CATEGORIES}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_category_results,
            pattern=rf"^{callbacks.DIVAR_CATEGORY_PREFIX}(?:house|land|car)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(divar.show_all_results, pattern=rf"^{callbacks.DIVAR_SHOW_ALL}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_page,
            pattern=rf"^{callbacks.DIVAR_PAGE_PREFIX}[A-Za-z0-9]+_\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_listing_detail,
            pattern=rf"^{callbacks.DIVAR_DETAIL_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.buy_listing,
            pattern=rf"^{callbacks.DIVAR_BUY_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_my_listings, pattern=rf"^{callbacks.DIVAR_MY_LISTINGS}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(divar.show_owned_assets, pattern=rf"^{callbacks.DIVAR_CREATE}$")
    )
    application.add_handler(
        CallbackQueryHandler(divar.show_filters, pattern=rf"^{callbacks.DIVAR_FILTERS}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_city_filters,
            pattern=rf"^(?:{callbacks.DIVAR_FILTER_CITY_MENU}|{callbacks.DIVAR_FILTER_CITY_PREFIX}(?:all|\d+))$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.show_filter_category,
            pattern=rf"^{callbacks.DIVAR_FILTER_CATEGORY_PREFIX}(?:house|land|car)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(divar.clear_filters, pattern=rf"^{callbacks.DIVAR_FILTER_CLEAR}$")
    )
    application.add_handler(
        CallbackQueryHandler(divar.apply_filters, pattern=rf"^{callbacks.DIVAR_FILTER_APPLY}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            divar.cancel_listing,
            pattern=rf"^{callbacks.DIVAR_CANCEL_PREFIX}\d+$",
        )
    )

    # 🚗 نمایشگاه ماشین حاج ممد callbacks.
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_vehicle_menu, pattern=rf"^{callbacks.VEHICLE_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_vehicle_catalog, pattern=rf"^{callbacks.VEHICLE_CATALOG}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_vehicle_catalog_page,
            pattern=rf"^{callbacks.VEHICLE_PAGE_PREFIX}\d+$",
        )
    )
    # Execute callback first: its data is a strict model-id plus the server
    # understood confirmation suffix, never a client-supplied price.
    application.add_handler(
        CallbackQueryHandler(
            vehicle.confirm_vehicle_purchase,
            pattern=rf"^{callbacks.VEHICLE_CONFIRM_PREFIX}\d+:ok$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_vehicle_confirmation,
            pattern=rf"^{callbacks.VEHICLE_CONFIRM_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_vehicle_model,
            pattern=rf"^{callbacks.VEHICLE_MODEL_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_my_cars, pattern=rf"^{callbacks.VEHICLE_MY_CARS}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            vehicle.show_owned_vehicle,
            pattern=rf"^{callbacks.VEHICLE_OWNED_PREFIX}\d+$",
        )
    )

    # Housing callbacks — all must be registered BEFORE the unknown fallback.
    application.add_handler(
        CallbackQueryHandler(
            housing.show_housing_menu, pattern=rf"^{callbacks.HOUSING_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(housing.show_my_houses, pattern=rf"^{callbacks.HOUSES_MY}$")
    )
    application.add_handler(
        CallbackQueryHandler(housing.show_market, pattern=rf"^{callbacks.HOUSES_MARKET}$")
    )
    application.add_handler(
        CallbackQueryHandler(housing.show_rentals, pattern=rf"^{callbacks.HOUSES_RENTALS}$")
    )
    application.add_handler(
        CallbackQueryHandler(housing.show_my_rents, pattern=rf"^{callbacks.HOUSES_MY_RENTS}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.show_buy_confirmation,
            pattern=rf"^{callbacks.HOUSE_BUY_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.confirm_buy,
            pattern=rf"^{callbacks.HOUSE_BUY_CONFIRM_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.show_sale_options,
            pattern=rf"^{callbacks.HOUSE_SELL_OPTIONS_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.confirm_sell,
            pattern=rf"^{callbacks.HOUSE_SELL_SET_PREFIX}\d+_\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.cancel_sale,
            pattern=rf"^{callbacks.HOUSE_SELL_CANCEL_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.show_rentout_options,
            pattern=rf"^{callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.confirm_rent_out,
            pattern=rf"^{callbacks.HOUSE_RENT_SET_PREFIX}\d+_\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.cancel_rent,
            pattern=rf"^{callbacks.HOUSE_RENT_CANCEL_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.show_rent_confirmation,
            pattern=rf"^{callbacks.RENT_CONFIRM_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.pay_rent, pattern=rf"^{callbacks.RENT_PAY_PREFIX}\d+$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.end_rent_contract, pattern=rf"^{callbacks.RENT_END_PREFIX}\d+$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            housing.show_house_info, pattern=rf"^{callbacks.HOUSE_INFO_PREFIX}\d+$"
        )
    )

    # Land / Construction / Renovation callbacks — BEFORE the unknown fallback.
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_my_lands, pattern=rf"^{callbacks.RE_LANDS_MY}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_lands_market, pattern=rf"^{callbacks.RE_LANDS_MARKET}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_land_info, pattern=rf"^{callbacks.RE_LAND_INFO_PREFIX}\d+$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_land_buy_confirmation,
            pattern=rf"^{callbacks.RE_LAND_BUY_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.confirm_land_buy,
            pattern=rf"^{callbacks.RE_LAND_BUY_OK_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_build_menu, pattern=rf"^{callbacks.RE_BUILD_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_build_type_picker,
            pattern=rf"^{callbacks.RE_BUILD_LAND_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_build_step,
            pattern=rf"^{callbacks.RE_BUILD_SPEC_PREFIX}\d+_[av](?:_(?:\d+|[mge])){{0,4}}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_construction_confirmation,
            pattern=rf"^{callbacks.RE_BUILD_CONFIRM_PREFIX}"
            rf"\d+_[av_0-9mge]+_P[01]E[01]S[01]$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.confirm_construction,
            pattern=rf"^{callbacks.RE_BUILD_EXEC_PREFIX}"
            rf"\d+_[av_0-9mge]+_P[01]E[01]S[01]$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.cancel_construction,
            pattern=rf"^{callbacks.RE_BUILD_CANCEL_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_status, pattern=rf"^{callbacks.RE_STATUS}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_renov_menu, pattern=rf"^{callbacks.RE_RENOV_MENU}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_renovation_options,
            pattern=rf"^{callbacks.RE_RENOV_OPTS_PREFIX}\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.show_renovation_confirmation,
            pattern=rf"^{callbacks.RE_RENOV_CONFIRM_PREFIX}\d+_(?:q|k|ba|r|p|e|s|m)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            realestate.confirm_renovation,
            pattern=rf"^{callbacks.RE_RENOV_OK_PREFIX}\d+_(?:q|k|ba|r|p|e|s|m)$",
        )
    )

    # Admin panel router — BEFORE the unknown fallback.
    application.add_handler(
        CallbackQueryHandler(admin_panel.admin_callback, pattern=r"^adm_")
    )

    # Main menu callbacks
    application.add_handler(
        CallbackQueryHandler(main_menu.show_profile, pattern=rf"^{callbacks.PROFILE}$")
    )
    application.add_handler(
        CallbackQueryHandler(main_menu.show_status, pattern=rf"^{callbacks.STATUS}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            main_menu.back_to_main, pattern=rf"^{callbacks.BACK_TO_MAIN}$"
        )
    )
    application.add_handler(CallbackQueryHandler(main_menu.unknown_callback))

    application.add_error_handler(error_handler)


__all__ = ["register_handlers"]
