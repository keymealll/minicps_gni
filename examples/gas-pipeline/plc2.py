"""
gas-pipeline plc2.py — Tank Level Controller

PLC2 monitors the separator tank liquid level (LT201) and controls:
    - AV2: liquid drain valve
    - PUMP1: pump-ejector assembly

Control Logic:
    - If LT201 >= H (1.0m): open AV2 + start PUMP1 (drain liquid)
    - If LT201 <= L (0.3m): close AV2 + stop PUMP1 (stop draining)
    - If LT201 >= HH (1.3m): WARNING - dangerously high
    - If LT201 <= LL (0.1m): WARNING - dangerously low
"""

from minicps.devices import PLC
from utils import PLC2_DATA, STATE, PLC2_PROTOCOL
from utils import PLC_SAMPLES, PLC_PERIOD_SEC
from utils import IP, LT201_THRESH

import time

PLC1_ADDR = IP['plc1']
PLC2_ADDR = IP['plc2']
PLC3_ADDR = IP['plc3']

# Tags for state DB access
LT201 = ('LT201', 2)
AV2 = ('AV2', 2)
PUMP1 = ('PUMP1', 2)


class GasPLC2(PLC):

    def pre_loop(self, sleep=0.1):
        print('DEBUG: gas-pipeline plc2 enters pre_loop')
        time.sleep(sleep)

    def main_loop(self):
        """plc2 main loop.

            - reads tank liquid level sensor
            - drives drain valve and pump according to control strategy
            - updates internal enip server
        """

        print('DEBUG: gas-pipeline plc2 enters main_loop.')

        count = 0
        while(count <= PLC_SAMPLES):

            # Read tank level from state DB [meters]
            lt201 = float(self.get(LT201))
            print("DEBUG PLC2 - get lt201: %.4f m" % lt201)

            # Publish to ENIP server
            self.send(LT201, lt201, PLC2_ADDR)

            if lt201 >= LT201_THRESH['HH']:
                print("WARNING PLC2 - lt201 over HH: %.3f >= %.3f m." % (
                    lt201, LT201_THRESH['HH']))

            if lt201 >= LT201_THRESH['H']:
                # OPEN AV2 + START PUMP — liquid too high, drain it
                print("INFO PLC2 - lt201 over H -> open AV2, start PUMP1.")
                self.set(AV2, 1)
                self.send(AV2, 1, PLC2_ADDR)
                self.set(PUMP1, 1)
                self.send(PUMP1, 1, PLC2_ADDR)

            elif lt201 <= LT201_THRESH['LL']:
                print("WARNING PLC2 - lt201 under LL: %.3f <= %.3f m." % (
                    lt201, LT201_THRESH['LL']))

            elif lt201 <= LT201_THRESH['L']:
                # CLOSE AV2 + STOP PUMP — liquid too low, stop draining
                print("INFO PLC2 - lt201 under L -> close AV2, stop PUMP1.")
                self.set(AV2, 0)
                self.send(AV2, 0, PLC2_ADDR)
                self.set(PUMP1, 0)
                self.send(PUMP1, 0, PLC2_ADDR)

            time.sleep(PLC_PERIOD_SEC)
            count += 1

        print('DEBUG gas-pipeline plc2 shutdown')


if __name__ == "__main__":

    plc2 = GasPLC2(
        name='plc2',
        state=STATE,
        protocol=PLC2_PROTOCOL,
        memory=PLC2_DATA,
        disk=PLC2_DATA)
