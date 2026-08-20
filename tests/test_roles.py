from tests.test_api import auth, login


def test_consumer_registration_cannot_escalate_role(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "safe_consumer",
            "email": "safe_consumer@example.com",
            "password": "ConsumerPass1!",
            "full_name": "Safe Consumer",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "consumer"


def test_creator_can_login_after_admin_enrolment(client):
    admin_token = login(client, "admin_seed", "AdminPass123!")
    response = client.post(
        "/api/admin/creators",
        json={
            "username": "creator_auth_test",
            "email": "creator_auth_test@example.com",
            "password": "CreatorPass9!",
            "full_name": "Creator Auth Test",
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "creator"

    creator_token = login(client, "creator_auth_test", "CreatorPass9!")
    me = client.get("/api/auth/me", headers=auth(creator_token))
    assert me.status_code == 200
    assert me.json()["role"] == "creator"


def test_creator_login_page_is_served(client):
    response = client.get("/creator-login.html")
    assert response.status_code == 200
    assert "Creator sign in" in response.text
