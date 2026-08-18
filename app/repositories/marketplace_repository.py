from app.database.database import Database


class MarketplaceRepository:
    """Persist lightweight seller listings and service-provider profiles."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._create_tables()

    def _create_tables(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS seller_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_mobile TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price_text TEXT,
                area TEXT,
                source_message TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_seller_listings_mobile_status
            ON seller_listings(seller_mobile, status)
            """
        )
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS service_provider_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_mobile TEXT NOT NULL,
                service_name TEXT NOT NULL,
                details TEXT,
                area TEXT,
                source_message TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_provider_mobile_status
            ON service_provider_profiles(provider_mobile, status)
            """
        )

    def save_seller_listing(self, *, seller_mobile: str, product_name: str, price_text: str | None,
                            area: str | None, source_message: str | None) -> int:
        cursor = self.database.execute(
            """INSERT INTO seller_listings(seller_mobile,product_name,price_text,area,source_message,status,updated_at)
               VALUES(?,?,?,?,?,'ACTIVE',CURRENT_TIMESTAMP)""",
            (seller_mobile, product_name, price_text, area, source_message),
        )
        return int(cursor.lastrowid)

    def save_service_provider_profile(self, *, provider_mobile: str, service_name: str, details: str | None,
                                      area: str | None, source_message: str | None) -> int:
        cursor = self.database.execute(
            """INSERT INTO service_provider_profiles(provider_mobile,service_name,details,area,source_message,status,updated_at)
               VALUES(?,?,?,?,?,'ACTIVE',CURRENT_TIMESTAMP)""",
            (provider_mobile, service_name, details, area, source_message),
        )
        return int(cursor.lastrowid)

    def list_seller_listings_for_user(self, seller_mobile: str, limit: int = 20) -> list[dict]:
        rows = self.database.fetchall(
            """SELECT product_name,price_text,area,updated_at
               FROM seller_listings
               WHERE seller_mobile=? AND status='ACTIVE'
               ORDER BY updated_at DESC, id DESC
               LIMIT ?""",
            (str(seller_mobile), max(1, int(limit))),
        )
        return [dict(row) for row in rows]

    def list_service_provider_profiles_for_user(self, provider_mobile: str, limit: int = 20) -> list[dict]:
        rows = self.database.fetchall(
            """SELECT service_name,details,area,updated_at
               FROM service_provider_profiles
               WHERE provider_mobile=? AND status='ACTIVE'
               ORDER BY updated_at DESC, id DESC
               LIMIT ?""",
            (str(provider_mobile), max(1, int(limit))),
        )
        return [dict(row) for row in rows]

    def find_service_providers(self, service_names: list[str], limit: int = 30) -> list[dict]:
        """Return unique active providers whose saved service name matches any supplied alias."""
        aliases = [self._norm(value) for value in service_names if self._norm(value)]
        if not aliases:
            return []
        rows = self.database.fetchall(
            """SELECT provider_mobile,service_name,details,area,updated_at
               FROM service_provider_profiles
               WHERE status='ACTIVE'
               ORDER BY updated_at DESC"""
        )
        seen = set()
        result = []
        for row in rows:
            service = self._norm(row['service_name'])
            if not any(self._similar(service, alias) for alias in aliases):
                continue
            mobile = str(row['provider_mobile'])
            if mobile in seen:
                continue
            seen.add(mobile)
            result.append(dict(row))
            if len(result) >= max(1, int(limit)):
                break
        return result

    @staticmethod
    def _norm(value) -> str:
        return ' '.join(str(value or '').casefold().strip().split())

    @classmethod
    def _similar(cls, a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        at, bt = set(a.split()), set(b.split())
        return bool(at and bt and (len(at & bt) / max(1, min(len(at), len(bt)))) >= 0.6)
