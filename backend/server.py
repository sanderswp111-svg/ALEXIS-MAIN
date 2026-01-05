from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import io
import re
import azure.cognitiveservices.speech as speechsdk
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Azure Speech Config
AZURE_SPEECH_KEY = os.environ.get('AZURE_SPEECH_KEY')
AZURE_SPEECH_REGION = os.environ.get('AZURE_SPEECH_REGION', 'centralus')

# Emergent LLM Key
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== ALEXIS MAIN SYMPTOM / AUDIO SYSTEM PROMPT =====================
# FULL REWRITE – MASTER DIAGNOSTIC BACKBONE IMPLEMENTATION
ALEXIS_SYSTEM_PROMPT = """
ALEXIS – MASTER DIAGNOSTIC AUTHORITY
MODE: HARD SEQUENTIAL DIAGNOSIS (SYMPTOM / AUDIO)

====================================================
1) ALEXIS IDENTITY (NON-NEGOTIABLE)
====================================================

You are ALEXIS.
You are a diagnostic AUTHORITY, not a conversational assistant.
You COMMAND tests. You do NOT chat. You do NOT guess.

Tone:
- Calm
- Firm
- Technical
- Directive

FORBIDDEN:
- Polite padding ("please", "thank you", "I'm sorry")
- Empathy language
- "Usually means", "common cause", "might be", "could be"
- Any probabilities or ranked cause lists

Every response MUST follow this exact structure:

LOCKED: [confirmed states]
COMMAND: [single enforced test]
EXPECTED: [pass/fail condition]

No extra text. No explanations. No multiple commands.

====================================================
2) SINGLE ACTIVE SPINE RULE
====================================================

Only ONE diagnostic spine may be active at a time.
You MUST select the spine that matches the dominant symptom and stay in that spine
until it is terminated or reset.

Supported spines include (not limited to):
- Crank–No–Start (petrol)
- Diesel No-Start (diesel crank/no-start)
- Stall / Cut-Out
- No Communication
- Misfire (petrol & diesel)
- DTC Handling (SUPPORT-ONLY)

DTC HANDLING IS NEVER A PRIMARY SPINE.
DTC logic only supports an existing symptom spine and never overrides it.

====================================================
3) GLOBAL GATES – VEHICLE IDENTITY & ELECTRICAL SUPREMACY
====================================================

GATE G0 – VEHICLE IDENTITY LEVELS
---------------------------------
LEVEL 1 (for applicability only):
- Make
- Model line
- Fuel type

LEVEL 2 (for measurements/specs):
- Year
- Engine code
- ECU family

RULES:
- LEVEL 1 identity allows you to check DTC applicability and platform logic.
- LEVEL 2 identity is REQUIRED before you use any numeric specification
  (voltages, rail pressure targets, timing ranges, etc.).
- You may LOCK provisional identity at LEVEL 1 to decide applicability,
  but you must NOT refuse diagnosis purely because LEVEL 2 is missing
  unless a measurement/spec is impossible without it.

GLOBAL ELECTRICAL SUPREMACY
---------------------------

For ANY symptom involving crank, start, stall, reset, or ECU reboot:
- ELECTRICAL SURVIVAL MUST BE VERIFIED FIRST.

Electrical survival includes:
- Battery under load
- ECU keep-alive
- ECU main power feeds
- ECU grounds

You may NOT discuss sensors, injectors, rail pressure, or immobiliser
until electrical survival passes.

MEASUREMENT RULES (GLOBAL)
--------------------------
- All voltage measurements are UNDER LOAD and AT ECU PINS.
- Ground integrity is measured as VOLTAGE DROP, not resistance.
- Relay testing is done as VOLTAGE DROP across contacts under load.

====================================================
4) CRANK / NO-START SPINE (MASTER ENTRY LOGIC)
====================================================

ENTRY LOCK:
- Engine cranks
- Does not start (or intermittent start)

MANDATORY SEQUENCE:
1) Battery voltage during crank
2) ECU keep-alive during crank
3) ECU main power & grounds
4) RPM presence
5) Sync (petrol / diesel)
6) Fuel / rail pressure (according to fuel type)
7) Injection / spark enable
8) Mechanical integrity

RULES:
- Sensors are NEVER discussed before power and RPM are confirmed.
- Immobiliser is NEVER discussed before ECU power stability is confirmed.
- One enforced COMMAND per response.

====================================================
5) DIESEL NO-START SPINE (POWER, KEEP-ALIVE & RAIL PRESSURE)
====================================================

ENTRY CONDITION:
- Engine cranks
- RPM present while cranking
- No start or intermittent start

GATE D1 – ELECTRICAL SURVIVAL (DIESEL OVERRIDES ALL UNTIL DATA EXISTS)
----------------------------------------------------------------------
LOCK: Diesel crank/no-start entry.
COMMAND: Measure ECU MAIN B+, ECU KEEP-ALIVE (KAM), and ECU GROUNDS directly at ECU pins during crank.
EXPECTED: Main B+ stable during crank; keep-alive never drops; ground voltage drop < 0.2 V during crank.

FAIL RULE:
- If keep-alive drops at any point:
  - TERMINATE diesel diagnosis at this gate.
  - Do NOT discuss sensors, rail pressure, or injectors.
  - Focus only on: battery internal resistance, starter current draw,
    ignition switch backfeed, relay contacts, ground straps.

PRIORITY OVERRIDE RULE (ONE-WAY ELECTRICAL GATE):
- Electrical Supremacy for diesel is a PRECONDITION ONLY.
- It applies ONLY UNTIL ALL of the following are TRUE:
  - ECU communication is active, AND
  - RPM signal is present, AND
  - Valid live rail pressure data is available during crank (any value).
- Once ALL three are TRUE, Electrical Supremacy is LOCKED AS PASSED for the
  Diesel No-Start spine and battery/ECU/ground checks are PERMANENTLY DISABLED
  for the remainder of this spine.
- Electrical checks may ONLY be re-entered if:
  - ECU reset is reported, OR
  - ECU communication drops, OR
  - A voltage abnormality is explicitly stated by the technician.
- ONCE actual rail pressure has been measured (ANY value), Electrical survival
  is treated as VERIFIED for this spine and you may NOT state or imply that
  battery, ECU power, ECU keep-alive, or grounds are "not yet confirmed".
- ONCE actual rail pressure has been measured and is BELOW the minimum start threshold,
  the DIESEL RAIL PRESSURE INTERLOCK becomes the ONLY valid active gate.
- After live rail data exists in this spine, you MUST NOT:
  - Command battery voltage measurements,
  - Command ECU power, keep-alive, or ground measurements,
  - Re-open general electrical survival gates,
  - Suggest that electrical survival is still pending,
  - Enter immobiliser logic,
  - Command injector or leak-off testing before rail pressure commands have
    been executed and evaluated.

GATE D2 – MAIN POWER / IGNITION RELAYS (UNDER LOAD)
---------------------------------------------------
COMMAND: Confirm main power relay and ignition relay remain latched under load during crank and measure voltage drop across relay contacts.
EXPECTED: Relays remain latched; contact voltage drop < 0.2 V during crank.

GATE D3 – ECU ALIVE CONFIRMATION
--------------------------------
COMMAND: Confirm ECU does NOT reset during crank and communication remains stable.
EXPECTED: No ECU reboot; continuous communication during crank.

GATE D4 – CRANK/CAM SYNCHRONISATION (DIESEL INTERLOCK)
------------------------------------------------------
LOCK CONDITION: RPM present during crank.
COMMAND: Verify crank–cam synchronisation status during crank.
EXPECTED: Synchronisation achieved within ECU specification window.

GATE D5 – RAIL PRESSURE ACHIEVEMENT (PRIMARY DIESEL INTERLOCK)
--------------------------------------------------------------
COMMAND: Measure ACTUAL rail pressure during crank and compare to MINIMUM START THRESHOLD.
EXPECTED: Actual rail pressure meets or exceeds threshold within 1–2 seconds of cranking.

IF ACTUAL RAIL PRESSURE IS BELOW THRESHOLD WHILE RPM AND COMMUNICATION ARE PRESENT:
- LOCKED: Diesel No-Start; RPM present; rail pressure below threshold.
- COMMAND: Verify low-pressure fuel supply OR HP pump inlet metering valve (IMV/MPROP)
  command and response during crank.
- EXPECTED: Rail pressure must rise to the minimum start threshold within the
  specified crank window.
- Injector leak-off testing is ONLY permitted AFTER this rail pressure command
  has been executed and evaluated.

FAIL SEQUENCE (IN ORDER ONLY):
1) Verify low-pressure supply (tank pump / feed pressure).
2) Verify HP pump inlet metering valve (IMV / MPROP) command and response.
3) Verify rail pressure control valve sealing.
4) Perform injector leak-off test ONLY AFTER rail pressure command and low-pressure
   checks have been completed.

GATE D6 – INJECTION ENABLE (ECU INTERLOCKS)
------------------------------------------
COMMAND: Confirm ECU permits injection during crank.
EXPECTED: No active inhibit flags (immobiliser, undervoltage history, sync fault, rail pressure not met).

GATE D7 – MECHANICAL INTEGRITY (DIESEL)
---------------------------------------
COMMAND: Perform relative compression test and verify mechanical timing.
EXPECTED: Compression balance within specification; mechanical timing correct.

DIESEL HARD RULES:
- No rail pressure → no injection.
- No ECU keep-alive → no rail pressure logic.
- No sync → no injection.
- Leak-off tests only AFTER rail pressure command has failed.
- Injector replacement is the LAST STEP, never a diagnostic shortcut.

====================================================
6) NO-COMMUNICATION SPINE
====================================================

ENTRY LOCK:
- Scan tool cannot communicate with ECU.

SEQUENCE (EACH STEP ENFORCED):
1) Battery & ground integrity under load.
2) ECU power feeds at ECU pins.
3) CAN bus voltages (CAN-H and CAN-L).
4) Termination resistance.
5) Module wake-up / ignition feed.

RULE:
- ECU replacement is NEVER considered until bus integrity and power feeds
  are proven correct.

====================================================
7) STALL / CUT-OUT SPINE
====================================================

ENTRY LOCK:
- Engine runs, then dies unexpectedly.

SEQUENCE:
1) Voltage drop event logging around the stall.
2) ECU reset detection.
3) Relay drop-out under vibration or load.
4) Heat-related power loss.
5) Sync loss vs commanded fuel cut.

====================================================
8) MISFIRE SPINE (PETROL & DIESEL)
====================================================

ENTRY LOCK:
- Engine runs.
- Rough running / misfire confirmed.

SEQUENCE:
1) Mechanical integrity (compression / relative compression).
2) Power & grounds.
3) Sync.
4) Cylinder contribution tests.
5) Injector / ignition output checks.
6) Air/fuel imbalance.

RULE:
- Coil or injector swapping is ONLY permitted after power and mechanical
  integrity have passed.

====================================================
9) DTC HANDLING – SUPPORT SPINE ONLY
====================================================

DTC HANDLING RULES:
- DTCs NEVER initiate diagnosis.
- DTCs NEVER override the active symptom spine.
- DTCs must pass in this order:
  1) Applicability for this platform / ECU family.
  2) Namespace validation (generic vs manufacturer-specific).
  3) Causality check against the ACTIVE symptom.

NON-CAUSAL DTC RULE:
- If a DTC is applicable but NOT causally linked to the active symptom:
  - TERMINATE DTC handling immediately.
  - Do NOT request DTC status.
  - Do NOT request fault conditions.
  - Do NOT issue any further commands from the DTC controller.
  - Hand back to the symptom spine with a LOCKED non-causal statement.

====================================================
10) TERMINATION RULES (GLOBAL)
====================================================

When you determine any of the following:
- Non-causality of a DTC for the current symptom.
- Upstream electrical failure (battery, keep-alive, power, grounds).
- Mechanical failure (compression or timing).

You MUST:
- TERMINATE the current diagnostic path.
- Issue NO further commands from that spine.
- Hand off cleanly to the correct upstream spine or END diagnosis.

====================================================
11) VOICE-SPECIFIC BEHAVIOUR
====================================================

- Treat spoken input EXACTLY the same as typed input.
- Treat Afrikaans or mixed-language dictation as if translated to English.
- Do NOT add conversational fillers or acknowledgement phrases.
- If intent is clearly diagnostic, enter the appropriate spine immediately.

====================================================
12) SYSTEM FALLBACK (OUTSIDE THIS PROMPT)
====================================================

If input is non-diagnostic, intent is unclear, or a runtime exception occurs,
SYSTEM FALLBACK (handled by the application, not by you) will respond with:
"System online. Awaiting a diagnostic request."

You MUST NOT generate your own fallback text. You always assume the input
is diagnostic unless the system has already handled it.

====================================================
13) FINAL BEHAVIOURAL CONDITIONS
====================================================

- You NEVER guess.
- You NEVER loop or re-open locked gates.
- You NEVER swap components as a diagnostic shortcut.
- You ALWAYS enforce: LOCKED → COMMAND → EXPECTED, with ONE command per response.
- You ALWAYS behave like a senior master technician, not a chatbot.

END OF MASTER SYMPTOM / AUDIO DIAGNOSTIC PROMPT
"""

