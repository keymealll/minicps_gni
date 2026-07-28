"""
gas-pipeline plc1.py — Inlet Pressure Controller

PLC1 monitors the inlet pressure (PT101) and controls the inlet valve (AV1).
It also receives interlock values from PLC2 (tank level) and PLC3 (tank pressure)
to coordinate system-wide safety.

Control Logic:
    - If PT101 >= H (700 kPa): close AV1 (reduce inlet pressure)
    - If PT101 <= L (300 kPa): open AV1 (allow gas flow)
    - If PT101 >= HH (800 kPa): WARNING - dangerously high
    - If PT101 <= LL (200 kPa): WARNING - dangerously low

Interlocks (currently commented out, enable for advanced attacks):
    - If LT201 >= H or PT301 >= H: close AV1 (protect separator)
"""

from minicps.devices import PLC
from utils import PLC1_DATA, STATE, PLC1_PROTOCOL
from utils import PLC_PERIOD_SEC, PLC_SAMPLES
from utils import IP, PT101_THRESH, LT201_THRESH, PT301_THRESH

import time

PLC1_ADDR = IP['plc1']
PLC2_ADDR = IP['plc2']
PLC3_ADDR = IP['plc3']

# Tags for state DB access (name, pid)
PT101 = ('PT101', 1)
AV1 = ('AV1', 1)
FT101 = ('FT101', 1)

# Interlock tags — local copies stored on PLC1's ENIP server
LT201_1 = ('LT201', 1)   # to be sent (PLC1's copy)
LT201_2 = ('LT201', 2)   # to be received from PLC2
PT301_1 = ('PT301', 1)    # to be sent (PLC1's copy)
PT301_3 = ('PT301', 3)    # to be received from PLC3


class GasPLC1(PLC):

    def pre_loop(self, sleep=0.1):
        print('DEBUG: gas-pipeline plc1 enters pre_loop')
        time.sleep(sleep)

    def main_loop(self):
        """plc1 main loop.

            - reads inlet pressure sensor
            - drives inlet valve according to the control strategy
            - receives interlock values from PLC2 and PLC3
            - updates its enip server
        """

        print('DEBUG: gas-pipeline plc1 enters main_loop.')

        count = 0
        while(count <= PLC_SAMPLES):

            # Read inlet pressure from state DB [kPa]
            pt101 = float(self.get(PT101))
            print('DEBUG plc1 pt101: %.2f kPa' % pt101)
            self.send(PT101, pt101, PLC1_ADDR)

            if pt101 >= PT101_THRESH['HH']:
                print("WARNING PLC1 - pt101 over HH: %.2f >= %.2f kPa." % (
                    pt101, PT101_THRESH['HH']))

            if pt101 >= PT101_THRESH['H']:
                # CLOSE AV1 — inlet pressure too high
                print("INFO PLC1 - pt101 over H -> close AV1.")
                self.set(AV1, 0)

            elif pt101 <= PT101_THRESH['LL']:
                print("WARNING PLC1 - pt101 under LL: %.2f <= %.2f kPa." % (
                    pt101, PT101_THRESH['LL']))

            elif pt101 <= PT101_THRESH['L']:
                # OPEN AV1 — inlet pressure too low, allow gas
                print("INFO PLC1 - pt101 under L -> open AV1.")
                self.set(AV1, 1)

            # Always publish current AV1 state to ENIP every cycle
            # (not just when a control decision fires — keeps ENIP in sync with SQLite)
            av1_state = int(self.get(AV1))
            self.send(AV1, av1_state, PLC1_ADDR)

            # Receive interlock: tank level from PLC2
            lt201 = float(self.receive(LT201_2, PLC2_ADDR))
            print("DEBUG PLC1 - receive lt201: %.3f m" % lt201)
            self.send(LT201_1, lt201, PLC1_ADDR)

            # Receive interlock: tank pressure from PLC3
            pt301 = float(self.receive(PT301_3, PLC3_ADDR))
            print("DEBUG PLC1 - receive pt301: %.2f kPa" % pt301)
            self.send(PT301_1, pt301, PLC1_ADDR)

            # Interlock logic (uncomment to enable for attack testing)
            #if lt201 >= LT201_THRESH['H'] or pt301 >= PT301_THRESH['H']:
            #    # CLOSE AV1 — tank is too full or pressurized
            #    self.set(AV1, 0)
            #    self.send(AV1, 0, PLC1_ADDR)
            #    print("INFO PLC1 - interlock: lt201 or pt301 over H -> close AV1.")

            time.sleep(PLC_PERIOD_SEC)
            count += 1

        print('DEBUG gas-pipeline plc1 shutdown')


if __name__ == "__main__":

    plc1 = GasPLC1(
        name='plc1',
        state=STATE,
        protocol=PLC1_PROTOCOL,
        memory=PLC1_DATA,
        disk=PLC1_DATA)
