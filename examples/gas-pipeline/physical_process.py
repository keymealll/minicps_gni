"""
Gas Pipeline Midstream — Physical Process Simulation

Simulates a gas-liquid separator in a midstream pipeline.
Gas enters through an inlet valve (AV1), flows into a separator tank
where liquid condensate settles to the bottom. Gas exits through an
outlet valve (AV3), and liquid is drained by a pump-ejector (PUMP1)
through drain valve (AV2).

State variables:
    - PT101: Inlet pressure (kPa) — pressure upstream of separator
    - LT201: Tank liquid level (m) — condensate level in separator
    - PT301: Tank pressure (kPa) — gas pressure inside separator
    - AV1:   Inlet valve (0=closed, 1=open)
    - AV2:   Drain valve (0=closed, 1=open)
    - AV3:   Gas outlet valve (0=closed, 1=open)
    - PUMP1: Pump-ejector (0=off, 1=on)
    - FT101: Inlet flow rate
"""

from minicps.devices import Tank

from utils import TANK_SECTION, INIT_TANK_LEVEL
from utils import GAS_INFLOW_PRESSURE, CONDENSATE_RATE
from utils import GAS_OUTFLOW_RATE, PUMP_DRAIN_RATE
from utils import INLET_PRESSURE_DROP, INLET_PRESSURE_BUILDUP
from utils import NATURAL_PRESSURE_DECAY
from utils import PT101_THRESH, LT201_THRESH, PT301_THRESH
from utils import STATE, PP_PERIOD_SEC, PP_PERIOD_HOURS, PP_SAMPLES
from utils import INIT_INLET_PRESSURE, INIT_TANK_PRESSURE, INIT_INLET_FLOW

import pandas as pd
import sys
import time


# Tag tuples for state DB access (name, pid)
PT101 = ('PT101', 1)
AV1 = ('AV1', 1)
FT101 = ('FT101', 1)
LT201 = ('LT201', 2)
AV2 = ('AV2', 2)
PUMP1 = ('PUMP1', 2)
PT301 = ('PT301', 3)
AV3 = ('AV3', 3)


class GasSeparator(Tank):

    def pre_loop(self):

        # Initialize actuator and sensor states
        self.set(AV1, 1)       # inlet valve open
        self.set(AV2, 0)       # drain valve closed
        self.set(AV3, 1)       # gas outlet valve open
        self.set(PUMP1, 0)     # pump off

        # Initialize sensor readings
        self.inlet_pressure = self.set(PT101, INIT_INLET_PRESSURE)
        self.tank_level = self.set(LT201, INIT_TANK_LEVEL)
        self.tank_pressure = self.set(PT301, INIT_TANK_PRESSURE)
        self.set(FT101, INIT_INLET_FLOW)

    def main_loop(self):

        count = 0
        columns = ['Time', 'AV1', 'AV2', 'AV3', 'PUMP1',
                    'PT101', 'LT201', 'PT301', 'FT101']
        df = pd.DataFrame(columns=columns)
        timestamp = 0

        while(count <= PP_SAMPLES):

            inlet_pressure = float(self.inlet_pressure)
            tank_level = float(self.tank_level)
            tank_pressure = float(self.tank_pressure)

            # ---- Read actuator states from DB ----
            av1 = int(self.get(AV1))
            av2 = int(self.get(AV2))
            av3 = int(self.get(AV3))
            pump1 = int(self.get(PUMP1))

            # ---- Gas Inflow (when AV1 is open) ----
            if av1 == 1:
                self.set(FT101, INIT_INLET_FLOW)
                # Gas flows into separator: increases tank pressure
                tank_pressure += GAS_INFLOW_PRESSURE * PP_PERIOD_HOURS
                # Condensate accumulates: increases liquid level
                tank_level += CONDENSATE_RATE * PP_PERIOD_HOURS
                # Inlet pressure drops when gas is flowing through
                inlet_pressure -= INLET_PRESSURE_DROP * PP_PERIOD_HOURS
            else:
                self.set(FT101, 0.0)
                # Backpressure builds when valve is closed
                inlet_pressure += INLET_PRESSURE_BUILDUP * PP_PERIOD_HOURS

            # ---- Gas Outflow (when AV3 is open) ----
            if av3 == 1:
                tank_pressure -= GAS_OUTFLOW_RATE * PP_PERIOD_HOURS

            # ---- Liquid Drain (when AV2 open AND PUMP1 on) ----
            if av2 == 1 and pump1 == 1:
                tank_level -= PUMP_DRAIN_RATE * PP_PERIOD_HOURS

            # ---- Natural effects ----
            tank_pressure -= NATURAL_PRESSURE_DECAY * PP_PERIOD_HOURS

            # ---- Clamp values (cannot go negative) ----
            if inlet_pressure <= 0.0:
                inlet_pressure = 0.0
            if tank_level <= 0.0:
                tank_level = 0.0
            if tank_pressure <= 0.0:
                tank_pressure = 0.0

            # ---- Update state DB ----
            print("DEBUG inlet_pressure: %.2f kPa | "
                  "tank_level: %.4f m | "
                  "tank_pressure: %.2f kPa | "
                  "AV1=%d AV2=%d AV3=%d PUMP1=%d" % (
                      inlet_pressure, tank_level, tank_pressure,
                      av1, av2, av3, pump1))

            self.inlet_pressure = self.set(PT101, inlet_pressure)
            self.tank_level = self.set(LT201, tank_level)
            self.tank_pressure = self.set(PT301, tank_pressure)

            # ---- Safety checks ----
            if tank_pressure >= PT301_THRESH['HH']:
                print('CRITICAL: Tank pressure above HH at count: ', count)
                break

            if tank_level >= LT201_THRESH['HH']:
                print('CRITICAL: Tank level above HH at count: ', count)
                break

            if inlet_pressure >= PT101_THRESH['HH']:
                print('CRITICAL: Inlet pressure above HH at count: ', count)
                break

            # ---- Log data to CSV ----
            new_data = pd.DataFrame(
                data=[[timestamp, av1, av2, av3, pump1,
                       inlet_pressure, tank_level, tank_pressure,
                       float(self.get(FT101))]],
                columns=columns)
            df = pd.concat([df, new_data])
            df.to_csv('logs/data.csv', index=False)

            count += 1
            time.sleep(PP_PERIOD_SEC)
            timestamp += PP_PERIOD_SEC


if __name__ == '__main__':

    separator = GasSeparator(
        name='separator',
        state=STATE,
        protocol=None,
        section=TANK_SECTION,
        level=INIT_TANK_LEVEL
    )