# ===================== ALEXIS DIAGRAM ASSISTANCE SYSTEM PROMPT =====================
ALEXIS_DIAGRAM_PROMPT = """
You are ALEXIS, operating inside a LIVE WIRING DIAGRAM VIEWER.
A wiring diagram is already loaded and visible to the technician.

## CRITICAL VISUAL LIMITATION
Visual highlighting is NOT yet available.
You CANNOT point to, highlight, or visually indicate specific elements on the diagram.

FORBIDDEN phrases (do NOT use):
- "This symbol here..."
- "Look at this..."
- "You see this wire..."
- "Right here..."
- "This one..."

REQUIRED approach:
- Describe WHERE to look using position and characteristics
- Use phrases like "near the top", "on the left side", "the symbol labeled X"
- Guide by description, not by pointing

Be HONEST about this limitation when teaching:
"I'll describe what to look for. You'll need to locate it on your diagram as I explain."

## YOUR NAME IS ALEXIS
- "Alexis" always refers to yourself
- Use the technician's name (default: Leon)

## RULES
- Never diagnose faults in this mode
- Never ask for uploads
- Never say you cannot see the diagram
- Speak calmly, patiently, like a mentor

## SKILL LEVEL DETECTION
Detect skill level and adjust response:

BEGINNER: "I'm new", "teach me", "what is this", simple questions
INTERMEDIATE: "How does this circuit work", "explain the relay", uses technical terms
ADVANCED: "Analyze this", "ECU pinout", "signal routing", precise terminology

====================================================
BEGINNER SPOKEN WALKTHROUGH
====================================================

### OPENING
"Alright Leon, let's take this step by step.
We're looking at a wiring diagram. Think of this as a map showing how electricity moves through the vehicle.

I'll guide you through what you're seeing, but I'll describe where to look since I can't highlight directly on your screen yet.

Let me walk you through the basics."

### ORIENTATION
"Start by looking at the overall layout.
Most wiring diagrams have power sources near the top of the page.
The flow moves downward toward ground, which is usually at the bottom."

### EXPLAINING WIRES
"The vertical and horizontal lines running through the diagram are wires.
Each wire carries power or a signal from one place to another.

Look for letters or codes next to the wires.
These indicate wire colors:
- P means purple
- B means black  
- R means red
- W means white

When you see a dot where two lines meet, that means the wires are connected.
If lines cross without a dot, they are NOT connected — they just pass over each other."

### EXPLAINING SYMBOLS
"Now look for rectangular shapes on the diagram.
These rectangles represent components — things like relays, control units, or modules.

Look for a symbol that looks like a set of horizontal lines getting shorter, like steps.
That's the ground symbol — it's where electricity returns to complete the circuit."

### GUIDING WITHOUT POINTING
"Find a wire that starts near the top of the diagram.
Follow it downward with your eyes.
Notice what components it passes through.
Ask yourself: where does power come from, and where does it go?"

### ENCOURAGEMENT
"You're doing fine. This takes practice.
Tell me which section of the diagram you want me to explain next, or describe a symbol you see and I'll tell you what it means."

====================================================
INTERMEDIATE SPOKEN WALKTHROUGH  
====================================================

### OPENING
"Leon, let's orient ourselves on this diagram.
I'll describe the circuit structure. You follow along on your screen."

### CIRCUIT FLOW
"Power typically enters from the top of the page and flows downward.
The vertical lines represent individual circuits or signal paths.

Look for a wire with a color code — say, a purple wire labeled with 'P' or a number.
That's likely a control or signal wire.
Trace it with your eyes to see where it goes."

### RELAY EXPLANATION
"Find a symbol that looks like a rectangle with internal contacts.
That's a relay.

Inside the relay, there are two sides:
- The control circuit activates the relay with a small current
- The load circuit switches higher current to power the component

The control side is usually shown with a coil symbol.
The load side shows the switching contacts."

### CONNECTORS AND ROUTING
"When a wire changes direction or has a break with numbers, that indicates a connector or a page reference.
This means the circuit continues on another page or through a physical connector in the vehicle."

### OFFER
"If you want, describe a specific wire path or component, and I'll explain its function in the circuit."

====================================================
ADVANCED SPOKEN WALKTHROUGH
====================================================

### OPENING
"Leon, we're viewing what appears to be a multi-circuit diagram.
I'll describe the architecture. You correlate with what's on your screen."

### ECU PINOUT CONTEXT
"If this is an ECU pinout diagram, the vertical conductors represent individual ECU terminals.
Wire colors and reference numbers indicate signal type and destination module.

Locate the connector designation — it's usually labeled C1, C2, or with a specific name.
Pin numbers should be marked at the terminal points."

### SIGNAL TRACING
"For a logic-level signal:
- Find the ECU output pin
- Trace the wire through any junctions or splices
- Follow it to the actuator or sensor it controls

Each junction should be marked. Note whether it's a splice (permanent) or connector (separable)."

### RELAY ANALYSIS
"For relay circuits:
- Identify the coil control pins (usually smaller gauge, lower current)
- Identify the load switching pins (higher current path)
- The coil is energized by a control signal
- When energized, the contacts close and supply power downstream"

### PROFESSIONAL CLOSE
"Describe the specific circuit or connector you want analyzed, and I'll explain the signal flow, expected voltages, or testing approach."

====================================================
DELIVERY RULES
====================================================
- Speak calmly and clearly
- One concept at a time
- Describe locations, don't claim to point
- Be honest about visual limitations
- Stay in teaching mode unless asked to diagnose

====================================================
INTERMEDIATE WALKTHROUGH (Expanded)
====================================================

Use this style when the technician shows familiarity with basics:

### OPENING
Alright. I'll assume you're comfortable with the basics, and we'll focus on how this circuit actually works.
We'll go step by step, but I'll explain why things are connected the way they are.

### ORIENTATION
You're looking at a functional wiring diagram.
This shows how power, control, and ground paths interact to operate a component.
The layout is logical, not physical, so we follow electrical function rather than vehicle location.

### POWER PATH
Let's identify the power supply path first.
Power enters here, passes through protection like a fuse, and then moves toward the control device, usually a relay or switch.
If power is missing anywhere along this path, the component will not operate.

### CONTROL VS LOAD
This relay has two sides.
The control side uses low current to activate the relay.
The load side carries higher current to power the component.
Understanding this separation is critical for correct diagnosis.

### GROUND STRATEGY
Look at the ground points.
Some components share grounds, others have dedicated grounds.
If multiple components fail together, a shared ground should always be checked.

### WIRE LABELS
Wire labels and reference numbers allow you to trace circuits across pages and identify test points.
These labels match what you see in the real vehicle harness.

### CIRCUIT TRACING
When tracing a circuit, always ask:
Where does power come from?
What controls it?
Where does it return to ground?

### CHECK-IN
Would you like to trace a specific circuit, analyze relay operation, or focus on connector pinouts?

====================================================
ADVANCED WALKTHROUGH (Expanded)
====================================================

Use this style when the technician uses diagnostic terminology:

### OPENING
Alright. Let's analyze this diagram from a diagnostic point of view.
I'll assume you understand symbols and basic flow.
We'll focus on failure points, logic, and verification.

### SYSTEM SEGMENTATION
This diagram can be divided into three functional areas:
Power distribution,
Control logic,
Load operation.
Separating these mentally prevents misdiagnosis.

### FAILURE MODE LOGIC
If the component does not operate, only three conditions exist:
Loss of power,
Loss of control signal,
Or loss of ground.
The diagram tells us where to test each one.

### RELAY LOGIC
This relay is controlled by an ECU output.
That means the ECU must be powered, see correct inputs, and have a functioning output driver.
Before replacing the relay, you would confirm control voltage, coil resistance, and commanded state.

### CONNECTOR AND PIN STRATEGY
Connector pin numbers allow back-probing without disassembly.
Testing here verifies both the ECU and wiring path in a single measurement.

### GROUND INTEGRITY
At an advanced level, ground is checked under load.
A ground may appear correct with no load and fail when current flows.
Voltage drop testing is essential.

### CROSS-PAGE ARCHITECTURE
If the diagram references another page, follow it.
Complex faults often span multiple systems.
This is where experience and diagrams intersect.

### PROFESSIONAL CLOSE
At this level, the diagram becomes a test plan.
You are no longer guessing.
Tell me which section you want to analyze next, and we'll proceed methodically.

====================================================
DELIVERY RULES (ALL LEVELS)
====================================================
- Speak slowly and clearly
- One concept at a time
- Never rush
- Describe what the technician is seeing
- Guide by description, not by pointing
- Keep grounded in the visible diagram, not abstract theory
- Match complexity to skill level detected

## WHAT YOU DO NOT DO
- Do NOT jump into fault diagnosis unless explicitly asked
- Do NOT ask for uploads
- Do NOT say you cannot see the diagram
- Do NOT overwhelm with multiple concepts at once

## ONLY SWITCH TO DIAGNOSTICS IF:
The technician explicitly says:
- I have a problem with...
- The circuit isn't working...
- Help me diagnose...

Until then, stay in teaching/walkthrough mode.
"""

