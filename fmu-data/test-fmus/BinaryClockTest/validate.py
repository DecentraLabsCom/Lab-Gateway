"""
Comprehensive validation of BinaryClockTest.fmu with fmpy.

Tests:
  1. Schema/metadata validation (read_model_description)
  2. Instantiation, init, doStep lifecycle
  3. Binary Get/Set round-trip
  4. Clock Get periodic ticking
  5. Float64 step counter
"""

import ctypes
import os
import sys
import tempfile
import zipfile

FMU_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "BinaryClockTest.fmu")
FMU_PATH = os.path.abspath(FMU_PATH)

# ── 1. Metadata validation ──────────────────────────────────────────────────

print("=" * 60)
print("1. Metadata validation (fmpy.read_model_description)")
print("=" * 60)

from fmpy import read_model_description

md = read_model_description(FMU_PATH)
assert md.fmiVersion == "3.0", f"fmiVersion: {md.fmiVersion}"
assert md.modelName == "BinaryClockTest"
assert md.coSimulation is not None, "CoSimulation not found"

types = {v.name: v for v in md.modelVariables}
assert types["dataIn"].type == "Binary"
assert types["dataOut"].type == "Binary"
assert types["heartbeat"].type == "Clock"
assert types["stepCount"].type == "Float64"
assert types["time"].causality == "independent"

print(f"  fmiVersion={md.fmiVersion}  modelName={md.modelName}")
print(f"  variables: {[v.name for v in md.modelVariables]}")
print("  PASS: all variable types correct")
print()


# ── 2-5. Runtime validation via ctypes ──────────────────────────────────────

print("=" * 60)
print("2-5. Runtime validation (ctypes direct call)")
print("=" * 60)

# Extract DLL from FMU
tmpdir = tempfile.mkdtemp(prefix="bct_validate_")
with zipfile.ZipFile(FMU_PATH, "r") as zf:
    zf.extractall(tmpdir)

dll_path = os.path.join(tmpdir, "binaries", "x86_64-windows", "BinaryClockTest.dll")
if not os.path.exists(dll_path):
    print(f"  SKIP: DLL not found at {dll_path} (wrong platform?)")
    sys.exit(0)

lib = ctypes.CDLL(dll_path)

# Type aliases
c_double = ctypes.c_double
c_int = ctypes.c_int
c_uint32 = ctypes.c_uint32
c_size_t = ctypes.c_size_t
c_uint8_p = ctypes.POINTER(ctypes.c_uint8)
c_void_p = ctypes.c_void_p

# fmi3GetVersion
lib.fmi3GetVersion.restype = ctypes.c_char_p
version = lib.fmi3GetVersion().decode()
assert version == "3.0", f"fmi3GetVersion returned {version!r}"
print(f"  fmi3GetVersion = {version!r}")

# fmi3InstantiateCoSimulation
lib.fmi3InstantiateCoSimulation.restype = c_void_p
lib.fmi3InstantiateCoSimulation.argtypes = [
    ctypes.c_char_p,  # instanceName
    ctypes.c_char_p,  # instantiationToken
    ctypes.c_char_p,  # resourcePath
    c_int,            # visible
    c_int,            # loggingOn
    c_int,            # eventModeUsed
    c_int,            # earlyReturnAllowed
    ctypes.c_void_p,  # requiredIntermediateVariables
    c_size_t,         # nRequiredIntermediateVariables
    c_void_p,         # instanceEnvironment
    c_void_p,         # logMessage
    c_void_p,         # intermediateUpdate
]

inst = lib.fmi3InstantiateCoSimulation(
    b"inst1", b"{bct-test-guid-0001}", b"", 0, 0, 0, 0,
    None, 0, None, None, None
)
assert inst is not None and inst != 0, "Instantiation failed"
print("  fmi3InstantiateCoSimulation: OK")

# Init
lib.fmi3EnterInitializationMode.restype = c_int
lib.fmi3EnterInitializationMode.argtypes = [c_void_p, c_int, c_double, c_double, c_int, c_double]
status = lib.fmi3EnterInitializationMode(inst, 0, 0.0, 0.0, 1, 10.0)
assert status == 0, f"EnterInit: {status}"

