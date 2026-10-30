# Generic memory-model contract

This file describes only the interface a timing model must satisfy.
It contains no device timings.

A host presents memory commands at an integer cycle, one device clock
per cycle. The model either accepts the command and updates bank state
and a byte array, or records a violation and does not pretend the
command was legal.

Required operations: ACTIVATE, PRECHARGE, READ, WRITE, REFRESH,
MODE REGISTER SET, and a reset/initialization sequence.

Each violation names the constraint, the cycle the command was offered,
and the earliest cycle it would have been legal.

Reads return previously written bytes. Writes honor a per-byte mask.
A command that arrives early is not delayed into a legal slot by the
checker. The caller sees the violation.

Two page policies are configuration, not hidden behavior:
open-page leaves a row open; closed-page precharges after a burst
when the caller asks for that.

Parameters are numbers taken from a datasheet, each with a section
citation and a unit. Nanosecond minimums convert to cycles by rounding up.
