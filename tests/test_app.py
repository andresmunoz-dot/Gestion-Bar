from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch

import bcrypt

import app as auth_module
from app import app


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_homepage_serves_existing_html(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Barrica", response.data)
        response.close()

    def test_anonymous_session_does_not_require_database(self):
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"user": None})

    def test_auth_database_connection_uses_configured_connection_helper(self):
        connection = Mock()

        with patch.object(auth_module, "get_db_connection", return_value=connection):
            with auth_module._database_connection() as actual_connection:
                self.assertIs(actual_connection, connection)

        connection.close.assert_called_once_with()

    def test_login_requires_json(self):
        response = self.client.post("/api/auth/login", data="not json")

        self.assertEqual(response.status_code, 415)
        self.assertIn("error", response.get_json())

    def test_login_rejects_invalid_credentials_before_database_access(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "short"},
        )

        self.assertEqual(response.status_code, 400)

    def test_register_rejects_short_password_before_database_access(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "password": "short",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_database_configuration_error_is_returned_as_json(self):
        with patch.object(
            auth_module,
            "get_db_connection",
            side_effect=auth_module.DatabaseConfigurationError("missing settings"),
        ):
            response = self.client.post(
                "/api/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "validpassword",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.get_json())

    def test_register_creates_a_bcrypt_password_and_session(self):
        cursor = Mock()
        cursor.lastrowid = 17
        connection = Mock()
        connection.cursor.return_value = cursor

        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_create_session", return_value="session-token"),
        ):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "name": "  Test User  ",
                    "email": "TEST@example.com",
                    "password": "validpassword",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(),
            {"user": {"name": "Test User", "email": "test@example.com"}},
        )
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        stored_password = cursor.execute.call_args.args[1][2].encode("ascii")
        self.assertTrue(bcrypt.checkpw(b"validpassword", stored_password))

    def test_login_creates_an_http_only_session(self):
        password = "validpassword"
        user_cursor = Mock()
        user_cursor.fetchone.return_value = {
            "id": 7,
            "name": "Test User",
            "email": "test@example.com",
            "password_hash": bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt(rounds=4),
            ).decode("ascii"),
        }
        cleanup_cursor = Mock()
        connection = Mock()
        connection.cursor.side_effect = [user_cursor, cleanup_cursor]

        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_is_login_blocked", return_value=False),
            patch.object(auth_module, "_create_session", return_value="session-token"),
        ):
            response = self.client.post(
                "/api/auth/login",
                json={"email": "TEST@example.com", "password": password},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"user": {"name": "Test User", "email": "test@example.com"}},
        )
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", response.headers["Set-Cookie"])
        self.assertEqual(
            user_cursor.execute.call_args.args[1],
            ("test@example.com",),
        )

    def test_logout_without_session_does_not_require_database(self):
        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
