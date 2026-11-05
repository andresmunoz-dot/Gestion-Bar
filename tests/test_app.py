from contextlib import nullcontext
from pathlib import Path
import re
from typing import Any, cast
import unittest
from unittest.mock import Mock, patch

import bcrypt

import app as auth_module
from app import app


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _json(self, response: Any) -> dict[str, Any]:
        data = response.get_json()
        self.assertIsInstance(data, dict)
        return cast(dict[str, Any], data)

    def test_homepage_serves_existing_html(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Barrica", response.data)
        response.close()

    def test_anonymous_session_does_not_require_database(self) -> None:
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._json(response), {"user": None})

    def test_auth_database_connection_uses_configured_connection_helper(self) -> None:
        connection = Mock()

        with patch.object(auth_module, "get_db_connection", return_value=connection):
            with auth_module._database_connection() as actual_connection:
                self.assertIs(actual_connection, connection)

        connection.close.assert_called_once_with()

    def test_login_requires_json(self) -> None:
        response = self.client.post("/api/auth/login", data="not json")

        self.assertEqual(response.status_code, 415)
        self.assertIn("error", self._json(response))

    def test_login_rejects_invalid_credentials_before_database_access(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "short"},
        )

        self.assertEqual(response.status_code, 400)

    def test_register_rejects_short_password_before_database_access(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "password": "short",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_register_rejects_digits_in_name_before_database_access(self) -> None:
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
                    self._json(response),
                    {"error": "El nombre no puede contener números."},
                )
                database.assert_not_called()

    def test_register_accepts_accented_names(self) -> None:
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
                    "role": "administrador",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._json(response)["user"]["role"], "administrador")

    def test_database_configuration_error_is_returned_as_json(self) -> None:
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
        self.assertIn("error", self._json(response))

    def test_register_creates_a_bcrypt_password_and_session(self) -> None:
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
            self._json(response),
            {
                "user": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "role": "vendedor",
                },
                "token": "session-token",
            },
        )
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        stored_password = cursor.execute.call_args.args[1][2].encode("ascii")
        self.assertTrue(bcrypt.checkpw(b"validpassword", stored_password))

    def test_login_creates_an_http_only_session(self) -> None:
        password = "validpassword"
        user_cursor = Mock()
        user_cursor.fetchone.return_value = {
            "id": 7,
            "name": "Test User",
            "email": "test@example.com",
            "role": "administrador",
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
                json={
                    "email": "TEST@example.com",
                    "password": password,
                    "role": "administrador",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._json(response),
            {
                "user": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "role": "administrador",
                },
                "token": "session-token",
            },
        )
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", response.headers["Set-Cookie"])
        self.assertEqual(
            user_cursor.execute.call_args.args[1],
            ("test@example.com",),
        )

    def test_seller_cannot_login_as_administrator(self) -> None:
        password = "validpassword"
        user_cursor = Mock()
        user_cursor.fetchone.return_value = {
            "id": 9,
            "name": "Vendedor Uno",
            "email": "vendedor@example.com",
            "role": "vendedor",
            "password_hash": bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt(rounds=4),
            ).decode("ascii"),
        }
        connection = Mock()
        connection.cursor.return_value = user_cursor

        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_is_login_blocked", return_value=False),
        ):
            response = self.client.post(
                "/api/auth/login",
                json={
                    "email": "vendedor@example.com",
                    "password": password,
                    "role": "administrador",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Vendedor", self._json(response)["error"])

    def test_bar_endpoints_enforce_authentication_and_roles(self) -> None:
        unauth = self.client.get("/api/bar/dashboard")
        self.assertEqual(unauth.status_code, 401)

        seller_user = {
            "id": 2,
            "name": "Cajero",
            "email": "cajero@barrica.com",
            "role": "vendedor",
        }
        with patch.object(auth_module, "_get_session_user", return_value=seller_user):
            forbidden_prod = self.client.post(
                "/api/bar/products",
                headers={"Authorization": "Bearer seller-token"},
                json={"name": "Ron", "category": "Licores", "price_cop": 90000, "stock": 5, "min_stock": 2},
            )
            self.assertEqual(forbidden_prod.status_code, 403)

            forbidden_table = self.client.post(
                "/api/bar/tables",
                headers={"Authorization": "Bearer seller-token"},
                json={"table_number": 10, "label": "Mesa 10", "capacity": 4},
            )
            self.assertEqual(forbidden_table.status_code, 403)

            forbidden_role = self.client.post(
                "/api/bar/users/2/role",
                headers={"Authorization": "Bearer seller-token"},
                json={"role": "administrador"},
            )
            self.assertEqual(forbidden_role.status_code, 403)

    def test_html_prices_match_server_plans(self) -> None:
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
    def _payment(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
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

    def test_simulated_payment_returns_a_labelled_receipt(self) -> None:
        response = self.client.post("/api/payments/simulate", json=self._payment())

        self.assertEqual(response.status_code, 201)
        receipt = self._json(response)["receipt"]
        self.assertTrue(receipt["simulated"])
        self.assertRegex(receipt["number"], r"^SIM-\d{8}-[0-9A-F]{6}$")
        self.assertEqual(receipt["currency"], "COP")
        self.assertEqual(receipt["amount"], 59 * auth_module.COP_PER_USD)
        self.assertEqual(receipt["amounts"], {"USD": 59, "COP": 59 * auth_module.COP_PER_USD})
        self.assertEqual(receipt["payer"]["email"], "maria@example.com")
        self.assertEqual(receipt["card"], {"holder": "Maria Jose Nunez", "brand": "Visa", "last4": "4242"})

    def test_simulated_payment_in_dollars_uses_server_price(self) -> None:
        response = self.client.post(
            "/api/payments/simulate",
            json=self._payment(plan="multilocal", currency="USD", amount=1),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._json(response)["receipt"]["amount"], 129)

    def test_simulated_payment_rejects_digits_in_names(self) -> None:
        for field in ("payer_name", "card_holder"):
            with self.subTest(field=field):
                response = self.client.post(
                    "/api/payments/simulate", json=self._payment(**{field: "Juan 3"})
                )

                self.assertEqual(response.status_code, 400)
                body = self._json(response)
                self.assertEqual(body["field"], field)
                self.assertEqual(
                    body["error"], "El nombre no puede contener números."
                )

    def test_simulated_payment_requires_only_digits_in_numeric_fields(self) -> None:
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
                    self.assertEqual(self._json(response)["field"], field)

    def test_simulated_payment_rejects_unknown_plan_currency_and_document_type(self) -> None:
        for field, value in (("plan", "gratis"), ("plan", ["pro"]), ("currency", "EUR"), ("document_type", "PAS")):
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/payments/simulate", json=self._payment(**{field: value})
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self._json(response)["field"], field)

    def test_simulated_payment_never_echoes_sensitive_card_data(self) -> None:
        response = self.client.post(
            "/api/payments/simulate",
            json=self._payment(card_number="4242424242424242", card_cvv="123", card_expiry="08/29"),
        )

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 201)
        for secret in ("4242424242424242", "08/29", '"123"'):
            self.assertNotIn(secret, body)

    def test_logout_without_session_does_not_require_database(self) -> None:
        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._json(response), {"ok": True})

    def test_pwa_manifest_and_download_section_are_served(self) -> None:
        manifest_response = self.client.get("/app/manifest.webmanifest")
        self.assertEqual(manifest_response.status_code, 200)
        manifest = self._json(manifest_response)
        self.assertEqual(manifest["short_name"], "Barrica")
        self.assertEqual(manifest["start_url"], "/app")
        self.assertEqual(manifest["display"], "standalone")
        manifest_response.close()

        app_response = self.client.get("/app")
        self.assertEqual(app_response.status_code, 200)
        self.assertIn(b"Control de mesas y cuentas", app_response.data)
        self.assertIn(b"Administrador", app_response.data)
        self.assertIn(b"Vendedor", app_response.data)
        app_response.close()

        exe_response = self.client.get("/downloads/BarricaDesktop.exe")
        self.assertEqual(exe_response.status_code, 200)
        self.assertTrue(exe_response.data.startswith(b"MZ"))
        exe_response.close()

        mobile_dl = self.client.get("/downloads/Barrica-Movil.html")
        self.assertEqual(mobile_dl.status_code, 200)
        mobile_dl.close()

        icon_response = self.client.get("/icon.svg")
        self.assertEqual(icon_response.status_code, 200)
        self.assertIn("image/svg+xml", icon_response.content_type)
        icon_response.close()

        sw_response = self.client.get("/app/sw.js")
        self.assertEqual(sw_response.status_code, 200)
        sw_response.close()

        html = (Path(auth_module.ROOT) / "Untitled-1.html").read_text(encoding="utf-8")
        for platform in ("pc", "android", "ios"):
            self.assertIn(f'data-app-platform="{platform}"', html)
        for role in ("administrador", "vendedor"):
            self.assertIn(f'data-select-role="{role}"', html)


if __name__ == "__main__":
    unittest.main()