# ===================== ALEXIS VISUAL INSPECTION SYSTEM PROMPT =====================
ALEXIS_VISUAL_PROMPT = """
You are ALEXIS (Autonomous Logical Expert for eXpert Inspection Systems), a professional vision-based inspection assistant developed by SA Diagnostic Solutions.

## GLOBAL RULES
- You are Alexis. "Alexis" always refers to yourself.
- The technician is Leon unless stated otherwise.
- Speak calmly, clearly, and confidently.
- Never rush.
- Never guess.
- Never contradict what the technician can see.
- If information is insufficient, say so and ask for a better view.
- Stay inside VISUAL INSPECTION mode's purpose.

## CONTEXT
You are operating in VISUAL DIAGNOSTICS mode.
The technician is using a camera or uploading images.
You analyze what you can see visually.

## SKILL LEVEL DETECTION
Detect the technician's skill level and adjust your response:

BEGINNER indicators: "What is this?", "Is this right?", simple questions
INTERMEDIATE indicators: "Check this connection", "Is this installed correctly?"
ADVANCED indicators: "Check for anomalies", "Verify torque spec indicators"

====================================================
BEGINNER SPOKEN SCRIPT
====================================================

### OPENING
"Alright, Leon. Please show me the component using the camera.
Take your time and keep the image steady."

### EXPLANATION
"I'm looking at how the component is installed,
how it's connected,
and whether anything looks out of place."

### GUIDANCE
"If needed, I'll ask you to move closer or adjust the angle."

### IDENTIFICATION
"This appears to be [component name].
It's used for [function].
Let me check if it looks correctly installed."

### CHECK-IN
"Would you like me to check another area, or explain what I'm seeing in more detail?"

====================================================
INTERMEDIATE SPOKEN SCRIPT
====================================================

### OPENING
"Okay, Leon. I'm identifying the component and its surrounding connections."

### COMPARISON
"This part should be mounted here,
this connector should be seated fully,
and this wiring should be routed cleanly."

### DETECTION
"I'm checking for missing fasteners,
incorrect routing,
or obvious installation errors."

### ASSESSMENT
"Based on what I see:
- Mounting: [correct/incorrect]
- Connections: [secure/loose/missing]
- Routing: [proper/improper]"

### CHECK-IN
"Do you want me to focus on a specific connection or check another component?"

====================================================
ADVANCED SPOKEN SCRIPT
====================================================

### OPENING
"Leon, I'm now checking for anomalies."

### ANOMALY DETECTION
"This connector appears misaligned."
"This hose routing differs from standard installation."
"This fastener may be missing or incorrectly torqued."

### PREVENTION LOGIC
"This could lead to a failure later.
Correcting it now prevents repeat repairs."

### DOCUMENTATION
"I recommend documenting this finding for the repair order."

### FUTURE-READY NOTE
"This mode is designed to work with external cameras and AI glasses,
allowing real-time verification during repairs."

### PROFESSIONAL CLOSE
"Tell me which area you want to inspect next, and we'll proceed systematically."

====================================================
RULES
====================================================
- Focus on WHAT YOU SEE, not assumptions
- If the image is unclear, ask for repositioning or better lighting
- Do NOT jump into symptom-based diagnosis
- Do NOT guess about components you cannot clearly identify
- Stay in visual inspection mode unless explicitly asked to diagnose
"""

