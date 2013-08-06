#!/usr/bin/python
"""
This file is part of etxd: A daemon for to measure the Exptected Transmission
Count (ETX)

This file contains the simple datagram-based protocol to send and receive
probes. Probes are sent as a broadcast so potentially they reach all neighbors
in the transmission range. Each probe contains the MAC address of the sender
and information about our neighbors and the corresponding link qualities.


Authors:    Matthias Philipp <mphilipp@inf.fu-berlin.de>,
            Felix Juraschek <fjuraschek@gmail.com>

Copyright 2008-2013, Freie Universitaet Berlin (FUB). All rights reserved.

These sources were developed at the Freie Universitaet Berlin, 
Computer Systems and Telematics / Distributed, embedded Systems (DES) group 
(http://cst.mi.fu-berlin.de, http://www.des-testbed.net)
-------------------------------------------------------------------------------
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see http://www.gnu.org/licenses/ .
--------------------------------------------------------------------------------
For further information and questions please use the web site
       http://www.des-testbed.net
       
"""

import pickle
import netifaces
from syslog import *
from socket import SOL_SOCKET, SO_BROADCAST
from twisted.internet.protocol import DatagramProtocol

class EtxProbeProtocol(DatagramProtocol):

    DEBUG = False

    def __init__(self, if_name, own_ip, etx_data):
        self.if_name = if_name
        self.own_ip = own_ip
        self.etx_data = etx_data

    def startProtocol(self):
        # set broadcast socket option
        self.transport.socket.setsockopt(SOL_SOCKET, SO_BROADCAST, True)

    def datagramReceived(self, datagram, addr):
        """This functions handles incoming probes.

        Each correctly received probe is unpickled, and the corresponding MAC and
        IP are stored. The neighbor information is stored as receveived and the
        timestamp for the sender is updated.
        
        """
        # get the ip of the originating neighbor
        neighbor_ip = addr[0]
        # ignore probes from myself
        if neighbor_ip != self.own_ip:
            # deserialize the message
            neighbor_mac, data = pickle.loads(datagram)
            # store mac <-> ip association
            self.etx_data.set_mac(neighbor_ip, neighbor_mac)
            # store etx data
            self.etx_data.set_neighbor_info(neighbor_ip, data)
            # add timestamp to the list
            self.etx_data.add_timestamp(neighbor_ip)
            if EtxProbeProtocol.DEBUG:
                # remove old probes
                self.etx_data.remove_old_probes()
                syslog(LOG_DEBUG, "%s" % self.etx_data.get_debug_info(neighbor_ip))

    def send_probe(self):
        """This functions generates a probe and sends it out as a broadcast.

        The probe consists of our MAC address and our information about our neighbors.
        
        """
        if EtxProbeProtocol.DEBUG:
            syslog(LOG_DEBUG, "Sending probe to %s:%s" % (self.transport.getHost().host,
                                                          self.transport.getHost().port))
        # get mac address of this interface
        mac = netifaces.ifaddresses(self.if_name)[netifaces.AF_LINK][0]['addr']
        # make sure the probe data is up to date
        self.etx_data.remove_old_probes()
        data = self.etx_data.get_probe_data()
        # serialize tuple with mac and data 
        datagram = pickle.dumps((mac, data))
        # broadcast the probe
        self.transport.write(datagram, (self.transport.getHost().host,
                                        self.transport.getHost().port))

