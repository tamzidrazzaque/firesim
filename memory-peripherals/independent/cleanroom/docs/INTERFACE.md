# Neutral command-checker interface

This contract describes how an external stimulus presents commands.
It does not define device timing and it does not describe a controller.

The device clock is an integer. Cycle 0 is the first clock after the
checker is constructed. The caller supplies the cycle number on each
offered command. The simulator does not have to tick idle clocks
between commands. Legality is computed from the offered cycle and from
timestamps retained by the checker.

A command offered before it is legal is a violation. The checker must
not replace the offered cycle with a later cycle, must not insert a
wait, and must not update architectural bank or array state for that
rejected command.

## Chisel module

Package `rpc`, module `RpcTimingChecker`.

Inputs:

- `valid`: this step offers one command
- `cycle`: device-clock cycle chosen by the caller
- `packet`: the parallel request packet, using the bit layout documented
  from the datasheet in `docs/PACKET.md`
- `tckPs`: clock period in picoseconds, constant for a run
- `refreshSelect`: a small integer selecting a documented interpretation
  when the datasheet does not give one completion time. The meaning of
  each value is written by the implementer in `docs/TRACEABILITY.md`.
  Value 0 must mean "do not collapse an unspecified completion time":
  a command whose legality depends on that unknown time is reported as
  an interpretation result, not as a definite accept and not as a
  definite violation.

Outputs:

- `accepted`: the command was legal and state was updated
- `kind`: interpretation result, as distinct from accept and from a
  definite violation
- `constraintId`: stable numeric id, 0 when accepted
- `earliest`: earliest offered cycle at which this same command could
  have been legal, or 0 when no wait would make it legal
- `opCode`: decoded command class

The Chisel module is the component that decides. A Scala helper may
parse files, but the accept or violation result consumed by tests and
by `rpc.Replay` must be peeked from the module during a Chisel simulation.

## Replay program

`sbt "runMain rpc.Replay --tck-ps <picoseconds> --refresh-select <n> <file.jsonl>"`

Each JSON object has:

- `cycle`: integer device cycle
- `packet_hex`: hexadecimal digits of the 32-bit packet, without a prefix

Extra JSON fields are ignored. The program prints one line per record,
in order:

- `ACCEPT cycle=<n> op=<name>`
- `VIOLATION constraint=<name> offered=<n> earliest=<n> op=<name>`
- `INTERPRETATION constraint=<name> offered=<n> earliest=<n> op=<name> detail=<text>`

`earliest` is `na` when waiting cannot make the command legal.
The process exit code is 0 when the file was fully checked, including
when violations were reported. Usage and parse errors exit non-zero.

## Configuration

Support every speed column and refresh mode the datasheet defines.
Nanosecond minima become cycles with `ceil(time_ps / tck_ps)`.
Cycle minima stay in cycles. Mode-register fields in the packet select
dependent timings such as CAS latency. Do not hard-wire one latency
when the packet can program another legal value.

## Ambiguity

If the datasheet does not state a numeric duration, do not invent one
and do not pick a single favorite. Keep the unspecified case visible
through `INTERPRETATION`, and implement every reading you can justify
from the text as a non-zero `--refresh-select` value. A command that is
early under every documented reading is a `VIOLATION`.

## Traceability

`docs/TRACEABILITY.md` lists every enforced constraint, its numeric
rule, the datasheet section or table, and the unit. `docs/PACKET.md`
lists the packet bit fields. `docs/AMBIGUITY.md` lists behavior the
datasheet does not specify.
