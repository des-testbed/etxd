#!/usr/bin/python
"""
ETXD: A daemon for to measure the Exptected Transmission Count (ETX)

This is the entry point and program flow control for etxd. First, command line
arguments are parsed and, if desired, the process is detached from the current
session and runs as a daemon in the background. The data structures, protocols,
and ports are initialized and finally, sending (and receiving) of probes to 
(and from) neighbors begins.

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

import netifaces
import time
import random
import sys
import getopt
import os
import subprocess
from syslog import *

from twisted.internet import epollreactor
epollreactor.install()
from twisted.internet import reactor
from twisted.internet.error import CannotListenError
from twisted.web import server

sys.path.insert(0, '/usr/share/etxd') 
from etx_probe import EtxProbeProtocol
from etx_data import EtxData
from etx_ipc import EtxIpcFactory
from etx_web import EtxWebServer

class Interface:
    """Class that encapsulates all the information associated with a network
    interface.

        name:     name of the interface (e.g. wlan0)

        The following fields will be set in initialize_interfaces(..)
        data:     pointer to an instance of EtxData
        protocol: pointer to an instance of EtxProbeProtocol
        port:     object which provides IListeningPort for stopping the probe protocol
        ipc_port: object which provides IListeningPort for stopping the ipc protocol
    """
    def __init__(self, if_name):
        self.name = if_name


def print_data(interfaces):
    """Logs the neighbor data for all interfaces to the log file. Calls itself again later
    when the window has expired.

    """
    for interface in interfaces.values():
        # check if there is any neighborhood data available for the particular interface
        if hasattr(interface, 'data'):
            interface.data.remove_old_probes()
            syslog(LOG_DEBUG, "%s: %s" % (interface.name, interface.data.get_neighbors()))
    reactor.callLater(WINDOW, print_data, interfaces)


def send_probe(interface):
    """Initiates to send a probe over the specified interface. Adds a random jitter to the 
    sending interval in order to reduce the chance of message collisions.

    """
    # stop sending probes if the object reference has been deleted
    if not hasattr(interface, 'protocol'):
        return
    # send the probe
    interface.protocol.send_probe()
    # variate delay by +-10% to avoid collisions due to synchronization 
    jitter = random.uniform(0.0, 0.2*INTERVAL)
    reactor.callLater(0.9*INTERVAL + jitter, send_probe, interface)


def initialize_interfaces(interfaces):
    """Initialized the network interfaces. If the interface is UP, it is ensured, that an instance
    of ETXData is associated with the interface. The EtxProbeProtocol is associated and started. 
    Finally, the IPC protocol is initialized to support requests of other processes. 

    """
    # iterate over all interfaces 
    for interface in interfaces.values():
        # see if the interface is configured
        if subprocess.call("ifconfig | grep -q %s" % interface.name, shell=True) != 0:
            # see if we previously used the interface
            if hasattr(interface, 'port'):
                # stop listening for probes
                interface.port.stopListening()
                del interface.port
                # stop listening for IPC connections
                interface.ipc_port.stopListening()
                del interface.ipc_port
                # stop sending probes
                del interface.protocol
                # clear data
                del interface.data
            if DEBUG:
                syslog(LOG_DEBUG, "%s: interface not configured" % (interface.name))
            continue
        # interface is up, try to determine its ip and broadcast address
        try:
            inet_addr = netifaces.ifaddresses(interface.name)[netifaces.AF_INET][0]['addr']
            bcast_addr = netifaces.ifaddresses(interface.name)[netifaces.AF_INET][0]['broadcast']
        except KeyError:
            syslog(LOG_WARNING, "%s: unable to determine IP address, although the interface seems to be up" % (interface.name))
            continue
        # interface is up, see if we are already listening on it
        if hasattr(interface, 'port'):
            # we are listening, see if the broadcast address has changed
            if interface.port.getHost().host != bcast_addr:
                # interface has been reconfigured, stop listening at the old
                # address
                syslog(LOG_INFO, "%s: interface has been reconfigured" % (interface.name))
                interface.port.stopListening()
                del interface.port
                # stop listening for IPC connections
                interface.ipc_port.stopListening()
                del interface.ipc_port
                # stop sending probes
                del interface.protocol
                # clear data
                del interface.data
            else:
                # broadcast address still up to date and we are already
                # listening, nothing to do
                continue
        # interface is up, but we are not listening (anymore)
        # initialize data
        interface.data = EtxData(inet_addr)
        # create probe protocol for this interface
        interface.protocol = EtxProbeProtocol(interface.name, inet_addr, interface.data)
        try:
            # try to listen at the broadcast address
            interface.port = reactor.listenUDP(PROBE_PORT, interface.protocol, bcast_addr)
            syslog(LOG_INFO, "%s: listening for probes at %s:%s"  % (interface.name, bcast_addr, PROBE_PORT))
        except CannotListenError:
            syslog(LOG_WARNING, "%s: unable to listen at %s:%s, although the interface seems to be up. Maybe another interface uses the same broadcast address" % (interface.name, bcast_addr, PROBE_PORT))
            del interface.data
            del interface.protocol
            continue
        # if everything was initialized successfully, start sending probes
        reactor.callWhenRunning(send_probe, interface)
        try:
            # listen for ipc connections on the wireless interface
            interface.ipc_port = reactor.listenTCP(IPC_PORT, EtxIpcFactory(interfaces), 10, inet_addr)
        except CannotListenError:
            syslog(LOG_WARNING, "%s: unable to listen for IPC connections at %s:%s" % (interface.name, bcast_addr, IPC_PORT))
    # schedule next execution of this function
    reactor.callLater(WINDOW, initialize_interfaces, interfaces)


def main():
    """Main function to start the etxd program flow after any command line arguments have been
    parsed and depending on the configuration, the process has been double-forked to the
    background. 

    """
    # dictionary that stores all Interface objects indexed by the interface name
    interfaces = dict()

    # iterate over all interface names 
    for if_name in if_names:
        # initialize interface list
        interfaces[if_name] = Interface(if_name)

    # initialize interfaces
    reactor.callWhenRunning(initialize_interfaces, interfaces)

    # create factory for ipc protocol
    ipc_factory = EtxIpcFactory(interfaces)
    # listen for ipc connections on localhost
    reactor.listenTCP(IPC_PORT, ipc_factory, 10, '127.0.0.1')

    # create server for JSON RPC
    web_server = EtxWebServer(interfaces, os.uname()[1])
    # get IP of the ethernet interface
    inet_addr = netifaces.ifaddresses("eth0")[netifaces.AF_INET][0]['addr']	
    # listen for RPC connections on the ethernet interface
    reactor.listenTCP(IPC_PORT, server.Site(web_server), 10, inet_addr)

    # print debug output if requested
    if DEBUG:
        reactor.callWhenRunning(print_data, interfaces)

    # start the twisted event loop
    reactor.run()


if __name__ == "__main__":
    # entry point if this program is executed. First, the command line arguments are parsed and depending on the
    # configuration, the process is double-forked to the background

    # set default values 
    IPC_PORT = 9157
    PROBE_PORT = 9158
    INTERVAL = 1 # seconds
    WINDOW = 10 # seconds
    DEBUG = False
    FOREGROUND = False

    # prepare logger
    openlog("etxd", LOG_PID|LOG_PERROR, LOG_DAEMON)

    # parse command line parameters
    try:
        opt_list, if_names = getopt.getopt(sys.argv[1:], "fDi:w:p:")
    except getopt.GetoptError:
        syslog(LOG_ERR, "Error while parsing parameters: %s" % sys.exc_info()[1]) 
        sys.exit(1)

    # set options according to command line parameters
    debug_count = 0
    for item in opt_list:
        opt, val = item
        if opt == "-p":
            if val.isdigit() and int(val) > 0:
                IPC_PORT = int(val)
                PROBE_PORT = IPC_PORT + 1
            else:
                syslog(LOG_WARNING, "Warning: Invalid port specification. Using default: %s" % IPC_PORT)
        elif opt == "-i":
            if val.isdigit() and int(val) > 0:
                INTERVAL = int(val)
            else:
                syslog(LOG_WARNING, "Warning: Invalid interval specification. Using default: %s" % INTERVAL)
        elif opt == "-w":
            if val.isdigit() and int(val) > 0:
                WINDOW = int(val)
            else:
                syslog(LOG_WARNING, "Warning: Invalid window size specification.  Using default: %s" % WINDOW)
        elif opt == "-D":
            debug_count += 1
            DEBUG = True
            if debug_count > 1:
                EtxProbeProtocol.DEBUG = True
        elif opt == "-f":
            FOREGROUND = True

    # check if window size and interval correspond
    if WINDOW < INTERVAL:
        syslog(LOG_ERR, "Error: Window (%s) must be >= interval (%s)!" % (WINDOW, INTERVAL))
        sys.exit(1)

    # forward configuration to the data class
    EtxData.WINDOW = WINDOW
    EtxData.INTERVAL = INTERVAL

    if DEBUG:
        syslog(LOG_DEBUG, "IPC_PORT:   %s" % IPC_PORT)
        syslog(LOG_DEBUG, "PROBE_PORT: %s" % PROBE_PORT)
        syslog(LOG_DEBUG, "INTERVAL:   %s" % INTERVAL)
        syslog(LOG_DEBUG, "WINDOW:     %s" % WINDOW)
        syslog(LOG_DEBUG, "DEBUG:      %s" % DEBUG)
        syslog(LOG_DEBUG, "FOREGROUND: %s" % FOREGROUND)

    for if_name in list(if_names):
        # check if interface is valid
        if if_name not in netifaces.interfaces():
            syslog(LOG_WARNING, "Warning: Interface %s does not exist, ignoring it." % if_name)
            if_names.remove(if_name)

    if len(if_names) < 1:
        syslog(LOG_ERR, "Error: No valid network interfaces specified, exiting.")
        sys.exit(1)

    if not FOREGROUND:
        # do the UNIX double-fork magic, see Stevens' "Advanced 
        # Programming in the UNIX Environment" for details (ISBN 0201563177)
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit first parent
                sys.exit(0) 
        except OSError, e: 
            print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror) 
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/") 
        os.setsid() 
        os.umask(0) 

        # do second fork
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit from second parent, save eventual PID before
                pidfile = open("/var/run/etxd.pid", "w")
                pidfile.write("%d" % pid)
                pidfile.close()
                sys.exit(0) 
        except OSError, e: 
            print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror) 
            sys.exit(1) 

        # Redirect standard file descriptors.
        si = file('/dev/null', 'r')
        so = file('/dev/null', 'a+')
        se = file('/dev/null', 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

    # start the daemon main loop
    main() 

