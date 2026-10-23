.. _manager-environment-variables:

Manager Environment Variables
=============================

This page contains a centralized reference for the environment variables used by the
manager.

.. _runfarm-prefix:

``FIRESIM_RUNFARM_PREFIX``
--------------------------

This environment variable is used to prefix all Run Farm tags with some prefix in the
AWS EC2 case. This is useful for separating run farms between multiple copies of
FireSim.

.. _buildfarm-prefix:

``FIRESIM_BUILDFARM_PREFIX``
----------------------------

This environment variable is used to prefix all Build Farm tags with some prefix in the
AWS EC2 case. This is mainly for CI use only.

.. _fesvr-prefix:

``FIRESIM_FESVR_PREFIX``
------------------------

This optional environment variable selects a host-only FESVR installation for FireSim
driver and RTL-simulator builds. The prefix must contain ``include/fesvr`` and
``lib/libfesvr.a``. It is forwarded to builds started by both the bitstream builder and
the runtime manager.

When unset, target projects should use ``RISCV`` for backward compatibility. Keeping
the variables distinct is useful when the target cross-toolchain does not ship FESVR::

    export RISCV=/path/to/riscv-target-toolchain
    export FIRESIM_FESVR_PREFIX=/path/to/host-fesvr-install

Target-project driver makefrags must use ``FIRESIM_FESVR_PREFIX`` for FESVR headers and
libraries in order to honor the override. Do not replace ``RISCV`` with the FESVR-only
prefix: target-software and debug-ROM builds still require the cross-toolchain.
