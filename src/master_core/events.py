# Copyright (C) 2019 OpenMotics BV
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
Module to handle Events from the Core
"""

import logging
from master_core.fields import WordField

logger = logging.getLogger('openmotics')


class Event(object):
    class Types(object):
        OUTPUT = 'OUTPUT'
        INPUT = 'INPUT'
        SENSOR = 'SENSOR'
        UNKNOWN = 'UNKNOWN'

    class SensorType(object):
        TEMPERATURE = 'TEMPERATURE'
        HUMIDITY = 'HUMIDITY'
        BRIGHTNESS = 'BRIGHTNESS'
        UNKNOWN = 'UNKNOWN'

    def __init__(self, data):
        self._type = data['type']
        self._action = data['action']
        self._device_nr = data['device_nr']
        self._data = data['data']

    @property
    def type(self):
        type_map = {0: Event.Types.OUTPUT,
                    1: Event.Types.INPUT,
                    2: Event.Types.SENSOR}
        return type_map.get(self._type, Event.Types.UNKNOWN)

    @property
    def data(self):
        if self.type == Event.Types.OUTPUT:
            timer_type = 'NO_TIMER'
            timer_factor = None
            if self._data[1] == 1:
                timer_type = '100_MS'
                timer_factor = 0.1
            elif self._data[1] == 2:
                timer_type = '1_S'
                timer_factor = 1
            elif self._data[2] == 2:
                timer_type = '1_M'
                timer_factor = 60
            return {'output': self._device_nr,
                    'status': self._action == 1,
                    'dimmer_value': self._data[0],
                    'timer_type': timer_type,
                    'timer_factor': timer_factor,
                    'timer_value': Event._word_decode(self._data[2:])}
        if self.type == Event.Types.INPUT:
            return {'input': self._device_nr,
                    'status': self._action == 1}
        if self.type == Event.Types.SENSOR:
            sensor_type = Event.SensorType.UNKNOWN
            sensor_value = None
            if self._action == 0:
                sensor_type = Event.SensorType.TEMPERATURE
                sensor_value = self._data[1]
            elif self._action == 1:
                sensor_type = Event.SensorType.HUMIDITY
                sensor_value = self._data[1]
            elif self._action == 2:
                sensor_type = Event.SensorType.BRIGHTNESS
                sensor_value = Event._word_decode(self._data[0:2])
            return {'sensor': self._device_nr,
                    'type': sensor_type,
                    'value': sensor_value}
        return None

    @staticmethod
    def _word_decode(data):
        return WordField.decode(str(chr(data[0])) + str(chr(data[1])))

    def __str__(self):
        return '{0} ({1})'.format(self.type, self.data)
