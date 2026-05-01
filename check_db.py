#!/usr/bin/env python3
"""
Check sorteios database for draw button issues
"""
import sqlite3
import sys
from pathlib import Path

# Find database
db_path = Path("/Users/edilsonsilva/Clientes/OverFlow/Sorteios/sorteios.db")
if not db_path.exists():
    print(f"❌ Database not found: {db_path}")
    sys.exit(1)

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    print("=" * 60)
    print("SORTEIOS DATABASE CHECK")
    print("=" * 60)
    
    # Check campaigns
    print("\n📊 CAMPAIGNS:")
    cursor.execute("SELECT id, title, status FROM campaign ORDER BY id DESC LIMIT 5")
    campaigns = cursor.fetchall()
    if campaigns:
        for cid, title, status in campaigns:
            print(f"  #{cid}: {title} [{status}]")
    else:
        print("  ❌ No campaigns found!")
    
    # Check quotas for each campaign
    print("\n📍 QUOTAS BY CAMPAIGN:")
    cursor.execute("""
        SELECT c.id, c.title, COUNT(q.id) total, 
               SUM(CASE WHEN q.status='paid' THEN 1 ELSE 0 END) paid,
               SUM(CASE WHEN q.status='reserved' THEN 1 ELSE 0 END) reserved
        FROM campaign c
        LEFT JOIN quota q ON c.id = q.campaign_id
        GROUP BY c.id
        ORDER BY c.id DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for cid, title, total, paid, reserved in rows:
            status_str = ""
            if total == 0:
                status_str = " ⚠️  NO QUOTAS (draw will fail!)"
            elif paid == 0:
                status_str = " ⚠️  No paid quotas (draw might fail)"
            else:
                status_str = f" ✅ Can draw"
            
            print(f"  #{cid}: {title}")
            print(f"      Total: {total}, Paid: {paid}, Reserved: {reserved}{status_str}")
    else:
        print("  ❌ Join failed")
    
    # Check if there's any quota with status != 'none'
    print("\n🎟️  QUOTA STATUS DISTRIBUTION:")
    cursor.execute("SELECT status, COUNT(*) FROM quota GROUP BY status")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}")
    
    # Check admin users
    print("\n👤 ADMIN USERS:")
    cursor.execute("SELECT id, name, email FROM admin_user LIMIT 5")
    admins = cursor.fetchall()
    if admins:
        for aid, name, email in admins:
            print(f"  {name} ({email})")
    else:
        print("  ❌ No admin users found!")
    
    # Final diagnosis
    print("\n" + "=" * 60)
    print("DIAGNOSIS:")
    cursor.execute("SELECT COUNT(*) FROM campaign")
    camp_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM quota")
    quota_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM quota WHERE status IN ('paid', 'reserved')")
    valid_quotas = cursor.fetchone()[0]
    
    if camp_count == 0:
        print("❌ No campaigns exist - create one first")
    elif quota_count == 0:
        print("❌ No quotas exist for any campaign - create quotas first")
    elif valid_quotas == 0:
        print("❌ No PAID or RESERVED quotas - draw_winner() will fail")
        print("   → Add quotas to a campaign and mark some as 'paid'")
    else:
        print("✅ Database looks good for drawing!")
        print(f"   - {camp_count} campaign(s)")
        print(f"   - {valid_quotas} valid quota(s) ready to draw")
    
    print("=" * 60)
    conn.close()

except sqlite3.Error as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
