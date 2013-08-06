#!/usr/bin/python
"""
This file is part of etxd: A daemon for to measure the Exptected Transmission
Count (ETX)

This class defines a tiny web server to serve requests for the node's
neighbor list. The web server is configured in etxd.py to listen on the
ethernet interface of the node. This server is used by the Testbed 
Management System (TBMS) to retrieve a snapshot of the network toplogoy.


Authors:    Matthias Philipp <mphilipp@inf.fu-berlin.de>,
            Felix Juraschek <fjuraschek@gmail.com>

Copyright 2008- Freie Universitaet Berlin (FUB). All rights reserved.

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

from twisted.web import resource
import simplejson
import time

class EtxWebServer(resource.Resource):

    isLeaf = True

    def __init__(self, interfaces, hostname):
        self.interfaces = interfaces
        self.hostname = hostname

    def render_GET(self, request):
        """This functions handles the GET requests by returning a list of
        neighbors.

        All neighbors are returned, regardless via which interface they
        are reachable. For each neighbor, its MAC adress, the link
        quality (ETX), and the local interface the neighbor can be
        reached with is returned.
        
        """
        # initialize dictionary to assemble all neighbors
        ret_val = { 
            "node": self.hostname,
            "time": time.time(),
            "neighbors": []
        }

        # return neighborhood information for all interfaces
        for interface in self.interfaces.values():
            # discard interfaces without data
            if not hasattr(interface, 'data'):
                continue
            # make sure the data is up to date
            interface.data.remove_old_probes()
            neighbors = interface.data.get_neighbors()
            for neighbor, quality in neighbors.items():
                mac = interface.data.get_mac(neighbor)
                # ignore the item if we cannot determine the corresponding MAC
                if not mac:
                    syslog(LOG_ERR, "Unable to determine MAC address for %s"
                                    % neighbor)
                    continue
                # append the neighbor to the return dictionary
                ret_val["neighbors"].append({
                    "if_name": interface.name,
                    "mac_address": mac,
                    "quality": quality
                })
        return simplejson.dumps(ret_val) + "\n"

