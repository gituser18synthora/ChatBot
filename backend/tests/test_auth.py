from __future__ import annotations


def test_login_success(client, seed):
    resp = client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert "access_token" not in body["data"]
    assert "refresh_token" not in body["data"]
    assert body["data"]["user"]["role"] == "super_admin"
    assert resp.headers.get("Set-Cookie")


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


def test_logout_revokes_session(client, auth):
    headers = auth("root@x.com")
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_password_is_hashed(app, seed):
    from app.models.user import User
    u = User.query.filter_by(email="root@x.com").first()
    assert u.password_hash != "password123"
    assert u.check_password("password123")


def _csrf(client):
    cookie = client.get_cookie("cb_csrf")
    return cookie.value if cookie else ""


def _refresh_cookie(client):
    cookie = client.get_cookie("cb_refresh", path="/api/v1/auth/refresh")
    return cookie.value if cookie else ""


def test_csrf_required_for_unsafe_methods(client, seed):
    login = client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"})
    assert login.status_code == 200
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "csrf_failed"


def test_refresh_rotates_cookie_and_keeps_session(client, seed):
    assert client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"}).status_code == 200
    old_refresh = _refresh_cookie(client)
    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": _csrf(client)})
    assert resp.status_code == 200, resp.get_json()
    assert "access_token" not in resp.get_json()["data"]
    assert _refresh_cookie(client) != old_refresh
    assert client.get("/api/v1/auth/me").status_code == 200


def test_reused_refresh_token_revokes_session(client, seed):
    assert client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"}).status_code == 200
    old_refresh = _refresh_cookie(client)
    csrf = _csrf(client)
    assert client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}).status_code == 200
    client.set_cookie("cb_refresh", old_refresh, domain="localhost", path="/api/v1/auth/refresh")
    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": _csrf(client)})
    assert resp.status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_all_revokes_every_session(client, seed):
    assert client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"}).status_code == 200
    headers = {"X-CSRF-Token": _csrf(client)}
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_account_locks_after_repeated_failures(client, seed):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "wrong"})
    resp = client.post("/api/v1/auth/login", json={"email": "root@x.com", "password": "password123"})
    assert resp.status_code == 423
