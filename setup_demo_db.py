import os
import json
from pathlib import Path

db_file = Path("backend/database/apibridge.db")
if db_file.exists():
    try:
        os.remove(db_file)
    except Exception as e:
        print("Note: Could not delete old db file:", e)

from backend.app.database.db import init_db, get_db
from backend.app.services.diff_engine import compare_specs
from backend.app.services.adapter_service import generate_deterministic_adapter

init_db()

conn = get_db()
cur = conn.cursor()

# Clean tables
cur.execute("DELETE FROM test_runs")
cur.execute("DELETE FROM adapters")
cur.execute("DELETE FROM changes")
cur.execute("DELETE FROM spec_versions")
cur.execute("DELETE FROM apis")

samples_dir = Path("samples")

# =========================================================
# SERVICE 1: User Management Service
# =========================================================
cur.execute(
    "INSERT INTO apis (id, name, description) VALUES (1, 'User Management Service', 'Legacy User & Customer Management API')"
)

with open(samples_dir / "users_v1.json", "r", encoding="utf-8") as f:
    u_v1_text = f.read()
    u_v1_spec = json.loads(u_v1_text)

with open(samples_dir / "customers_v2.json", "r", encoding="utf-8") as f:
    u_v2_text = f.read()
    u_v2_spec = json.loads(u_v2_text)

cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (1, 1, '1.0.0', ?)",
    (json.dumps(u_v1_spec, indent=2),),
)
cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (2, 1, '2.0.0', ?)",
    (json.dumps(u_v2_spec, indent=2),),
)

u_changes = compare_specs(u_v1_spec, u_v2_spec)
for ch in u_changes:
    cur.execute(
        """
        INSERT INTO changes (api_id, old_version_id, new_version_id, endpoint, method, change_type, severity, description, details)
        VALUES (1, 1, 2, ?, ?, ?, ?, ?, ?)
        """,
        (ch["endpoint"], ch["method"], ch["change_type"], ch["severity"], ch["description"], json.dumps(ch.get("details") or {})),
    )

u_code, u_exp = generate_deterministic_adapter(
    old_endpoint="/users",
    new_endpoint="/customers",
    method="GET",
    field_mappings={"full_name": "name"},
)
cur.execute(
    """
    INSERT INTO adapters (id, api_id, old_endpoint, new_endpoint, method, status, adapter_code, explanation)
    VALUES (1, 1, '/users', '/customers', 'GET', 'APPROVED', ?, ?)
    """,
    (u_code, u_exp),
)

cur.execute(
    "INSERT INTO apis (id, name, description) VALUES (2, 'E-Commerce Catalog Service', 'Online store products and inventory API')"
)

with open(samples_dir / "products_v1.json", "r", encoding="utf-8") as f:
    p_v1_text = f.read()
    p_v1_spec = json.loads(p_v1_text)

with open(samples_dir / "items_v2.json", "r", encoding="utf-8") as f:
    p_v2_text = f.read()
    p_v2_spec = json.loads(p_v2_text)

cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (3, 2, '1.0.0', ?)",
    (json.dumps(p_v1_spec, indent=2),),
)
cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (4, 2, '2.0.0', ?)",
    (json.dumps(p_v2_spec, indent=2),),
)

p_changes = compare_specs(p_v1_spec, p_v2_spec)
for ch in p_changes:
    cur.execute(
        """
        INSERT INTO changes (api_id, old_version_id, new_version_id, endpoint, method, change_type, severity, description, details)
        VALUES (2, 3, 4, ?, ?, ?, ?, ?, ?)
        """,
        (ch["endpoint"], ch["method"], ch["change_type"], ch["severity"], ch["description"], json.dumps(ch.get("details") or {})),
    )

p_code, p_exp = generate_deterministic_adapter(
    old_endpoint="/products",
    new_endpoint="/items",
    method="GET",
    field_mappings={"item_name": "title"},
)
cur.execute(
    """
    INSERT INTO adapters (id, api_id, old_endpoint, new_endpoint, method, status, adapter_code, explanation)
    VALUES (2, 2, '/products', '/items', 'GET', 'APPROVED', ?, ?)
    """,
    (p_code, p_exp),
)

cur.execute(
    "INSERT INTO apis (id, name, description) VALUES (3, 'Core Banking Accounts Service', 'Financial accounts, balances, and digital wallets API')"
)

with open(samples_dir / "banking_v1.json", "r", encoding="utf-8") as f:
    b_v1_text = f.read()
    b_v1_spec = json.loads(b_v1_text)

with open(samples_dir / "banking_v2.json", "r", encoding="utf-8") as f:
    b_v2_text = f.read()
    b_v2_spec = json.loads(b_v2_text)

cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (5, 3, '1.0.0', ?)",
    (json.dumps(b_v1_spec, indent=2),),
)
cur.execute(
    "INSERT INTO spec_versions (id, api_id, version_tag, raw_spec) VALUES (6, 3, '2.0.0', ?)",
    (json.dumps(b_v2_spec, indent=2),),
)

b_changes = compare_specs(b_v1_spec, b_v2_spec)
for ch in b_changes:
    cur.execute(
        """
        INSERT INTO changes (api_id, old_version_id, new_version_id, endpoint, method, change_type, severity, description, details)
        VALUES (3, 5, 6, ?, ?, ?, ?, ?, ?)
        """,
        (ch["endpoint"], ch["method"], ch["change_type"], ch["severity"], ch["description"], json.dumps(ch.get("details") or {})),
    )

b_code, b_exp = generate_deterministic_adapter(
    old_endpoint="/accounts",
    new_endpoint="/wallets",
    method="GET",
    field_mappings={"wallet_id": "acc_no", "client_name": "holder"},
)
cur.execute(
    """
    INSERT INTO adapters (id, api_id, old_endpoint, new_endpoint, method, status, adapter_code, explanation)
    VALUES (3, 3, '/accounts', '/wallets', 'GET', 'APPROVED', ?, ?)
    """,
    (b_code, b_exp),
)

conn.commit()
conn.close()

print("=" * 65)
print("  APIBridge AI Database Seed Complete!")
print("  Service 1: User Management Service (ID: 1)")
print("    - Adapter #1: /users -> /customers | full_name -> name")
print("  Service 2: E-Commerce Catalog Service (ID: 2)")
print("    - Adapter #2: /products -> /items | item_name -> title")
print("  Service 3: Core Banking Accounts Service (ID: 3)")
print("    - Adapter #3: /accounts -> /wallets | wallet_id -> acc_no, client_name -> holder")
print("=" * 65)
