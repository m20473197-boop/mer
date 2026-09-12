"""Callback data identifiers.

Single source of truth for inline-button callback values. Adding a future
screen means adding one constant here, one keyboard builder and one handler
— nothing else in the codebase changes.
"""

PROFILE: str = "profile"
STATUS: str = "status"
BACK_TO_MAIN: str = "back_main"

# Job system
JOBS_MENU: str = "jobs_menu"
JOBS_LIST: str = "jobs_list"
JOBS_MY_JOB: str = "jobs_my_job"
JOBS_SETTLE: str = "jobs_settle"
JOBS_LEAVE: str = "jobs_leave"
JOBS_APPLY_PREFIX: str = "jobs_apply_"  # + job_id
JOBS_HISTORY: str = "jobs_history"

# Business System — only predefined catalog keys may follow BUSINESS_START_PREFIX
BUSINESS_MENU: str = "business_menu"
BUSINESS_LIST: str = "business_list"
BUSINESS_MY: str = "business_my"
BUSINESS_INCOME: str = "business_income"
BUSINESS_START_PREFIX: str = "business_start_"

# 📈 بازار ایران — the four fixed asset detail screens
MARKET_MENU: str = "iran_market_menu"
MARKET_ASSET_PREFIX: str = "iran_market_asset_"

# 🧱 دیوار ایران — state stays server-side; callbacks carry only short ids.
DIVAR_MENU: str = "divar_menu"
DIVAR_CATEGORIES: str = "divar_categories"
DIVAR_SEARCH: str = "divar_search"
DIVAR_FILTERS: str = "divar_filters"
DIVAR_MY_LISTINGS: str = "divar_my_listings"
DIVAR_CREATE: str = "divar_create"
DIVAR_SHOW_ALL: str = "divar_all"
DIVAR_CATEGORY_PREFIX: str = "divar_category_"
DIVAR_DETAIL_PREFIX: str = "divar_detail_"
DIVAR_BUY_PREFIX: str = "divar_buy_"
DIVAR_PAGE_PREFIX: str = "divar_page_"
DIVAR_CANCEL_PREFIX: str = "divar_cancel_"
DIVAR_FILTER_CATEGORY_PREFIX: str = "divar_filter_category_"
DIVAR_FILTER_CITY_MENU: str = "divar_filter_city_menu"
DIVAR_FILTER_CITY_PREFIX: str = "divar_filter_city_"
DIVAR_FILTER_PRICE: str = "divar_filter_price"
DIVAR_FILTER_AREA: str = "divar_filter_area"
DIVAR_FILTER_NEIGHBORHOOD: str = "divar_filter_neighborhood"
DIVAR_FILTER_CLEAR: str = "divar_filter_clear"
DIVAR_FILTER_APPLY: str = "divar_filter_apply"
DIVAR_INPUT_CANCEL: str = "divar_input_cancel"
DIVAR_SELL_HOUSE_PREFIX: str = "divar_sell_house_"
DIVAR_SELL_LAND_PREFIX: str = "divar_sell_land_"

# 🚗 نمایشگاه ماشین حاج ممد — model/ownership ids are validated by VehicleService.
VEHICLE_MENU: str = "vehicle_menu"
VEHICLE_CATALOG: str = "vehicle_catalog"
VEHICLE_MY_CARS: str = "vehicle_my_cars"
VEHICLE_PAGE_PREFIX: str = "vehicle_page_"
VEHICLE_MODEL_PREFIX: str = "vehicle_model_"
VEHICLE_CONFIRM_PREFIX: str = "vehicle_confirm_"
VEHICLE_OWNED_PREFIX: str = "vehicle_owned_"

# Housing / Real-estate system
HOUSING_MENU: str = "h_menu"
HOUSES_MY: str = "h_my"                    # my houses / assets
HOUSES_MARKET: str = "h_mkt"               # houses available for purchase
HOUSES_RENTALS: str = "h_rents"            # houses available for rent
HOUSES_MY_RENTS: str = "h_myrents"         # my rental contracts (as tenant)
HOUSE_INFO_PREFIX: str = "h_info_"         # + house_id
HOUSE_BUY_PREFIX: str = "h_buy_"           # + house_id (confirmation screen)
HOUSE_BUY_CONFIRM_PREFIX: str = "h_buyok_"  # + house_id (executes purchase)
HOUSE_SELL_OPTIONS_PREFIX: str = "h_sellopt_"  # + house_id (price presets)
HOUSE_SELL_SET_PREFIX: str = "h_sellset_"  # + house_id + _ + per_mille
HOUSE_SELL_CANCEL_PREFIX: str = "h_sellcancel_"  # + house_id
HOUSE_RENTOUT_OPTIONS_PREFIX: str = "h_rentopt_"  # + house_id (deposit presets)
HOUSE_RENT_SET_PREFIX: str = "h_rentset_"  # + house_id + _ + deposit_percent
HOUSE_RENT_CANCEL_PREFIX: str = "h_rentcancel_"  # + house_id
RENT_CONFIRM_PREFIX: str = "h_rentok_"     # + house_id (executes renting)
RENT_PAY_PREFIX: str = "h_rentpay_"        # + contract_id
RENT_END_PREFIX: str = "h_rentend_"        # + contract_id

