from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.runtime_config import (
    build_postgres_url,
    build_sqlite_url,
    database_url_hint,
    effective_database_url,
    env_export_path,
    read_runtime_config,
    write_runtime_database_url,
)
from app.db.session import check_db_connection, get_db, init_db, make_session, reset_engine
from app.schemas import (
    CiscoSetupRequest,
    CiscoSetupResponse,
    DatabaseSetupRequest,
    DatabaseSetupResponse,
    PostgresBootstrapRequest,
    PostgresBootstrapResponse,
    PostgresDefaultsResponse,
    SetupStatusResponse,
)
from app.services.cisco_api_client import CiscoApiClient, CiscoApiError
from app.services.credential_store import CredentialStore

router = APIRouter(prefix="/setup", tags=["Setup"])


_POSTGRES_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,62}$")


def _clean_postgres_identifier(value: str, *, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not _POSTGRES_IDENTIFIER_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PostgreSQL {field_name}. Use 1-63 letters, numbers, underscores, or hyphens; it must not start with a hyphen.",
        )
    return cleaned


def _quote_pg_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _docker_postgres_defaults() -> dict[str, str | int]:
    return {
        "host": "postgres",
        "port": 5432,
        "host_port": int(os.getenv("EOX_POSTGRES_HOST_PORT", "5433")),
        "database": os.getenv("EOX_POSTGRES_DB", "eox_cache"),
        "username": os.getenv("EOX_POSTGRES_USER", "eox_user"),
        "password": os.getenv("EOX_POSTGRES_PASSWORD", "eox_password"),
    }


