"""
gas-pipeline utils.py

Gas-Liquid Separator (Midstream Pipeline) simulation constants.

sqlite and enip use name (string) and pid (int) as key and the state stores
values as strings.

Actuator valve convention:
    - 0 = closed
    - 1 = open

Pump convention:
    - 0 = off
    - 1 = on

sqlite uses float keyword and cpppo uses REAL keyword.
"""

from minicps.utils import build_debug_logger

gas_log = build_debug_logger(
    name=__name__,
    bytes_per_file=10000,
    rotating_files=2,
    lformat='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    ldir='logs/',
    suffix='')

# ============================================================
# Physical Process Constants
# ============================================================

GRAVITATION = 9.81             # m/s^2

# Separator tank dimensions
TANK_LENGTH = 4.0              # m (horizontal cylindrical)
TANK_DIAMETER = 2.0            # m
TANK_SECTION = 3.14            # m^2 (approximate cross-section)

# Flow rates (simplified units for simulation)
GAS_INFLOW_PRESSURE = 8.0     # kPa added per simulation hour when AV1 open
CONDENSATE_RATE = 0.12         # m of liquid level added per sim hour when AV1 open
GAS_OUTFLOW_RATE = 10.0        # kPa removed per sim hour when AV3 open
PUMP_DRAIN_RATE = 0.15         # m of liquid level removed per sim hour when AV2+PUMP1

# Inlet pressure dynamics
INLET_PRESSURE_DROP = 5.0      # kPa drop per sim hour when AV1 open (gas flowing through)
INLET_PRESSURE_BUILDUP = 12.0  # kPa rise per sim hour when AV1 closed (backpressure)

# Natural effects
NATURAL_PRESSURE_DECAY = 0.5   # kPa per sim hour (micro-leaks)

# Timing
PLC_PERIOD_SEC = 0.40          # PLC update rate in seconds
PLC_PERIOD_HOURS = PLC_PERIOD_SEC / 3600.0
PLC_SAMPLES = 1000

PP_RESCALING_HOURS = 100
PP_PERIOD_SEC = 0.20           # physical process update rate in seconds
PP_PERIOD_HOURS = (PP_PERIOD_SEC / 3600.0) * PP_RESCALING_HOURS
PP_SAMPLES = int(PLC_PERIOD_SEC / PP_PERIOD_SEC) * PLC_SAMPLES

# ============================================================
# Control Logic Thresholds
# ============================================================

# PT101 - Inlet Pressure (kPa)
PT101_THRESH = {
    'LL': 200.0,
    'L':  300.0,
    'H':  700.0,
    'HH': 800.0,
}

# LT201 - Tank Liquid Level (meters)
LT201_THRESH = {
    'LL': 0.10,
    'L':  0.30,
    'H':  1.00,
    'HH': 1.30,
}

# PT301 - Tank Pressure (kPa)
PT301_THRESH = {
    'LL': 150.0,
    'L':  250.0,
    'H':  600.0,
    'HH': 750.0,
}

# Initial values
INIT_INLET_PRESSURE = 500.0    # kPa
INIT_TANK_LEVEL = 0.50         # m
INIT_TANK_PRESSURE = 400.0     # kPa
INIT_INLET_FLOW = 5.0          # m^3/h

# ============================================================
# Network Topology
# ============================================================

IP = {
    'plc1': '192.168.1.10',
    'plc2': '192.168.1.20',
    'plc3': '192.168.1.30',
    'hmi':  '192.168.1.40',
    'attacker': '192.168.1.77',
}

NETMASK = '/24'

MAC = {
    'plc1': '00:1D:9C:C7:B0:70',
    'plc2': '00:1D:9C:C8:BC:46',
    'plc3': '00:1D:9C:C8:BD:F2',
    'hmi':  '00:1D:9C:C7:FA:2C',
    'attacker': 'AA:AA:AA:AA:AA:AA',
}

# ============================================================
# PLC Data (memory/disk placeholders)
# ============================================================

PLC1_DATA = {
    'TODO': 'TODO',
}
PLC2_DATA = {
    'TODO': 'TODO',
}
PLC3_DATA = {
    'TODO': 'TODO',
}

# ============================================================
# PLC1 - Inlet Pressure Controller
# ============================================================

PLC1_ADDR = IP['plc1']
PLC1_TAGS = (
    ('PT101',  1, 'REAL'),     # inlet pressure sensor
    ('AV1',    1, 'INT'),      # actuator valve 1 (inlet)
    ('FT101',  1, 'REAL'),     # inlet flow transmitter
    # interlocks received from PLC2 and PLC3
    ('LT201',  1, 'REAL'),     # tank level (copy from PLC2)
    ('PT301',  1, 'REAL'),     # tank pressure (copy from PLC3)
)
PLC1_SERVER = {
    'address': PLC1_ADDR,
    'tags': PLC1_TAGS
}
PLC1_PROTOCOL = {
    'name': 'enip',
    'mode': 1,
    'server': PLC1_SERVER
}

# ============================================================
# PLC2 - Tank Level Controller
# ============================================================

PLC2_ADDR = IP['plc2']
PLC2_TAGS = (
    ('LT201',  2, 'REAL'),     # tank liquid level sensor
    ('AV2',    2, 'INT'),      # actuator valve 2 (liquid drain)
    ('PUMP1',  2, 'INT'),      # pump-ejector assembly
)
PLC2_SERVER = {
    'address': PLC2_ADDR,
    'tags': PLC2_TAGS
}
PLC2_PROTOCOL = {
    'name': 'enip',
    'mode': 1,
    'server': PLC2_SERVER
}

# ============================================================
# PLC3 - Tank Pressure Controller
# ============================================================

PLC3_ADDR = IP['plc3']
PLC3_TAGS = (
    ('PT301',  3, 'REAL'),     # tank pressure sensor
    ('AV3',    3, 'INT'),      # actuator valve 3 (gas outlet)
)
PLC3_SERVER = {
    'address': PLC3_ADDR,
    'tags': PLC3_TAGS
}
PLC3_PROTOCOL = {
    'name': 'enip',
    'mode': 1,
    'server': PLC3_SERVER
}

# ============================================================
# State Database
# ============================================================

PATH = 'gas_pipeline_db.sqlite'
NAME = 'gas_pipeline'

STATE = {
    'name': NAME,
    'path': PATH
}

SCHEMA = """
CREATE TABLE gas_pipeline (
    name              TEXT NOT NULL,
    pid               INTEGER NOT NULL,
    value             TEXT,
    PRIMARY KEY (name, pid)
);
"""

SCHEMA_INIT = """
    INSERT INTO gas_pipeline VALUES ('PT101',   1, '500.0');
    INSERT INTO gas_pipeline VALUES ('AV1',     1, '1');
    INSERT INTO gas_pipeline VALUES ('FT101',   1, '5.0');

    INSERT INTO gas_pipeline VALUES ('LT201',   2, '0.500');
    INSERT INTO gas_pipeline VALUES ('AV2',     2, '0');
    INSERT INTO gas_pipeline VALUES ('PUMP1',   2, '0');

    INSERT INTO gas_pipeline VALUES ('PT301',   3, '400.0');
    INSERT INTO gas_pipeline VALUES ('AV3',     3, '1');
"""
