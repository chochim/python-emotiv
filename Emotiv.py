# -*- coding: utf-8 -*-
# vim:set et ts=4 sw=4:
#
## Copyright (C) 2012 Ozan Çağlayan <ocaglayan@gsu.edu.tr>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

from __future__ import print_function

import os
import sys

import usb.core
import usb.util

import numpy as np

from bitstring import BitArray

from matplotlib import pyplot as plt
from Crypto.Cipher import AES

class EmotivEPOCNotFoundException(Exception):
    pass

class EmotivEPOC(object):
    def __init__(self, serialNumber=None):
        # Apparently these can change from dongle to dongle
        # so leave this just for reference
        # self.EPOC_VID = 0x1234
        # self.EPOC_PID = 0xED02

        # These seem to be the same for every device
        self.INTERFACE_DESC = "Emotiv RAW DATA"
        self.MANUFACTURER_DESC = "Emotiv Systems Pty Ltd"

        # Channel names
        self.channels = ['Counter', 'Battery',
                        'F3', 'FC5', 'AF3', 'F7', 'T7', 'P7', 'O1',
                        'O2', 'P8', 'T8', 'F8', 'AF4', 'FC6', 'F4',
                        'GyroX', 'GyroY',
                        'Quality F3', 'Quality FC5', 'Quality AF3',
                        'Quality F7', 'Quality T7', 'Quality P7',
                        'Quality 01', 'Quality O2', 'Quality P8',
                        'Quality T8', 'Quality F8', 'Quality AF4',
                        'Quality FC6', 'Quality F4']

        # Battery levels
        self.battery_levels = {247:99,
                               246:97,
                               245:93,
                               244:89,
                               243:85,
                               242:82,
                               241:77,
                               240:72,
                               239:66,
                               238:62,
                               237:55,
                               236:46,
                               235:32,
                               234:20,
                               233:12,
                               232: 6,
                               231: 4,
                               230: 3,
                               229: 2,
                               228: 1,
                               227: 1,
                               226: 1,
                               }
        self.battery_levels.update(dict([(k,100) for k in range(248, 256)]))
        self.battery_levels.update(dict([(k,0)   for k in range(128, 226)]))

        # One can want to specify the dongle with its serial
        self.serialNumber = serialNumber

        # Serial number indexed device map
        self.devices = {}
        self.endpoints = {}

    def _is_emotiv_epoc(self, device):
        """Custom match function for libusb."""
        try:
            manu = usb.util.get_string(device, len(self.MANUFACTURER_DESC),
                                       device.iManufacturer)
        except usb.core.USBError, ue:
            # Skip failing devices as it happens on Raspberry Pi
            if ue.errno == 32:
                return False

        if manu == self.MANUFACTURER_DESC:
            # Found a dongle, check for interface class 3
            for interf in device.get_active_configuration():
                ifStr = usb.util.get_string(device, len(self.INTERFACE_DESC),
                                            interf.iInterface)
                if ifStr == self.INTERFACE_DESC:
                    return True

    def enumerate(self):
        devs = usb.core.find(find_all=True, custom_match=self._is_emotiv_epoc)

        if not devs:
            raise EmotivEPOCNotFoundException("No plugged Emotiv EPOC")

        for dev in devs:
            sn = usb.util.get_string(dev, 32, dev.iSerialNumber)
            cfg = dev.get_active_configuration()

            for interf in dev.get_active_configuration():
                if dev.is_kernel_driver_active(interf.bInterfaceNumber):
                    # Detach kernel drivers and claim through libusb
                    dev.detach_kernel_driver(interf.bInterfaceNumber)
                    usb.util.claim_interface(dev, interf.bInterfaceNumber)

            # 2nd interface is the one we need
            self.endpoints[sn] = usb.util.find_descriptor(interf,
                                 bEndpointAddress=usb.ENDPOINT_IN|2)

            self.devices[sn] = dev
            self.serialNumber = sn

            # FIXME: Default to the first device for now
            break

    def setupEncryption(self, research=True):
        """Generate the encryption key and setup Crypto module.
        The key is based on the serial number of the device and the information
        whether it is a research or consumer device.
        """
        if research:
            self.key = ''.join([self.serialNumber[15], '\x00',
                                self.serialNumber[14], '\x54',
                                self.serialNumber[13], '\x10',
                                self.serialNumber[12], '\x42',
                                self.serialNumber[15], '\x00',
                                self.serialNumber[14], '\x48',
                                self.serialNumber[13], '\x00',
                                self.serialNumber[12], '\x50'])
        else:
            self.key = ''.join([self.serialNumber[15], '\x00',
                                self.serialNumber[14], '\x48',
                                self.serialNumber[13], '\x00',
                                self.serialNumber[12], '\x54',
                                self.serialNumber[15], '\x10',
                                self.serialNumber[14], '\x42',
                                self.serialNumber[13], '\x00',
                                self.serialNumber[12], '\x50'])

        self.cipher = AES.new(self.key)

    def acquireData(self):
        try:
            raw = self.endpoints[self.serialNumber].read(32, timeout=1000)
            bits = BitArray(bytes=self.cipher.decrypt(raw))
        except usb.USBError as e:
            if e.errno == 110:
                print("Make sure that headset is turned on.")
            else:
                print(e)

        if bits[0]:
            print("Battery level: %u" % (self.battery_levels[bits[0:8].uint]))

    def connect(self):
        pass

    def waitForContact(self):
        pass

    def getContactQuality(self):
        pass

    def getBatteryLevel(self):
        pass

    def disconnect(self):
        """Release the claimed interfaces."""

        for dev in self.devices.values():
            cfg = dev.get_active_configuration()

            for interf in dev.get_active_configuration():
                usb.util.release_interface(dev, interf.bInterfaceNumber)

if __name__ == "__main__":

    if len(sys.argv) > 2:
        # Pass a specific S/N
        emotiv = EmotivEPOC(sys.argv[1])
    else:
        emotiv = EmotivEPOC()

    print("Enumerating devices...")
    emotiv.enumerate()
    for k,v in emotiv.devices.iteritems():
        print("Found dongle with S/N: %s" % k)

    emotiv.setupEncryption()

    try:
        while True:
            emotiv.acquireData()
    except KeyboardInterrupt, ke:
        emotiv.disconnect()
        sys.exit(1)
