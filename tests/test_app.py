from contextlib import nullcontext
from pathlib import Path
import re
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

    def test_register_rejects_digits_in_name_before_database_access(self):
        for name in ("Juan123", "7", "Ana 2", "Luis ٣"):
            with self.subTest(name=name):
                with patch.object(auth_module, "_database_connection") as database:
                    response = self.client.post(
                        "/api/auth/register",
                        json={
                            "name": name,
                            "email": "test@example.com",
                            "password": "validpassword",
                        },
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json(),
                    {"error": "El nombre no puede contener números."},
                )
                database.assert_not_called()

    def test_register_accepts_accented_names(self):
        cursor = Mock()
        cursor.lastrowid = 3
        connection = Mock()
        connection.cursor.return_value = cursor

        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_create_session", return_value="session-token"),
        ):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "name": "María José Núñez-O'Brien",
                    "email": "maria@example.com",
                    "password": "validpassword",
                },
            )

        self.assertEqual(response.status_code, 201)

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

    def test_html_prices_match_server_plans(self):
        html = (Path(auth_module.ROOT) / "Untitled-1.html").read_text(encoding="utf-8")
        found = {
            plan: (int(usd), int(cop))
            for plan, usd, cop in re.findall(
                r'data-plan="(\w+)"[^>]*data-usd="(\d+)"[^>]*data-cop="(\d+)"', html
            )
        }

        self.assertEqual(set(found), set(auth_module.PLANS))
        for plan_id, plan in auth_module.PLANS.items():
            self.assertEqual(
                found[plan_id],
                (plan["usd"], plan["usd"] * auth_module.COP_PER_USD),
                plan_id,
            )

    # --- Pago de prueba -------------------------------------------------

    @staticmethod
    def _payment(**overrides):
        payload = {
            "plan": "pro",
            "currency": "COP",
            "payer_name": "María José Núñez",
            "email": "MARIA@example.com",
            "document_type": "CC",
            "document_number": "1012345678",
            "phone": "3001234567",
            "card_holder": "Maria Jose Nunez",
            "card_last4": "4242",
            "card_brand": "Visa",
        }
        payload.update(overrides)
        return payload

    def test_simulated_payment_returns_a_labelled_receipt(self):
        response = self.client.post("/api/payments/simulate", json=self._payment())

        self.assertEqual(response.status_code, 201)
        receipt = response.get_json()["receipt"]
        self.assertTrue(receipt["simulated"])
        self.assertRegex(receipt["number"], r"^SIM-\d{8}-[0-9A-F]{6}$")
        self.assertEqual(receipt["currency"], "COP")
        self.assertEqual(receipt["amount"], 59 * auth_module.COP_PER_USD)
        self.assertEqual(receipt["amounts"], {"USD": 59, "COP": 59 * auth_module.COP_PER_USD})
        self.assertEqual(receipt["payer"]["email"], "maria@example.com")
        self.assertEqual(receipt["card"], {"holder": "Maria Jose Nunez", "brand": "Visa", "last4": "4242"})

    def test_simulated_payment_in_dollars_uses_server_price(self):
        response = self.client.post(
            "/api/payments/simulate",
            json=self._payment(plan="multilocal", currency="USD", amount=1),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["receipt"]["amount"], 129)

    def test_simulated_payment_rejects_digits_in_names(self):
        for field in ("payer_name", "card_holder"):
            with self.subTest(field=field):
                response = self.client.post(
                    "/api/payments/simulate", json=self._payment(**{field: "Juan 3"})
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["field"], field)
                self.assertEqual(
                    response.get_json()["error"], "El nombre no puede contener números."
                )

    def test_simulated_payment_requires_only_digits_in_numeric_fields(self):
        cases = {
            "document_number": ["12345", "12345A78", "١٢٣٤٥٦٧", "1234 5678", "1" * 13],
            "phone": ["123456", "300-123-4567", "30012345678901234"],
            "card_last4": ["424", "42A2", "42424", "٤٢٤٢"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.client.post(
                        "/api/payments/simulate", json=self._payment(**{field: value})
                    )

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json()["field"], field)

    def test_simulated_payment_rejects_unknown_plan_currency_and_document_type(self):
        for field, value in (("plan", "gratis"), ("plan", ["pro"]), ("currency", "EUR"), ("document_type", "PAS")):
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/payments/simulate", json=self._payment(**{field: value})
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["field"], field)

    def test_simulated_payment_never_echoes_sensitive_card_data(self):
        response = self.client.post(
            "/api/payments/simulate",
            json=self._payment(card_number="4242424242424242", card_cvv="123", card_expiry="08/29"),
        )

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 201)
        for secret in ("4242424242424242", "08/29", '"123"'):
            self.assertNotIn(secret, body)

    def test_logout_without_session_does_not_require_database(self):
        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
