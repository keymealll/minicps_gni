# Gas Pipeline Midstream — Step-by-Step Guide

> This guide walks you through running the Gas Pipeline Midstream simulation using MiniCPS.
> Follow it from top to bottom like a lab manual.

---

## What You're Working With

A **gas-liquid separator** in a midstream pipeline. Gas from upstream wells enters the separator, liquid condensate drops to the bottom, and clean gas exits out the top.

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                  GAS-LIQUID SEPARATOR SYSTEM                    │
    │                                                                 │
    │  Gas In              Separator Tank                Gas Out      │
    │  ════╗           ┌──────────────────┐              ╔════        │
    │      ║           │  ░░░░░░░░░░░░░░  │  gas space   ║           │
    │  [AV1]──FT101──→ │  ░░░░░░░░░░░░░░  │──────────→ [AV3]──→     │
    │  Inlet            │  ════════════════│              Gas          │
    │  Valve            │  ≈≈≈≈≈≈≈≈≈≈≈≈≈≈ │  liquid      Outlet      │
    │                   │  ≈≈≈≈≈≈≈≈≈≈≈≈≈≈ │                          │
    │  PT101            │  LT201 ↕  PT301 │              Liquid Out   │
    │  (inlet           └────────┬─────────┘              ╔════       │
    │   pressure)                │                        ║           │
    │                        [AV2]──→──[PUMP1]──────→ drain           │
    │                        Drain     Pump-Ejector                   │
    │                        Valve     Assembly                       │
    └─────────────────────────────────────────────────────────────────┘
```

### The Three Controllers

```
    ┌──────────────── Network Switch (s1) ────────────────┐
    │                                                      │
    PLC1              PLC2              PLC3           ATTACKER    HMI
    192.168.1.10      192.168.1.20      192.168.1.30  .77         .40
    ────────────      ────────────      ────────────
    Reads: PT101      Reads: LT201      Reads: PT301
    Controls: AV1     Controls: AV2     Controls: AV3
                      Controls: PUMP1
```

| PLC | Sensor | Actuators | Job |
|-----|--------|-----------|-----|
| PLC1 | PT101 (Inlet Pressure, kPa) | AV1 (Inlet Valve) | Keep inlet pressure in safe range |
| PLC2 | LT201 (Tank Level, meters) | AV2 (Drain Valve), PUMP1 (Pump) | Keep liquid level in safe range |
| PLC3 | PT301 (Tank Pressure, kPa) | AV3 (Gas Outlet Valve) | Keep tank pressure in safe range |

### Control Logic Thresholds

```
    PT101 - Inlet Pressure (kPa)        LT201 - Tank Level (m)
    800 ── HH ⚠️ DANGER                 1.30 ── HH ⚠️ DANGER
    700 ── H  → Close AV1               1.00 ── H  → Open AV2 + PUMP1
                                          
    300 ── L  → Open AV1                0.30 ── L  → Close AV2 + PUMP1
    200 ── LL ⚠️ DANGER                 0.10 ── LL ⚠️ DANGER

    PT301 - Tank Pressure (kPa)
    750 ── HH ⚠️ DANGER
    600 ── H  → Open AV3 (vent gas)

    250 ── L  → Close AV3 (build pressure)
    150 ── LL ⚠️ DANGER
```

---

## Prerequisites

- **Linux** (Ubuntu recommended) with root access
- **Mininet** installed (`sudo apt-get install mininet`)
- **Open vSwitch** installed (`sudo apt-get install openvswitch-switch`)
- **Python 3** with minicps, cpppo, pandas installed
- **minicps** installed (`pip install -e .` from minicps root)

---

## Step 1 — Navigate to the Project

```bash
cd /path/to/minicps/examples/gas-pipeline
```

## Step 2 — Initialize the Database (Run Once)

```bash
sudo python3 init.py
```

You should see:
```
gas_pipeline_db.sqlite successfully created.
```

## Step 3 — Start the Simulation

```bash
sudo python3 run.py
```

You will see:
```
*** Creating network
*** Adding hosts: plc1 plc2 plc3 hmi attacker s1
*** Ping: testing ping reachability
*** Results: 0% dropped (20/20 received)
mininet>
```

## Step 4 — Watch Normal Operation

```bash
mininet> s1 tail -f logs/process.log
```

You should see three values oscillating:
```
DEBUG inlet_pressure: 487.22 kPa | tank_level: 0.5334 m | tank_pressure: 395.50 kPa | AV1=1 AV2=0 AV3=1 PUMP1=0
```

- **Inlet pressure** (PT101) should oscillate between ~300-700 kPa
- **Tank level** (LT201) should oscillate between ~0.3-1.0m
- **Tank pressure** (PT301) should oscillate between ~250-600 kPa

Press `Ctrl+C` to stop watching.

## Step 5 — Verify Attacker Connectivity

```bash
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'
```

Expected output:
```
PT101:1              == [487.22]: 'OK'
```

## Step 6 — Check Individual PLC Logs

```bash
mininet> plc1 tail -5 logs/plc1.log
mininet> plc2 tail -5 logs/plc2.log
mininet> plc3 tail -5 logs/plc3.log
```

## Step 7 — View CSV Data

```bash
mininet> s1 cat logs/data.csv
```

---

## Cleanup

```bash
mininet> exit
sudo mn -c
sudo pkill -f cpppo
rm gas_pipeline_db.sqlite    # reset database
```

---

## Quick Reference — ENIP Tags

| Tag | PLC | Type | Description |
|-----|-----|------|-------------|
| `PT101:1` | PLC1 | REAL | Inlet pressure (kPa) |
| `AV1:1` | PLC1 | INT | Inlet valve (0=closed, 1=open) |
| `FT101:1` | PLC1 | REAL | Inlet flow rate |
| `LT201:1` | PLC1 | REAL | Tank level copy (interlock) |
| `PT301:1` | PLC1 | REAL | Tank pressure copy (interlock) |
| `LT201:2` | PLC2 | REAL | Tank liquid level (m) |
| `AV2:2` | PLC2 | INT | Drain valve |
| `PUMP1:2` | PLC2 | INT | Pump-ejector |
| `PT301:3` | PLC3 | REAL | Tank pressure (kPa) |
| `AV3:3` | PLC3 | INT | Gas outlet valve |

### Read a tag:
```bash
attacker python3 -m cpppo.server.enip.client --print --address <IP> '<TAG>'
```

### Write a tag:
```bash
attacker python3 -m cpppo.server.enip.client --address <IP> '<TAG>=<VALUE>'
```
