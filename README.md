# MAC-Following

Scripts developed to automate the proccess of gathering and documenting the paths to endpoints of solicited data cells in the network. Starting from the PE and going to the final point in an access switch by making use of the MAC address of each device.

The script gathers information from the ARP and MAC Address tables of every router/switch in the network and then documents the exact path each mac-address goes trhough when delivering data in the network. This data was solicited so that it could later be correlated with the utilization of each link and used to analize the possible optimization of traffic in the network.
