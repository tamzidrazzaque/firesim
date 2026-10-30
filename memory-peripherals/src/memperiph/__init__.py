"""HyperRAM and RPC DRAM models for the SLICE memory-peripherals project."""

from .hyperram import HyperRAMDevice, HyperRAMFased, HyperRAMParams
from .rpcdram import RpcDramDevice, RpcDramFased, RpcDramParams

__all__ = [
    "HyperRAMDevice",
    "HyperRAMFased",
    "HyperRAMParams",
    "RpcDramDevice",
    "RpcDramFased",
    "RpcDramParams",
]
