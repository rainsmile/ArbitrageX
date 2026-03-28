"""Wait for database to be ready before starting the application."""
import sys
import time
import pymysql

def wait_for_db(max_retries: int = 30, delay: float = 2.0):
    """Try to connect to MySQL, retrying until success or max retries."""
    import os

    host = os.getenv("DB_HOST", "127.0.0.1")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "myuser")
    password = os.getenv("MYSQL_PASSWORD", "YourPassword123!")
    database = os.getenv("MYSQL_DATABASE", "arbitrage")

    # Parse from DATABASE_URL if available
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        # Extract host from URL like mysql+aiomysql://user:pass@host:port/db
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_url.replace("mysql+aiomysql://", "mysql://"))
            host = parsed.hostname or host
            port = parsed.port or port
            user = parsed.username or user
            password = parsed.password or password
            database = parsed.path.lstrip("/").split("?")[0] or database
        except Exception:
            pass

    for attempt in range(1, max_retries + 1):
        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, connect_timeout=5,
            )
            conn.close()
            print(f"✅ Database ready (attempt {attempt})")
            return True
        except Exception as e:
            print(f"⏳ Waiting for database... (attempt {attempt}/{max_retries}): {e}")
            time.sleep(delay)

    print("❌ Database not ready after max retries")
    return False

if __name__ == "__main__":
    success = wait_for_db()
    sys.exit(0 if success else 1)
