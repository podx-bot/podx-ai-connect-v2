class CapabilityRepository:
    VALID_CAPABILITIES = {
        "BUYER",
        "SELLER",
        "SERVICE_CUSTOMER",
        "SERVICE_PROVIDER",
        "WORKER",
        "EMPLOYER",
        "DELIVERY_PARTNER",
    }

    def __init__(self, database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS user_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_mobile TEXT NOT NULL,
                capability TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(whatsapp_mobile, capability)
            )
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_capabilities_mobile
            ON user_capabilities(whatsapp_mobile)
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_capabilities_capability
            ON user_capabilities(capability)
            """
        )

    def add(self, whatsapp_mobile: str, capability: str, source: str | None = None) -> None:
        normalized = self._normalize(capability)
        self.database.execute(
            """
            INSERT INTO user_capabilities (
                whatsapp_mobile, capability, source, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile, capability)
            DO UPDATE SET
                source = COALESCE(excluded.source, user_capabilities.source),
                updated_at = CURRENT_TIMESTAMP
            """,
            (whatsapp_mobile, normalized, source),
        )

    def add_many(self, whatsapp_mobile: str, capabilities, source: str | None = "registration") -> None:
        for capability in capabilities:
            self.add(whatsapp_mobile, capability, source=source)

    def list_for_user(self, whatsapp_mobile: str) -> list[str]:
        rows = self.database.fetchall(
            """
            SELECT capability
            FROM user_capabilities
            WHERE whatsapp_mobile = ?
            ORDER BY capability ASC
            """,
            (whatsapp_mobile,),
        )
        return [str(row["capability"]) for row in rows]

    def has(self, whatsapp_mobile: str, capability: str) -> bool:
        normalized = self._normalize(capability)
        row = self.database.fetchone(
            """
            SELECT 1
            FROM user_capabilities
            WHERE whatsapp_mobile = ? AND capability = ?
            LIMIT 1
            """,
            (whatsapp_mobile, normalized),
        )
        return row is not None

    @classmethod
    def _normalize(cls, capability: str) -> str:
        normalized = str(capability or "").strip().upper()
        if normalized not in cls.VALID_CAPABILITIES:
            raise ValueError(f"Unsupported user capability: {capability}")
        return normalized
