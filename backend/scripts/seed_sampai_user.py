import asyncio, os, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

# Load .env from the backend directory (parent of scripts/)
_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_here, "..", ".env"), override=True)

import asyncpg

async def seed():
    url = os.getenv("ASYNCPG_DATABASE_URL") or os.getenv("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    print(f"Connecting to: {url[:50]}...")
    conn = await asyncpg.connect(url)

    # Ensure is_system column exists
    col = await conn.fetchval(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='is_system'"
    )
    if not col:
        await conn.execute("ALTER TABLE users ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT FALSE")
        print("Added is_system column")

    # Insert SAMpai user
    row = await conn.fetchrow("SELECT id FROM users WHERE username='SAMpai'")
    if row:
        # Update is_system in case it was created without it
        await conn.execute("UPDATE users SET is_system=TRUE WHERE username='SAMpai'")
        print(f"SAMpai user exists, id={row['id']} (ensured is_system=TRUE)")
    else:
        r = await conn.fetchrow(
            "INSERT INTO users (username, email, hashed_password, is_system) "
            "VALUES ($1, $2, $3, TRUE) RETURNING id",
            "SAMpai", "sampai@system.local", "!locked!"
        )
        print(f"SAMpai user created, id={r['id']}")

    await conn.close()

asyncio.run(seed())