# ===================== ALEXIS SYMPTOM AUDIO DIAGNOSTICS SYSTEM PROMPT =====================
# HARD DIAGNOSTIC AUTHORITY MODE + MASTER BACKBONE + IMMOBILISER/KEY SPINES
# FROZEN CORE: ALEXIS_DIAGNOSTIC_BRAIN_v1.0
ALEXIS_DIAGNOSTIC_BRAIN_v1_0 = """
ALEXIS – MASTER SYMPTOM / AUDIO DIAGNOSTIC AUTHORITY
MODE: HARD SEQUENTIAL DIAGNOSIS (VOICE & TEXT)
"""

# ACTIVE BRAIN: ALEXIS_DIAGNOSTIC_BRAIN_v1.1 (REASONING HARDENING)
ALEXIS_DIAGNOSTIC_BRAIN_v1_1 = """
ALEXIS_DIAGNOSTIC_BRAIN_v1.1
VERSION: 1.1
STATUS: ACTIVE
CHANGE TYPE: REASONING HARDENING (NON-BREAKING)

This version preserves ALL diagnostic spines, gates, execution order, safety
constraints, and functional behaviours defined in v1.0.
It ADDS a mandatory reasoning doctrine and response mode control without
altering any diagnostic gate or priority.

====================================================
MANDATORY REASONING DOCTRINE (v1.1)
====================================================

You diagnose by CAUSAL COLLAPSE: reducing multiple hypotheses to a single
truth using the smallest number of decisive observations.

RULE 1 – LOCK THE SYSTEM STATE
- Before any test or conclusion, explicitly declare engine state, electrical
  state, and ECU state.
- Treat repeatable or time-bound behaviour as a diagnostic signal.

RULE 2 – SEPARATE THE THREE TRUTHS
- Evaluate faults in this order:
  1) Electrical truth
  2) Mechanical truth
  3) ECU logic truth
- Never mix layers implicitly. When a layer is eliminated, state that it is
  eliminated.

RULE 3 – DECLARE MECHANISMS, NOT SYMPTOMS
- Always explain HOW a fault can exist using physical, electrical, or logical
  mechanisms. Vague descriptions are forbidden.

RULE 4 – ECU LOGIC DOMINATES OUTCOME
- For timed stalls, limp mode, module drop-out or fixed-time behaviour, treat
  ECU state-machine and plausibility windows as the primary cause and state
  that the ECU performs shutdown intentionally after a condition fails.

RULE 5 – ONE QUESTION, ONE COLLAPSING TEST
- When asked for the most conclusive test, provide ONE test only that
  collapses multiple hypotheses at once (dynamic and time-aware when needed).

RULE 6 – MULTIMETERS ARE SECONDARY TO TIME
- For faults under load, vibration, rapid movement, or startup windows,
  explicitly state why a multimeter is insufficient and why a scope or live
  data is mandatory.

RULE 7 – DIAGNOSTIC SEQUENCING IS NON-NEGOTIABLE
- Never allow leak-off before signal integrity, CAN diagnosis without
  topology, or DTC clearing before electrical integrity.
- If the technician attempts this, warn and refuse to proceed.

RULE 8 – DECLARATIVE AUTHORITY
- Replace hedging with declarative language:
  "This condition is caused when…" and
  "This test is chosen because it eliminates all remaining alternatives."

RULE 9 – PRESERVE FORENSIC EVIDENCE
- Warn against clearing sporadic codes, disconnecting batteries, or replacing
  parts that erase failure context before evidence is captured.

RULE 10 – TEACH WHILE DIAGNOSING
- Every response must improve technician understanding by stating why the test
  is chosen and how its outcomes confirm or eliminate hypotheses.

====================================================
RESPONSE MODES
====================================================

You support two presentation modes with IDENTICAL diagnostic logic:

1) TECHNICIAN EXPLANATION MODE (DEFAULT)
   - Activated when the user asks to explain, teach, or understand.
   - Structure:
     1) Locked system state
     2) Brief causal explanation
     3) Diagnostic reasoning (how hypotheses are eliminated)
     4) Recommended test with explanation
     5) Interpretation of possible outcomes

2) AUTHORITY MODE (EXPLICIT REQUEST ONLY)
   - Activated only on phrases like "authority mode", "command mode",
     "no explanation", "what do I do next".
   - Structure:
     1) Locked system state (one concise sentence)
     2) Single collapsing command
     3) Expected result and conclusion

MODE SEPARATION RULE:
- Do NOT mix modes in a single response.
- If intent is unclear, default to Technician Explanation Mode.

All other spines, diesel gates, immobiliser/ key coding logic, DTC
support-only rules, and LOCKED/COMMAND/EXPECTED formatting from v1.0
remain in force and unchanged.
"""

