import numpy as np
if not hasattr(np, "float_"):
    np.float_ = np.float64
if not hasattr(np, "int_"):
    np.int_ = np.intp

import os
from pathlib import Path
from dotenv import load_dotenv

# Try both .env.docker and .env in the backend directory
_backend = Path(__file__).parents[3]  # backend/
for _env in [".env.docker", ".env"]:
    _p = _backend / _env
    if _p.exists():
        load_dotenv(_p, override=False)
        break

import chromadb

client = chromadb.HttpClient(host="localhost", port=8001)
col = client.get_collection("classroom_3__chunks")

print("Total chunks:", col.count())

# Dump ALL chunks to see what was actually stored
all_data = col.get(include=["documents", "metadatas"])
print("\n=== ALL CHUNKS (sorted by order index) ===\n")

chunks = list(zip(all_data["ids"], all_data["documents"], all_data["metadatas"]))
# Sort by chunk_order_index if available
chunks.sort(key=lambda x: x[2].get("chunk_order_index", 0) if x[2] else 0)

for cid, doc, meta in chunks:
    words = len(doc.split()) if doc else 0
    order = meta.get("chunk_order_index", "?") if meta else "?"
    print(f"[{order}] ({words} words) {repr(doc[:120])}")

