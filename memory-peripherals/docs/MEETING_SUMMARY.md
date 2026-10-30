# Memory models for HyperRAM and RPC DRAM

The Python models run and the tests check data and cycle counts, not just that a simulator exited. HyperRAM is a host-visible HyperBus device: 3 cycles of command, 7 cycles of latency at 200 MHz, doubled when a refresh collides or when CR0 asks for fixed latency. It does not have HBM’s banks. RPC DRAM is a four-bank DRAM whose command and data share one bus. At the datasheet’s 800 MHz an open row streams at about 2.9 GB/s out of a 3.2 GB/s pin ceiling. Closing the page after every burst, which is what the ETH controller’s command FSM does, drops the same sequential stream to about 0.6 GB/s.

The private HyperRAM repository was not accessible. The S80KS2562 PDF did not download. Timings are the public HyperRAM 2.0 200 MHz column and the Etron Rev 1.4 tables, with every constant labeled specified, inferred, or approximate.

Nothing was programmed onto the U250. A 38.4 GB/s HBM number in the spreadsheet is the published pin ceiling of one HBM2 channel, included so the scale is obvious. It is not a new HBM run.

A 2 KiB HyperRAM read is split so chip-select stays within the 4 µs tCSM limit; the 389 MB/s number already includes that split. ID0 is `0x0E86`. The Chisel RPC model now issues the next column command 8 cycles later instead of waiting out the burst, and a fuzzer run with refresh enabled printed 237 refresh stalls and still exited 0. The ETH `rpc_cmd_fsm` produces closed-page ACT, CAS, PRE. Its timing FSM and PHY are still not in that test, and the fuzzer’s `error` pin is tied off, so exit 0 is not a data check.
