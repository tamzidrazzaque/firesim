# Provenance of the frozen EM6GA16L checker

This directory is a copy of the model produced on 2026-10-30 by a
separate Cursor agent. The producing session did not receive the ETH
Zurich controller, the existing Python or Chisel RPC models, prior
traces, or this repository's history.

## Isolation

The agent ran as `cursor-agent` under Linux Landlock ABI 4. Before the
run, a probe inside the same policy could not open the project tree,
the ETH RTL, prior agent transcripts, or `/proc/self/root/...` paths
into those trees. `stat` is not mediated by this kernel's Landlock, so
a guessed path can still show that a file exists. Directory listing and
`open` outside the allowlist failed.

The allowlist was the workspace, the agent binary, and generic system
paths (`/usr`, `/lib`, `/etc`, `/dev`, `/proc/self`, and the system
resolver). User namespaces and the Docker socket were unavailable, so
Landlock was the filesystem boundary.

Network connect was logged and not filtered by address. The log
contains TCP/443 connections to `52.21.130.202`, `3.92.129.183`,
`34.225.159.174`, `3.101.224.52`, and `2606:4700::6812:137d`, plus
local datagram sockets. The session transcript has no read of
`memory-peripherals` or the controller tree and no ETH mention. The
only `github` strings are filenames in unused tool files that were
already inside the workspace.

## Session

| Item | Value |
|---|---|
| Session | `bfa1afa5-1b33-45d9-ad77-b8c613a81ca4` |
| Model | Claude Opus 5.5, extra-high (`claude-opus-5-5-xhigh`) |
| Exit code | 0 |
| Specification | Etron EM6GA16L Rev. 1.4, 74 pages, SHA-256 `c04a6b4192570c7b165efeeee0b3a8d2ee58c69c66609d5272103d2b517741cc` |
| Scala sources SHA-256 | `766dc95fe44bf909c9cf761f7d1ea5c9aa18dd7c6d9f5d22281dc23f749d2823` |
| Kept tree SHA-256 | `1c22e161c534d98a9b1a86d6f09f5c51b72c5a41d4e99842026a255f7860196c` |
| Checker | `rpc.RpcTimingChecker`, simulated by `rpc.Replay` |
| Tests | 63 succeeded, 0 failed (`results/sbt-test.txt`) |

The Scala hash covers every `.scala` file in this copy, including the
fictional spacing example. The kept-tree hash also covers the
datasheet, traceability notes, Verilog, and the agent's own test logs.
No checker source was edited after these hashes were computed.

## Inputs the agent was given

`TASK.md`, `docs/FASED_CONTRACT.md`, `docs/INTERFACE.md`,
`example/ToySpacingChecker.scala`, the Rev. 1.4 PDF and its text
extract, page rasters rendered from that PDF, and a Chisel 3.6.0 /
Scala 2.13.10 / JDK 11 build. The example's numbers are not device
timings.
