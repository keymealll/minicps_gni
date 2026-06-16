"""
toy topology
"""

from mininet.topo import Topo

from utils import PLC1_MAC, PLC2_MAC
from utils import PLC1_ADDR, PLC2_ADDR, NETMASK

ATTACKER_ADDR = '10.0.0.100'
ATTACKER_MAC  = '00:00:00:00:00:64'


class ToyTopo(Topo):

    def build(self):

        switch = self.addSwitch('s1')

        plc1 = self.addHost(
            'plc1',
            ip=PLC1_ADDR + NETMASK,
            mac=PLC1_MAC)
        self.addLink(plc1, switch)

        plc2 = self.addHost(
            'plc2',
            ip=PLC2_ADDR + NETMASK,
            mac=PLC2_MAC)
        self.addLink(plc2, switch)

        attacker = self.addHost(
            'attacker',
            ip=ATTACKER_ADDR + NETMASK,
            mac=ATTACKER_MAC)
        self.addLink(attacker, switch)
