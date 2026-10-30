# Assignment

Build a cycle-accurate timing and state model of the Etron EM6GA16L
RPC DRAM from the supplied Rev. 1.4 specification only.

Read these files first:

- `spec/EM6GA16L.pdf`
- `spec/EM6GA16L.txt` (text extract; figures and multi-column tables are flattened)
- `spec/pages/page-*.png` (one raster image per PDF page; use these for figures and tables)
- `docs/FASED_CONTRACT.md`
- `docs/INTERFACE.md`
- `example/ToySpacingChecker.scala` (interface shape only; its numbers are fictional)

The workspace JDK is 11. The build is Scala 2.13.10, Chisel 3.6.0, and
sbt 1.10.2. `sbt` is on `PATH`. A smoke test already passes. Keep that
toolchain.

## Implement

1. A specification-derived RPC DRAM timing and bank-state engine.
2. A Chisel module `rpc.RpcTimingChecker` matching `docs/INTERFACE.md`.
   It must be suitable to wrap later in a generic FASED-style memory
   model: parameters are explicit, and one offered command is accepted
   or rejected at the caller's cycle.
3. `rpc.Replay`, which simulates that Chisel module. Do not decide
   legality only in ordinary Scala and then print it. Tests must peek
   the module outputs.
4. Tests for legal commands and for illegal commands, including cases
   that are legal at a boundary cycle and illegal one cycle earlier.
5. Configuration for the timing profiles and clock periods supported by
   the specification. `ceil(time_ps / tck_ps)` converts nanosecond
   minima. The mode-register packet selects dependent parameters.
6. `docs/TRACEABILITY.md`, `docs/PACKET.md`, and `docs/AMBIGUITY.md`.
7. Explicit handling of unspecified timing. Do not invent a single
   completion time when the datasheet does not give one.

An early command is reported and does not change bank or array state.
Do not repair it.

Cover the command, initialization, refresh, and data-timing rules in
specification sections 2, 4, 5, 7, and 11, including mode-register
fields and the command packet formats. Model one device in normal
parallel-packet operation. State clearly which diagrams you did not
implement (serial streaming, power-down, training, analog setup and
hold, and anything else you leave out).

## Replay self-check

Create `spec/selftest.jsonl` with a short legal sequence and at least
one deliberately early command. Show both results from:

```bash
sbt "runMain rpc.Replay --tck-ps 1250 --refresh-select 0 spec/selftest.jsonl"
```

Also run a second clock period that the datasheet allows and record the
command you used. Save the command output in `results/selftest.txt`.

## Finish

Run `sbt test` and save the output in `results/sbt-test.txt`.
Emit Verilog for `RpcTimingChecker` to `generated/RpcTimingChecker.v`.
Do not download memory-controller RTL, other RPC DRAM models, or
application notes that are not already in this workspace. Scala library
downloads required by `sbt` are fine. The specification PDF in `spec/`
is the authority for device behavior.