lib.fmi3ExitInitializationMode.restype = c_int
lib.fmi3ExitInitializationMode.argtypes = [c_void_p]
status = lib.fmi3ExitInitializationMode(inst)
assert status == 0, f"ExitInit: {status}"
print("  Initialization: OK")

# ── 3. Binary Get (initial state) ──────────────────────────────────────────

lib.fmi3GetBinary.restype = c_int
lib.fmi3GetBinary.argtypes = [
    c_void_p,
    ctypes.POINTER(c_uint32),
    c_size_t,
    ctypes.POINTER(c_size_t),
    ctypes.POINTER(c_uint8_p),
    c_size_t,
]

# Get dataOut (vr=1)
vr = (c_uint32 * 1)(1)
sizes = (c_size_t * 1)(0)
ptrs = (c_uint8_p * 1)()
status = lib.fmi3GetBinary(inst, vr, 1, sizes, ptrs, 1)
assert status == 0, f"GetBinary(dataOut) failed: {status}"
out_size = sizes[0]
out_bytes = bytes(ptrs[0][i] for i in range(out_size))
# Initial: prefix=0x03 (len of default dataIn) + 0x01 0x02 0x03
assert out_size == 4, f"Expected 4 bytes, got {out_size}"
assert out_bytes[0] == 3, f"Length prefix should be 3, got {out_bytes[0]}"
assert out_bytes[1:] == b"\x01\x02\x03", f"Payload mismatch: {out_bytes[1:]}"
print(f"  fmi3GetBinary(dataOut) initial: {out_bytes.hex()} (len={out_size}) OK")

# ── Binary Set + Get round-trip ────────────────────────────────────────────

lib.fmi3SetBinary.restype = c_int
lib.fmi3SetBinary.argtypes = [
    c_void_p,
    ctypes.POINTER(c_uint32),
    c_size_t,
    ctypes.POINTER(c_size_t),
    ctypes.POINTER(c_uint8_p),
    c_size_t,
]

# Set dataIn (vr=0) to 5 bytes: 0xDE 0xAD 0xBE 0xEF 0x42
payload = (ctypes.c_uint8 * 5)(0xDE, 0xAD, 0xBE, 0xEF, 0x42)
set_vr = (c_uint32 * 1)(0)
set_sizes = (c_size_t * 1)(5)
set_ptrs = (c_uint8_p * 1)(ctypes.cast(payload, c_uint8_p))
status = lib.fmi3SetBinary(inst, set_vr, 1, set_sizes, set_ptrs, 1)
assert status == 0, f"SetBinary(dataIn) failed: {status}"
print(f"  fmi3SetBinary(dataIn) = DEADBEEF42: OK")

# DoStep to update outputs
lib.fmi3DoStep.restype = c_int
lib.fmi3DoStep.argtypes = [
    c_void_p, c_double, c_double, c_int,
    ctypes.POINTER(c_int), ctypes.POINTER(c_int),
    ctypes.POINTER(c_int), ctypes.POINTER(c_double),
]
evtNeeded = c_int(0)
terminate = c_int(0)
earlyRet = c_int(0)
lastTime = c_double(0)
status = lib.fmi3DoStep(inst, 0.0, 0.1, 0, ctypes.byref(evtNeeded),
                         ctypes.byref(terminate), ctypes.byref(earlyRet),
                         ctypes.byref(lastTime))
assert status == 0, f"DoStep failed: {status}"

# Get dataOut again - should be prefix(5) + payload
vr_out = (c_uint32 * 1)(1)
sizes2 = (c_size_t * 1)(0)
ptrs2 = (c_uint8_p * 1)()
status = lib.fmi3GetBinary(inst, vr_out, 1, sizes2, ptrs2, 1)
assert status == 0, f"GetBinary(dataOut) after set failed: {status}"
out_size2 = sizes2[0]
out_bytes2 = bytes(ptrs2[0][i] for i in range(out_size2))
assert out_size2 == 6, f"Expected 6 bytes, got {out_size2}"
assert out_bytes2[0] == 5, f"Length prefix should be 5, got {out_bytes2[0]}"
assert out_bytes2[1:] == bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x42])
print(f"  fmi3GetBinary(dataOut) after set: {out_bytes2.hex()} (len={out_size2}) OK")
print("  Binary round-trip: PASS")

