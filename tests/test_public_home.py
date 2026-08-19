from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.public_home import router


def test_public_home_is_available_and_describes_podx() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "PODX AI CONNECT" in response.text
    assert "Final choice always remains with the user" in response.text
    assert "Affiliate or referral relationships do not decide" in response.text
