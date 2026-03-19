import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, is_postgres, get_hot_slugs
from scripts.ingestion.parallel_ingestor import load_registry

def seed_companies():
    """Seed the companies table from company_registry.json and tag P0 tiers."""
    print(">>> Seeding companies table...")
    
    registry = load_registry()
    hot_slugs = get_hot_slugs()
    
    if not registry:
        print("Error: Registry is empty.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    
    count = 0
    hot_tagged = 0
    
    try:
        BATCH_SIZE = 100
        for i, c in enumerate(registry):
            name = c.get("company")
            ats = c.get("ats")
            slug = c.get("slug")
            
            if not slug:
                continue
                
            tier = "P2"
            if slug in hot_slugs or name in hot_slugs:
                tier = "P0"
                hot_tagged += 1
                
            try:
                if is_postgres():
                    cursor.execute("""
                        INSERT INTO companies (slug, name, ats_type, tier)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (slug) DO UPDATE SET
                            name = EXCLUDED.name,
                            ats_type = EXCLUDED.ats_type,
                            tier = EXCLUDED.tier
                    """, (slug, name, ats, tier))
                else:
                    cursor.execute("""
                        INSERT INTO companies (slug, name, ats_type, tier)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT (slug) DO UPDATE SET
                            name = excluded.name,
                            ats_type = excluded.ats_type,
                            tier = excluded.tier
                    """, (slug, name, ats, tier))
                count += 1
                
                if count % BATCH_SIZE == 0:
                    conn.commit()
                    print(f"Processed {count}/{len(registry)} companies...")
            except Exception as e:
                print(f"Error inserting {slug}: {e}")
                
        conn.commit()
        print(f"Successfully seeded {count} companies ({hot_tagged} tagged as P0/Hot).")
        
    finally:
        conn.close()

if __name__ == "__main__":
    seed_companies()
