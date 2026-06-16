# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About MiniCPS

MiniCPS is a Python framework for simulating Cyber-Physical Systems (CPS) on top of [Mininet](https://github.com/mininet/mininet). It models ICS/SCADA environments with PLCs, sensors, actuators, and industrial protocols (EtherNet/IP and Modbus TCP), primarily for security research.

**Platform constraint**: Linux only. The protocol code explicitly raises `OSError` on non-Linux platforms. Mininet requires root (`sudo`).

## Commands

### Running tests

```bash
# All tests (requires sudo for Mininet)
sudo nosetests -s -v --exe --rednose tests/

# Single test module
sudo nosetests -s -v --exe --rednose tests/devices_tests.py

# Single test class
sudo nosetests -s -v --exe --rednose tests/devices_tests.py:TestDevice

# Specific protocol tests
sudo nosetests -s -v --exe --rednose tests/protocols_tests.py:TestEnipProtocol
sudo nosetests -s -v --exe --rednose tests/protocols_tests.py:TestModbusProtocol

# CI-equivalent (no sudo needed, subset of tests)
nosetests -s -v --exe --rednose tests/protocols_tests.py tests/devices_tests.py tests/states_tests.py
```

### Running examples

Each example needs a one-time DB init before the first run:

```bash
# swat-s1 (main reference example)
cd examples/swat-s1
sudo python init.py       # create and seed the SQLite state DB (run once)
sudo python run.py        # start Mininet, spawn PLCs and physical process

# toy example
cd examples/toy
sudo python init.py
sudo python run.py
```

### Cleanup

```bash
make clean                # remove .pyc, .log, coverage files
make clean-simulation     # kill cpppo servers + sudo mn -c (Mininet cleanup)
make clean-mininet        # sudo mn -c only
make clean-cpppo          # kill lingering cpppo server processes
```

## Architecture

### Core library (`minicps/`)

**Two-layer design**: every device has a *physical layer* (state/DB) and a *network layer* (protocol).

- **`devices.py`** — `Device` base class wires together a state backend and a protocol. Subclasses (`PLC`, `HMI`, `Tank`, `SCADAServer`, `RTU`) override `pre_loop()` and `main_loop()`. Construction calls `_init_state()` → `_init_protocol()` → `_start()` (which calls `pre_loop` + `main_loop`) → `_stop()` in sequence.

- **`states.py`** — `SQLiteState` and `RedisState` (Redis is a stub). The state backend is selected by file extension in `state['path']`: `.sqlite` or `.redis`. SQLiteState uses prepared statements; the `what` tuple passed to `get()`/`set()` must match the table's primary key fields in order.

- **`protocols.py`** — `EnipProtocol` (wraps `cpppo` via `subprocess.Popen`) and `ModbusProtocol` (wraps `pymodbus/synch-client.py` via subprocess). When `mode=1`, the constructor starts a background server subprocess. Client calls (`send`/`receive`) also spawn subprocesses and block until they return. ENIP default port: 44818; Modbus default port: 502.

- **`networks.py`** — Graph vertex/edge classes (`PLC`, `HMI`, `Attacker`, `DumbSwitch`, etc.) plus `MininetTopoFromNxGraph` to convert a networkx graph into a Mininet topology.

- **`mcps.py`** — `MiniCPS` container; subclass it for each simulation and override `__init__` to start/stop the Mininet network and issue `host.cmd(...)` calls to spawn device processes.

- **`utils.py`** — `build_debug_logger` (rotating file + stream handler) and `wait_timeout` for subprocess management.

### Example structure (`examples/swat-s1/`)

Shows the canonical simulation pattern:
- `utils.py` — constants, IP/MAC maps, ENIP tag definitions, SQLite schema and init SQL, protocol dicts
- `init.py` — creates and seeds the SQLite DB (run once before `run.py`)
- `topo.py` — Mininet `Topo` subclass defining hosts and links
- `run.py` — `MiniCPS` subclass that starts Mininet and issues `host.cmd('python plcN.py &> logs/plcN.log &')` calls
- `plc1.py`, `plc2.py`, `plc3.py` — `PLC` subclasses implementing control logic in `main_loop()`
- `physical_process.py` — simulates the physical plant (tank level dynamics)

### Key conventions

- **State keys**: tuples of `(name, pid)` e.g. `('LIT101', 1)`. ENIP server tags use `(name, pid, type)` e.g. `('LIT101', 1, 'REAL')`.
- **Protocol dict**: `{'name': 'enip'|'modbus', 'mode': 0|1, 'server': {...}}`. Mode 0 = client only; mode 1 = client + server.
- **State dict**: `{'path': '/path/to/db.sqlite', 'name': 'table_name'}`.
- All values stored in SQLite are TEXT; callers must cast to `float`/`int` when reading.
- Log files go to `logs/` (created relative to the CWD where the process runs).
- The `temp/` directory holds SQLite DBs used by tests.