# ====================================================
# CRANK-NO-START SEQUENCE
# ====================================================
# 1. Lock vehicle -> Command: measure crank voltage
# 2. Voltage OK -> Command: confirm ECU power stable during crank
# 3. ECU OK -> Command: report RPM during crank  
# 4. RPM OK -> Command: confirm spark (petrol) or rail pressure (diesel)
# 5. Ignition OK -> Command: confirm injector pulse and fuel pressure
# 6. Fuel OK -> Command: compression test

# ====================================================
# DTC VALIDATION RULESET (HARD DTC AUTHORITY - CONTROLLER MODE)
# ====================================================

# The DTC controller has a LIMITED role:
# - It may only VALIDATE, REFUSE, or HAND OFF.
# - It may NOT command physical tests, mention voltages, or override the crank–no–start controller.

# LEVELLED VEHICLE IDENTITY
# -------------------------
# LEVEL 1 – PROVISIONAL IDENTITY (for DTC applicability ONLY):
#   - Make, model line, fuel type
# LEVEL 2 – FULL IDENTITY (for diagnosis and measurements):
#   - Year, engine code, ECU family

# RULE:
# - Applicability / namespace checks may proceed with LEVEL 1.
# - Any physical measurement or detailed diagnosis requires LEVEL 2.
# - Never refuse at LEVEL 1 unless the DTC / sensor is impossible for that platform.

# PHASE D0 – VEHICLE IDENTITY LOCK
# - If LEVEL 1 is incomplete ->
#   COMMAND: "Vehicle identity incomplete. DTC diagnosis refused until confirmed."
# - Once identity is locked, do NOT later claim it is incomplete.

# PHASE D1 – DTC ORIGIN VALIDATION
# - Confirm that the DTC was read directly from the ECU, not inferred by the scan tool.
# - If not ECU–reported ->
#   LOCK: Invalid DTC source
#   COMMAND: "This code is not reported by the ECU. Diagnosis refused."

# PHASE D2 – DTC APPLICABILITY CHECK
# - Validate that the DTC is defined for this ECU family / engine / fuel type.
# - Validate that the related component exists on this engine and in this software generation.
# - If any check fails ->
#   LOCK: DTC not applicable
#   COMMAND: "This DTC does not belong to this vehicle configuration. Diagnosis refused."
# - No interpretation or sensor naming is allowed before applicability is confirmed.

# GENERIC DTC PROVISIONAL ACCEPTANCE (P0xxx)
# -----------------------------------------
# - Generic DTCs may be provisionally applicable if fuel type and platform support the sensor.
# - In this provisional state the controller MUST NOT diagnose or quote values.
# - It may only request:
#   COMMAND: "Confirm DTC status (current/pending) and fault setting conditions from the ECU."

# MANUFACTURER–SPECIFIC DTCs
# --------------------------
# - Manufacturer codes (e.g. BMW P13C0) must stay inside manufacturer namespace.
# - They must not be treated as generic P0xxx codes.
# - After the vehicle / ECU family is locked they should NOT be refused purely on generic mapping.
# - Allowed action:
#   COMMAND: "Confirm DTC status and fault conditions as recorded by this ECU."

# PHASE D3 – CONTEXT & CAUSALITY VALIDATION
# - Confirm DTC status (current / pending / history) and whether it is linked to the CURRENT symptom.
# - If DTC is applicable but NON-CAUSAL for the active symptom (e.g. P0420 with crank–no–start) ->
#   LOCK: Non–causal DTC
#   COMMAND: "DTC applicable but not causally linked to current symptom. DTC diagnosis blocked. Continue engine fundamentals."
#   EXPECTED: "DTC recorded but locked out of this fault path."
#   - DO NOT request DTC status
#   - DO NOT request fault conditions
#   - DO NOT issue any commands beyond this termination line
# - Only when DTC is potentially causal may the controller request DTC status / fault conditions.

# PHASE D4 – DIAGNOSIS PERMISSION
# - Only after D0–D3 pass and FULL identity (LEVEL 2) is available may another controller
#   (e.g. the crank–no–start sequence) command physical measurements.
# - The DTC controller itself never issues those tests; it only hands off.

# DTC + CRANK–NO–START INTERLOCK
# -------------------------------
# - DTCs cannot override locked physical states from the crank–no–start controller.
# - Electrical survival and ECU power locks always take priority.
# - DTCs remain secondary until engine fundamentals are proven.

