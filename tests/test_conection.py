from unittest import TestCase
from unittest.mock import Mock, patch

import bcrypt

import conection


class AdminPasswordResetTests(TestCase):
    def test_reset_hashes_password_sets_admin_role_and_revokes_sessions(self) -> None:
        password = "SecureTestPassword2026*"
        cursor = Mock()
        cursor.fetchone.return_value = (42,)
        connection = Mock()
        connection.cursor.return_value = cursor

        with (
            patch.object(conection.getpass, "getpass", side_effect=[password, password]),
            patch.object(conection, "get_connection", return_value=connection),
        ):
            conection.actualizar_contrasena_admin()

        self.assertEqual(cursor.execute.call_args_list[0].args[1], ("admin@gmail.com",))
        update_args = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(update_args[1:], ("administrador", 42))
        self.assertTrue(
            bcrypt.checkpw(password.encode("utf-8"), update_args[0].encode("ascii"))
        )
        self.assertEqual(
            cursor.execute.call_args_list[2].args[1],
            (42,),
        )
        connection.commit.assert_called_once_with()
        cursor.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_password_mismatch_does_not_connect_to_database(self) -> None:
        with (
            patch.object(conection.getpass, "getpass", side_effect=["PasswordOne2026*", "PasswordTwo2026*"]),
            patch.object(conection, "get_connection") as get_connection,
            self.assertRaisesRegex(ValueError, "no coinciden"),
        ):
            conection.actualizar_contrasena_admin()

        get_connection.assert_not_called()

    def test_reset_creates_missing_admin_account_and_revokes_sessions(self) -> None:
        password = "SecureTestPassword2026*"
        cursor = Mock()
        cursor.fetchone.return_value = None
        cursor.lastrowid = 99
        connection = Mock()
        connection.cursor.return_value = cursor

        with (
            patch.object(conection.getpass, "getpass", side_effect=[password, password]),
            patch.object(conection, "get_connection", return_value=connection),
        ):
            conection.actualizar_contrasena_admin()

        insert_args = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(insert_args[0], "Administrador Barika")
        self.assertEqual(insert_args[1], "admin@gmail.com")
        self.assertTrue(bcrypt.checkpw(password.encode("utf-8"), insert_args[2].encode("ascii")))
        self.assertEqual(insert_args[3], "administrador")
        self.assertEqual(cursor.execute.call_args_list[2].args[1], (99,))
        connection.commit.assert_called_once_with()
        cursor.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_short_password_does_not_connect_to_database(self) -> None:
        with (
            patch.object(conection.getpass, "getpass", side_effect=["short", "short"]),
            patch.object(conection, "get_connection") as get_connection,
            self.assertRaisesRegex(ValueError, "12 y 72 bytes"),
        ):
            conection.actualizar_contrasena_admin()
        get_connection.assert_not_called()
