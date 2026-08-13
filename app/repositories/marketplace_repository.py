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

    def save_seller_listing(
        self,
        *,
        seller_mobile: str,
        product_name: str,
        price_text: str | None,
        area: str | None,
        source_message: str | None,
    ) -> int:
        cursor = self.database.execute(
            """
            INSERT INTO seller_listings (
                seller_mobile,
                product_name,
                price_text,
                area,
                source_message,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', CURRENT_TIMESTAMP)
            """,
            (seller_mobile, product_name, price_text, area, source_message),
        )
        return int(cursor.lastrowid)

    def save_service_provider_profile(
        self,
        *,
        provider_mobile: str,
        service_name: str,
        details: str | None,
        area: str | None,
        source_message: str | None,
    ) -> int:
        cursor = self.database.execute(
            """
            INSERT INTO service_provider_profiles (
                provider_mobile,
                service_name,
                details,
                area,
                source_message,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', CURRENT_TIMESTAMP)
            """,
            (provider_mobile, service_name, details, area, source_message),
        )
        return int(cursor.lastrowid)