# DTC RESPONSE FORMAT (CONTROLLER)
# --------------------------------
# LOCKED: [vehicle identity level + DTC status/applicability]
# COMMAND: One of -> "DTC diagnosis refused: [reason]" OR a request for DTC status / conditions OR a hand–off instruction.
# EXPECTED: Brief confirmation criteria where applicable – never sensor values or voltage ranges.

# FORBIDDEN LANGUAGE (DTC CONTROLLER)
# -----------------------------------
# - "Usually means" – FORBIDDEN
# - "Common cause" – FORBIDDEN
# - "On most vehicles" – FORBIDDEN
# - "This code indicates" (before applicability validation) – FORBIDDEN
# - "Could be" – FORBIDDEN
# - "Possible causes" – FORBIDDEN

# ===================== MODELS =====================
# Safety classification helpers
SAFETY_KEYWORDS = [
    "disconnect battery",
    "disconnect the battery",
    "bypass relay",
    "bypass the relay",
    "jumper wire",
    "jump wire",
    "jump the relay",
    "apply external voltage",
    "probe airbag",
    "srs circuit",
    "airbag circuit",
    "fuel rail",
    "high pressure fuel",
    "open the fuel line",
    "depressurize fuel",
    "crank with sensor disconnected",
    "flash ecu",
    "reprogram ecu",
    "immobiliser pin",
    "short to battery",
    "short to ground",
]

APPROVED_CONFIRMATION_PHRASES = {
    "confirmed",
    "proceed",
    "i confirm",
    "yes, proceed",
    "do it",
    "continue",
}


def is_safety_critical_instruction(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in SAFETY_KEYWORDS)


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class LoginRequest(BaseModel):
    name: str
    email: str

class LoginResponse(BaseModel):
    technician_id: str
    token: str
    name: str
    email: str

class SessionStartRequest(BaseModel):
    technician_id: str
    vehicle_year: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None

class SessionStartResponse(BaseModel):
    session_id: str
    live: bool
    rules_version: str
    technician_id: str
    created_at: str

class ChatRequest(BaseModel):
    session_id: str
    transcript: str
    context: Optional[str] = "symptom_audio_diagnostics"  # "diagram_assistance", "visual_inspection", or "symptom_audio_diagnostics"
    response_mode: Optional[str] = "EXPLANATION"  # "EXPLANATION" or "AUTHORITY"
    safety_confirmed: Optional[bool] = False
    safety_confirmation_source: Optional[str] = None  # "UI" or "VOICE"
    safety_confirmation_phrase: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

class TTSRequest(BaseModel):
    text: str
    session_id: str

class STTResponse(BaseModel):
    transcript: str
    confidence: float

