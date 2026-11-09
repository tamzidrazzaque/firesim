# Technology model roadmap

## What is in the tree now

Class 1, DRAM and HBM, is the existing FASED DDR3 FR-FCFS model and `HBMModel`. Both ran the 200-transaction fuzzer to a passing result in this session. The HBM4-8000 table remains a timing table on the HBM2 state machine.

Class 2, byte-addressable NVM, is `TechSpecMemory`. It has separate read and write latency, a shared issuer, a 32-bit endurance flag that does not drop writes, and a direct-mapped retention sample that does not flip bits. The illustrative card is latency 30, service 1, outstanding 32. It is not a calibrated FeFET, MRAM, or ReRAM.

Class 3, page-oriented NAND, is not implemented.

## What a NAND model would have to be

The FeFET string study supplies a device reference, not a memory latency. Frozen +P current is about 56 µA / N. At N = 32 and VPASS = 0.90 V that is 1.79 µA. The 139 ns figure is `1 pF * 0.25 V / 1.79 µA`. The 1 pF capacitance is assumed. The negative polarization is not a stable stored state under the default `TAU0`. There is no page buffer, ECC, or controller in that deck. Those 139 ns must not be programmed as the access latency of a NAND device.

A credible model needs page reads, page programs, erase blocks, a finite set of planes or dies, and a page buffer. It should sit on its own address region. It should not replace the 8-byte AXI port behind the Radiance L2. The adapter is a controller that accepts page requests and returns beats from the page buffer, with program and erase occupying a die for their own service times. That controller is the next model, after a Radiance closed loop exists for the byte-addressable card.

## Next build, in order

1. On a machine that can see `/scratch/trazzaque/chipyard`, point that FireSim checkout at `investigation/techspec-emerging-memory` and run one existing two-SM ELF three times: DDR3, HBM2, and TechSpec. Do not retune the L2 in the same comparison.
2. Repeat the outstanding-depth and latency sweep on that ELF.
3. Only then add a page-level NAND key, fed by a sensitivity card that cites the FeFET string current as a device input and does not claim a calibrated retention time.
