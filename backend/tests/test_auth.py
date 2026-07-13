from __future__ import annotations


def test_login_success(client, seed):
    resp = client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["user"]["role"] == "super_admin"


def test_login_bad_password(client, seed):
    resp = client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_me_requires_auth(client, seed):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_user(client, auth):
    resp = client.get("/api/v1/auth/me", headers=auth("root@x.com"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["email"] == "root@x.com"


def test_logout_revokes_token(client, auth):
    headers = auth("root@x.com")
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    # Token is now revoked.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_password_is_hashed(app, seed):
    from app.models.user import User
    u = User.query.filter_by(email="root@x.com").first()
    assert u.password_hash != "password123"
    assert u.check_password("password123")
