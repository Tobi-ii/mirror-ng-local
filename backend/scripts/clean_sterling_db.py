import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.database import get_db

def clean_existing_sterling():
    conn = get_db()
    cursor = conn.execute("SELECT id, narration FROM transactions WHERE bank = 'Sterling Bank'")
    updated = 0
    for row in cursor.fetchall():
        raw = row['narration']
        if not raw:
            continue
        normalized = raw
        normalized = re.sub(r'(?i)(?<=[a-zA-Z])(to|from)(?=[A-Z])', r' \1 ', normalized)
        normalized = re.sub(r'(?i)(?<=[a-z])(to|from)(?=[a-zA-Z])', r' \1 ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        match = re.search(r'\bto\s+(.+?)(?:\s+remark|\s+date|\s+value|$)', normalized, re.IGNORECASE)
        if match:
            raw_name = match.group(1).strip()
            clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_name)
            clean_name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', clean_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            if " AND " in clean_name:
                clean_name = clean_name.split(" AND ")[0].strip()
            if "..." in clean_name:
                clean_name = clean_name.split("...")[0].strip()
            if clean_name != raw:
                conn.execute("UPDATE transactions SET narration = ? WHERE id = ?", (clean_name, row['id']))
                updated += 1
                print(f"  Fixed: {raw[:50]}... -> {clean_name}")
    conn.commit()
    conn.close()
    print(f"\nCleaned {updated} existing Sterling transactions.")

if __name__ == "__main__":
    clean_existing_sterling()