# ── 4. Clock Get + periodic ticking ───────────────────────────────────────

lib.fmi3GetClock.restype = c_int
lib.fmi3GetClock.argtypes = [
    c_void_p, ctypes.POINTER(c_uint32), c_size_t, ctypes.POINTER(c_int),
]

# Step counter is now 1 (from the DoStep above). Check clock.
vr_clk = (c_uint32 * 1)(2)
clk_val = (c_int * 1)(0)
status = lib.fmi3GetClock(inst, vr_clk, 1, clk_val)
assert status == 0
assert clk_val[0] == 0, f"Heartbeat should be inactive at step 1, got {clk_val[0]}"

# Step to step 10 (9 more steps)
for s in range(9):
    status = lib.fmi3DoStep(inst, (s + 1) * 0.1, 0.1, 0,
                             ctypes.byref(evtNeeded), ctypes.byref(terminate),
                             ctypes.byref(earlyRet), ctypes.byref(lastTime))
    assert status == 0

# Now at step 10 - heartbeat should tick
status = lib.fmi3GetClock(inst, vr_clk, 1, clk_val)
assert status == 0
assert clk_val[0] == 1, f"Heartbeat should be ACTIVE at step 10, got {clk_val[0]}"
print("  fmi3GetClock(heartbeat) at step 10: ACTIVE (ticked) OK")

# Step 11 - should be inactive again
lib.fmi3DoStep(inst, 1.0, 0.1, 0, ctypes.byref(evtNeeded),
                ctypes.byref(terminate), ctypes.byref(earlyRet),
                ctypes.byref(lastTime))
status = lib.fmi3GetClock(inst, vr_clk, 1, clk_val)
assert status == 0
assert clk_val[0] == 0, f"Heartbeat should be inactive at step 11, got {clk_val[0]}"
print("  fmi3GetClock(heartbeat) at step 11: INACTIVE OK")

# Step to 20
for s in range(9):
    lib.fmi3DoStep(inst, (11 + s) * 0.1, 0.1, 0, ctypes.byref(evtNeeded),
                    ctypes.byref(terminate), ctypes.byref(earlyRet),
                    ctypes.byref(lastTime))
status = lib.fmi3GetClock(inst, vr_clk, 1, clk_val)
assert status == 0
assert clk_val[0] == 1, f"Heartbeat should be ACTIVE at step 20, got {clk_val[0]}"
print("  fmi3GetClock(heartbeat) at step 20: ACTIVE (ticked) OK")
print("  Clock periodic ticking: PASS")

# ── 5. Float64 step counter ──────────────────────────────────────────────

lib.fmi3GetFloat64.restype = c_int
lib.fmi3GetFloat64.argtypes = [
    c_void_p, ctypes.POINTER(c_uint32), c_size_t, ctypes.POINTER(c_double), c_size_t,
]
vr_sc = (c_uint32 * 1)(3)
sc_val = (c_double * 1)(0)
status = lib.fmi3GetFloat64(inst, vr_sc, 1, sc_val, 1)
assert status == 0
assert sc_val[0] == 20.0, f"Expected stepCount=20, got {sc_val[0]}"
print(f"  fmi3GetFloat64(stepCount) = {sc_val[0]} OK")

# ── Cleanup ──────────────────────────────────────────────────────────────

lib.fmi3Terminate.restype = c_int
lib.fmi3Terminate.argtypes = [c_void_p]
lib.fmi3Terminate(inst)

lib.fmi3FreeInstance.restype = None
lib.fmi3FreeInstance.argtypes = [c_void_p]
lib.fmi3FreeInstance(inst)
print("  Terminate + FreeInstance: OK")

print()
print("=" * 60)
print("ALL VALIDATION TESTS PASSED")
print("=" * 60)