def _create_postgres_database_if_needed(request: PostgresBootstrapRequest) -> tuple[bool, bool, str | None]:
    database = _clean_postgres_identifier(request.database, field_name="database name")
    maintenance_database = _clean_postgres_identifier(request.maintenance_database, field_name="maintenance database name")
    maintenance_url = build_postgres_url(
        host=request.host,
        port=request.port,
        database=maintenance_database,
        username=request.username,
        password=request.password,
    )
    engine = create_engine(maintenance_url, future=True, pool_pre_ping=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = bool(connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :database"), {"database": database}).scalar())
            if exists:
                return False, True, None
            if request.test_only or not request.create_database:
                return False, False, None
            connection.execute(text(f"CREATE DATABASE {_quote_pg_identifier(database)}"))
            return True, False, None
    except Exception as exc:
        return False, False, str(exc)
    finally:
        engine.dispose()


def _sqlite_setup_response(*, test_only: bool = False) -> DatabaseSetupResponse:
    database_url = build_sqlite_url(path=None)
    ok, error = check_db_connection(database_url)
    if not ok:
        return DatabaseSetupResponse(
            ok=False,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(database_url),
            message=f"SQLite setup failed: {error}",
            env_file=None,
        )
    if test_only:
        return DatabaseSetupResponse(
            ok=True,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(database_url),
            message="SQLite connection test passed",
            env_file=None,
        )
    runtime = write_runtime_database_url(database_url, write_env_file=True)
    reset_engine(database_url)
    init_db(database_url)
    return DatabaseSetupResponse(
        ok=True,
        tested=True,
        saved=True,
        initialized=True,
        database_url_hint=database_url_hint(runtime.database_url),
        message="SQLite local database is ready",
        env_file=str(env_export_path()),
    )


@router.get("/status", response_model=SetupStatusResponse)
def setup_status() -> SetupStatusResponse:
    runtime = read_runtime_config()
    db_ready, db_error = check_db_connection()
    if not db_ready:
        return SetupStatusResponse(
            database_ready=False,
            database_error=db_error,
            database_url_hint=database_url_hint(),
            database_config_source=runtime.database_source,
            cisco_credentials_configured=False,
            api_base_url="",
            token_url="",
            has_cached_token=False,
        )

    with make_session() as db:
        try:
            store = CredentialStore(db)
            status = store.status()
        except Exception as exc:
            return SetupStatusResponse(
                database_ready=False,
                database_error=str(exc),
                database_url_hint=database_url_hint(),
                database_config_source=runtime.database_source,
                cisco_credentials_configured=False,
                api_base_url="",
                token_url="",
                has_cached_token=False,
            )
    return SetupStatusResponse(
        database_ready=db_ready,
        database_error=db_error,
        database_url_hint=database_url_hint(),
        database_config_source=runtime.database_source,
        cisco_credentials_configured=bool(status["configured"]),
        client_id_hint=status["client_id_hint"],
        api_base_url=str(status["api_base_url"]),
        token_url=str(status["token_url"]),
        has_cached_token=bool(status["has_cached_token"]),
    )


@router.post("/database/use-sqlite", response_model=DatabaseSetupResponse)
def configure_sqlite_default() -> DatabaseSetupResponse:
    return _sqlite_setup_response(test_only=False)




@router.get("/database/postgres-defaults", response_model=PostgresDefaultsResponse)
def postgres_defaults() -> PostgresDefaultsResponse:
    defaults = _docker_postgres_defaults()
    internal_url = build_postgres_url(
        host=str(defaults["host"]),
        port=int(defaults["port"]),
        database=str(defaults["database"]),
        username=str(defaults["username"]),
        password=str(defaults["password"]),
    )
    host_url = build_postgres_url(
        host="127.0.0.1",
        port=int(defaults["host_port"]),
        database=str(defaults["database"]),
        username=str(defaults["username"]),
        password=str(defaults["password"]),
    )
    return PostgresDefaultsResponse(
        host=str(defaults["host"]),
        port=int(defaults["port"]),
        host_port=int(defaults["host_port"]),
        database=str(defaults["database"]),
        username=str(defaults["username"]),
        password=str(defaults["password"]),
        internal_url_hint=database_url_hint(internal_url),
        host_url_hint=database_url_hint(host_url),
        notes=[
            "Use postgres:5432 from the API container and GUI setup.",
            "Use 127.0.0.1:5433 only from the server shell or external database tools.",
            "Click Save + Create Tables to initialize the app schema without running shell commands.",
        ],
    )


@router.post("/database/use-docker-postgres", response_model=PostgresBootstrapResponse)
def configure_docker_postgres_default() -> PostgresBootstrapResponse:
    defaults = _docker_postgres_defaults()
    request = PostgresBootstrapRequest(
        host=str(defaults["host"]),
        port=int(defaults["port"]),
        database=str(defaults["database"]),
        username=str(defaults["username"]),
        password=str(defaults["password"]),
        create_database=True,
        initialize_tables=True,
        save_as_active=True,
        write_env_file=True,
        test_only=False,
    )
    return bootstrap_postgres_database(request)


@router.post("/database/postgres/bootstrap", response_model=PostgresBootstrapResponse)
def bootstrap_postgres_database(request: PostgresBootstrapRequest) -> PostgresBootstrapResponse:
    database_name = _clean_postgres_identifier(request.database, field_name="database name")
    target_url = build_postgres_url(
        host=request.host,
        port=request.port,
        database=database_name,
        username=request.username,
        password=request.password,
    )
    created, existed, create_error = _create_postgres_database_if_needed(request)
    if create_error:
        return PostgresBootstrapResponse(
            ok=False,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(target_url),
            message=f"PostgreSQL server/database setup failed: {create_error}",
            env_file=None,
            database_created=False,
            database_existed=False,
            tables_initialized=False,
            active_database_saved=False,
            database_name=database_name,
        )

    if request.test_only and not existed and not created:
        return PostgresBootstrapResponse(
            ok=True,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(target_url),
            message="PostgreSQL server connection passed. Database does not exist yet; click Save + Create Tables to create it.",
            env_file=None,
            database_created=False,
            database_existed=False,
            tables_initialized=False,
            active_database_saved=False,
            database_name=database_name,
        )

    ok, error = check_db_connection(target_url)
    if not ok:
        return PostgresBootstrapResponse(
            ok=False,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(target_url),
            message=f"PostgreSQL database connection failed: {error}",
            env_file=None,
            database_created=created,
            database_existed=existed,
            tables_initialized=False,
            active_database_saved=False,
            database_name=database_name,
        )

    if request.test_only:
        return PostgresBootstrapResponse(
            ok=True,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(target_url),
            message="PostgreSQL database connection test passed",
            env_file=None,
            database_created=created,
            database_existed=existed or created,
            tables_initialized=False,
            active_database_saved=False,
            database_name=database_name,
        )

    tables_initialized = False
    if request.initialize_tables:
        init_db(target_url)
        tables_initialized = True

    runtime = None
    active_saved = False
    if request.save_as_active:
        runtime = write_runtime_database_url(target_url, write_env_file=request.write_env_file)
        reset_engine(target_url)
        active_saved = True

    message_parts = ["PostgreSQL ready"]
    if created:
        message_parts.append("database created")
    elif existed:
        message_parts.append("database already existed")
    if tables_initialized:
        message_parts.append("tables initialized")
    if active_saved:
        message_parts.append("saved as active app database")

    return PostgresBootstrapResponse(
        ok=True,
        tested=True,
        saved=active_saved,
        initialized=tables_initialized,
        database_url_hint=database_url_hint(runtime.database_url if runtime else target_url),
        message="; ".join(message_parts),
        env_file=str(env_export_path()) if active_saved and request.write_env_file else None,
        database_created=created,
        database_existed=existed or created,
        tables_initialized=tables_initialized,
        active_database_saved=active_saved,
        database_name=database_name,
    )


@router.post("/database/configure", response_model=DatabaseSetupResponse)
def configure_database(request: DatabaseSetupRequest) -> DatabaseSetupResponse:
    if request.database_type == "sqlite":
        database_url = build_sqlite_url(path=request.sqlite_path)
    elif request.database_type == "url" or request.database_url:
        if not request.database_url:
            raise HTTPException(status_code=400, detail="Database URL is required for Advanced URL mode")
        database_url = request.database_url
    else:
        database_url = build_postgres_url(
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password,
        )
    ok, error = check_db_connection(database_url)
    if not ok:
        return DatabaseSetupResponse(
            ok=False,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(database_url),
            message=f"Database connection failed: {error}",
            env_file=None,
        )
    if request.test_only:
        return DatabaseSetupResponse(
            ok=True,
            tested=True,
            saved=False,
            initialized=False,
            database_url_hint=database_url_hint(database_url),
            message="Database connection test passed",
            env_file=None,
        )

    runtime = write_runtime_database_url(database_url, write_env_file=request.write_env_file)
    reset_engine(database_url)
    initialized = False
    if request.initialize_after_save:
        init_db(database_url)
        initialized = True
    return DatabaseSetupResponse(
        ok=True,
        tested=True,
        saved=True,
        initialized=initialized,
        database_url_hint=database_url_hint(runtime.database_url),
        message="Database setup saved" + (" and tables initialized" if initialized else ""),
        env_file=str(env_export_path()) if request.write_env_file else None,
    )


@router.post("/database/initialize")
def initialize_database() -> dict[str, str]:
    try:
        init_db()
        return {"status": "ok", "message": "Database tables are ready", "database_url": database_url_hint(effective_database_url())}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database initialization failed: {exc}") from exc


@router.post("/cisco", response_model=CiscoSetupResponse)
def configure_cisco(request: CiscoSetupRequest, db: Session = Depends(get_db)) -> CiscoSetupResponse:
    if not any([request.client_id, request.client_secret, request.access_token, request.api_base_url, request.token_url]):
        raise HTTPException(status_code=400, detail="Provide at least one Cisco setup value to save")

    store = CredentialStore(db)
    store.setup_cisco_credentials(
        client_id=request.client_id,
        client_secret=request.client_secret,
        access_token=request.access_token,
        token_expires_in_seconds=request.token_expires_in_seconds,
        api_base_url=request.api_base_url,
        token_url=request.token_url,
        grant_type=request.grant_type,
    )

    token_cached = bool(store.get_valid_access_token())
    if request.test_connection:
        try:
            CiscoApiClient(db).test_connection()
            token_cached = True
            return CiscoSetupResponse(
                configured=True,
                tested=True,
                message="Cisco API credentials saved and token test passed",
                token_cached=token_cached,
            )
        except CiscoApiError as exc:
            raise HTTPException(status_code=400, detail=f"Saved credentials, but Cisco token test failed: {exc}") from exc

    return CiscoSetupResponse(
        configured=store.cisco_credentials_configured(),
        tested=False,
        message="Cisco API setup saved",
        token_cached=token_cached,
    )


@router.post("/demo-data")
def load_demo_data(db: Session = Depends(get_db)):
    from app.db.models import ProductEox, EoxAnnouncement, EoxAnnouncementTable, EoxAffectedProduct, PidCatalog, SystemEvent

    ready, error = check_db_connection()
    if not ready:
        raise HTTPException(status_code=503, detail=f"Database is not initialized or connected: {error}")

    try:
        # Delete previous demo seeded data to prevent duplicates
        db.query(EoxAffectedProduct).filter(EoxAffectedProduct.source == "demo_seed").delete()
        db.query(ProductEox).filter(ProductEox.source == "demo_seed").delete()
        db.query(EoxAnnouncementTable).filter(EoxAnnouncementTable.heading.like("%EOL Milestones%") | EoxAnnouncementTable.heading.like("%Product Part Numbers Affected%")).delete()
        db.query(EoxAnnouncement).filter(EoxAnnouncement.source == "demo_seed").delete()
        db.query(PidCatalog).filter(PidCatalog.source == "demo_seed").delete()
        db.query(SystemEvent).filter(SystemEvent.source == "demo_seed").delete()
        db.commit()

        # Add mock EoxAnnouncements
        ann1 = EoxAnnouncement(
            announcement_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-9300-series-switches/eos-eol-notice-c51-744321.html",
            announcement_name="End-of-Sale and End-of-Life Announcement for the Cisco Catalyst 9300 Series Switches",
            title="End-of-Sale and End-of-Life Announcement for the Cisco Catalyst 9300 Series Switches",
            technology="Switches",
            series="Cisco Catalyst 9300 Series Switches",
            source="demo_seed",
            payload={},
            raw_response={}
        )
        ann2 = EoxAnnouncement(
            announcement_url="https://www.cisco.com/c/en/us/products/collateral/wireless/5520-wireless-controller/eos-eol-notice-c51-743285.html",
            announcement_name="End-of-Sale and End-of-Life Announcement for the Cisco 5520 Wireless Controller",
            title="End-of-Sale and End-of-Life Announcement for the Cisco 5520 Wireless Controller",
            technology="Wireless",
            series="Cisco 5500 Series Wireless Controllers",
            source="demo_seed",
            payload={},
            raw_response={}
        )
        ann3 = EoxAnnouncement(
            announcement_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-2960-x-series-switches/eos-eol-notice-c51-743012.html",
            announcement_name="End-of-Sale and End-of-Life Announcement for the Cisco Catalyst 2960-X Series Switches",
            title="End-of-Sale and End-of-Life Announcement for the Cisco Catalyst 2960-X Series Switches",
            technology="Switches",
            series="Cisco Catalyst 2960-X Series Switches",
            source="demo_seed",
            payload={},
            raw_response={}
        )
        db.add_all([ann1, ann2, ann3])
        db.commit()
        db.refresh(ann1)
        db.refresh(ann2)
        db.refresh(ann3)

        # Add EoxAnnouncementTables
        t1_ann1 = EoxAnnouncementTable(
            announcement_id=ann1.id,
            table_index=1,
            heading="Table 1. EOL Milestones",
            headers=["Milestone", "Definition", "Date"],
            rows=[
                {"Milestone": "End-of-Life Announcement Date", "Definition": "The date the document that announces...", "Date": "October 31, 2023"},
                {"Milestone": "End-of-Sale Date", "Definition": "The last date to order...", "Date": "October 31, 2024"},
                {"Milestone": "Last Ship Date", "Definition": "The last-possible ship date...", "Date": "January 31, 2025"},
                {"Milestone": "End of SW Maintenance Releases Date", "Definition": "The last date that Cisco Engineering...", "Date": "October 31, 2025"},
                {"Milestone": "End of Vulnerability/Security Support", "Definition": "The last date that Cisco Engineering...", "Date": "October 31, 2027"},
                {"Milestone": "Last Date of Support", "Definition": "The last date to receive applicable service...", "Date": "October 31, 2029"}
            ],
            raw_table={}
        )
        t2_ann1 = EoxAnnouncementTable(
            announcement_id=ann1.id,
            table_index=2,
            heading="Table 2. Product Part Numbers Affected by This Announcement",
            headers=["End-of-Sale Product Part Number", "Product Description", "Replacement Product Part Number", "Replacement Product Description"],
            rows=[
                {"End-of-Sale Product Part Number": "C9300-24T-A", "Product Description": "Catalyst 9300 24-port data, Network Advantage", "Replacement Product Part Number": "C9300X-24T-A", "Replacement Product Description": "Catalyst 9300X 24-port data, Network Advantage"},
                {"End-of-Sale Product Part Number": "C9300-24T-E", "Product Description": "Catalyst 9300 24-port data, Network Essentials", "Replacement Product Part Number": "C9300X-24T-E", "Replacement Product Description": "Catalyst 9300X 24-port data, Network Essentials"},
                {"End-of-Sale Product Part Number": "C9300-24T", "Product Description": "Catalyst 9300 24-port data only", "Replacement Product Part Number": "C9300X-24T", "Replacement Product Description": "Catalyst 9300X 24-port data only"}
            ],
            raw_table={}
        )
        t1_ann2 = EoxAnnouncementTable(
            announcement_id=ann2.id,
            table_index=1,
            heading="Table 1. EOL Milestones",
            headers=["Milestone", "Definition", "Date"],
            rows=[
                {"Milestone": "End-of-Life Announcement Date", "Definition": "The date the document that announces...", "Date": "February 1, 2020"},
                {"Milestone": "End-of-Sale Date", "Definition": "The last date to order...", "Date": "February 1, 2021"},
                {"Milestone": "Last Ship Date", "Definition": "The last-possible ship date...", "Date": "May 1, 2021"},
                {"Milestone": "End of SW Maintenance Releases Date", "Definition": "The last date that Cisco Engineering...", "Date": "February 1, 2022"},
                {"Milestone": "End of Vulnerability/Security Support", "Definition": "The last date that Cisco Engineering...", "Date": "February 1, 2024"},
                {"Milestone": "Last Date of Support", "Definition": "The last date to receive applicable service...", "Date": "February 1, 2026"}
            ],
            raw_table={}
        )
        t2_ann2 = EoxAnnouncementTable(
            announcement_id=ann2.id,
            table_index=2,
            heading="Table 2. Product Part Numbers Affected by This Announcement",
            headers=["End-of-Sale Product Part Number", "Product Description", "Replacement Product Part Number", "Replacement Product Description"],
            rows=[
                {"End-of-Sale Product Part Number": "AIR-CT5520-K9", "Product Description": "Cisco 5520 Wireless Controller", "Replacement Product Part Number": "C9800-40-K9", "Replacement Product Description": "Cisco Catalyst 9800-40 Wireless Controller"}
            ],
            raw_table={}
        )
        t1_ann3 = EoxAnnouncementTable(
            announcement_id=ann3.id,
            table_index=1,
            heading="Table 1. EOL Milestones",
            headers=["Milestone", "Definition", "Date"],
            rows=[
                {"Milestone": "End-of-Life Announcement Date", "Definition": "The date the document that announces...", "Date": "October 31, 2020"},
                {"Milestone": "End-of-Sale Date", "Definition": "The last date to order...", "Date": "October 31, 2021"},
                {"Milestone": "Last Ship Date", "Definition": "The last-possible ship date...", "Date": "January 31, 2022"},
                {"Milestone": "End of SW Maintenance Releases Date", "Definition": "The last date that Cisco Engineering...", "Date": "October 31, 2022"},
                {"Milestone": "End of Vulnerability/Security Support", "Definition": "The last date that Cisco Engineering...", "Date": "October 31, 2024"},
                {"Milestone": "Last Date of Support", "Definition": "The last date to receive applicable service...", "Date": "October 31, 2026"}
            ],
            raw_table={}
        )
        t2_ann3 = EoxAnnouncementTable(
            announcement_id=ann3.id,
            table_index=2,
            heading="Table 2. Product Part Numbers Affected by This Announcement",
            headers=["End-of-Sale Product Part Number", "Product Description", "Replacement Product Part Number", "Replacement Product Description"],
            rows=[
                {"End-of-Sale Product Part Number": "WS-C2960X-48FPD-L", "Product Description": "Catalyst 2960-X 48 GigE PoE 740W, 2 x 10G SFP+, LAN Base", "Replacement Product Part Number": "C9200L-48P-4X-E", "Replacement Product Description": "Catalyst 9200L 48-port PoE+, 4 x 10G SFP+, Network Essentials"}
            ],
            raw_table={}
        )
        db.add_all([t1_ann1, t2_ann1, t1_ann2, t2_ann2, t1_ann3, t2_ann3])
        db.commit()

        # Add ProductEox entries
        p1 = ProductEox(
            pid="C9300-24T",
            normalized_pid="C9300-24T",
            technology="Switches",
            product_name="Catalyst 9300 24-Port Data Only",
            series="Cisco Catalyst 9300 Series Switches",
            status="End of Sale",
            source="demo_seed",
            end_of_sale_date="2024-10-31",
            last_date_of_support="2029-10-31",
            end_of_sw_maintenance="2025-10-31",
            end_of_security_support="2027-10-31",
            end_of_routine_failure_analysis="2025-10-31",
            eox_announcement_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-9300-series-switches/eos-eol-notice-c51-744321.html",
            product_bulletin_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-9300-series-switches/eos-eol-notice-c51-744321.html",
            payload={},
            raw_response={}
        )
        p2 = ProductEox(
            pid="AIR-CT5520-K9",
            normalized_pid="AIR-CT5520-K9",
            technology="Wireless",
            product_name="Cisco 5520 Wireless Controller",
            series="Cisco 5500 Series Wireless Controllers",
            status="End of Support",
            source="demo_seed",
            end_of_sale_date="2021-02-01",
            last_date_of_support="2026-02-01",
            end_of_sw_maintenance="2022-02-01",
            end_of_security_support="2024-02-01",
            end_of_routine_failure_analysis="2022-02-01",
            eox_announcement_url="https://www.cisco.com/c/en/us/products/collateral/wireless/5520-wireless-controller/eos-eol-notice-c51-743285.html",
            product_bulletin_url="https://www.cisco.com/c/en/us/products/collateral/wireless/5520-wireless-controller/eos-eol-notice-c51-743285.html",
            payload={},
            raw_response={}
        )
        p3 = ProductEox(
            pid="WS-C2960X-48FPD-L",
            normalized_pid="WS-C2960X-48FPD-L",
            technology="Switches",
            product_name="Catalyst 2960-X 48 GigE PoE 740W, 2 x 10G SFP+, LAN Base",
            series="Cisco Catalyst 2960-X Series Switches",
            status="End of Sale",
            source="demo_seed",
            end_of_sale_date="2021-10-31",
            last_date_of_support="2026-10-31",
            end_of_sw_maintenance="2022-10-31",
            end_of_security_support="2024-10-31",
            end_of_routine_failure_analysis="2022-10-31",
            eox_announcement_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-2960-x-series-switches/eos-eol-notice-c51-743012.html",
            product_bulletin_url="https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-2960-x-series-switches/eos-eol-notice-c51-743012.html",
            payload={},
            raw_response={}
        )
        p4 = ProductEox(
            pid="ISR4331/K9",
            normalized_pid="ISR4331/K9",
            technology="Routers",
            product_name="Cisco ISR 4331 (3GE, 2-NIM, 1-SM, 4G FLASH, 4G DRAM, IPB)",
            series="Cisco 4000 Series Integrated Services Routers",
            status="Active",
            source="demo_seed",
            end_of_sale_date="N/A",
            last_date_of_support="N/A",
            end_of_sw_maintenance="N/A",
            end_of_security_support="N/A",
            end_of_routine_failure_analysis="N/A",
            eox_announcement_url=None,
            product_bulletin_url=None,
            payload={},
            raw_response={}
        )
        p5 = ProductEox(
            pid="N9K-C93180YC-FX",
            normalized_pid="N9K-C93180YC-FX",
            technology="Switches",
            product_name="Nexus 93180YC-FX Switch",
            series="Cisco Nexus 9000 Series Switches",
            status="Active",
            source="demo_seed",
            end_of_sale_date="N/A",
            last_date_of_support="N/A",
            end_of_sw_maintenance="N/A",
            end_of_security_support="N/A",
            end_of_routine_failure_analysis="N/A",
            eox_announcement_url=None,
            product_bulletin_url=None,
            payload={},
            raw_response={}
        )
        db.add_all([p1, p2, p3, p4, p5])
        db.commit()
        db.refresh(p1)
        db.refresh(p2)
        db.refresh(p3)
        db.refresh(p4)
        db.refresh(p5)

        # Add EoxAffectedProducts
        ap1 = EoxAffectedProduct(
            announcement_id=ann1.id,
            product_id=p1.id,
            pid="C9300-24T",
            normalized_pid="C9300-24T",
            technology="Switches",
            product_description="Catalyst 9300 24-port data only",
            source="demo_seed",
            table_index=2,
            row_index=2,
            row_hash="hash_c9300_24t",
            payload={"End-of-Sale Product Part Number": "C9300-24T", "Product Description": "Catalyst 9300 24-port data only", "Replacement Product Part Number": "C9300X-24T", "Replacement Product Description": "Catalyst 9300X 24-port data only"},
            raw_response={}
        )
        ap2 = EoxAffectedProduct(
            announcement_id=ann2.id,
            product_id=p2.id,
            pid="AIR-CT5520-K9",
            normalized_pid="AIR-CT5520-K9",
            technology="Wireless",
            product_description="Cisco 5520 Wireless Controller",
            source="demo_seed",
            table_index=2,
            row_index=0,
            row_hash="hash_air_ct5520",
            payload={"End-of-Sale Product Part Number": "AIR-CT5520-K9", "Product Description": "Cisco 5520 Wireless Controller", "Replacement Product Part Number": "C9800-40-K9", "Replacement Product Description": "Cisco Catalyst 9800-40 Wireless Controller"},
            raw_response={}
        )
        ap3 = EoxAffectedProduct(
            announcement_id=ann3.id,
            product_id=p3.id,
            pid="WS-C2960X-48FPD-L",
            normalized_pid="WS-C2960X-48FPD-L",
            technology="Switches",
            product_description="Catalyst 2960-X 48 GigE PoE 740W, 2 x 10G SFP+, LAN Base",
            source="demo_seed",
            table_index=2,
            row_index=0,
            row_hash="hash_ws_c2960x",
            payload={"End-of-Sale Product Part Number": "WS-C2960X-48FPD-L", "Product Description": "Catalyst 2960-X 48 GigE PoE 740W, 2 x 10G SFP+, LAN Base", "Replacement Product Part Number": "C9200L-48P-4X-E", "Replacement Product Description": "Catalyst 9200L 48-port PoE+, 4 x 10G SFP+, Network Essentials"},
            raw_response={}
        )
        db.add_all([ap1, ap2, ap3])
        db.commit()

        # Add PidCatalog entries
        pc1 = PidCatalog(
            pid="C9300-24T",
            normalized_pid="C9300-24T",
            technology="Switches",
            category_name="Switches",
            product_name="Catalyst 9300 24-Port Data Only",
            product_url="",
            is_eox=True,
            source="demo_seed",
            payload={}
        )
        pc2 = PidCatalog(
            pid="AIR-CT5520-K9",
            normalized_pid="AIR-CT5520-K9",
            technology="Wireless",
            category_name="Wireless",
            product_name="Cisco 5520 Wireless Controller",
            product_url="",
            is_eox=True,
            source="demo_seed",
            payload={}
        )
        pc3 = PidCatalog(
            pid="WS-C2960X-48FPD-L",
            normalized_pid="WS-C2960X-48FPD-L",
            technology="Switches",
            category_name="Switches",
            product_name="Catalyst 2960-X 48 GigE PoE 740W, 2 x 10G SFP+, LAN Base",
            product_url="",
            is_eox=True,
            source="demo_seed",
            payload={}
        )
        pc4 = PidCatalog(
            pid="ISR4331/K9",
            normalized_pid="ISR4331/K9",
            technology="Routers",
            category_name="Routers",
            product_name="Cisco ISR 4331",
            product_url="",
            is_eox=False,
            source="demo_seed",
            payload={}
        )
        pc5 = PidCatalog(
            pid="N9K-C93180YC-FX",
            normalized_pid="N9K-C93180YC-FX",
            technology="Switches",
            category_name="Switches",
            product_name="Nexus 93180YC-FX Switch",
            product_url="",
            is_eox=False,
            source="demo_seed",
            payload={}
        )
        db.add_all([pc1, pc2, pc3, pc4, pc5])
        db.commit()

        # Add a SystemEvent
        evt = SystemEvent(
            level="info",
            event_type="demo_seeded",
            source="demo_seed",
            message="Mock demo EOX data successfully loaded into local database.",
            payload={"products_added": 5, "announcements_added": 3}
        )
        db.add(evt)
        db.commit()

        return {"status": "ok", "message": "Demo EOX data loaded successfully (5 products, 3 announcements seeded)."}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to load demo data: {exc}") from exc

