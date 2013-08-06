#!/usr/bin/python
"""
This file is part of etxd: A daemon for to measure the Exptected Transmission
Count (ETX)

This class defines the protocol for the inter process communication interface
of the ETX daemon. The interface handles request of other processes for the 
local network topology. The requests may originate from this node or from
neighboring nodes that want to determine their 2-hop neighborhood. The
typical program to use this interface is the channel assignment framework
DES-Chan.


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

from syslog import *

from twisted.internet.protocol import ServerFactory
from twisted.protocols.basic import LineOnlyReceiver
from pythonwifi import iwlibs

class EtxIpcFactory(ServerFactory):

    def __init__(self, interfaces):
        self.interfaces = interfaces
        self.protocol = EtxIpcProtocol


class EtxIpcProtocol(LineOnlyReceiver):
    """The protocol supports 5 different request types, which are defined as follows


    - NEIGHBORS [interface]:    returns the IP address for each neighbor, local interface
                                to reach the neighbor, and the link quality. If no interface
                                is specified, all neighbors of all interfaces are returned.

    - MAC:                      returns the MAC address for each neighbor, local interface
                                to reach the neighbor, and the link quality.

    - CHAFT [min_quality]:      returns the IP address for each neighbor and the channel the
                                neighbor can be reached on. If min_quality is supplied, only
                                neighbors with links are returned that satisfy min_quality.                    

    - QUALITY neighbor_ip:      returns the quality (transmission probability) of the link
                                to the specified neighbor. 

    - ETX neighbor_ip:          returns the ETX value of the link to the specified neighbor.

    """
    delimiter = '\n'
    ERR_SYNTAX = "INVALID SYNTAX"

    def connectionMade(self):
        """This functions logs the connection. 

        """
        syslog(LOG_INFO, "Handling IPC connection from %s:%s" % (self.transport.getPeer().host,
                                                  self.transport.getPeer().port))

    def lineReceived(self, request):
        """Handles the supported requests.

        Depending on the particular request, either a bunch of neighbors are returned
        or information about the link quality to a particular neighbor. See above
        for the available request.

        """
        request = request.split()
        if len(request) == 0:
            request.append("")
        # compare commands case-insensitive
        request[0] = request[0].upper()

        if request[0] == "NEIGHBORS":
            # see if additional argument is given, this would be the interface name
            if len(request) > 1:
                # neighborhood information for a specific interface is requested
                if_name = request[1]
                if if_name in self.factory.interfaces.keys():
                    interface = self.factory.interfaces[if_name]
                    # discard interfaces without data
                    if not hasattr(interface, 'data'):
                        return
                    # make sure the data is up to date
                    interface.data.remove_old_probes()
                    for neighbor, quality in interface.data.get_neighbors().items():
                        self.sendLine("%s:%s:%s" % (if_name, neighbor, quality)) 
            else:
                # return neighborhood information for all interfaces
                for interface in self.factory.interfaces.values():
                    # discard interfaces without data
                    if not hasattr(interface, 'data'):
                        continue
                    # make sure the data is up to date
                    interface.data.remove_old_probes()
                    for neighbor, quality in interface.data.get_neighbors().items():
                        self.sendLine("%s:%s:%s" % (interface.name, neighbor, quality)) 

        elif request[0] == "MAC":
            # return neighborhood information for all interfaces
            for interface in self.factory.interfaces.values():
                # discard interfaces without data
                if not hasattr(interface, 'data'):
                    continue
                # make sure the data is up to date
                interface.data.remove_old_probes()
                neighbors = interface.data.get_neighbors()
                for neighbor, quality in neighbors.items():
                    mac = interface.data.get_mac(neighbor)
                    if not mac:
                        syslog(LOG_ERR, "Unable to determine MAC address for %s"
                                        % neighbor)
                        continue
                    self.sendLine("%s|%s|%s" % (interface.name, mac, quality)) 

        elif request[0] == "CHAFT":
            # see if additional argument for the minimum link quality is given
            if len(request) > 1 and \
                    (float(request[1]) >= 0 and float(request[1]) <= 1):
                min_prob = float(request[1])
            else:
                min_prob = 0
            # return neighbors and channel for all interfaces
            for interface in self.factory.interfaces.values():
                # discard interfaces without data
                if not hasattr(interface, 'data'):
                    continue
                # get the channel of the interface
                channel = iwlibs.Wireless(interface.name).getChannel()
                # make sure the data is up to date
                interface.data.remove_old_probes()
                for neighbor, quality in interface.data.get_neighbors().items():
                    if quality >= min_prob:
                        self.sendLine("%s:%d" % (neighbor, channel)) 

        elif request[0] == "QUALITY":
            # see if the neighbor argument is supplied, for which the quality
            # (transmission probability should be returned
            if len(request) < 2:
                # return error message
                self.sendLine(EtxIpcProtocol.ERR_SYNTAX)
            else:
                neighbor = request[1]
                for interface in self.factory.interfaces.values():
                    # discard interfaces without data
                    if not hasattr(interface, 'data'):
                        continue
                    # make sure the data is up to date
                    interface.data.remove_old_probes()
                    if neighbor in interface.data.get_neighbors().keys():
                        quality = interface.data.get_transmission_probability(neighbor)
                        self.sendLine("%s:%s" % (neighbor, quality)) 

        elif request[0] == "ETX":
            # see if the neighbor argument is supplied, for which the ETX values should
            # be returned
            if len(request) < 2:
                # return error message
                self.sendLine(EtxIpcProtocol.ERR_SYNTAX)
            else:
                neighbor = request[1]
                for interface in self.factory.interfaces.values():
                    # discard interfaces without data
                    if not hasattr(interface, 'data'):
                        continue
                    # make sure the data is up to date
                    interface.data.remove_old_probes()
                    if neighbor in interface.data.get_neighbors().keys():
                        etx = interface.data.get_etx(neighbor)
                        self.sendLine("%s:%s" % (neighbor, etx)) 

        else:
            # return error message
            self.sendLine(EtxIpcProtocol.ERR_SYNTAX)
        # close the connection
        self.transport.loseConnection()

