# Copyright (C) 2019 OpenMotics BVBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Tests for the users module.

@author: fryckbos
"""

import unittest
import time
import os
from threading import Lock

from gateway.users import UserController


class UserControllerTest(unittest.TestCase):
    """ Tests for UserController. """

    def setUp(self):  # pylint: disable=C0103
        """ Run before each test. """
        self._db = "test.user.{0}.db".format(time.time())
        if os.path.exists(self._db):
            os.remove(self._db)

    def tearDown(self):  # pylint: disable=C0103
        """ Run after each test. """
        if os.path.exists(self._db):
            os.remove(self._db)

    def _get_controller(self):
        """ Get a UserController using FILE. """
        return UserController(self._db, Lock(), {'username': 'om', 'password': 'pass'}, 10)

    def test_empty(self):
        """ Test an empty database. """
        user_controller = self._get_controller()
        success, data = user_controller.login('fred', 'test')
        self.assertFalse(success)
        self.assertEquals(data, 'invalid_credentials')
        self.assertEquals(False, user_controller.check_token('some token 123'))
        self.assertEquals(None, user_controller.get_role('fred'))

        success, data = user_controller.login('om', 'pass')
        self.assertTrue(success)
        self.assertNotEquals(None, data)

        self.assertTrue(user_controller.check_token(data))

    def test_terms(self):
        """ Tests acceptance of the terms """
        user_controller = self._get_controller()
        user_controller.create_user('om2', 'pass', 'admin', True)
        success, data = user_controller.login('om2', 'pass')
        self.assertFalse(success)
        self.assertEqual(data, 'terms_not_accepted')
        success, data = user_controller.login('om2', 'pass', accept_terms=True)
        self.assertTrue(success)
        self.assertIsNotNone(data)
        success, data = user_controller.login('om2', 'pass')
        self.assertTrue(success)
        self.assertIsNotNone(data)

    def test_all(self):
        """ Test all methods of UserController. """
        user_controller = self._get_controller()
        user_controller.create_user('fred', 'test', 'admin', True)

        self.assertEquals(False, user_controller.login('fred', '123', accept_terms=True)[0])
        self.assertFalse(user_controller.check_token('blah'))

        token = user_controller.login('fred', 'test', accept_terms=True)[1]
        self.assertNotEquals(None, token)

        self.assertTrue(user_controller.check_token(token))
        self.assertFalse(user_controller.check_token('blah'))

        self.assertEquals('admin', user_controller.get_role('fred'))

    def test_token_timeout(self):
        """ Test the timeout on the tokens. """
        user_controller = UserController(self._db, Lock(), {'username': 'om', 'password': 'pass'}, 3)

        token = user_controller.login('om', 'pass')[1]
        self.assertNotEquals(None, token)
        self.assertTrue(user_controller.check_token(token))

        time.sleep(4)

        self.assertFalse(user_controller.check_token(token))

        token = user_controller.login('om', 'pass')[1]
        self.assertNotEquals(None, token)
        self.assertTrue(user_controller.check_token(token))

    def test_timeout(self):
        """ Test logout. """
        user_controller = UserController(self._db, Lock(), {'username': 'om', 'password': 'pass'}, 3)

        token = user_controller.login('om', 'pass')[1]
        self.assertNotEquals(None, token)
        self.assertTrue(user_controller.check_token(token))

        user_controller.logout(token)
        self.assertFalse(user_controller.check_token(token))

    def test_get_usernames(self):
        """ Test getting all usernames. """
        user_controller = self._get_controller()
        self.assertEquals(['om'], user_controller.get_usernames())

        user_controller.create_user('test', 'test', 'admin', True)
        self.assertEquals(['om', 'test'], user_controller.get_usernames())

    def test_remove_user(self):
        """ Test removing a user. """
        user_controller = self._get_controller()
        self.assertEquals(['om'], user_controller.get_usernames())

        user_controller.create_user('test', 'test', 'admin', True)

        token = user_controller.login('test', 'test', accept_terms=True)[1]
        self.assertTrue(user_controller.check_token(token))

        user_controller.remove_user('test')

        self.assertFalse(user_controller.check_token(token))
        self.assertEquals(['om'], user_controller.get_usernames())

        try:
            user_controller.remove_user('om')
            self.fail('Should have raised exception !')
        except Exception as exception:
            self.assertEquals('Cannot delete last admin account', str(exception))

    def test_case_insensitive(self):
        """ Test the case insensitivity of the username. """
        user_controller = self._get_controller()

        user_controller.create_user('TEST', 'test', 'admin', True)

        token = user_controller.login('test', 'test', accept_terms=True)[1]
        self.assertTrue(user_controller.check_token(token))

        token = user_controller.login('TesT', 'test', accept_terms=True)[1]
        self.assertTrue(user_controller.check_token(token))

        self.assertEquals('invalid_credentials', user_controller.login('test', 'Test')[1])

        self.assertEquals(['om', 'test'], user_controller.get_usernames())


if __name__ == '__main__':
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
