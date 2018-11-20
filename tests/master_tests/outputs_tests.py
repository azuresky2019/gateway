# Copyright (C) 2016 OpenMotics BVBA
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
Tests for the outputs module.
"""

import unittest
import time

from master.outputs import OutputStatus


class OutputStatusTest(unittest.TestCase):
    """ Tests for OutputStatus. """

    def test_update(self):
        """ Test for partial_update and full_update"""
        outputs = [{'id': 1, 'name': 'light1', 'floor_level': 1, 'light': 1,
                    'type': 'D', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                    'max_power': 1, 'status': 1, 'dimmer': 10},
                   {'id': 2, 'name': 'light2', 'floor_level': 2, 'light': 1,
                    'type': 'D', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                    'max_power': 1, 'status': 0, 'dimmer': 20},
                   {'id': 3, 'name': 'light1', 'floor_level': 1, 'light': 0,
                    'type': 'O', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                    'max_power': 1, 'status': 0, 'dimmer': 0}]
        status = OutputStatus(1)
        status.full_update(outputs)

        status.partial_update([])  # Everything is off
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(10, status.get_outputs()[0]['dimmer'])
        self.assertEquals(0, status.get_outputs()[1]['status'])
        self.assertEquals(20, status.get_outputs()[1]['dimmer'])
        self.assertEquals(0, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])

        status.partial_update([(3, 0), (2, 1)])
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(10, status.get_outputs()[0]['dimmer'])
        self.assertEquals(1, status.get_outputs()[1]['status'])
        self.assertEquals(1, status.get_outputs()[1]['dimmer'])
        self.assertEquals(1, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])

        update = [{'id': 1, 'name': 'light1', 'floor_level': 1, 'light': 1,
                   'type': 'D', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                   'max_power': 1, 'status': 0, 'dimmer': 50},
                  {'id': 2, 'name': 'light2', 'floor_level': 2, 'light': 1,
                   'type': 'D', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                   'max_power': 1, 'status': 0, 'dimmer': 80},
                  {'id': 3, 'name': 'light1', 'floor_level': 1, 'light': 0,
                   'type': 'O', 'controller_out': 1, 'timer': 200, 'ctimer': 200,
                   'max_power': 1, 'status': 1, 'dimmer': 0}]

        status.full_update(update)
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(50, status.get_outputs()[0]['dimmer'])
        self.assertEquals(0, status.get_outputs()[1]['status'])
        self.assertEquals(80, status.get_outputs()[1]['dimmer'])
        self.assertEquals(1, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])

    def test_should_refresh(self):
        """ Test for should_refresh. """
        status = OutputStatus(100)
        status.full_update([])
        self.assertFalse(status.should_refresh())

        status = OutputStatus(0.001)
        status.full_update([])
        time.sleep(0.01)
        self.assertTrue(status.should_refresh())


if __name__ == "__main__":
    unittest.main()