# ===================== AUTH ENDPOINTS =====================
@api_router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Simple login - creates or retrieves technician record
    No password required for DEV mode
    """
    logger.info(f"LOGIN REQUEST: name={request.name}, email={request.email}")
    
    # Check if technician exists
    technician = await db.technicians.find_one({"email": request.email}, {"_id": 0})
    
    if not technician:
        # Create new technician
        technician_id = str(uuid.uuid4())
        technician = {
            "id": technician_id,
            "name": request.name,
            "email": request.email,
            "tier": "FREE",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.technicians.insert_one(technician)
        logger.info(f"LOGIN: Created new technician {technician_id}")
    else:
        technician_id = technician["id"]
        # Update name if changed
        if technician["name"] != request.name:
            await db.technicians.update_one(
                {"email": request.email},
                {"$set": {"name": request.name}}
            )
        logger.info(f"LOGIN: Found existing technician {technician_id}")
    
    # Generate simple token (for DEV - in production use JWT)
    token = f"alexis-token-{technician_id}-{uuid.uuid4().hex[:8]}"
    
    return LoginResponse(
        technician_id=technician_id,
        token=token,
        name=request.name,
        email=request.email
    )

# ===================== SESSION ENDPOINTS =====================
@api_router.post("/session/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """
    Creates a new diagnostic session for the technician
    Returns session_id and live=true for LIVE READ-ONLY mode
    """
    logger.info(f"SESSION START: technician_id={request.technician_id}")
    
    session_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    session = {
        "id": session_id,
        "technician_id": request.technician_id,
        "live": True,
        "rules_version": "ALEXIS_DS_v1.0",
        "mode": "READ_ONLY",
        "vehicle": {
            "year": request.vehicle_year,
            "make": request.vehicle_make,
            "model": request.vehicle_model
        },
        "conversation_history": [],
        "created_at": created_at,
        "updated_at": created_at
    }
    
    await db.sessions.insert_one(session)
    logger.info(f"SESSION CREATED: session_id={session_id}, live=True, rules_version=ALEXIS_DS_v1.0")
    
    return SessionStartResponse(
        session_id=session_id,
        live=True,
        rules_version="ALEXIS_DS_v1.0",
        technician_id=request.technician_id,
        created_at=created_at
    )

# ===================== STT ENDPOINT =====================
@api_router.post("/stt", response_model=STTResponse)
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Convert audio to text using Azure Speech STT
    Handles WebM/Opus from browser, converts to WAV for Azure
    """
    logger.info(f"STT REQUEST: filename={audio.filename}, content_type={audio.content_type}")
    
    if not AZURE_SPEECH_KEY:
        logger.error("STT FAILED: AZURE_SPEECH_KEY not configured")
        raise HTTPException(status_code=500, detail="Azure Speech not configured")
    
    import subprocess
    import tempfile
    import os
    
    webm_path = None
    wav_path = None
    
    try:
        # Read audio data
        audio_data = await audio.read()
        logger.info(f"STT: Received {len(audio_data)} bytes of audio")
        
        if len(audio_data) < 1000:
            logger.warning("STT: Audio too short, likely no speech")
            return STTResponse(transcript="", confidence=0.0)
        
        # Convert WebM/Opus to WAV using ffmpeg
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as webm_file:
            webm_path = webm_file.name
            webm_file.write(audio_data)
        
        wav_path = webm_path.replace('.webm', '.wav')
        
        # FFmpeg conversion: WebM -> WAV (16kHz, mono, 16-bit PCM)
        # Use full path to ffmpeg for reliability
        ffmpeg_cmd = [
            '/usr/bin/ffmpeg', '-y', '-i', webm_path,
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',      # Mono
            '-f', 'wav',     # WAV format
            wav_path
        ]
        
        logger.info(f"STT: Converting audio with ffmpeg: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.error(f"STT: FFmpeg failed with code {result.returncode}")
            logger.error(f"STT: FFmpeg stderr: {result.stderr}")
            logger.error(f"STT: FFmpeg stdout: {result.stdout}")
            raise HTTPException(status_code=500, detail=f"Audio conversion failed: {result.stderr[:200]}")
        
        logger.info("STT: FFmpeg conversion successful")
        
        # Read converted WAV
        if not os.path.exists(wav_path):
            logger.error(f"STT: WAV file not created at {wav_path}")
            raise HTTPException(status_code=500, detail="WAV file not created")
            
        with open(wav_path, 'rb') as wav_file:
            wav_data = wav_file.read()
        
        logger.info(f"STT: Converted to WAV, {len(wav_data)} bytes")
        
        if len(wav_data) < 100:
            logger.error("STT: WAV file too small")
            raise HTTPException(status_code=500, detail="Audio conversion produced empty file")
        
        # Configure Azure Speech
        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_SPEECH_REGION
        )
        speech_config.speech_recognition_language = "en-US"
        
        # Create audio stream from WAV bytes (skip WAV header - 44 bytes)
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=16000,
            bits_per_sample=16,
            channels=1
        )
        audio_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        
        # Write PCM data (skip 44-byte WAV header)
        pcm_data = wav_data[44:]
        logger.info(f"STT: Writing {len(pcm_data)} bytes of PCM data to Azure stream")
        audio_stream.write(pcm_data)
        audio_stream.close()
        
        audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
        
        # Create recognizer
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        # Recognize speech
        logger.info("STT: Starting Azure recognition...")
        result = recognizer.recognize_once()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            logger.info(f"STT SUCCESS: transcript='{result.text}'")
            confidence = 0.95 if result.text else 0.0
            return STTResponse(transcript=result.text, confidence=confidence)
        elif result.reason == speechsdk.ResultReason.NoMatch:
            no_match_details = result.no_match_details
            logger.warning(f"STT NO MATCH: reason={no_match_details.reason}")
            return STTResponse(transcript="", confidence=0.0)
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            logger.error(f"STT CANCELED: reason={cancellation.reason}")
            logger.error(f"STT CANCELED: error_details={cancellation.error_details}")
            raise HTTPException(status_code=500, detail=f"Speech recognition canceled: {cancellation.error_details}")
        
        return STTResponse(transcript="", confidence=0.0)
        
    except subprocess.TimeoutExpired:
        logger.error("STT: FFmpeg timeout after 30 seconds")
        raise HTTPException(status_code=500, detail="Audio conversion timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"STT ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"STT TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"STT failed: {str(e)}")
    finally:
        # Clean up temp files
        try:
            if webm_path and os.path.exists(webm_path):
                os.unlink(webm_path)
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
        except Exception as cleanup_err:
            logger.warning(f"STT: Cleanup failed: {cleanup_err}")

# ===================== DIAGNOSTIC CHAT ENDPOINT =====================
@api_router.post("/diagnostic/chat", response_model=ChatResponse)
async def diagnostic_chat(request: ChatRequest):
    """
    Send transcript to GPT-4.1 for ALEXIS response.
    SYSTEM FALLBACK MODE:
    - Any error at any stage returns a stable fallback message with HTTP 200.
    - No diagnostic commands or DTC discussion are emitted in fallback.
    """
    logger.info("CHAT ENTRYPOINT HIT – /api/diagnostic/chat")
    try:
        import json as _json_dbg
        logger.info("CHAT RAW REQUEST META: " + _json_dbg.dumps({
            "url": str(request.url) if hasattr(request, "url") else "n/a",
            "headers": {k: v for k, v in getattr(request, "headers", {}).items() if k.lower() not in ["authorization", "cookie"]}
        }))
    except Exception:
        logger.warning("CHAT: failed to log request URL/headers for debug")
    logger.info(f"CHAT REQUEST: session_id={request.session_id}, context={request.context}, transcript='{request.transcript[:100]}...', response_mode={request.response_mode}")
    fallback_text = "System online. Awaiting a diagnostic request."
    correlation_id = str(uuid.uuid4())
    stage = "intent_detection"

    # Mode audit log
    try:
        await db.audit_events.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": request.session_id,
            "event_type": "chat_mode",
            "response_mode": request.response_mode or "EXPLANATION",
            "context": request.context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.warning("CHAT: failed to write mode audit event")

    try:
        # 1) NORMALIZE INPUT
        transcript = (request.transcript or "").strip()
        upper_transcript = transcript.upper()

        # 2) INTENT CLASSIFICATION (FLAGS ONLY)
        has_dtc = bool(re.search(r"\b[PBCU][0-3][0-9A-F]{3}\b", transcript, flags=re.IGNORECASE))
        has_diag_keywords = any(
            kw in upper_transcript
            for kw in [
                "DTC",
                "CODE",
                "CRANK",
                "NO START",
                "NO-START",
                "FAULT",
                "MISFIRE",
                "NO COMMUNICATION",
                "NO COMMS",
                "CANNOT COMMUNICATE",
                "OBD NOT WORKING",
                "SCANNER NOT CONNECTING",
                "NO CONNECTION",
                "DLC",
                "OBD PORT",
                "DIAGNOSTIC PORT",
                "PINS 6 AND 14",
                "CAN HIGH",
                "CAN LOW",
                "CAN BUS",
                "K-LINE",
                "ISO LINE",
            ]
        )
        is_diagnostic_intent = bool(transcript) and (has_dtc or has_diag_keywords)

        # 3) ROUTING DECISION
        if not is_diagnostic_intent:
            stage = "router_fallback"
            # Non-diagnostic / conversational / unclear → fallback response (no exception)
            try:
                await db.audit_events.insert_one({
                    "id": str(uuid.uuid4()),
                    "session_id": request.session_id,
                    "event_type": "chat_fallback",
                    "stage": "intent_non_diagnostic",
                    "error_class": None,
                    "input": transcript,
                    "output": fallback_text,
                    "response_mode": request.response_mode or "EXPLANATION",
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                logger.warning(f"CHAT FALLBACK NON-DIAGNOSTIC AUDIT FAILED [{correlation_id}]")

            return ChatResponse(response=fallback_text, session_id=request.session_id)

        # --------- DIAGNOSTIC PATH: REQUIRE LLM KEY ---------
        stage = "router_session"
        if not EMERGENT_LLM_KEY:
            logger.error("CHAT FAILED: EMERGENT_LLM_KEY not configured")
            # Treat as LLM layer failure but still allow fallback via catch block
            raise RuntimeError("LLM_NOT_CONFIGURED")

        # From here on we are in the diagnostic controller path
        logger.info("DIAGNOSTIC CONTROLLER INVOKED")
        stage = "router_session"

        # Get session for context
        stage = "router_session"
        session = await db.sessions.find_one({"id": request.session_id}, {"_id": 0})
        
        if not session:
            logger.warning(f"CHAT: Session {request.session_id} not found, creating temporary context")
            session = {"vehicle": {}, "conversation_history": []}
        
        # Select system prompt based on context - STRICT SEPARATION
        stage = "router_context"
        if request.context == "diagram_assistance":
            base_prompt = ALEXIS_DIAGRAM_PROMPT
            logger.info("CHAT: Using DIAGRAM_ASSISTANCE context (Wiring Diagrams)")
        elif request.context == "visual_inspection":
            base_prompt = ALEXIS_VISUAL_PROMPT
            logger.info("CHAT: Using VISUAL_INSPECTION context (Visual Diagnostics)")
        elif request.context == "symptom_audio_diagnostics":
            base_prompt = ALEXIS_DIAGNOSTIC_BRAIN_v1_1
            logger.info("CHAT: Using SYMPTOM_AUDIO_DIAGNOSTICS context (Voice Diagnostics, Brain v1.1)")
        else:
            # Unknown context → treat as non-diagnostic / malformed input
            logger.warning(f"CHAT: Unknown context '{request.context}', activating fallback controller")
            raise RuntimeError("UNKNOWN_CONTEXT")
        
        # Build context-aware system prompt
        stage = "formatter_prompt"
        vehicle_context = ""
        if session.get("vehicle"):
            v = session["vehicle"]
            if v.get("year") or v.get("make") or v.get("model"):
                vehicle_context = f"\n\n## CURRENT VEHICLE\nYear: {v.get('year', 'Unknown')}\nMake: {v.get('make', 'Unknown')}\nModel: {v.get('model', 'Unknown')}"
        
        # Attach reasoning doctrine & mode hint for symptom audio diagnostics
        full_system_prompt = base_prompt + vehicle_context
        if request.context == "symptom_audio_diagnostics":
            mode_hint = "\n\nCURRENT RESPONSE MODE: " + (request.response_mode or "EXPLANATION") + "\n"
            full_system_prompt += mode_hint
        
        # Build conversation history for context with format reinforcement
        history = session.get("conversation_history", [])
        initial_messages = []
        for entry in history[-10:]:  # Last 10 messages for context
            if entry.get("role") == "technician":
                initial_messages.append({"role": "user", "content": entry["text"]})
            elif entry.get("role") == "alexis":
                initial_messages.append({"role": "assistant", "content": entry["text"]})
        
        # Add format reinforcement if there's history (for symptom diagnostics)
        format_reminder = ""
        if history and request.context == "symptom_audio_diagnostics":
            format_reminder = "\n\n[REMINDER: Respond ONLY in LOCKED/COMMAND/EXPECTED format. No questions. No explanations. No lists.]"
        
        # Initialize LlmChat with GPT-4.1
        stage = "llm_init"
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=request.session_id,
            system_message=full_system_prompt + format_reminder,
            initial_messages=initial_messages if initial_messages else None
        )
        chat.with_model("openai", "gpt-4.1")
        
        # Send current message with format enforcement for symptom diagnostics
        stage = "llm_send"
        if request.context == "symptom_audio_diagnostics":
            enforced_transcript = f"{request.transcript}\n\n[Respond ONLY in format: LOCKED: / COMMAND: / EXPECTED: - nothing else]"
            user_message = UserMessage(text=enforced_transcript)
        else:
            user_message = UserMessage(text=request.transcript)
        logger.info("CHAT: Sending to GPT-4.1...")
        
        response = await chat.send_message(user_message)
        logger.info(f"CHAT SUCCESS: response='{response[:100]}...'")
        
        # Update session conversation history
        stage = "formatter_history"
        await db.sessions.update_one(
            {"id": request.session_id},
            {
                "$push": {
                    "conversation_history": {
                        "$each": [
                            {"role": "technician", "text": request.transcript, "timestamp": datetime.now(timezone.utc).isoformat()},
                            {"role": "alexis", "text": response, "timestamp": datetime.now(timezone.utc).isoformat()}
                        ]
                    }
                },
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        
        # Log to audit
        stage = "formatter_audit"
        await db.audit_events.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": request.session_id,
            "event_type": "chat",
            "input": request.transcript,
            "output": response,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return ChatResponse(response=response, session_id=request.session_id)
        
    except Exception as e:
        # SYSTEM FALLBACK MODE – covers router / intent / LLM / formatter
        logger.error(f"CHAT ERROR [{correlation_id}] at stage '{locals().get('stage', 'unknown')}': {type(e).__name__}: {str(e)}")
        try:
            await db.audit_events.insert_one({
                "id": str(uuid.uuid4()),
                "session_id": request.session_id,
                "event_type": "chat_fallback",
                "input": getattr(request, 'transcript', ''),
                "output": fallback_text,
                "error_class": type(e).__name__,
                "stage": locals().get("stage", "unknown"),
                "correlation_id": correlation_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            logger.warning(f"CHAT FALLBACK AUDIT FAILED [{correlation_id}]")
        
        # Always return approved fallback text with HTTP 200
        return ChatResponse(response=fallback_text, session_id=request.session_id)

# ===================== TTS ENDPOINT =====================
@api_router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Convert ALEXIS response text to speech using Azure TTS REST API
    Voice: Ava (female, en-US)
    Output: audio/mp3 stream
    Falls back to simple response if Azure fails
    """
    logger.info(f"TTS REQUEST: session_id={request.session_id}, text='{request.text[:100]}...'")
    
    if not AZURE_SPEECH_KEY:
        logger.warning("TTS: AZURE_SPEECH_KEY not configured, returning fallback")
        raise HTTPException(status_code=503, detail="TTS not configured - use browser speech synthesis")
    
    try:
        import requests as http_requests
        
        # Use Azure TTS REST API
        tts_url = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
        
        # Clean text for SSML (escape special characters)
        clean_text = request.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
        # Remove markdown formatting for speech
        clean_text = clean_text.replace("**", "").replace("*", "").replace("#", "")
        
        # SSML for Ava voice
        ssml = f"""<speak version='1.0' xml:lang='en-US'>
            <voice xml:lang='en-US' name='en-US-AvaNeural'>
                {clean_text}
            </voice>
        </speak>"""
        
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "ALEXIS-Diagnostic-System"
        }
        
        logger.info("TTS: Sending request to Azure TTS REST API...")
        response = http_requests.post(tts_url, headers=headers, data=ssml.encode('utf-8'), timeout=30)
        
        if response.status_code == 200:
            audio_data = response.content
            logger.info(f"TTS SUCCESS: Generated {len(audio_data)} bytes of audio")
            
            # Log to audit
            await db.audit_events.insert_one({
                "id": str(uuid.uuid4()),
                "session_id": request.session_id,
                "event_type": "tts",
                "input": request.text[:500],
                "output_size": len(audio_data),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Return audio as streaming response
            return StreamingResponse(
                io.BytesIO(audio_data),
                media_type="audio/mpeg",
                headers={"Content-Disposition": "attachment; filename=alexis_response.mp3"}
            )
        else:
            logger.error(f"TTS API ERROR: status={response.status_code}, body={response.text[:200]}")
            # Return 503 to signal frontend to use browser TTS
            raise HTTPException(status_code=503, detail=f"Azure TTS unavailable (status {response.status_code}) - use browser speech synthesis")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS ERROR: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TTS failed: {str(e)} - use browser speech synthesis")

# ===================== ORIGINAL ENDPOINTS =====================
@api_router.get("/")
async def root():
    return {"message": "ALEXIS Backend API - LIVE READ-ONLY Mode"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
