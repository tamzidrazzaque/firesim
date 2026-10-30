# Next steps

## Can be done now, without a board

1. The fuzzer metasims already exit 0. The next simulation step is a directed AXI program whose addresses are also replayed on the Python model, so the Chisel trace can be diffed rather than only checked for completion.
2. Point the Chisel RPC refresh plusarg at a short stall and check that the fuzzer still retires. The full 1.6 ms stall is the right physical number and a poor default for a smoke test, which is why `tREFI` defaults to 0.
3. Vendor the Bender dependencies of `rpc_dram_controller` (`common_cells` 1.21.0, `axi` 0.35.0, `register_interface` 0.3.1, `tech_cells_generic` 0.2.9) and elaborate `rpc_phy` against `rtl/rpc_array` through a thin command adapter. The decoder test is the first slice of that.
4. When Ella’s HyperRAM repository is readable, compare our CR0 reset value, ID registers, and refresh-collision behavior with that model. Do not copy a vendor model into this tree.

## Needs a controller, not a board

- A HyperRAM controller with an AXI or TileLink front door. The Python device and `rtl/hyperram_txn` can sit behind a small adapter. `evaluate.py` already scores a host script.
- The ETH controller’s AXI front door and digital PHY now pass the directed pin-memory bench and Chipyard Rocket/BOOM bank workload. Extend this to long-run refresh, additional traffic shapes, and observed hardware traces before using it as a physical timing claim.
- Agree the burst-count convention (BC+1) with whoever writes the controller. Both the ETH FSM and LiteDRAM use it. A controller that treats BC as the raw word count will be short by one word.

## Needs the physical boards

- A HyperRAM module or the S80KS2562 on a carrier the U250 can reach, with the voltage rails and the reset pin identified. A bare U250 is not that board.
- An RPC DRAM device on a carrier. The ETH chip used a 200 MHz digital PHY. The part itself is specified to 800 MHz. The model has both profiles; the board clock decides which one is the ground truth.
- A trace capture: request address, read/write, byte length, chip-select or command cycle, first-data cycle, and for HyperRAM the RWDS level during the command phase. Cycle counts in the memory clock, not host nanoseconds alone.
- Absolute limits enforced outside the model: supply voltage, tCSM, tRESET, and no overlapping ZQ. `safe_probe_plan()` is the software allow-list, not an electrical permit.

## Calibration, once a trace exists

`src/memperiph/calibrate.py` recovers HyperRAM base latency from `(first_data - start - 3)` and RPC RL from open-page row-hit latency. It was checked by hiding the model’s own latency and fitting it back. That test is labeled synthetic in the suite. Replacing the synthetic trace with a captured one is the real calibration loop. Do not change a timing constant because one controller and the model disagree until the datasheet, the controller, and a scope or ILA trace have been compared.

## Coordination

- Ella: access to `hyperram-phy-secret`, and whether the PHY under development speaks the transaction layer or the pins.
- Whoever owns the Chipyard SoC config: one memory port should instantiate one model. Do not also stripe inside the model if the L2 already striped, which is the same rule the HBM notes call out.
- The existing HBM branch should stay the HBM implementation. This project adds siblings; it does not replace `HBMModel`.
