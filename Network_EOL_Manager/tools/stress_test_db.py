#!/usr/bin/env python3
import sys
import time
from pathlib import Path

# Add backend root to PATH
PRODUCT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PRODUCT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import init_db, make_session
from app.services.seed_persistence import SeedPersistenceService

DB_URL = "postgresql+psycopg://eox_user:eox_password@localhost:5433/eox_cache"

def generate_mock_seed(count: int) -> dict:
    print(f"Generating {count} mock EOX records...")
    records = []
    for i in range(count):
        records.append({
            "pid": f"STRESS-PID-{i}",
            "technology": "Routing",
            "source": "stress_test",
            "announcement_name": f"Stress Notice {i}",
            "announcement_url": f"https://example.com/notice-{i}",
            "payload": {
                "PID": f"STRESS-PID-{i}",
                "ProductIDDescription": f"Stress test product descriptor {i}",
                "End-of-Sale Date": "January 31, 2027",
                "Last Date of Support": "January 31, 2032",
                "EOXAnnouncementURL": f"https://example.com/notice-{i}",
                "affected_product_row": {
                    "table_index": 2,
                    "row_index": 1,
                    "columns": {"End-of-Sale Product Part Number": f"STRESS-PID-{i}"},
                },
                "announcement_tables": [
                    {
                        "table_index": 1,
                        "headers": ["Milestone", "Date"],
                        "rows": [{"columns": {"Milestone": "End-of-Sale Date", "Date": "January 31, 2027"}}],
                    },
                    {
                        "table_index": 2,
                        "headers": ["End-of-Sale Product Part Number"],
                        "rows": [{"columns": {"End-of-Sale Product Part Number": f"STRESS-PID-{i}"}}],
                    },
                ],
            },
            "raw_response": {"source": "stress_test"},
        })
    return {
        "source": "stress_test",
        "pid_catalog": [],
        "eox_records": records
    }

def run_stress_test(count: int = 20000):
    print(f"Initializing Database connection to {DB_URL}...")
    init_db(DB_URL)
    
    seed = generate_mock_seed(count)
    
    print("Connecting and starting database transaction...")
    db = make_session(DB_URL)
    
    start_time = time.time()
    try:
        # Clear existing stress test records if any to make it a clean, reproducible run
        print("Cleaning previous stress test records...")
        from app.db.models import ProductEox, EoxAnnouncement, EoxAnnouncementTable, EoxAffectedProduct
        db.query(EoxAffectedProduct).filter(EoxAffectedProduct.source == "stress_test").delete()
        db.query(EoxAnnouncementTable).delete()
        db.query(EoxAnnouncement).filter(EoxAnnouncement.source == "stress_test").delete()
        db.query(ProductEox).filter(ProductEox.source == "stress_test").delete()
        db.commit()
        
        print("Inserting records into PostgreSQL...")
        persistence = SeedPersistenceService(db)
        result = persistence.save_seed(
            seed,
            source_path="stress_test",
            mode="stress",
            overwrite=True,
            commit=True
        )
        
        elapsed = time.time() - start_time
        print("\n--- STRESS TEST RESULTS ---")
        print(f"Total inserted Products: {result.products_inserted}")
        print(f"Total inserted Announcements: {result.announcements_inserted}")
        print(f"Total inserted Announcement Tables: {result.announcement_tables_inserted}")
        print(f"Total inserted Affected Rows: {result.affected_rows_inserted}")
        print(f"Elapsed Time: {elapsed:.2f} seconds")
        print(f"Throughput: {count / elapsed:.2f} records/second")
        print("----------------------------")
        
    except Exception as exc:
        print(f"Stress test encountered an error: {exc}", file=sys.stderr)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    count = 20000
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    run_stress_test(count)