# Land / Construction / Renovation system
RE_LANDS_MY: str = "re_lands_my"           # زمین‌های من
RE_LANDS_MARKET: str = "re_lands_mkt"      # خرید زمین (list)
RE_LAND_INFO_PREFIX: str = "re_li_"        # + land_id (اطلاعات ملک)
RE_LAND_BUY_PREFIX: str = "re_lb_"         # + land_id (buy confirmation)
RE_LAND_BUY_OK_PREFIX: str = "re_lbo_"     # + land_id (executes purchase)
RE_BUILD_MENU: str = "re_build"            # ساخت خانه (pick a vacant land)
RE_BUILD_LAND_PREFIX: str = "re_b_"        # + land_id (building type picker)
RE_BUILD_SPEC_PREFIX: str = "re_bs_"       # + blueprint steps (see handler)
RE_BUILD_CONFIRM_PREFIX: str = "re_bc_"    # + full blueprint (confirm screen)
RE_BUILD_EXEC_PREFIX: str = "re_bx_"       # + full blueprint (starts project)
RE_BUILD_CANCEL_PREFIX: str = "re_bcx_"    # + project_id (cancel construction)
RE_STATUS: str = "re_status"               # وضعیت ساخت
RE_RENOV_MENU: str = "re_renov"            # بازسازی خانه (pick a house)
RE_RENOV_OPTS_PREFIX: str = "re_ro_"       # + house_id (renovation options)
RE_RENOV_CONFIRM_PREFIX: str = "re_rc_"    # + house_id + type (confirm)
RE_RENOV_OK_PREFIX: str = "re_rk_"         # + house_id + type (starts project)

# Admin panel — every admin screen lives under the ``adm_`` namespace.
ADM_MENU: str = "adm_menu"
ADM_DASH: str = "adm_dash"
# Users
ADM_UL_PREFIX: str = "adm_ul_"             # + page (user list)
ADM_U_PREFIX: str = "adm_u_"               # + player_id (user detail)
ADM_UTX_PREFIX: str = "adm_utx_"           # + player_id (transactions)
ADM_UPROP_PREFIX: str = "adm_upr_"         # + player_id (houses + lands)
ADM_BAN_PREFIX: str = "adm_ban_"           # + player_id (ban confirm)
ADM_BANOK_PREFIX: str = "adm_banok_"       # + player_id (execute ban)
ADM_UNBAN_PREFIX: str = "adm_unban_"       # + player_id (execute unban)
# Economy
ADM_ECON: str = "adm_econ"
ADM_ASSET_PREFIX: str = "adm_asset_"       # + asset code
ADM_EVENT_PREFIX: str = "adm_event_"       # + event id
ADM_EVENT_END_PREFIX: str = "adm_eve_"     # + event id (end early)
ADM_CRISIS: str = "adm_crisis"             # one-tap crisis confirm screen
ADM_CRISIS_OK: str = "adm_crisis_ok"       # execute crisis
# Real estate
ADM_ESTATE: str = "adm_estate"
ADM_HL_PREFIX: str = "adm_hl_"             # + page (house list)
ADM_HD_PREFIX: str = "adm_hd_"             # + house_id (house detail)
ADM_HE_PREFIX: str = "adm_he_"             # + house_id (house edit menu)
ADM_HT_PREFIX: str = "adm_ht_"             # + house_id + _ + p/e/s (facility toggle)
ADM_HK_PREFIX: str = "adm_hk_"             # + house_id + _ + 0/1/2 (kitchen)
ADM_HQ_PREFIX: str = "adm_hq_"             # + house_id + _ + 0..3 (quality)
ADM_NL_PREFIX: str = "adm_nl_"             # + page (land list)
ADM_ND_PREFIX: str = "adm_nd_"             # + land_id (land detail)
ADM_NE_PREFIX: str = "adm_ne_"             # + land_id (land edit menu)
ADM_LI_PREFIX: str = "adm_li_"             # + page (active listings)
ADM_LICLOSE_PREFIX: str = "adm_lic_"       # + listing_id (close)
ADM_C_PREFIX: str = "adm_c_"               # + page (rental contracts)
ADM_CD_PREFIX: str = "adm_cd_"             # + contract_id (contract detail)
ADM_CTERM_PREFIX: str = "adm_ct_"          # + contract_id (terminate)
# Jobs
ADM_JOBS: str = "adm_jobs"
ADM_JOB_PREFIX: str = "adm_job_"           # + job_id (job detail)
ADM_JOB_TOGGLE_PREFIX: str = "adm_jt_"     # + job_id (activate/deactivate)
ADM_W_PREFIX: str = "adm_w_"               # + page (active workers)
# Trading
ADM_TRADE: str = "adm_trade"
ADM_TS_PREFIX: str = "adm_ts_"             # + page (recent sales)
ADM_TA: str = "adm_ta"                     # market activity feed
# Bot settings
ADM_SETTINGS: str = "adm_set"
ADM_TG_PREFIX: str = "adm_tg_"             # + feature name (toggle on/off)
# Database tools
ADM_DB: str = "adm_db"
ADM_DB_STATS: str = "adm_dbstats"
ADM_DB_BACKUP: str = "adm_dbbackup"
ADM_DB_BACKUPS: str = "adm_dbrs"           # backup list (restore picker)
ADM_DB_RESTORE_PREFIX: str = "adm_dbr_"    # + filename (restore confirm)
ADM_DB_RESTORE_OK_PREFIX: str = "adm_dbo_"  # + filename (execute restore)
ADM_DB_CLEAN: str = "adm_dbclean"
# Logs
ADM_LOGS: str = "adm_logs"
ADM_LOG_PREFIX: str = "adm_log_"           # + category + _ + page
# Free-text input flows (ConversationHandler entry — see admin_panel)
ADM_IN_PREFIX: str = "adm_in_"             # + code[_target[_extra]]
ADM_IN_CANCEL: str = "adm_cancel"
