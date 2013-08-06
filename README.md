etxd
====

Implementation of a daemon to measure the expected transmission count (ETX) link metric as proposed in "A high-throughput path metric for multi-hop wireless routing" by D. De Couto, D.Aguayo, J. Bicket, R. Morris, in MobiCom 2003.

The ETX daemon transmits periodically probes and keeps track of the received ones from its neighbors. Based on the statistics of the received probes on the node in question and the neigbor node, the probability of a successful unicast transmission (including the ACK) are determined. 

The implementation supports to customize the probe interval, the window size, and the network interfaces used to send (and receive) probes. The data can be retrieved with a simple protocol via a IPC interface or via a simple web server that returns the neighbors and the corresponding link quality in json.

Installation from git
---------------------
1. Clone the repository:

		git clone git://github.com/des-testbed/etxd.git
    
2. Please make sure you have the following Python modules installed:

		- twisted
		- netifaces
		- pythonwifi
		- simplejson
  
Starting and using the daemon
-----------------------------
1. Start the daemon

	etxd can be started from the command line with:

		python etxd.py wlan0 wlan1 wlan2
    
  This starts the ETX daemon with the standard configuration with a probe interval of 1 second and a window size of 10 seconds.

2. Retrieving the ETX information

	The ETX neighborhood information on a network node can be retrieved by two different ways. etxd provides a IPC interface on port 9157 that supports several commands to get the information you want. Here is a simple example if you are logged in on the node in question:

		t9-207:~# echo "NEIGHBORS" | nc localhost 9157
		wlan0:172.16.21.252:1.0
		wlan0:172.16.21.254:1.0

	The program also provides a simple web server listening on the same port at eth0 that returns all neighbors and the qualitiy of the corresponding links in json.

		t9-213:~# printf 'GET /  HTTP/1.1\r\nConnection: close\r\n\r\n' | nc 192.168.21.254 9157
		HTTP/1.1 200 OK
		Date: Tue, 06 Aug 2013 10:02:42 GMT
		Connection: close
		Content-Type: text/html
		Content-Length: 209
		Server: TwistedWeb/10.1.0

		{"node": "t9-213", "neighbors": [{"quality": 1.0, "if_name": "wlan0", "mac_address": "00:1f:1f:09:09:e2"}, {"quality": 1.0, "if_name": "wlan0", "mac_address": "00:1f:1f:09:06:e9"}], "time": 1375783362.084379}


