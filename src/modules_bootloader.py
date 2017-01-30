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
Tool to bootload the slave modules (output, dimmer, input and temperature).

@author: fryckbos
"""

import argparse
from ConfigParser import ConfigParser

from serial import Serial

import constants

import master.master_api as master_api
from master.master_communicator import MasterCommunicator
from master.eeprom_controller import EepromFile, EepromAddress

import intelhex
import time
import sys


def create_bl_action(cmd, input):
    """ Create a bootload action, this uses the command and the inputs
    to calculate the crc for the action, the crc is added to input.

    :param cmd: The bootload action (from master_api).
    :type cmd: MasterCommandSpec
    :param input: dict with the inputs for the action.
    :type input: dict
    :returns: tuple of (cmd, input).
    """
    crc = 0

    crc += ord(cmd.action[0])
    crc += ord(cmd.action[1])

    for field in cmd.input_fields:
        if field.name == "literal" and field.encode(None) == "C":
            break

        for byte in field.encode(input[field.name]):
            crc += ord(byte)

    input['crc0'] = crc / 256
    input['crc1'] = crc % 256

    return (cmd, input)


def check_bl_crc(cmd, output):
    """ Check the crc in the response from the master.

    :param cmd: The bootload action (from master_api).
    :type cmd: MasterCommandSpec
    :param output: dict containing the values for the output field.
    :type output: dict
    :returns: True if the crc is valid.
    """
    crc = 0

    crc += ord(cmd.action[0])
    crc += ord(cmd.action[1])

    for field in cmd.output_fields:
        if field.name == "literal" and field.encode(None) == "C":
            break

        for byte in field.encode(output[field.name]):
            crc += ord(byte)

    return output['crc0'] == (crc / 256) and output['crc1'] == (crc % 256)


def get_module_addresses(master_communicator, type):
    """ Get the addresses for the modules of the given type.

    :param master_communicator: used to read the addresses from the master eeprom.
    :type master_communicator: MasterCommunicator
    :param type: the type of the module (o, d, i, t)
    :param type: chr
    :returns: A list containing the addresses of the modules (strings of length 4).
    """
    eeprom_file = EepromFile(master_communicator)
    no_modules = eeprom_file.read([EepromAddress(0, 1, 2)])
    modules = []

    no_input_modules = ord(no_modules[0].bytes[0])
    for i in range(no_input_modules):
        modules.append(eeprom_file.read([EepromAddress(2 + i, 0, 4)])[0].bytes)

    no_output_modules = ord(no_modules[0].bytes[1])
    for i in range(no_output_modules):
        modules.append(eeprom_file.read([EepromAddress(33 + i, 0, 4)])[0].bytes)

    return [module for module in modules if module[0].lower() == type]


def pretty_address(address):
    """ Create a pretty printed version of an address.

    :param address: address string
    :type address: string
    :returns: string with format 'M.x.y.z' where M is in {o, d, i, t} and x,y,z are integers.
    """
    return "%s.%d.%d.%d" % (address[0], ord(address[1]), ord(address[2]), ord(address[3]))


def calc_crc(ihex, blocks):
    """ Calculate the crc for a hex file.

    :param ihex: intelhex file.
    :type ihex: IntelHex
    :param blocks: the number of blocks.
    :type blocks: Integer
    :returns: tuple containing 4 crc bytes.
    """
    sum = 0
    for i in range(64 * blocks - 8):
        sum += ihex[i]

    crc0 = (sum & (255 << 24)) >> 24
    crc1 = (sum & (255 << 16)) >> 16
    crc2 = (sum & (255 << 8)) >> 8
    crc3 = (sum & (255 << 0)) >> 0

    return (crc0, crc1, crc2, crc3)


def check_result(cmd, result):
    """ Raise an exception if the crc for the result is invalid,
    or if the error_code is set in the result.
    """
    if not check_bl_crc(cmd, result):
        raise Exception("Crc check failed on %s" % cmd.action)

    if result.get('error_code', None) != 0:
        raise Exception("%s returned error code %d" % (cmd.action, result['error_code']))


def do_command(master_communicator, action, retry=True):
    """ Execute a command using the master communicator. If the command times out, retry.
    :param master_communicator: Used to communicate with the master.
    :type master_communicator: MasterCommunicator
    :param action: the command to execute.
    :type action: tuple of command, input (generated by create_bl_action).
    :param retry: If the master command should be retried
    :type retry: boolean
    """
    cmd = action[0]
    try:
        check_result(cmd, master_communicator.do_command(*action))
    except Exception as exception:
        print "Got exception while executing command: %s" % exception
        if retry:
            print "Retrying..."
            check_result(cmd, master_communicator.do_command(*action))
        else:
            raise exception

def bootload(master_communicator, address, version, ihex, crc, blocks, logger):
    """ Bootload 1 module.

    :param master_communicator: Used to communicate with the master.
    :type master_communicator: MasterCommunicator
    :param address: Address for the module to bootload
    :type address: string of length 4
    :param version: The new version
    :type version: tuple of 3 integers
    :param ihex: The hex file
    :type ihex: IntelHex
    :param crc: The crc for the hex file
    :type crc: tuple of 4 bytes
    :param blocks: The number of blocks to write
    :type blocks:
    """
    logger("Going to bootloader")
    try:
        do_command(master_communicator, create_bl_action(master_api.modules_goto_bootloader(),
                                                         {"addr" : address, "sec" : 5}), False)
    except:
        print "No response on goto bootloader: OK"

    time.sleep(1)

    logger("Setting the firmware crc")
    do_command(master_communicator,
               create_bl_action(master_api.modules_new_crc(),
                                {"addr" : address, "ccrc0": crc[0], "ccrc1": crc[1],
                                 "ccrc2": crc[2], "ccrc3": crc[3]}))

    logger("Setting new firmware version")
    do_command(master_communicator, create_bl_action(master_api.modules_new_firmware_version(),
                                                     {"addr" : address, "f1n": version[0],
                                                      "f2n": version[1], "f3n": version[2]}))

    try:
        logger("Going to long mode")
        master_communicator.do_command(master_api.change_communication_mode_to_long())

        logger("Writing firmware data")
        for i in range(blocks):
            bytes = ""
            for j in range(64):
                if i == blocks - 1 and j >= 56:
                    # The first 8 bytes (the jump) is placed at the end of the code.
                    bytes += chr(ihex[j - 56])
                else: 
                    bytes += chr(ihex[i*64 + j])

            print "Block %d" % i
            do_command(master_communicator,
                       create_bl_action(master_api.modules_update_firmware_block(),
                                        {"addr" : address, "block" : i, "bytes": bytes}))
    finally:
        logger("Going to short mode")
        master_communicator.do_command(master_api.change_communication_mode_to_short())

    logger("Integrity check")
    do_command(master_communicator, create_bl_action(master_api.modules_integrity_check(),
                                                     {"addr" : address}))

    logger("Going to application")
    do_command(master_communicator, create_bl_action(master_api.modules_goto_application(),
                                                     {"addr" : address}))

    time.sleep(2)

    logger("Verifying firmware")
    do_command(master_communicator, create_bl_action(master_api.modules_get_version(),
                                                     {"addr": address}))


def bootload_modules(type, filename, version, verbose, logger):
    """ Bootload all modules of the given type with the firmware in the given filename.

    :param type: Type of the modules (o, d, i, t, c)
    :type type: chr
    :param filename: The filename for the hex file to load
    :type filename: string
    :param version: The new version that is loaded
    :type version: tuple of 3 integers
    :param verbose: If true the serial communication is printed.
    :param verbose: boolean
    """
    config = ConfigParser()
    config.read(constants.get_config_file())

    port = config.get('OpenMotics', 'controller_serial')

    master_serial = Serial(port, 115200)
    master_communicator = MasterCommunicator(master_serial, verbose=verbose)
    master_communicator.start()

    addresses = get_module_addresses(master_communicator, type)

    blocks = 922 if type == 'c' else 410
    ihex = intelhex.IntelHex(filename)
    crc = calc_crc(ihex, blocks)

    for address in addresses:
        logger("Bootloading module %s" % pretty_address(address))
        bootload(master_communicator, address, version, ihex, crc, blocks, logger)


def main():
    """ The main function. """
    parser = argparse.ArgumentParser(description='Tool to bootload the slave modules '
                                                 '(output, dimmer, input and temperature).')

    parser.add_argument('-t', '--type', dest='type', choices=['o', 'd', 'i', 't', 'c'],
                        required=True, help='the type of module to bootload (choices: o, d, i, t, c)')
    parser.add_argument('-f', '--file', dest='file', required=True,
                        help='the filename of the hex file to bootload')
    parser.add_argument('-v', '--version', dest='version', required=True,
                        help='the version number for the new firmware (format: x.y.z)')

    parser.add_argument('-l', '--log', dest='log', required=False)

    parser.add_argument('-V', '--verbose', dest='verbose', action='store_true',
                        help='show the serial output')

    args = parser.parse_args()

    version = [int(x) for x in args.version.split(".")]

    log_file = None
    if log is not None:
        log_file = open(log, 'a')
        logger = lambda msg: log_file.write('%s\n' % msg)
    else:
        logger = lambda msg: sys.stdout.write('%s\n' % msg)

    bootload_modules(args.type, args.file, version, args.verbose, logger)

    if log_file is not None:
        log_file.close()


if __name__ == '__main__':
    main()
