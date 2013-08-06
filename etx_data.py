#!/usr/bin/python
"""
This file is part of etxd: A daemon for to measure the Exptected Transmission
Count (ETX)

This class functions as the storage for all information about our neighbors for
a particular interface. Based on the received probes, the transmission
probability and the corresponding ETX values can be calculated. A clean-up
mechanism can be triggered to remove obsolete information.  

The class follows a lazy implementation where incoming data from received probes is
first saved as it is. The transmission probabilities and ETX values are 
calculated on demand only, thus ensuring their freshness. 

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

import time

class EtxData():

    # configured in etxd.py
    WINDOW = None
    INTERVAL = None

    def __init__(self, ip_address, neighbor_probes=None,
                 received_probes=None):
        """ Constructor:

        ip_address - the IP address of the associated interface
        neighbor_probes - number of received probes from the neighbors' neighbors 
        received_probes - arrival times of received probes per neighbor

        """
        self.ip_address = ip_address
        # initialize our custom ARP cache
        self._mac_addresses = {}
        # _neighbor_probes keeps the number of received probes from the
        # neighbors' neighbors 
        # _neighbor_probes[originator][originators' neighbor] = number of
        # received probes
        if neighbor_probes is None:
            # the empty dict is intentionally not given as default parameter
            # because python evaluates default parameters only once when it
            # defines the function
            self._neighbor_probes = dict()
        else:
            self._neighbor_probes = neighbor_probes
        # _received_probes keeps a list of arival times of the probe messages
        # from a particular neighbor during the last window time 
        # _received_probes[neighbor] = [timestamp, ...]
        if received_probes is None:
            self._received_probes = dict()
        else:
            self._received_probes = received_probes


    def __repr__(self):
        return "EtxData(%s, %r, %r)" % (self.ip_address, self._neighbor_probes,
                                        self._received_probes)


    def set_neighbor_info(self, neighbor, data):
        """Sets the neighborhood information of the given neighbor.

        """
        self._neighbor_probes[neighbor] = data


    def add_timestamp(self, neighbor, timestamp=None):
        """Adds a timestamp, which indicates a successfully received probe, for
        the given neighbor to the internal data structure.
        The optional timestamp argument allows to use a different reference time
        than the current time, which is the default.

        """
        # use current time, if timestamp not given
        if timestamp == None:
            timestamp = time.time()
        # prepare data structure if first entry for that neighbor
        if neighbor not in self._received_probes.keys():
            self._received_probes[neighbor] = list()
        # append timestamp
        self._received_probes[neighbor].append(timestamp)


    def remove_old_probes(self, timestamp=None):
        """Removes all probes that have been received before the last window
        time from the internal data structures.
        The optional timestamp argument allows to use a different reference time
        than the current time, which is the default.

        """
        # use current time, if timestamp not given
        if timestamp == None:
            timestamp = time.time()
        for neighbor in self._received_probes.keys():
            # remove all timestamps that are older than window size
            while len(self._received_probes[neighbor]) > 0 and self._received_probes[neighbor][0] + EtxData.WINDOW < timestamp:
               del self._received_probes[neighbor][0] 
            # if we have not received any probes during the last window size,
            # then the probe information from that neighbor is also out-dated
            if len(self._received_probes[neighbor]) == 0 and neighbor in self._neighbor_probes.keys():
                del self._neighbor_probes[neighbor]
                # also remove the now unsued key from the dictionary
                del self._received_probes[neighbor]


    def get_transmission_probability(self, neighbor):
        """Returns the probability that a packet is successfully transmitted to
        the specified neighbor and the corresponding ACK packet is received.

        """
        # probability that a data packet successfully arrives at the recipient
        df = self._get_forward_ratio(neighbor)
        # probability that the ACK packet is successfully received
        dr = self._get_reverse_ratio(neighbor)
        # probability of a successful transmission
        return df * dr


    def get_etx(self, neighbor):
        """Returns the number of expected transmissions that are needed to
        successfully transmit a packet to the neighbor and receive the
        corresponding ACK packet.

        """
        p = self.get_transmission_probability(neighbor)
        if p == 0:
            return -1
        else:
            return 1 / p

    
    def get_probe_data(self):
        """Returns dictionary that contains the number of probes that we
        received from each neighbor and the number of probes that he received
        from us during the last window period for each neighbor.

        """
        probe_data = dict()
        for neighbor in self._received_probes.keys():
            # for each neighbor we send the number of probes that we received
            # from him and the number of probes that he received from us 
            # _get_num_probes_recv_from_me(neighbor)
            # _get_num_probes_recv_from_neighbor(neighbor)
            probe_data[neighbor] = (self._get_num_probes_recv_from_neighbor(neighbor),
                                    self._get_num_probes_recv_from_me(neighbor))
        return probe_data
   

    def get_neighbors(self, etx=False):
        """Returns a dictionary that contains the transmission probability for
        each neighbor. If the optional agument etx is True, the etx value is
        used instead of transmission probability.

        """
        neighbors = dict()
        for neighbor in self._received_probes.keys():
            if etx:
                etx_value = self.get_etx(neighbor)
                if etx_value > 0:
                    neighbors[neighbor] = etx_value
            else:
                prob_value = self.get_transmission_probability(neighbor)
                if prob_value > 0:
                    neighbors[neighbor] = prob_value
        return neighbors


    def get_debug_info(self, neighbor):
        """Returns a string containing the forward and reverse delivery ratio
        for the specified neighbor.

        """
        info = "%s - %s: " % (self.ip_address, neighbor)
        received = self._get_num_probes_recv_from_neighbor(neighbor)
        sent = self._get_num_probes_recv_from_me(neighbor)
        expected = self._get_num_exp_probes()
        info += "reverse %s/%s, dr=%s, " % (received, expected,
                                            self._get_reverse_ratio(neighbor))
        info += "forward %s/%s, df=%s, " % (sent, expected,
                                            self._get_forward_ratio(neighbor))
        return info


    def set_mac(self, ip, mac):
        """Set the MAC address for the corresponding IP.

        """ 
        self._mac_addresses[ip] = mac


    def get_mac(self, ip):
        """Lookup a MAC address for the specified IP address.

        """
        try:
            return self._mac_addresses[ip]
        except KeyError:
            return None


    def _get_num_exp_probes(self):
        """Returns the number of probes that were expected to arrive during the
        window period.

        """
        return EtxData.WINDOW / EtxData.INTERVAL


    def _get_num_probes_recv_from_me(self, neighbor):
        """Returns the number of probes that the specified neighbor received
        from this node.

        If no information about that neighbor is available it returns 0.

        """
        if neighbor not in self._neighbor_probes.keys() or self.ip_address not in self._neighbor_probes[neighbor].keys():
            return 0
        return self._neighbor_probes[neighbor][self.ip_address][0]


    def _get_num_probes_recv_from_neighbor(self, neighbor):
        """Returns the number of probes that this node received from the 
        specified neighbor.

        If no information about that neighbor is available it returns 0.

        """
        if neighbor not in self._received_probes.keys():
            return 0
        return len(self._received_probes[neighbor])


    def _get_forward_ratio(self, neighbor):
        """Returns the forward delivery ratio for the connection to the
        specified neighbor.
        
        The forward delivery ratio is the probability that a packet is
        successfully received by the recipient.

        """
        df = float(self._get_num_probes_recv_from_me(neighbor)) / self._get_num_exp_probes()
        # sometimes more packets are received than expected (due to jitter)
        if df > 1:
            df = 1.0
        return df


    def _get_reverse_ratio(self, neighbor):
        """Returns the reverse delivery ratio for the connection to the
        specified neighbor.
        
        The forward delivery ratio is the probability that a packet from the
        neighbor is successfully received.

        """
        dr = float(self._get_num_probes_recv_from_neighbor(neighbor)) / self._get_num_exp_probes()
        # sometimes more packets are received than expected (due to jitter)
        if dr > 1:
            dr = 1.0
        return dr
   

    def _get_twohop_transmission_probability(self, neighbor_ip, twohop_neighbor_ip):
        """Returns the transmission probability for the connection between the
        specified neighbor and its neighbor.

        """
        if neighbor_ip not in self._neighbor_probes.keys() or \
           twohop_neighbor_ip not in self._neighbor_probes[neighbor_ip].keys():
            # if we have no data for the requested nodes, probability is 0
            return 0.0
        # probability that a data packet successfully arrives at the recipient
        df = float(self._neighbor_probes[neighbor_ip][twohop_neighbor_ip][0]) / self._get_num_exp_probes()
        if df > 1:
            df = 1.0
        # probability that the ACK packet is successfully received
        dr = float(self._neighbor_probes[neighbor_ip][twohop_neighbor_ip][1]) / self._get_num_exp_probes()
        if dr > 1:
            dr = 1.0
        # probability of a successful transmission
        return df * dr

