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
        self.assertEqual(self._json(response)["user"]["role"], "vendedor")

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
                    "role": "administrador",
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

    def test_register_for_pos_creates_account_without_requiring_subscription(self) -> None:
        cursor = Mock()
        cursor.lastrowid = 29
        connection = Mock()
        connection.cursor.return_value = cursor
        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_create_session", return_value="new-account-token"),
            patch.object(auth_module, "_get_active_subscription") as subscription_check,
        ):
            response = self.client.post("/api/auth/register", json={
                "name": "Nueva Vendedora",
                "email": "nueva@example.com",
                "password": "long-enough-password",
                "role": "vendedor",
                "purpose": "pos",
            })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._json(response)["user"]["email"], "nueva@example.com")
        self.assertEqual(self._json(response)["token"], "new-account-token")
        subscription_check.assert_not_called()

    def test_admin_login_to_pos_has_lifetime_entitlement_without_paid_subscription(self) -> None:
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
            patch.object(auth_module, "_get_active_subscription") as subscription_check,
        ):
            response = self.client.post(
                "/api/auth/login",
                json={
                    "email": "TEST@example.com",
                    "password": password,
                    "role": "vendedor",
                    "purpose": "pos",
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
        self.assertNotIn("Max-Age", response.headers["Set-Cookie"])
        subscription_check.assert_not_called()
        self.assertEqual(
            user_cursor.execute.call_args.args[1],
            ("test@example.com",),
        )

    def test_existing_admin_session_uses_current_database_role(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = {
            "id": 1,
            "name": "Admin",
            "email": "admin@example.com",
            "role": "vendedor",  # rol histórico de una sesión anterior
            "account_role": "administrador",
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        with (
            auth_module.app.app_context(),
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
        ):
            user = auth_module._get_session_user("old-session-token")
        self.assertEqual(user["role"], "administrador")

    def test_admin_subscription_status_is_lifetime_multilocal_without_database_lookup(self) -> None:
        admin = {"id": 1, "name": "Admin", "email": "admin@example.com", "role": "administrador"}
        with (
            patch.object(auth_module, "_require_user_session", return_value=(admin, None)),
            patch.object(auth_module, "_get_active_subscription") as subscription_check,
        ):
            response = self.client.get("/api/auth/subscription")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._json(response), {
            "active": True,
            "subscription": {"plan_id": "multilocal", "status": "lifetime", "lifetime": True},
        })
        subscription_check.assert_not_called()

    def test_admin_bar_guard_allows_lifetime_access_without_paid_subscription(self) -> None:
        admin = {"id": 1, "name": "Admin", "email": "admin@example.com", "role": "administrador"}
        with (
            auth_module.app.test_request_context("/api/bar/dashboard"),
            patch.object(auth_module, "_require_user_session", return_value=(admin, None)),
            patch.object(auth_module, "_get_active_subscription") as subscription_check,
        ):
            authorized, error = auth_module._require_bar_user()
        self.assertIsNone(error)
        self.assertEqual(authorized["subscription"]["plan_id"], "multilocal")
        self.assertEqual(authorized["subscription"]["status"], "lifetime")
        subscription_check.assert_not_called()

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
        self.client.set_cookie("barrica_session", "cookie-only-token")
        cookie_only = self.client.get("/api/bar/dashboard")
        self.assertEqual(cookie_only.status_code, 401)

        seller_user = {
            "id": 2,
            "name": "Cajero",
            "email": "cajero@barrica.com",
            "role": "vendedor",
        }
        with (
            patch.object(auth_module, "_get_session_user", return_value=seller_user),
            patch.object(auth_module, "_get_active_subscription", return_value={"plan_id": "pro", "status": "active"}),
        ):
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


    def test_pos_keeps_token_in_tab_storage_and_does_not_logout_on_reload(self) -> None:
        html = (Path(auth_module.ROOT) / "bar_app.html").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem(STORAGE_TOKEN_KEY, authToken)", html)
        self.assertIn("No cerrar sesión en pagehide", html)
        self.assertNotIn("window.addEventListener('pagehide', () =>", html)

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

    def _post_authenticated_payment(self, payload: dict[str, Any]) -> Any:
        user = {"id": 1, "name": "Test User", "email": "maria@example.com", "role": "vendedor"}
        with (
            patch.object(auth_module, "_require_user_session", return_value=(user, None)),
            patch.object(auth_module, "_record_test_subscription"),
        ):
            return self.client.post("/api/payments/simulate", json=payload)


    def test_pos_api_rejects_a_valid_session_without_a_subscription(self) -> None:
        user = {"id": 9, "name": "Vendedor Uno", "email": "vendedor@example.com", "role": "vendedor"}
        with (
            patch.object(auth_module, "_get_session_user", return_value=user),
            patch.object(auth_module, "_get_active_subscription", return_value=None),
        ):
            response = self.client.get("/api/bar/dashboard", headers={"Authorization": "Bearer valid-token"})
        self.assertEqual(response.status_code, 402)
        self.assertTrue(self._json(response)["subscription_required"])

    def test_pos_login_requires_an_active_subscription(self) -> None:
        password = "validpassword"
        user_cursor = Mock()
        user_cursor.fetchone.return_value = {
            "id": 9,
            "name": "Vendedor Uno",
            "email": "vendedor@example.com",
            "role": "vendedor",
            "password_hash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("ascii"),
        }
        connection = Mock()
        connection.cursor.return_value = user_cursor
        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_is_login_blocked", return_value=False),
            patch.object(auth_module, "_get_active_subscription", return_value=None),
        ):
            response = self.client.post("/api/auth/login", json={
                "email": "vendedor@example.com", "password": password,
                "role": "vendedor", "purpose": "pos",
            })
        self.assertEqual(response.status_code, 402)
        self.assertTrue(self._json(response)["subscription_required"])
        self.assertNotIn("Set-Cookie", response.headers)

    def test_login_never_creates_an_account_for_an_unknown_email(self) -> None:
        password = "validpassword"
        user_cursor = Mock()
        user_cursor.fetchone.return_value = None
        connection = Mock()
        connection.cursor.return_value = user_cursor
        with (
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
            patch.object(auth_module, "_is_login_blocked", return_value=False),
        ):
            response = self.client.post("/api/auth/login", json={
                "email": "nuevo@example.com", "password": password, "role": "vendedor",
            })
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Set-Cookie", response.headers)
        executed = " ".join(str(call.args[0]) for call in user_cursor.execute.call_args_list)
        self.assertNotIn("INSERT INTO users", executed)
        self.assertNotIn("UPDATE users", executed)

    def test_simulated_payment_activates_subscription_and_returns_receipt(self) -> None:
        user = {"id": 1, "name": "Test User", "email": "maria@example.com", "role": "vendedor"}
        with (
            patch.object(auth_module, "_require_user_session", return_value=(user, None)),
            patch.object(auth_module, "_record_test_subscription") as record,
        ):
            response = self.client.post("/api/payments/simulate", json=self._payment())
        self.assertEqual(response.status_code, 201)
        body = self._json(response)
        self.assertIn("receipt", body)
        self.assertEqual(
            body["subscription"],
            {"plan_id": "pro", "status": "test_active", "trial": False, "trial_days": 30},
        )
        record.assert_called_once_with(1, "pro", body["receipt"]["number"])

    def test_free_trial_is_allowed_once_per_account_and_blocked_on_second_attempt(self) -> None:
        user = {"id": 1, "name": "Test User", "email": "maria@example.com", "role": "vendedor"}
        with (
            patch.object(auth_module, "_require_user_session", return_value=(user, None)),
            patch.object(auth_module, "_has_used_free_trial", return_value=False),
            patch.object(auth_module, "_record_test_subscription") as record,
        ):
            first = self.client.post("/api/payments/simulate", json=self._payment(trial=True))
        self.assertEqual(first.status_code, 201)
        first_body = self._json(first)
        self.assertTrue(first_body["receipt"]["trial"])
        self.assertEqual(first_body["receipt"]["amount"], 0)
        self.assertRegex(first_body["receipt"]["number"], r"^TRIAL-\d{8}-[0-9A-F]{6}$")
        self.assertEqual(first_body["subscription"]["status"], "trial_active")
        record.assert_called_once_with(1, "pro", first_body["receipt"]["number"], is_trial=True)

        with (
            patch.object(auth_module, "_require_user_session", return_value=(user, None)),
            patch.object(auth_module, "_has_used_free_trial", return_value=True),
            patch.object(auth_module, "_record_test_subscription") as record_second,
        ):
            second = self.client.post("/api/payments/simulate", json=self._payment(trial=True))
        self.assertEqual(second.status_code, 409)
        self.assertTrue(self._json(second)["trial_used"])
        record_second.assert_not_called()

    def test_simulated_payment_must_match_the_signed_in_account(self) -> None:
        user = {"id": 1, "name": "Test User", "email": "account@example.com", "role": "vendedor"}
        with patch.object(auth_module, "_require_user_session", return_value=(user, None)):
            response = self.client.post("/api/payments/simulate", json=self._payment())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._json(response)["field"], "email")

    def test_simulated_payment_requires_an_account_session(self) -> None:
        response = self.client.post("/api/payments/simulate", json=self._payment())
        self.assertEqual(response.status_code, 401)
        self.assertIn("sesión", self._json(response)["error"].lower())

    def test_simulated_payment_returns_a_labelled_receipt(self) -> None:
        response = self._post_authenticated_payment(self._payment())

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
        response = self._post_authenticated_payment(
            self._payment(plan="multilocal", currency="USD", amount=1)
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
        response = self._post_authenticated_payment(
            self._payment(card_number="4242424242424242", card_cvv="123", card_expiry="08/29")
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

        for route in ("/app", "/bar_app", "/bar_app.html"):
            app_response = self.client.get(route)
            self.assertEqual(app_response.status_code, 200, route)
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

    def test_saludo_endpoint_returns_flask_api_message(self) -> None:
        response = self.client.get("/api/saludo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._json(response),
            {"mensaje": "¡Hola! Mi API en Flask funciona correctamente"},
        )

    def test_ghost_invoices_are_generated_on_checkout_and_restricted_to_admin(self) -> None:
        auth_module._POS_RUNTIME_STORE["invoices"].clear()
        auth_module._POS_RUNTIME_STORE["active_shift"] = None
        auth_module._POS_RUNTIME_STORE["closed_shifts"].clear()

        seller_user = {"id": 2, "name": "Carlos Cajero", "email": "carlos@barrica.com", "role": "vendedor"}
        admin_user = {"id": 1, "name": "Ana Admin", "email": "admin@barrica.com", "role": "administrador"}

        cursor = Mock()
        cursor.fetchone.return_value = {"id": 1, "label": "Mesa 1 · Salón"}
        cursor.fetchall.return_value = [
            {"product_name": "Negroni", "quantity": 2, "unit_price_cop": 28000},
            {"product_name": "Tabla de Quesos y Madurados", "quantity": 1, "unit_price_cop": 42000},
        ]
        connection = Mock()
        connection.cursor.return_value = cursor

        with (
            patch.object(auth_module, "_get_session_user", return_value=seller_user),
            patch.object(auth_module, "_get_active_subscription", return_value={"plan_id": "pro", "status": "active"}),
            patch.object(auth_module, "_database_connection", return_value=nullcontext(connection)),
        ):
            checkout_res = self.client.post(
                "/api/bar/tables/1/checkout",
                headers={"Authorization": "Bearer seller-token"},
                json={
                    "payment_method": "Efectivo",
                    "cash_received": 100000,
                    "client_name": "Cliente VIP",
                },
            )
            self.assertEqual(checkout_res.status_code, 200)
            checkout_data = self._json(checkout_res)
            self.assertEqual(checkout_data["total_cop"], 98000)
            self.assertIn("invoice", checkout_data)
            invoice = checkout_data["invoice"]
            self.assertEqual(invoice["client"], "Cliente VIP")
            self.assertEqual(invoice["table_label"], "Mesa 1 · Salón")
            self.assertEqual(invoice["cash_change"], 2000)
            self.assertEqual(len(invoice["items"]), 2)

            # El vendedor NO puede ingresar al historial de facturas fantasma
            forbidden_inv = self.client.get(
                "/api/bar/invoices",
                headers={"Authorization": "Bearer seller-token"},
            )
            self.assertEqual(forbidden_inv.status_code, 403)

        # El administrador SÍ puede ingresar al historial y consultar las facturas para reimprimirlas
        with (
            patch.object(auth_module, "_get_session_user", return_value=admin_user),
            patch.object(auth_module, "_get_active_subscription", return_value={"plan_id": "pro", "status": "active"}),
        ):
            admin_inv = self.client.get(
                "/api/bar/invoices",
                headers={"Authorization": "Bearer admin-token"},
            )
            self.assertEqual(admin_inv.status_code, 200)
            inv_list = self._json(admin_inv)["invoices"]
            self.assertEqual(len(inv_list), 1)
            self.assertEqual(inv_list[0]["folio"], invoice["folio"])

    def test_shift_open_and_close_generates_single_consolidated_receipt(self) -> None:
        auth_module._POS_RUNTIME_STORE["invoices"].clear()
        auth_module._POS_RUNTIME_STORE["active_shift"] = None
        auth_module._POS_RUNTIME_STORE["closed_shifts"].clear()

        seller_user = {"id": 2, "name": "Camila Rojas", "email": "camila@barrica.com", "role": "vendedor"}

        with (
            patch.object(auth_module, "_get_session_user", return_value=seller_user),
            patch.object(auth_module, "_get_active_subscription", return_value={"plan_id": "pro", "status": "active"}),
        ):
            open_res = self.client.post(
                "/api/bar/shifts/open",
                headers={"Authorization": "Bearer seller-token"},
                json={
                    "manager_name": "Camila Rojas",
                    "document_type": "CC",
                    "document_number": "1020304050",
                    "phone": "3001234567",
                    "email": "camila@barrica.com",
                    "position": "Encargada de Barra",
                    "initial_cash_cop": 50000,
                },
            )
            self.assertEqual(open_res.status_code, 201)

            # Registrar dos ventas con distintos medios de pago durante el turno
            self.client.post(
                "/api/bar/invoices",
                headers={"Authorization": "Bearer seller-token"},
                json={
                    "table_label": "Mesa 1 · Salón",
                    "payment_method": "Efectivo",
                    "client": "Juan Pérez",
                    "items": [{"product_name": "Negroni", "quantity": 2, "unit_price_cop": 28000}],
                    "total": 56000,
                },
            )
            self.client.post(
                "/api/bar/invoices",
                headers={"Authorization": "Bearer seller-token"},
                json={
                    "table_label": "Mesa 2 · Salón",
                    "payment_method": "Transferencia / Nequi",
                    "client": "María Gómez",
                    "items": [{"product_name": "Cerveza Club Colombia", "quantity": 3, "unit_price_cop": 9000}],
                    "total": 27000,
                },
            )

            close_res = self.client.post(
                "/api/bar/shifts/close",
                headers={"Authorization": "Bearer seller-token"},
                json={},
            )
            self.assertEqual(close_res.status_code, 200)
            receipt = self._json(close_res)["receipt"]
            self.assertEqual(receipt["manager"]["name"], "Camila Rojas")
            self.assertEqual(receipt["manager"]["document_number"], "1020304050")
            self.assertEqual(receipt["total_sales_cop"], 83000)
            self.assertEqual(receipt["total_items_qty"], 5)
            self.assertEqual(receipt["payment_breakdown"]["Efectivo"]["total_cop"], 56000)
            self.assertEqual(receipt["payment_breakdown"]["Transferencia / Nequi"]["total_cop"], 27000)
            self.assertEqual(receipt["expected_cash_in_box_cop"], 106000)

        bar_html = (Path(auth_module.ROOT) / "bar_app.html").read_text(encoding="utf-8")
        for element_id in (
            "ghost-invoice-dialog",
            "shift-receipt-dialog",
            "btn-clientes-sub-invoices",
            "crm-invoices-admin-panel",
            "tab-turno",
            "form-open-shift",
            "btn-close-shift",
        ):
            self.assertIn(f'id="{element_id}"', bar_html)


if __name__ == "__main__":
    unittest.main()


class LocalJsonDemoFrontendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.pos_html = (self.root / "bar_app.html").read_text(encoding="utf-8")
        self.portal_html = (self.root / "Untitled-1.html").read_text(encoding="utf-8")

    def test_pos_local_demo_uses_json_storage_and_exposes_backup_controls(self) -> None:
        self.assertIn("location.protocol === 'file:'", self.pos_html)
        self.assertIn("if (localMode) return localApi(path, options);", self.pos_html)
        self.assertIn("safeSet(localStorage, LOCAL_DB_KEY, JSON.stringify(db))", self.pos_html)
        self.assertIn('id="btn-export-local-json"', self.pos_html)
        self.assertIn('id="btn-import-local-json"', self.pos_html)
        self.assertIn("format: 'barika-local-json'", self.pos_html)
        self.assertIn("['test_active', 'active'].includes(localPlan.status)", self.pos_html)
        self.assertIn("if (!subscription.active) { goToPaymentPage('login', 'basico'); return; }", self.pos_html)
        self.assertIn("Correo o contraseña incorrectos. Crea primero una cuenta local.", self.pos_html)
        self.assertNotIn("status: 'local_demo', started_at", self.pos_html)
        self.assertIn("const lifetimeAdmin = db.sessionUser?.role === 'administrador'", self.pos_html)
        self.assertIn("const role = registering ? 'vendedor'", self.pos_html)
        self.assertIn("if (!authRoute && !subscriptionRoute && !lifetimeAdmin)", self.pos_html)
        self.assertIn("LOCAL_ADMIN_EMAIL = 'admin@gmail.com'", self.pos_html)
        self.assertIn("LOCAL_ADMIN_HASH", self.pos_html)
        self.assertIn("if (ensureLocalAdminAccount(parsed)) safeSet(localStorage, LOCAL_DB_KEY, JSON.stringify(parsed))", self.pos_html)
        self.assertNotIn("id=\"btn-pin-demo\"", self.pos_html)
        self.assertNotIn("local-mode-note", self.pos_html)
        self.assertNotIn("local-mode-warning", self.pos_html)

    def test_local_checkout_activates_only_after_authenticated_simulated_payment(self) -> None:
        self.assertIn("const LOCAL_DEMO_MODE", self.portal_html)
        self.assertIn("const localDemoAuth = async", self.portal_html)
        self.assertIn("const account = db.users.find", self.portal_html)
        self.assertIn("if (!account) throw new Error", self.portal_html)
        self.assertIn("status: 'test_active'", self.portal_html)
        self.assertIn("authUser.email.toLowerCase() !== payload.email.toLowerCase()", self.portal_html)
        self.assertNotIn('id="local-demo-dialog"', self.portal_html)
        self.assertNotIn("status: 'local_demo'", self.portal_html)
        self.assertIn("const role = endpoint === 'register' ? 'vendedor'", self.portal_html)
        self.assertIn("LOCAL_ADMIN_EMAIL = 'admin@gmail.com'", self.portal_html)
        self.assertIn("if (ensureLocalAdminAccount(db)) saveLocalDemoDb(db)", self.portal_html)
        self.assertNotIn("No se cobrará ni se generará una factura", self.portal_html)
        self.assertNotIn("El Modo Demo Local no procesa pagos", self.portal_html)

    def test_windows_launcher_opens_explicit_json_demo_mode(self) -> None:
        launcher = (self.root / "iniciar_demo_local_json.bat").read_text(encoding="utf-8")
        regular_launcher = (self.root / "iniciar_bar_app.bat").read_text(encoding="utf-8")
        self.assertIn("BARIKA_LOCAL_JSON_DEMO=1", launcher)
        self.assertIn("?mode=local", regular_launcher)
