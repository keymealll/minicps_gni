"""
gas-pipeline run.py
"""

from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import OVSBridge
from minicps.mcps import MiniCPS

from topo import GasPipelineTopo

import sys


class GasPipelineCPS(MiniCPS):

    """Main container used to run the gas pipeline simulation."""

    def __init__(self, name, net):

        self.name = name
        self.net = net

        net.start()

        net.pingAll()

        # start devices
        plc1, plc2, plc3, s1, hmi = self.net.get(
            'plc1', 'plc2', 'plc3', 's1', 'hmi')

        # Start PLCs (PLC2 and PLC3 first, then PLC1 which queries them)
        plc2.cmd(sys.executable + ' -u ' + ' plc2.py &> logs/plc2.log &')
        plc3.cmd(sys.executable + ' -u ' + ' plc3.py &> logs/plc3.log &')
        plc1.cmd(sys.executable + ' -u ' + ' plc1.py &> logs/plc1.log &')

        # Start the physical process simulation
        s1.cmd(sys.executable + ' -u ' + ' physical_process.py &> logs/process.log &')

        # Start HMI ENIP poller (reads from all PLCs, writes JSON for dashboard)
        hmi.cmd(sys.executable + ' -u ' + ' hmi_poller.py &> logs/hmi_poller.log &')

        print('')
        print('=' * 60)
        print('  To view the HMI dashboard, open a NEW terminal and run:')
        print('    cd examples/gas-pipeline && python3 hmi_server.py')
        print('  Then open http://localhost:8080 in your browser.')
        print('=' * 60)
        print('')

        CLI(self.net)

        net.stop()

if __name__ == "__main__":

    topo = GasPipelineTopo()
    net = Mininet(topo=topo, switch=OVSBridge, controller=None)

    gas_pipeline_cps = GasPipelineCPS(
        name='gas_pipeline',
        net=net)
