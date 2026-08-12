class AppointmentRepository:
    def __init__(self, database) -> None:
        self.database = database

    def create_request(
        self,
        customer_mobile: str,
        category: str,
        area: str,
        preferred_date: str,
        preferred_time: str,
    ) -> dict:
        cursor = self.database.execute(
            """
            INSERT INTO appointment_requests (
                customer_mobile,
                category,
                area,
                preferred_date,
                preferred_time,
                status
            ) VALUES (?, ?, ?, ?, ?, 'REQUESTED')
            """,
            (
                customer_mobile,
                category,
                area,
                preferred_date,
                preferred_time,
            ),
        )
        return {
            "id": cursor.lastrowid,
            "customer_mobile": customer_mobile,
            "category": category,
            "area": area,
            "preferred_date": preferred_date,
            "preferred_time": preferred_time,
            "status": "REQUESTED",
        }
