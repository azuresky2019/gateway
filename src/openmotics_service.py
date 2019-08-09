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
The main module for the OpenMotics
"""

import logging
import time

from bus.om_bus_service import MessageService
from bus.om_bus_client import MessageClient
from bus.om_bus_events import Events
from platform_utils import System
System.import_eggs()

from serial import Serial
from signal import signal, SIGTERM
from ConfigParser import ConfigParser
from threading import Thread, Lock


import constants

from serial_utils import RS485

from gateway.webservice import WebInterface, WebService
from gateway.gateway_api import GatewayApi
from gateway.users import UserController
from gateway.metrics import MetricsController
from gateway.metrics_collector import MetricsCollector
from gateway.metrics_caching import MetricsCacheController
from gateway.config import ConfigurationController
from gateway.scheduling import SchedulingController
from gateway.pulses import PulseCounterController
from gateway.observer import Observer

from master.eeprom_controller import EepromController, EepromFile
from master.eeprom_extension import EepromExtension
from master.maintenance import MaintenanceService
from master.master_communicator import MasterCommunicator
from master.passthrough import PassthroughService

from power.power_communicator import PowerCommunicator
from power.power_controller import PowerController

from plugins.base import PluginController


def setup_logger():
    """ Setup the OpenMotics logger. """
    logger = logging.getLogger("openmotics")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def log(message):
    logger = logging.getLogger("openmotics")
    logger.info(message)


def led_driver(message_client, master_communicator, power_communicator):
    """
    Blink the serial leds if necessary.
    :type message_client: bus.om_bus_client.MessageClient
    :type master_communicator: master.master_communicator.MasterCommunicator
    :type power_communicator: power.power_communicator.PowerCommunicator
    """
    master = (0, 0)
    power = (0, 0)

    while True:
        new_master = (master_communicator.get_bytes_read(), master_communicator.get_bytes_written())
        new_power = (power_communicator.get_bytes_read(), power_communicator.get_bytes_written())

        if master[0] != new_master[0] or master[1] != new_master[1]:
            message_client.send_event(Events.SERIAL_ACTIVITY, 5)
        if power[0] != new_power[0] or power[1] != new_power[1]:
            message_client.send_event(Events.SERIAL_ACTIVITY, 4)

        master = new_master
        power = new_power
        time.sleep(0.1)


class OpenmoticsService(object):

    def __init__(self):
        self._message_client = MessageClient('openmotics_service')

    def start(self):
        """ Main function. """
        log('Starting OM core service...')

        config = ConfigParser()
        config.read(constants.get_config_file())

        defaults = {'username': config.get('OpenMotics', 'cloud_user'),
                    'password': config.get('OpenMotics', 'cloud_pass')}
        controller_serial_port = config.get('OpenMotics', 'controller_serial')
        passthrough_serial_port = config.get('OpenMotics', 'passthrough_serial')
        power_serial_port = config.get('OpenMotics', 'power_serial')
        gateway_uuid = config.get('OpenMotics', 'uuid')

        config_lock = Lock()
        user_controller = UserController(constants.get_config_database_file(), config_lock, defaults, 3600)
        config_controller = ConfigurationController(constants.get_config_database_file(), config_lock)

        controller_serial = Serial(controller_serial_port, 115200)
        power_serial = RS485(Serial(power_serial_port, 115200, timeout=None))

        master_communicator = MasterCommunicator(controller_serial)
        eeprom_controller = EepromController(
            EepromFile(master_communicator),
            EepromExtension(constants.get_eeprom_extension_database_file())
        )

        if passthrough_serial_port:
            passthrough_serial = Serial(passthrough_serial_port, 115200)
            passthrough_service = PassthroughService(master_communicator, passthrough_serial)
            passthrough_service.start()

        power_controller = PowerController(constants.get_power_database_file())
        power_communicator = PowerCommunicator(power_serial, power_controller)

        pulse_controller = PulseCounterController(
            constants.get_pulse_counter_database_file(),
            master_communicator,
            eeprom_controller
        )

        observer = Observer(master_communicator, self._message_client)
        gateway_api = GatewayApi(master_communicator, power_communicator, power_controller, eeprom_controller, pulse_controller, self._message_client, observer, config_controller)

        observer.set_gateway_api(gateway_api)

        scheduling_controller = SchedulingController(constants.get_scheduling_database_file(), config_lock, gateway_api)

        maintenance_service = MaintenanceService(gateway_api, constants.get_ssl_private_key_file(),
                                                 constants.get_ssl_certificate_file())

        web_interface = WebInterface(user_controller, gateway_api, maintenance_service, self._message_client,
                                     config_controller, scheduling_controller)

        scheduling_controller.set_webinterface(web_interface)

        # Plugins
        plugin_controller = PluginController(web_interface, config_controller)
        web_interface.set_plugin_controller(plugin_controller)
        gateway_api.set_plugin_controller(plugin_controller)

        # Metrics
        metrics_cache_controller = MetricsCacheController(constants.get_metrics_database_file(), Lock())
        metrics_collector = MetricsCollector(gateway_api, pulse_controller)
        metrics_controller = MetricsController(plugin_controller, metrics_collector, metrics_cache_controller, config_controller, gateway_uuid)
        self._message_client.add_event_handler(metrics_controller.event_receiver)
        metrics_collector.set_controllers(metrics_controller, plugin_controller)
        metrics_controller.add_receiver(metrics_controller.receiver)
        metrics_controller.add_receiver(web_interface.distribute_metric)

        plugin_controller.set_metrics_controller(metrics_controller)
        plugin_controller.set_metrics_collector(metrics_collector)
        web_interface.set_metrics_collector(metrics_collector)
        web_interface.set_metrics_controller(metrics_controller)

        web_service = WebService(web_interface, config_controller)
        plugin_controller.set_webservice(web_service)

        observer.subscribe_master(Observer.MasterEvents.INPUT_TRIGGER, metrics_collector.on_input)
        observer.subscribe_master(Observer.MasterEvents.INPUT_TRIGGER, plugin_controller.process_input_status)
        observer.subscribe_master(Observer.MasterEvents.ON_OUTPUTS, metrics_collector.on_output)
        observer.subscribe_master(Observer.MasterEvents.ON_OUTPUTS, plugin_controller.process_output_status)
        observer.subscribe_master(Observer.MasterEvents.ON_SHUTTER_UPDATE, plugin_controller.process_shutter_status)
        observer.subscribe_events(web_interface.process_observer_event)

        led_thread = Thread(target=led_driver, args=(self._message_client, master_communicator, power_communicator))
        led_thread.setName("Serial led driver thread")
        led_thread.daemon = True
        led_thread.start()

        master_communicator.start()
        observer.start()
        power_communicator.start()
        metrics_controller.start()
        scheduling_controller.start()
        metrics_collector.start()
        web_service.start()
        gateway_api.start()
        plugin_controller.start()

        signal_request = {'stop': False}

        def stop(signum, frame):
            """ This function is called on SIGTERM. """
            _ = signum, frame
            log('Stopping OM core service...')
            web_service.stop()
            metrics_collector.stop()
            metrics_controller.stop()
            plugin_controller.stop()
            log('Stopping OM core service... Done')
            signal_request['stop'] = True

        signal(SIGTERM, stop)
        log('Starting OM core service... Done')
        while not signal_request['stop']:
            time.sleep(1)


if __name__ == "__main__":
    setup_logger()
    log("Starting OpenMotics service")

    # TODO: move message service to separate process
    message_service = MessageService()
    message_service.start()

    openmotics_service = OpenmoticsService()
    openmotics_service.start()







