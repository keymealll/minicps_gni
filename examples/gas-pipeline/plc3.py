"""
gas-pipeline plc3.py — Tank Pressure Controller

PLC3 monitors the separator tank pressure (PT301) and controls:
    - AV3: gas outlet valve

Control Logic:
    - If PT301 >= H (600 kPa): open AV3 (vent gas to reduce pressure)
    - If PT301 <= L (250 kPa): close AV3 (build pressure)
    - If PT301 >= HH (750 kPa): WARNING - dangerously high
    - If PT301 <= LL (150 kPa): WARNING - dangerously low
"""

from minicps.devices import PLC
from utils import PLC3_DATA, STATE, PLC3_PROTOCOL
from utils import PLC_SAMPLES, PLC_PERIOD_SEC
from utils import IP, PT301_THRESH

import time

PLC1_ADDR = IP['plc1']
PLC2_ADDR = IP['plc2']
PLC3_ADDR = IP['plc3']

# Tags for state DB access
PT301 = ('PT301', 3)
AV3 = ('AV3', 3)


class GasPLC3(PLC):

    def pre_loop(self, sleep=0.1):
        print('DEBUG: gas-pipeline plc3 enters pre_loop')
        time.sleep(sleep)

    def main_loop(self):
        """plc3 main loop.

            - reads tank pressure sensor
            - drives gas outlet valve according to control strategy
            - updates internal enip server
        """

        print('DEBUG: gas-pipeline plc3 enters main_loop.')

        count = 0
        while(count <= PLC_SAMPLES):

            # Read tank pressure from state DB [kPa]
            pt301 = float(self.get(PT301))
            print("DEBUG PLC3 - get pt301: %.2f kPa" % pt301)

            # Publish to ENIP server
            self.send(PT301, pt301, PLC3_ADDR)

            if pt301 >= PT301_THRESH['HH']:
                print("WARNING PLC3 - pt301 over HH: %.2f >= %.2f kPa." % (
                    pt301, PT301_THRESH['HH']))

            if pt301 >= PT301_THRESH['H']:
                # OPEN AV3 — tank pressure too high, vent gas
                print("INFO PLC3 - pt301 over H -> open AV3.")
                self.set(AV3, 1)

            elif pt301 <= PT301_THRESH['LL']:
                print("WARNING PLC3 - pt301 under LL: %.2f <= %.2f kPa." % (
                    pt301, PT301_THRESH['LL']))

            elif pt301 <= PT301_THRESH['L']:
                # CLOSE AV3 — tank pressure too low, build pressure
                print("INFO PLC3 - pt301 under L -> close AV3.")
                self.set(AV3, 0)

            # Always publish current AV3 state to ENIP every cycle
            av3_state = int(self.get(AV3))
            self.send(AV3, av3_state, PLC3_ADDR)

            time.sleep(PLC_PERIOD_SEC)
            count += 1

        print('DEBUG gas-pipeline plc3 shutdown')


if __name__ == "__main__":

    plc3 = GasPLC3(
        name='plc3',
        state=STATE,
        protocol=PLC3_PROTOCOL,
        memory=PLC3_DATA,
        disk=PLC3_DATA)
