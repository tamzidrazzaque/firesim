"""Run Farm management."""

from __future__ import annotations

import re
import logging
import abc
import json
import shlex
import secrets
from fabric.api import prefix, local, run, env, cd, warn_only, put, settings, hide  # type: ignore
from fabric.contrib.project import rsync_project  # type: ignore
from os.path import join as pjoin
import os
from pathlib import Path

from util.streamlogger import StreamLogger
from awstools.awstools import terminate_instances, get_instance_ids_for_instances
from runtools.utils import has_sudo, run_only_aws, check_script, is_on_aws, script_path
from buildtools.bitbuilder import get_deploy_dir

from typing import List, Dict, Optional, Union, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from runtools.run_farm import Inst
    from awstools.awstools import MockBoto3Instance

rootLogger = logging.getLogger()


class NBDTracker:
    """Track allocation of NBD devices on an instance. Used for mounting
    qcow2 images."""

    # max number of NBDs allowed by the nbd.ko kernel module
    NBDS_MAX: int = 128
    unallocd: List[str]
    allocated_dict: Dict[str, str]

    def __init__(self) -> None:
        self.unallocd = ["""/dev/nbd{}""".format(x) for x in range(self.NBDS_MAX)]

        # this is a mapping from .qcow2 image name to nbd device.
        self.allocated_dict = {}

    def get_nbd_for_imagename(self, imagename: str) -> str:
        """Call this when you need to allocate an nbd for a particular image,
        or when you need to know what nbd device is for that image.

        This will allocate an nbd for an image if one does not already exist.

        THIS DOES NOT CALL qemu-nbd to actually connect the image to the device"""
        if imagename not in self.allocated_dict.keys():
            # otherwise, allocate it
            assert len(self.unallocd) >= 1, "No NBDs left to allocate on this instance."
            self.allocated_dict[imagename] = self.unallocd.pop(0)

        return self.allocated_dict[imagename]


class InstanceDeployManager(metaclass=abc.ABCMeta):
    """Class used to represent different "run platforms" and how to start/stop and setup simulations.

    Attributes:
        parent_node: Run farm host associated with this platform implementation.
    """

    parent_node: Inst
    nbd_tracker: Optional[NBDTracker]
    # Not all platforms need enumeration
    # but the guide still say to do enumeration - which will fail for those platforms
    # make knob to skip for platforms that dynamically checks BDF
    NEED_ENUMERATION: bool = True

    def __init__(self, parent_node: Inst) -> None:
        """
        Args:
            parent_node: Run farm host to associate with this platform implementation
        """
        self.parent_node = parent_node
        self.sim_type_message = (
            "FPGA" if not parent_node.metasimulation_enabled else "Metasim"
        )
        # Set this to self.nbd_tracker = NBDTracker() in the __init__ of your
        # subclass if your system supports the NBD kernel module.
        self.nbd_tracker = None

    @abc.abstractmethod
    def infrasetup_instance(self, uridir: str) -> None:
        """Run platform specific implementation of how to setup simulations.

        Anything that should only be executed if prepping for an actual FPGA-based
        simulation (i.e. not metasim mode) should be gated by:

        if not self.parent_node.metasimulation_enabled:
            [FPGA-specific logic, e.g. flashing FPGAs]

        """
        raise NotImplementedError

    @abc.abstractmethod
    def enumerate_fpgas(self, uridir: str) -> None:
        """Run platform specific implementation of how to enumerate FPGAs for FireSim."""
        raise NotImplementedError

    @abc.abstractmethod
    def terminate_instance(self) -> None:
        """Run platform specific implementation of how to terminate host
        machines.

        Platforms that do not have a notion of terminating a machine should
        override this to do nothing.

        """
        raise NotImplementedError

    def instance_logger(self, logstr: str, debug: bool = False) -> None:
        """Log with this host's info as prefix."""
        if debug:
            rootLogger.debug("""[{}] """.format(env.host_string) + logstr)
        else:
            rootLogger.info("""[{}] """.format(env.host_string) + logstr)

    def sim_node_qcow(self) -> None:
        """If NBD is available and qcow2 support is required, install qemu-img
        management tools and copy NBD infra to remote node. This assumes that
        the kernel module was already built and exists in the directory on this
        machine."""
        if self.nbd_tracker is not None and self.parent_node.qcow2_support_required():
            self.instance_logger("""Setting up remote node for qcow2 disk images.""")
            # get qemu-nbd
            run_only_aws("sudo yum -y install qemu-img")
            # copy over kernel module
            put(
                "../build/nbd.ko",
                f"/home/{os.environ['USER']}/nbd.ko",
                mirror_local_mode=True,
            )

    def load_nbd_module(self) -> None:
        """If NBD is available and qcow2 support is required, load the nbd
        module. always unload the module first to ensure it is in a clean
        state."""
        if self.nbd_tracker is not None and self.parent_node.qcow2_support_required():
            self.instance_logger("Loading NBD Kernel Module.")
            self.unload_nbd_module()
            run_only_aws(
                f"""sudo insmod /home/{os.environ['USER']}/nbd.ko nbds_max={self.nbd_tracker.NBDS_MAX}"""
            )

    def unload_nbd_module(self) -> None:
        """If NBD is available and qcow2 support is required, unload the nbd
        module."""
        if self.nbd_tracker is not None and self.parent_node.qcow2_support_required():
            self.instance_logger("Unloading NBD Kernel Module.")

            # disconnect all /dev/nbdX devices before rmmod
            self.disconnect_all_nbds_instance()
            with warn_only():
                run_only_aws("sudo rmmod nbd")

    def disconnect_all_nbds_instance(self) -> None:
        """If NBD is available and qcow2 support is required, disconnect all
        nbds on the instance."""
        if self.nbd_tracker is not None and self.parent_node.qcow2_support_required():
            self.instance_logger("Disconnecting all NBDs.")

            # warn_only, so we can call this even if there are no nbds
            with warn_only():
                # build up one large command with all the disconnects
                fullcmd = []
                for nbd_index in range(self.nbd_tracker.NBDS_MAX):
                    fullcmd.append(
                        """sudo qemu-nbd -d /dev/nbd{nbdno}""".format(nbdno=nbd_index)
                    )

                run_only_aws("; ".join(fullcmd))

    def get_remote_sim_dir_for_slot(self, slotno: int) -> str:
        """Returns the path on the remote for a given slot number."""
        remote_home_dir = self.parent_node.get_sim_dir()
        remote_sim_dir = f"{remote_home_dir}/sim_slot_{slotno}/"

        # so that callers can reliably concatenate folders to the returned value
        assert (
            remote_sim_dir[-1] == "/"
        ), f"Return value of get_remote_sim_dir_for_slot({slotno}) must end with '/'."

        return remote_sim_dir

    def copy_sim_slot_infrastructure(self, slotno: int, uridir: str) -> None:
        """copy all the simulation infrastructure to the remote node."""
        if self.instance_assigned_simulations():
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            serv = self.parent_node.sim_slots[slotno]

            self.instance_logger(
                f"""Copying {self.sim_type_message} simulation infrastructure for slot: {slotno}."""
            )

            remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
            remote_sim_rsync_dir = remote_sim_dir + "rsyncdir/"
            run(f"mkdir -p {remote_sim_rsync_dir}")

            files_to_copy = serv.get_required_files_local_paths()

            # Append required URI paths to the end of this list
            hwcfg = serv.get_resolved_server_hardware_config()
            local_uri_paths = hwcfg.get_local_uri_paths(uridir)
            files_to_copy.extend(local_uri_paths)
            contracted_uri_paths = (
                set(local_uri_paths)
                if getattr(hwcfg, "artifact_sha256", None) is not None
                else set()
            )

            for local_path, remote_path in files_to_copy:
                if (local_path, remote_path) in contracted_uri_paths:
                    hwcfg.verify_local_uri_path(uridir, local_path, remote_path)
                # -z --inplace
                rsync_cap = rsync_project(
                    local_dir=local_path,
                    remote_dir=pjoin(remote_sim_rsync_dir, remote_path),
                    ssh_opts="-o StrictHostKeyChecking=no",
                    extra_opts=(
                        "-L --checksum"
                        if (local_path, remote_path) in contracted_uri_paths
                        else "-L"
                    ),
                    capture=True,
                )
                rootLogger.debug(rsync_cap)
                rootLogger.debug(rsync_cap.stderr)
                if getattr(rsync_cap, "failed", False):
                    raise RuntimeError(
                        f"Failed to copy simulation infrastructure file "
                        f"{local_path} to slot {slotno}: {rsync_cap.stderr}"
                    )

            run(f"cp -r {remote_sim_rsync_dir}/* {remote_sim_dir}/", shell=True)

    def extract_driver_tarball(self, slotno: int) -> None:
        """extract tarball that already exists on the remote node."""
        if self.instance_assigned_simulations():
            assert slotno < len(self.parent_node.sim_slots)
            serv = self.parent_node.sim_slots[slotno]

            hwcfg = serv.get_resolved_server_hardware_config()

            remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
            options = "-xf"

            with cd(remote_sim_dir):
                run(f"tar {options} {hwcfg.get_driver_tar_filename()}")

    def copy_switch_slot_infrastructure(self, switchslot: int) -> None:
        """copy all the switch infrastructure to the remote node."""
        if self.instance_assigned_switches():
            self.instance_logger(
                """Copying switch simulation infrastructure for switch slot: {}.""".format(
                    switchslot
                )
            )
            remote_home_dir = self.parent_node.get_sim_dir()
            remote_switch_dir = """{}/switch_slot_{}/""".format(
                remote_home_dir, switchslot
            )
            run("""mkdir -p {}""".format(remote_switch_dir))

            assert switchslot < len(self.parent_node.switch_slots)
            switch = self.parent_node.switch_slots[switchslot]
            files_to_copy = switch.get_required_files_local_paths()
            for local_path, remote_path in files_to_copy:
                put(
                    local_path,
                    pjoin(remote_switch_dir, remote_path),
                    mirror_local_mode=True,
                )

    def start_switch_slot(self, switchslot: int) -> None:
        """start a switch simulation."""
        if self.instance_assigned_switches():
            self.instance_logger(
                """Starting switch simulation for switch slot: {}.""".format(switchslot)
            )
            remote_home_dir = self.parent_node.get_sim_dir()
            remote_switch_dir = """{}/switch_slot_{}/""".format(
                remote_home_dir, switchslot
            )
            assert switchslot < len(self.parent_node.switch_slots)
            switch = self.parent_node.switch_slots[switchslot]
            with cd(remote_switch_dir):
                run(switch.get_switch_start_command())

    def copy_pipe_slot_infrastructure(self, pipeslot: int) -> None:
        """copy all the pipe infrastructure to the remote node."""
        if self.instance_assigned_pipes():
            self.instance_logger(
                """Copying pipe simulation infrastructure for pipe slot: {}.""".format(
                    pipeslot
                )
            )
            remote_home_dir = self.parent_node.get_sim_dir()
            remote_pipe_dir = """{}/pipe_slot_{}/""".format(remote_home_dir, pipeslot)
            run("""mkdir -p {}""".format(remote_pipe_dir))

            assert pipeslot < len(self.parent_node.pipe_slots)
            pipe = self.parent_node.pipe_slots[pipeslot]
            files_to_copy = pipe.get_required_files_local_paths()
            for local_path, remote_path in files_to_copy:
                put(
                    local_path,
                    pjoin(remote_pipe_dir, remote_path),
                    mirror_local_mode=True,
                )

    def start_pipe_slot(self, pipeslot: int) -> None:
        """start a pipe simulation."""
        if self.instance_assigned_pipes():
            self.instance_logger(
                """Starting pipe simulation for pipe slot: {}.""".format(pipeslot)
            )
            remote_home_dir = self.parent_node.get_sim_dir()
            remote_pipe_dir = """{}/pipe_slot_{}/""".format(remote_home_dir, pipeslot)
            assert pipeslot < len(self.parent_node.pipe_slots)
            pipe = self.parent_node.pipe_slots[pipeslot]
            with cd(remote_pipe_dir):
                run(pipe.get_pipe_start_command(has_sudo()))

    def start_sim_slot(self, slotno: int) -> None:
        """start a simulation."""
        if self.instance_assigned_simulations():
            self.instance_logger(
                f"""Starting {self.sim_type_message} simulation for slot: {slotno}."""
            )
            remote_home_dir = self.parent_node.sim_dir
            remote_sim_dir = f"""{remote_home_dir}/sim_slot_{slotno}/"""
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            server = self.parent_node.sim_slots[slotno]
            rootLogger.info(
                f"start_sim_slot slotno: {slotno} server_id {server.server_id_internal} remote_sim_dir {remote_sim_dir} {remote_home_dir}"
            )

            # make the local job results dir for this sim slot
            server.mkdir_and_prep_local_job_results_dir()
            sim_start_script_local_path = server.write_sim_start_script(
                slotno, f"+slotid={slotno}"
            )
            put(sim_start_script_local_path, remote_sim_dir)

            with cd(remote_sim_dir):
                run("chmod +x sim-run.sh")
                run("./sim-run.sh")

    def kill_switch_slot(self, switchslot: int) -> None:
        """kill the switch in slot switchslot."""
        if self.instance_assigned_switches():
            self.instance_logger(
                """Killing switch simulation for switchslot: {}.""".format(switchslot)
            )
            assert switchslot < len(self.parent_node.switch_slots)
            switch = self.parent_node.switch_slots[switchslot]
            with warn_only():
                run(switch.get_switch_kill_command())

    def kill_pipe_slot(self, pipeslot: int) -> None:
        """kill the pipe in slot pipeslot."""
        if self.instance_assigned_pipes():
            self.instance_logger(
                """Killing pipe simulation for pipeslot: {}.""".format(pipeslot)
            )
            assert pipeslot < len(self.parent_node.pipe_slots)
            pipe = self.parent_node.pipe_slots[pipeslot]
            with warn_only():
                if has_sudo():
                    run("sudo " + pipe.get_pipe_kill_command())
                else:
                    run(pipe.get_pipe_kill_command())

    def kill_sim_slot(self, slotno: int) -> None:
        """kill the simulation in slot slotno."""
        if self.instance_assigned_simulations():
            self.instance_logger(
                f"""Killing {self.sim_type_message} simulation for slot: {slotno}."""
            )
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            server = self.parent_node.sim_slots[slotno]
            with warn_only():
                run(server.get_sim_kill_command(slotno))

    def instance_assigned_simulations(self) -> bool:
        """return true if this instance has any assigned fpga simulations."""
        return len(self.parent_node.sim_slots) != 0

    def instance_assigned_switches(self) -> bool:
        """return true if this instance has any assigned switch simulations."""
        return len(self.parent_node.switch_slots) != 0

    def instance_assigned_pipes(self) -> bool:
        """return true if this instance has any assigned pipe simulations."""
        return len(self.parent_node.pipe_slots) != 0

    def remove_shm_files(self) -> None:
        if is_on_aws():
            run("sudo rm -rf /dev/shm/*")
        else:
            cmd = f"{script_path}/firesim-remove-dev-shm"
            check_script(cmd)
            run(f"sudo {cmd}")

    def start_pipe_slots(self) -> None:
        for slotno in range(len(self.parent_node.pipe_slots)):
            self.start_pipe_slot(slotno)

    def start_switch_slots(self) -> None:
        for slotno in range(len(self.parent_node.switch_slots)):
            self.start_switch_slot(slotno)

    def start_switches_and_pipes_instance(self) -> None:
        """Boot up all the switches and pipes on this host in screens."""
        if self.instance_assigned_pipes() or self.instance_assigned_switches():
            self.remove_shm_files()

        if self.instance_assigned_pipes() and self.instance_assigned_switches():
            self.start_switch_slots()
            self.start_pipe_slots()
        elif self.instance_assigned_pipes():
            self.start_pipe_slots()
        elif self.instance_assigned_switches():
            self.start_switch_slots()

    def start_simulations_instance(self) -> None:
        """Boot up all the sims on this host in screens."""
        if self.instance_assigned_simulations():
            # only on sim nodes
            rootLogger.info(
                f"start_simulations_instance {len(self.parent_node.sim_slots)}"
            )
            for slotno in range(len(self.parent_node.sim_slots)):
                self.start_sim_slot(slotno)

    def kill_switches_instance(self) -> None:
        """Kill all the switches on this host."""
        if self.instance_assigned_switches():
            for slotno in range(len(self.parent_node.switch_slots)):
                self.kill_switch_slot(slotno)
            self.remove_shm_files()

    def kill_pipes_instance(self) -> None:
        if self.instance_assigned_pipes():
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.kill_pipe_slot(slotno)
            self.remove_shm_files()  # TODO : remove shm files for only this instance

    def kill_simulations_instance(self, disconnect_all_nbds: bool = True) -> None:
        """Kill all simulations on this host."""
        if self.instance_assigned_simulations():
            # only on sim nodes
            for slotno in range(len(self.parent_node.sim_slots)):
                self.kill_sim_slot(slotno)
        if disconnect_all_nbds:
            # disconnect all NBDs
            self.disconnect_all_nbds_instance()

    def running_simulations(self) -> Dict[str, List[str]]:
        """collect screen results from this host to see what's running on it."""
        simdrivers = []
        switches = []
        pipes = []
        with settings(warn_only=True), hide("everything"):
            collect = run("screen -ls")
            for line in collect.splitlines():
                if "(Detached)" in line or "(Attached)" in line:
                    line_stripped = line.strip()
                    if "fsim" in line:
                        re_search_results = re.search(
                            "fsim([0-9][0-9]*)", line_stripped
                        )
                        assert re_search_results is not None
                        line_stripped = re_search_results.group(0)
                        line_stripped = line_stripped.replace("fsim", "")
                        simdrivers.append(line_stripped)
                    elif "switch" in line:
                        re_search_results = re.search(
                            "switch([0-9][0-9]*)", line_stripped
                        )
                        assert re_search_results is not None
                        line_stripped = re_search_results.group(0)
                        switches.append(line_stripped)
                    elif "pipe" in line:
                        re_search_results = re.search(
                            "pipe([0-9][0-9]*)", line_stripped
                        )
                        assert re_search_results is not None
                        line_stripped = re_search_results.group(0)
                        pipes.append(line_stripped)
        return {"switches": switches, "simdrivers": simdrivers, "pipes": pipes}

    def monitor_jobs_instance(
        self,
        prior_completed_jobs: List[str],
        is_final_loop: bool,
        is_networked: bool,
        terminateoncompletion: bool,
        job_results_dir: str,
    ) -> Dict[str, Dict[str, bool]]:
        """Job monitoring for this host."""
        self.instance_logger(
            f"Final loop?: {is_final_loop} Is networked?: {is_networked} Terminateoncomplete: {terminateoncompletion}",
            debug=True,
        )
        self.instance_logger(
            f"Prior completed jobs: {prior_completed_jobs}", debug=True
        )

        def do_terminate():
            if (not is_networked) or (is_networked and is_final_loop):
                if terminateoncompletion:
                    self.terminate_instance()

        if not self.instance_assigned_simulations() and (
            self.instance_assigned_switches() or self.instance_assigned_pipes()
        ):
            self.instance_logger(f"Polling switch/pipe-only node", debug=True)

            # just confirm that our switches are still running
            # switches will never trigger shutdown in the cycle-accurate -
            # they should run forever until torn down
            if is_final_loop:
                self.instance_logger(
                    f"Completing copies for switch-only node", debug=True
                )

                for counter in range(len(self.parent_node.switch_slots)):
                    switchsim = self.parent_node.switch_slots[counter]
                    switchsim.copy_back_switchlog_from_run(job_results_dir, counter)

                for counter in range(len(self.parent_node.pipe_slots)):
                    pipesim = self.parent_node.pipe_slots[counter]
                    pipesim.copy_back_pipelog_from_run(job_results_dir, counter)

                do_terminate()

                return {"switches": {}, "sims": {}, "pipes": {}}
            else:
                # get the status of the switch sims
                switchescompleteddict = {
                    k: False for k in self.running_simulations()["switches"]
                }
                for switchsim in self.parent_node.switch_slots:
                    swname = switchsim.switch_builder.switch_binary_name()
                    if swname not in switchescompleteddict.keys():
                        switchescompleteddict[swname] = True

                pipescompleteddict = {
                    k: False for k in self.running_simulations()["pipes"]
                }
                for pipesim in self.parent_node.pipe_slots:
                    pipename = pipesim.pipe_builder.pipe_binary_name()
                    if pipename not in pipescompleteddict.keys():
                        pipescompleteddict[pipename] = True

                return {
                    "switches": switchescompleteddict,
                    "sims": {},
                    "pipes": pipescompleteddict,
                }

        if self.instance_assigned_simulations():
            # this node has sims attached
            self.instance_logger(
                f"Polling node with simulations (and potentially switches)", debug=True
            )

            sim_slots = self.parent_node.sim_slots
            jobnames = [slot.get_job_name() for slot in sim_slots]
            all_jobs_completed = all(
                [(job in prior_completed_jobs) for job in jobnames]
            )

            self.instance_logger(f"jobnames: {jobnames}", debug=True)
            self.instance_logger(
                f"All jobs completed?: {all_jobs_completed}", debug=True
            )

            if all_jobs_completed:
                do_terminate()

                # in this case, all of the nodes jobs have already completed. do nothing.
                # this can never happen in the cycle-accurate case at a point where we care
                # about switch status, so don't bother to populate it
                jobnames_to_completed = {jname: True for jname in jobnames}
                return {"sims": jobnames_to_completed, "switches": {}, "pipes": {}}

            # at this point, all jobs are NOT completed. so, see how they're doing now:
            instance_screen_status = self.running_simulations()

            switchescompleteddict = {
                k: False for k in instance_screen_status["switches"]
            }
            pipescompleteddict = {k: False for k in instance_screen_status["pipes"]}
            slotsrunning = [x for x in instance_screen_status["simdrivers"]]
            self.instance_logger(
                f"Switch Slots running: {switchescompleteddict}", debug=True
            )
            self.instance_logger(
                f"pipe Slots running: {pipescompleteddict}", debug=True
            )
            self.instance_logger(f"Sim Slots running: {slotsrunning}", debug=True)

            if self.instance_assigned_switches():
                # fill in whether switches have terminated
                for switchsim in self.parent_node.switch_slots:
                    sw_name = switchsim.switch_builder.switch_binary_name()
                    if sw_name not in switchescompleteddict.keys():
                        switchescompleteddict[sw_name] = True

            if self.instance_assigned_pipes():
                for pipesim in self.parent_node.pipe_slots:
                    pipename = pipesim.pipe_builder.pipe_binary_name()
                    if pipename not in pipescompleteddict.keys():
                        pipescompleteddict[pipename] = True

            # fill in whether sims have terminated
            completed_jobs = (
                prior_completed_jobs.copy()
            )  # create local copy to append to
            for slotno, jobname in enumerate(jobnames):
                if (str(slotno) not in slotsrunning) and (
                    jobname not in completed_jobs
                ):
                    self.instance_logger(f"Slot {slotno}, Job {jobname} completed!")
                    completed_jobs.append(jobname)

                    # this writes the job monitoring file
                    sim_slots[slotno].copy_back_job_results_from_run(slotno)

            jobs_complete_dict = {job: job in completed_jobs for job in jobnames}
            now_all_jobs_complete = all(jobs_complete_dict.values())
            self.instance_logger(f"Now done?: {now_all_jobs_complete}", debug=True)

            if now_all_jobs_complete:
                if self.instance_assigned_switches():
                    # we have switches running here, so kill them,
                    # then copy off their logs. this handles the case where you
                    # have a node with one simulation and some switches, to make
                    # sure the switch logs are copied off.
                    #
                    # the other cases are when you have multiple sims and a cycle-acc network,
                    # in which case the all() will never actually happen (unless someone builds
                    # a workload where two sims exit at exactly the same time, which we should
                    # advise users not to do)
                    #
                    # a last use case is when there's no network, in which case
                    # instance_assigned_switches won't be true, so this won't be called

                    self.kill_switches_instance()

                    for counter, switch_slot in enumerate(
                        self.parent_node.switch_slots
                    ):
                        switch_slot.copy_back_switchlog_from_run(
                            job_results_dir, counter
                        )

                if self.instance_assigned_pipes():
                    self.kill_pipes_instance()
                    for counter, pipe_slot in enumerate(self.parent_node.pipe_slots):
                        pipe_slot.copy_back_pipelog_from_run(job_results_dir, counter)

                do_terminate()

            return {
                "switches": switchescompleteddict,
                "sims": jobs_complete_dict,
                "pipes": pipescompleteddict,
            }

        assert False


def remote_kmsg(message: str) -> None:
    """This will let you write whatever is passed as message into the kernel
    log of the remote machine.  Useful for figuring what the manager is doing
    w.r.t output from kernel stuff on the remote node."""
    commd = """echo '{}' | sudo tee /dev/kmsg""".format(message)
    run(commd, shell=True)


class EC2InstanceDeployManager(InstanceDeployManager):
    """This class manages actually deploying/running stuff based on the
    definition of an instance and the simulations/switches assigned to it.

    This is in charge of managing the locations of stuff on remote nodes.
    """

    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.nbd_tracker = NBDTracker()

    def get_and_install_aws_fpga_sdk(self) -> None:
        """Installs the aws-sdk. This gets us access to tools to flash the fpga."""
        if self.instance_assigned_simulations():
            with prefix("cd ../"):
                # use local version of aws_fpga on run farm nodes
                aws_fpga_upstream_version = local(
                    "git -C platforms/f2/aws-fpga-firesim-f2 describe --tags --always --dirty",
                    capture=True,
                )
                if "-dirty" in aws_fpga_upstream_version:
                    aws_fpga_upstream_version = aws_fpga_upstream_version.replace("-dirty", "")
                    rootLogger.critical(
                        "Unable to use local changes to aws-fpga. Continuing without them."
                    )
            self.instance_logger(
                """Installing AWS FPGA SDK on remote nodes. Upstream hash: {}""".format(
                    aws_fpga_upstream_version
                )
            )
            with warn_only():
                run("git clone https://github.com/firesim/aws-fpga-firesim-f2.git aws-fpga")
                run("cd aws-fpga && git checkout " + aws_fpga_upstream_version)
            with cd(f"/home/{os.environ['USER']}/aws-fpga"):
                run("source sdk_setup.sh")

    def fpga_node_xdma(self) -> None:
        """Copy XDMA infra to remote node. This assumes that the driver was
        already built and that a binary exists in the directory on this machine
        """
        if self.instance_assigned_simulations():
            self.instance_logger("""Copying AWS FPGA XDMA driver to remote node.""")
            run(f"mkdir -p /home/{os.environ['USER']}/xdma/")
            put(
                "../platforms/f2/aws-fpga-firesim-f2/sdk/dma_ip_drivers/XDMA/linux-kernel",
                f"/home/{os.environ['USER']}/xdma/",
                mirror_local_mode=True,
            )
            with cd(
                f"/home/{os.environ['USER']}/xdma/linux-kernel/xdma/"
            ), prefix("export PATH=/usr/bin:$PATH"):
                # prefix only needed if conda env is earlier in PATH
                # see build-setup-nolog.sh for explanation.
                run("make clean")
                run("make")

    def unload_xrt_and_xocl(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("Unloading XRT-related Kernel Modules.")

            with warn_only():
                # fpga mgmt tools seem to force load xocl after a flash now...
                # so we just remove everything for good measure:
                remote_kmsg("removing_xrt_start")
                run("sudo systemctl stop mpd")
                run("sudo yum remove -y xrt xrt-aws")
                remote_kmsg("removing_xrt_end")

    def unload_xdma(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("Unloading XDMA Driver Kernel Module.")

            with warn_only():
                # fpga mgmt tools seem to force load xocl after a flash now...
                # so we just remove everything for good measure:
                remote_kmsg("removing_xdma_start")
                run("sudo rmmod xdma")
                remote_kmsg("removing_xdma_end")

            # self.instance_logger("Waiting 10 seconds after removing kernel modules (esp. xocl).")
            # time.sleep(10)

    def clear_fpgas(self) -> None:
        if self.instance_assigned_simulations():
            # we always clear ALL fpga slots
            for slotno in range(self.parent_node.MAX_SIM_SLOTS_ALLOWED):
                self.instance_logger("""Clearing FPGA Slot {}.""".format(slotno))
                remote_kmsg("""about_to_clear_fpga{}""".format(slotno))
                run("""sudo fpga-clear-local-image -S {} -A""".format(slotno))
                remote_kmsg("""done_clearing_fpga{}""".format(slotno))

            for slotno in range(self.parent_node.MAX_SIM_SLOTS_ALLOWED):
                self.instance_logger(
                    """Checking for Cleared FPGA Slot {}.""".format(slotno)
                )
                remote_kmsg("""about_to_check_clear_fpga{}""".format(slotno))
                run(
                    """until sudo fpga-describe-local-image -S {} -R -H | grep -q "cleared"; do  sleep 1;  done""".format(
                        slotno
                    )
                )
                remote_kmsg("""done_checking_clear_fpga{}""".format(slotno))

    def flash_fpgas(self) -> None:
        if self.instance_assigned_simulations():
            dummyagfi = None
            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                agfi = firesimservernode.get_agfi()
                dummyagfi = agfi
                self.instance_logger(
                    """Flashing FPGA Slot: {} with agfi: {}.""".format(slotno, agfi)
                )
                run(
                    """sudo fpga-load-local-image -S {} -I {} -A""".format(slotno, agfi)
                )

            # We only do this because XDMA hangs if some of the FPGAs on the instance
            # are left in the cleared state. So, if you're only using some of the
            # FPGAs on an instance, we flash the rest with one of your images
            # anyway. Since the only interaction we have with an FPGA right now
            # is over PCIe where the software component is mastering, this can't
            # break anything.
            for slotno in range(
                len(self.parent_node.sim_slots), self.parent_node.MAX_SIM_SLOTS_ALLOWED
            ):
                self.instance_logger(
                    """Flashing FPGA Slot: {} with dummy agfi: {}.""".format(
                        slotno, dummyagfi
                    )
                )
                run(
                    """sudo fpga-load-local-image -S {} -I {} -A""".format(
                        slotno, dummyagfi
                    )
                )

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                self.instance_logger(
                    """Checking for Flashed FPGA Slot: {} with agfi: {}.""".format(
                        slotno, agfi
                    )
                )
                run(
                    """until sudo fpga-describe-local-image -S {} -R -H | grep -q "loaded"; do  sleep 1;  done""".format(
                        slotno
                    )
                )

            for slotno in range(
                len(self.parent_node.sim_slots), self.parent_node.MAX_SIM_SLOTS_ALLOWED
            ):
                self.instance_logger(
                    """Checking for Flashed FPGA Slot: {} with agfi: {}.""".format(
                        slotno, dummyagfi
                    )
                )
                run(
                    """until sudo fpga-describe-local-image -S {} -R -H | grep -q "loaded"; do  sleep 1;  done""".format(
                        slotno
                    )
                )

    def load_xdma(self) -> None:
        """load the xdma kernel module."""
        if self.instance_assigned_simulations():
            # fpga mgmt tools seem to force load xocl after a flash now...
            # xocl conflicts with the xdma driver, which we actually want to use
            # so we just remove everything for good measure before loading xdma:
            self.unload_xdma()
            # now load xdma
            self.instance_logger("Loading XDMA Driver Kernel Module.")
            # TODO: can make these values automatically be chosen based on link lat
            run(
                f"sudo insmod /home/{os.environ['USER']}/xdma/linux-kernel/xdma/xdma.ko poll_mode=1"  # rh: renamed to fit submodule 
            )

    def start_ila_server(self) -> None:
        """start the vivado hw_server and virtual jtag on simulation instance."""
        if self.instance_assigned_simulations():
            self.instance_logger("Starting Vivado hw_server.")
            run(
                """screen -S hw_server -d -m bash -c "script -f -c 'hw_server'"; sleep 1"""
            )
            self.instance_logger("Starting Vivado virtual JTAG.")
            run(
                """screen -S virtual_jtag -d -m bash -c "script -f -c 'sudo fpga-start-virtual-jtag -P 10201 -S 0'"; sleep 1"""
            )

    def kill_ila_server(self) -> None:
        """Kill the vivado hw_server and virtual jtag"""
        if self.instance_assigned_simulations():
            with warn_only():
                run("sudo pkill -SIGKILL hw_server")
            with warn_only():
                run("sudo pkill -SIGKILL fpga-local-cmd")

    def infrasetup_instance(self, uridir: str) -> None:
        """Handle infrastructure setup for this instance."""

        metasim_enabled = self.parent_node.metasimulation_enabled

        if self.instance_assigned_simulations():
            # This is a sim-host node.

            # copy sim infrastructure
            for slotno in range(len(self.parent_node.sim_slots)):
                self.copy_sim_slot_infrastructure(slotno, uridir)
                self.extract_driver_tarball(slotno)

            if not metasim_enabled:
                self.get_and_install_aws_fpga_sdk()
                # unload any existing edma/xdma/xocl
                self.unload_xrt_and_xocl()
                # # copy xdma driver # rh: commenting out for now to prevent loading of xdma.
                # self.fpga_node_xdma()
                # # load xdma
                # self.load_xdma()

            # setup nbd/qcow infra
            self.sim_node_qcow()
            # load nbd module
            self.load_nbd_module()

            if not metasim_enabled:
                # clear/flash fpgas
                self.clear_fpgas()
                self.flash_fpgas()

                # # re-load XDMA # rh: commenting out for now to prevent loading of xdma.
                # self.load_xdma()

                # restart (or start form scratch) ila server
                self.kill_ila_server()
                self.start_ila_server()

        if self.instance_assigned_switches():
            # all nodes could have a switch
            for slotno in range(len(self.parent_node.switch_slots)):
                self.copy_switch_slot_infrastructure(slotno)

        if self.instance_assigned_pipes():
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.copy_pipe_slot_infrastructure(slotno)

    def enumerate_fpgas(self, uridir: str) -> None:
        """FPGAs are enumerated already with F2"""
        return

    def terminate_instance(self) -> None:
        self.instance_logger("Terminating instance", debug=True)
        self.parent_node.terminate_self()


class VitisInstanceDeployManager(InstanceDeployManager):
    """This class manages a Vitis-enabled instance"""

    PLATFORM_NAME: str = "vitis"

    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)

    def clear_fpgas(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("""Clearing all FPGA Slots.""")

            card_bdfs = []
            with settings(warn_only=True), hide("everything"):
                # Examine forcibly puts the JSON in an output file (on the remote); The stdout
                # it produces is difficult to parse so use process substitution
                # to pipe JSON to stdout instead.
                # combine_stderr=False allows separate stdout and stderr streams
                xbutil_examine_json = run(
                    "xbutil examine --force --format JSON -o >(cat) > /dev/null",
                    pty=False,
                    combine_stderr=False,
                )
                if xbutil_examine_json.stderr != "":
                    rootLogger.critical(
                        f"xbutil returned:\n{xbutil_examine_json.stderr}"
                    )
                try:
                    json_dict = json.loads(xbutil_examine_json.stdout)
                except json.JSONDecodeError as e:
                    rootLogger.critical(
                        f"JSONDecodeError when parsing output from xbutil."
                    )
                    raise e
                card_bdfs = [d["bdf"] for d in json_dict["system"]["host"]["devices"]]

            for card_bdf in card_bdfs:
                run(f"xbutil reset -d {card_bdf} --force")

    def copy_bitstreams(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("""Copy bitstreams to flash.""")

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                serv = firesimservernode
                hwcfg = serv.get_resolved_server_hardware_config()

                bitstream_tar = hwcfg.get_bitstream_tar_filename()
                remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
                bitstream_tar_unpack_dir = f"{remote_sim_dir}/{self.PLATFORM_NAME}"
                bit = f"{remote_sim_dir}/{self.PLATFORM_NAME}/firesim.xclbin"

                # at this point the tar file is in the sim slot
                run(f"rm -rf {bitstream_tar_unpack_dir}")
                run(f"tar xvf {remote_sim_dir}/{bitstream_tar} -C {remote_sim_dir}")

    def infrasetup_instance(self, uridir: str) -> None:
        """Handle infrastructure setup for this platform."""
        if self.instance_assigned_simulations():
            # This is a sim-host node.

            # copy sim infrastructure
            for slotno in range(len(self.parent_node.sim_slots)):
                self.copy_sim_slot_infrastructure(slotno, uridir)
                self.extract_driver_tarball(slotno)

            if not self.parent_node.metasimulation_enabled:
                # clear/flash fpgas
                self.clear_fpgas()
                # copy bitstreams to use in run
                self.copy_bitstreams()

        if self.instance_assigned_switches():
            # all nodes could have a switch
            for slotno in range(len(self.parent_node.switch_slots)):
                self.copy_switch_slot_infrastructure(slotno)

        if self.instance_assigned_pipes():
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.copy_pipe_slot_infrastructure(slotno)

    def start_sim_slot(self, slotno: int) -> None:
        """start a simulation. (same as default except that you pass in the bitstream file)"""
        if self.instance_assigned_simulations():
            self.instance_logger(
                f"""Starting {self.sim_type_message} simulation for slot: {slotno}."""
            )
            remote_home_dir = self.parent_node.sim_dir
            remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            server = self.parent_node.sim_slots[slotno]
            hwcfg = server.get_resolved_server_hardware_config()

            bit = f"{remote_sim_dir}/{self.PLATFORM_NAME}/firesim.xclbin"

            if not self.parent_node.metasimulation_enabled:
                extra_args = f"+slotid={slotno} +binary_file={bit}"
            else:
                extra_args = None

            # make the local job results dir for this sim slot
            server.mkdir_and_prep_local_job_results_dir()
            sim_start_script_local_path = server.write_sim_start_script(
                slotno, extra_args
            )
            put(sim_start_script_local_path, remote_sim_dir)

            with cd(remote_sim_dir):
                run("chmod +x sim-run.sh")
                run("./sim-run.sh")

    def enumerate_fpgas(self, uridir: str) -> None:
        """FPGAs are enumerated already with Vitis"""
        return

    def terminate_instance(self) -> None:
        """VitisInstanceDeployManager machines cannot be terminated."""
        return


class XilinxAlveoInstanceDeployManager(InstanceDeployManager):
    """This class manages a Xilinx Alveo-enabled instance"""

    PLATFORM_NAME: Optional[str]

    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = None

    def load_xdma(self) -> None:
        """load the xdma kernel module."""
        if self.instance_assigned_simulations():
            # load xdma if unloaded
            if run("lsmod | grep -wq xdma", warn_only=True).return_code != 0:
                self.instance_logger("Loading XDMA Driver Kernel Module.")
                # must be installed to this path on sim. machine
                cmd = f"{script_path}/firesim-load-xdma-module"
                check_script(cmd)
                run(f"sudo {cmd}", shell=True)
            else:
                self.instance_logger("XDMA Driver Kernel Module already loaded.")
            cmd = f"{script_path}/firesim-chmod-xdma-perm"
            check_script(cmd)
            run(f"sudo {cmd}")

    def unload_xdma(self) -> None:
        """unload the xdma kernel module."""
        if self.instance_assigned_simulations():
            # unload xdma if loaded
            if run("lsmod | grep -wq xdma", warn_only=True).return_code == 0:
                self.instance_logger("Unloading XDMA Driver Kernel Module.")
                cmd = f"{script_path}/firesim-remove-xdma-module"
                check_script(cmd)
                run(f"sudo {cmd}", shell=True)
            else:
                self.instance_logger("XDMA Driver Kernel Module already unloaded.")

    def slot_to_bdf(self, slotno: int, json_db: str) -> str:
        # get fpga information from db
        self.instance_logger(f"""Determine BDF for {slotno}""")
        collect = run(f"cat {json_db}")
        db = json.loads(collect)
        assert slotno < len(
            db
        ), f"Less FPGAs available than slots ({slotno} >= {len(db)})"
        return db[slotno]["bdf"]

    def flash_fpgas(self) -> None:
        """JTAG-program all FPGAs in a single Vivado session.

        Supports heterogeneous configs (different bitstreams per slot).
        Uses program_fpga_fleet.tcl to avoid the hw_server wedge caused
        by back-to-back Vivado process launches.

        Wraps the JTAG flash with PCI disconnect/reconnect (via
        firesim-fpga-util.py) so the kernel picks up the new device
        configuration after reprogramming.
        """
        if self.instance_assigned_simulations():
            self.instance_logger("Flash all FPGA Slots (single-session).")

            json_db = self.parent_node.get_fpga_db()
            collect = run(f"cat {json_db}")
            db = json.loads(collect)

            mapping_lines = []
            scripts_synced = False

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                serv = firesimservernode
                hwcfg = serv.get_resolved_server_hardware_config()

                bitstream_tar = hwcfg.get_bitstream_tar_filename()
                remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
                bitstream_tar_unpack_dir = os.path.join(
                    remote_sim_dir, str(self.PLATFORM_NAME)
                )
                bit = os.path.join(bitstream_tar_unpack_dir, "firesim.bit")

                run(f"rm -rf {bitstream_tar_unpack_dir}")
                run(f"tar xvf {remote_sim_dir}/{bitstream_tar} -C {remote_sim_dir}")

                if not scripts_synced:
                    rsync_cap = rsync_project(
                        local_dir=f"../platforms/{self.PLATFORM_NAME}/scripts",
                        remote_dir=remote_sim_dir,
                        ssh_opts="-o StrictHostKeyChecking=no",
                        extra_opts="-L -p",
                        capture=True,
                    )
                    rootLogger.debug(rsync_cap)
                    rootLogger.debug(rsync_cap.stderr)
                    scripts_synced = True
                    scripts_dir = f"{remote_sim_dir}/scripts"

                assert slotno < len(db), f"Less FPGAs than slots ({slotno} >= {len(db)})"
                uid = db[slotno]["uid"]
                self.instance_logger(f"Slot {slotno}: {uid} -> {bit}")
                mapping_lines.append(f"{uid} {bit}")

            fpga_util = f"{script_path}/firesim-fpga-util.py"
            check_script(
                fpga_util,
                Path(f"{get_deploy_dir()}/../platforms/{self.PLATFORM_NAME}/scripts"),
            )

            self.instance_logger("Disconnecting all FPGAs from PCI bus.")
            for slotno in range(len(self.parent_node.sim_slots)):
                bdf = db[slotno]["bdf"]
                run(f"{fpga_util} --bdf {bdf} --disconnect-bdf --fpga-db {json_db}")

            map_file = f"{self.get_remote_sim_dir_for_slot(0)}/flash_map.txt"
            map_content = "\n".join(mapping_lines)
            run(f"cat > {map_file} << 'MAPEOF'\n{map_content}\nMAPEOF")

            tcl = f"{scripts_dir}/program_fpga_fleet.tcl"
            vivado = run("which vivado || which vivado_lab", warn_only=True).strip()
            if not vivado:
                raise RuntimeError("Could not find vivado or vivado_lab on PATH")
            run(f"{vivado} -mode batch -source {tcl} -tclargs -map_file {map_file}")

            self.instance_logger("Reconnecting all FPGAs to PCI bus.")
            for slotno in range(len(self.parent_node.sim_slots)):
                bdf = db[slotno]["bdf"]
                run(f"{fpga_util} --bdf {bdf} --reconnect-bdf --fpga-db {json_db}")

    def change_pcie_perms(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("""Change permissions on FPGA slot""")

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                bdf = self.slot_to_bdf(slotno, self.parent_node.get_fpga_db())

                self.instance_logger(
                    f"""Changing permissions on FPGA Slot: {slotno} (bdf:{bdf})"""
                )
                cmd = f"{script_path}/firesim-change-pcie-perms"
                check_script(cmd)
                run(f"""sudo {cmd} 0000:{bdf}""")

    def change_all_pcie_perms(self) -> None:
        collect = run("lspci | grep -i xilinx")

        bdfs = [
            {"busno": "0x" + i[:2], "devno": "0x" + i[3:5], "capno": "0x" + i[6:7]}
            for i in collect.splitlines()
            if len(i.strip()) >= 0
        ]
        for bdf in bdfs:
            busno = bdf["busno"]
            devno = bdf["devno"]
            capno = bdf["capno"]

            self.instance_logger(
                f"""Changing permissions on FPGA: bus:{busno}, dev:{devno}, cap:{capno}"""
            )
            cmd = f"{script_path}/firesim-change-pcie-perms"
            check_script(cmd)
            run(f"""sudo {cmd} 0000:{busno[2:]}:{devno[2:]}:{capno[2:]}""")

    def infrasetup_instance(self, uridir: str) -> None:
        """Handle infrastructure setup for this platform."""
        metasim_enabled = self.parent_node.metasimulation_enabled

        if self.instance_assigned_simulations():
            # This is a sim-host node.

            # copy sim infrastructure
            for slotno in range(len(self.parent_node.sim_slots)):
                self.copy_sim_slot_infrastructure(slotno, uridir)
                self.extract_driver_tarball(slotno)

            if not metasim_enabled:
                # unload xdma driver
                self.unload_xdma()
                # flash fpgas
                self.flash_fpgas()
                # load xdma driver
                self.load_xdma()
                # change pcie permissions
                self.change_pcie_perms()

        if self.instance_assigned_switches():
            # all nodes could have a switch
            for slotno in range(len(self.parent_node.switch_slots)):
                self.copy_switch_slot_infrastructure(slotno)

        if self.instance_assigned_pipes():
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.copy_pipe_slot_infrastructure(slotno)

    def create_fpga_database(self, uridir: str) -> None:
        self.instance_logger(f"""Creating FPGA database""")

        remote_home_dir = self.parent_node.get_sim_dir()
        remote_sim_dir = f"{remote_home_dir}/enumerate_fpgas_staging"
        remote_sim_rsync_dir = f"{remote_sim_dir}/rsyncdir/"
        run(f"mkdir -p {remote_sim_rsync_dir}")

        # only use the collateral from 1 driver (no need to copy all things)
        assert len(self.parent_node.sim_slots) > 0
        serv = self.parent_node.sim_slots[0]

        files_to_copy = serv.get_required_files_local_paths()

        # Append required URI paths to the end of this list
        hwcfg = serv.get_resolved_server_hardware_config()
        files_to_copy.extend(hwcfg.get_local_uri_paths(uridir))

        for local_path, remote_path in files_to_copy:
            # -z --inplace
            rsync_cap = rsync_project(
                local_dir=local_path,
                remote_dir=pjoin(remote_sim_rsync_dir, remote_path),
                ssh_opts="-o StrictHostKeyChecking=no",
                extra_opts="-L",
                capture=True,
            )
            rootLogger.debug(rsync_cap)
            rootLogger.debug(rsync_cap.stderr)

        run(f"cp -r {remote_sim_rsync_dir}/* {remote_sim_dir}/", shell=True)

        rsync_cap = rsync_project(
            local_dir=f"../platforms/{self.PLATFORM_NAME}/scripts",
            remote_dir=remote_sim_dir + "/",
            ssh_opts="-o StrictHostKeyChecking=no",
            extra_opts="-L -p",
            capture=True,
        )
        rootLogger.debug(rsync_cap)
        rootLogger.debug(rsync_cap.stderr)

        bitstream_tar = hwcfg.get_bitstream_tar_filename()
        bitstream_tar_unpack_dir = f"{remote_sim_dir}/{self.PLATFORM_NAME}"
        bitstream = f"{remote_sim_dir}/{self.PLATFORM_NAME}/firesim.bit"

        with cd(remote_sim_dir):
            run(f"tar -xf {hwcfg.get_driver_tar_filename()}")

        # at this point the tar file is in the sim slot
        run(f"rm -rf {bitstream_tar_unpack_dir}")
        run(f"tar xvf {remote_sim_dir}/{bitstream_tar} -C {remote_sim_dir}")

        driver = f"{remote_sim_dir}/FireSim-{self.PLATFORM_NAME}"
        json_db = self.parent_node.get_fpga_db()

        with cd(remote_sim_dir):
            # Use a system wide installed firesim-generate-fpga-db.py
            cmd = f"{script_path}/firesim-generate-fpga-db.py"
            check_script(
                cmd,
                Path(f"{get_deploy_dir()}/../platforms/{self.PLATFORM_NAME}/scripts"),
            )
            run(f"""{cmd} --bitstream {bitstream} --driver {driver} --out-db-json {json_db}""")

    def enumerate_fpgas(self, uridir: str) -> None:
        """Handle fpga setup for this platform."""

        if self.instance_assigned_simulations():
            # This is a sim-host node.

            # unload xdma driver
            self.unload_xdma()
            # load xdma driver
            self.load_xdma()

            # change all pcie permissions
            self.change_all_pcie_perms()

            # run the passes
            self.create_fpga_database(uridir)

    def terminate_instance(self) -> None:
        """XilinxAlveoInstanceDeployManager machines cannot be terminated."""
        return

    def start_sim_slot(self, slotno: int) -> None:
        """start a simulation. (same as the default except that you have a mapping from slotno to a specific BDF)"""
        if self.instance_assigned_simulations():
            self.instance_logger(
                f"""Starting {self.sim_type_message} simulation for slot: {slotno}."""
            )
            remote_home_dir = self.parent_node.sim_dir
            remote_sim_dir = f"""{remote_home_dir}/sim_slot_{slotno}/"""
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            server = self.parent_node.sim_slots[slotno]

            if not self.parent_node.metasimulation_enabled:
                bdf = (
                    self.slot_to_bdf(slotno, self.parent_node.get_fpga_db())
                    .replace(".", ":")
                    .split(":")
                )
                extra_args = f"+domain=0x0000 +bus=0x{bdf[0]} +device=0x{bdf[1]} +function=0x{bdf[2]} +bar=0x0 +pci-vendor=0x10ee +pci-device=0x903f"
            else:
                extra_args = None

            # make the local job results dir for this sim slot
            server.mkdir_and_prep_local_job_results_dir()
            sim_start_script_local_path = server.write_sim_start_script(
                slotno, extra_args
            )
            put(sim_start_script_local_path, remote_sim_dir)

            with cd(remote_sim_dir):
                run("chmod +x sim-run.sh")
                run("./sim-run.sh")


class XilinxAlveoU250InstanceDeployManager(XilinxAlveoInstanceDeployManager):
    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "xilinx_alveo_u250"


class XilinxAlveoU280InstanceDeployManager(XilinxAlveoInstanceDeployManager):
    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "xilinx_alveo_u280"


class XilinxAlveoU200InstanceDeployManager(XilinxAlveoInstanceDeployManager):
    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "xilinx_alveo_u200"


class CorigineXB10InstanceDeployManager(XilinxAlveoInstanceDeployManager):
    """Deploy XB10s without changing host-global XDMA state.

    XB10 hosts can contain multiple independently-owned cards behind one XDMA
    kernel module.  The generic Alveo flow unloads/reloads that module and
    chmods every ``/dev/xdma*`` node, which is not safe on a shared host.  This
    subclass instead removes/rescans only the selected PCI functions while the
    existing XDMA module remains registered.
    """

    VIVADO_SETTINGS_ENV = "FIRESIM_XB10_VIVADO_SETTINGS"
    DEFAULT_VIVADO_SETTINGS = "/ecad/tools/xilinx/2025.1/Vivado/settings64.sh"
    EXPECTED_VIVADO_VERSION = "2025.1"
    _BDF_RE = re.compile(r"^[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]$")
    _UID_RE = re.compile(r"^[A-Za-z0-9_.:-]+/[A-Za-z0-9_.:-]+$")

    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "corigine_xb10"

    @classmethod
    def _validate_fpga_db_entries(
        cls, raw_db: object, expected_slots: int
    ) -> List[Dict[str, str]]:
        if not isinstance(raw_db, list) or len(raw_db) != expected_slots:
            raise RuntimeError(
                "XB10 FPGA DB must contain exactly one entry per selected slot "
                f"({expected_slots} expected)"
            )
        if expected_slots < 1:
            raise RuntimeError("XB10 deployment has no selected FPGA slots")

        entries: List[Dict[str, str]] = []
        for index, raw_entry in enumerate(raw_db):
            if not isinstance(raw_entry, dict):
                raise RuntimeError(f"XB10 FPGA DB entry {index} is not a mapping")
            if not {"bdf", "uid", "device"}.issubset(raw_entry):
                raise RuntimeError(f"XB10 FPGA DB entry {index} is incomplete")
            bdf = str(raw_entry["bdf"])
            uid = str(raw_entry["uid"])
            device = str(raw_entry["device"])
            if cls._BDF_RE.fullmatch(bdf) is None:
                raise RuntimeError(
                    f"XB10 FPGA DB entry {index} has invalid BDF {bdf!r}"
                )
            if cls._UID_RE.fullmatch(uid) is None:
                raise RuntimeError(
                    f"XB10 FPGA DB entry {index} has invalid UID {uid!r}"
                )
            if re.fullmatch(r"[A-Za-z0-9_.:-]+", device) is None:
                raise RuntimeError(
                    f"XB10 FPGA DB entry {index} has invalid device name {device!r}"
                )
            entries.append({"bdf": bdf, "uid": uid, "device": device})

        bdfs = [entry["bdf"].lower() for entry in entries]
        uids = [entry["uid"] for entry in entries]
        if len(set(bdfs)) != len(bdfs):
            raise RuntimeError("XB10 FPGA DB contains duplicate BDFs")
        if len(set(uids)) != len(uids):
            raise RuntimeError("XB10 FPGA DB contains duplicate JTAG UIDs")
        return entries

    def _read_selected_fpga_db(self) -> Tuple[str, List[Dict[str, str]]]:
        json_db = self.parent_node.get_fpga_db()
        if not os.path.isabs(json_db):
            raise RuntimeError("XB10 FPGA DB path must be absolute")
        raw = run(f"cat -- {shlex.quote(json_db)}")
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid XB10 FPGA DB {json_db}: {error}") from error
        entries = self._validate_fpga_db_entries(
            parsed, len(self.parent_node.sim_slots)
        )
        return json_db, entries

    def _vivado_environment_prefix(self) -> str:
        settings_path = os.environ.get(
            self.VIVADO_SETTINGS_ENV, self.DEFAULT_VIVADO_SETTINGS
        )
        return (
            f"test -r {shlex.quote(settings_path)} && "
            f"source {shlex.quote(settings_path)}"
        )

    def _preflight_xb10_tools(self) -> Tuple[str, str, str]:
        """Resolve and version-check programming tools before PCI mutation."""
        environment = self._vivado_environment_prefix()
        command = (
            f"{environment} && "
            "vivado_bin=$(command -v vivado) && "
            "hw_server_bin=$(command -v hw_server) && "
            'version_line=$("$vivado_bin" -version | sed -n "1p") && '
            'printf "__FIRESIM_VIVADO__=%s\\n" "$vivado_bin" && '
            'printf "__FIRESIM_HW_SERVER__=%s\\n" "$hw_server_bin" && '
            'printf "__FIRESIM_VIVADO_VERSION__=%s\\n" "$version_line"'
        )
        output = str(run(command))
        markers: Dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("__FIRESIM_") and "=" in line:
                key, value = line.split("=", 1)
                markers[key] = value.strip()

        vivado = markers.get("__FIRESIM_VIVADO__", "")
        hw_server = markers.get("__FIRESIM_HW_SERVER__", "")
        version_line = markers.get("__FIRESIM_VIVADO_VERSION__", "")
        version_match = re.match(r"^[Vv]ivado\s+v([^\s]+)", version_line)
        if not vivado or not hw_server or version_match is None:
            raise RuntimeError("Unable to resolve Vivado and hw_server for XB10")
        if version_match.group(1) != self.EXPECTED_VIVADO_VERSION:
            raise RuntimeError(
                "Corigine XB10 programming requires Vivado "
                f"{self.EXPECTED_VIVADO_VERSION}, found {version_match.group(1)}"
            )
        return environment, vivado, hw_server

    def _run_card_action(
        self,
        action: str,
        bdf: str,
        card_helper: str,
        operation_token: str,
        warn: bool = False,
    ):
        if action != "reconnect-if-needed":
            raise ValueError(f"unsupported XB10 card action: {action}")
        command = (
            f"sudo {shlex.quote(card_helper)} {action} "
            f"--bdf {shlex.quote(bdf)} "
            f"--token {shlex.quote(operation_token)}"
        )
        if warn:
            with settings(warn_only=True):
                return run(command)
        return run(command)

    def _program_with_guaranteed_reconnect(
        self,
        entries: List[Dict[str, str]],
        card_helper: str,
        operation_token: str,
        program_command: str,
    ) -> None:
        """Program once, then reconnect every card which was disconnected."""
        primary_error: Optional[BaseException] = None
        primary_traceback = None
        reconnect_failures: List[str] = []
        try:
            run(program_command)
        except BaseException as error:
            primary_error = error
            primary_traceback = error.__traceback__
        finally:
            for entry in reversed(entries):
                bdf = entry["bdf"]
                try:
                    result = self._run_card_action(
                        "reconnect-if-needed",
                        bdf,
                        card_helper,
                        operation_token,
                        warn=True,
                    )
                except BaseException:
                    reconnect_failures.append(bdf)
                    continue
                if getattr(result, "return_code", 0) != 0:
                    reconnect_failures.append(bdf)

        if reconnect_failures:
            message = "Failed to reconnect XB10 BDF(s): " + ", ".join(
                reconnect_failures
            )
            if primary_error is None:
                raise RuntimeError(message)
            raise RuntimeError(message) from primary_error
        if primary_error is not None:
            raise primary_error.with_traceback(primary_traceback)

    def flash_fpgas(self) -> None:
        """Preflight and program only DB-selected XB10 cards."""
        if not self.instance_assigned_simulations():
            return

        self._require_xb10_artifact_contracts()
        _, entries = self._read_selected_fpga_db()
        environment, vivado, _ = self._preflight_xb10_tools()
        mapping_lines: List[str] = []
        scripts_dir: Optional[str] = None

        for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
            hwcfg = firesimservernode.get_resolved_server_hardware_config()
            remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
            unpack_dir = os.path.join(remote_sim_dir, str(self.PLATFORM_NAME))
            bit = os.path.join(unpack_dir, "firesim.bit")
            bitstream_archive = os.path.join(
                remote_sim_dir, hwcfg.get_bitstream_tar_filename()
            )
            # Recheck the archive after infrasetup and immediately before its
            # bytes can reach the programming flow.
            self._verify_remote_artifact_archive(slotno, "bitstream_tar")
            run(f"rm -rf {shlex.quote(unpack_dir)}")
            run(
                f"tar xvf {shlex.quote(bitstream_archive)} "
                f"-C {shlex.quote(remote_sim_dir)}"
            )
            self._verify_remote_extracted_bitstream(slotno)

            if scripts_dir is None:
                rsync_cap = rsync_project(
                    local_dir=f"../platforms/{self.PLATFORM_NAME}/scripts",
                    remote_dir=remote_sim_dir,
                    ssh_opts="-o StrictHostKeyChecking=no",
                    extra_opts="-L -p",
                    capture=True,
                )
                rootLogger.debug(rsync_cap)
                rootLogger.debug(rsync_cap.stderr)
                if getattr(rsync_cap, "failed", False):
                    raise RuntimeError(
                        "Failed to copy XB10 programming helper scripts: "
                        f"{rsync_cap.stderr}"
                    )
                scripts_dir = f"{remote_sim_dir}/scripts"

            entry = entries[slotno]
            mapping_lines.append(
                f"{entry['uid']}|{entry['device']}|{entry['bdf']} {bit}"
            )

        if scripts_dir is None:
            raise RuntimeError("XB10 deployment has no scripts directory")
        card_helper = f"{scripts_dir}/firesim-xb10-card.py"
        map_file = f"{self.get_remote_sim_dir_for_slot(0)}/flash_map.txt"
        quoted_lines = " ".join(shlex.quote(line) for line in mapping_lines)
        run(f"printf '%s\\n' {quoted_lines} > {shlex.quote(map_file)}")

        # Everything below is checked before the first PCI remove: exact BDF
        # shape/current binding/no open handles, unique live JTAG UID matches,
        # bitstream presence, and exact Vivado release.
        for entry in entries:
            run(
                f"sudo {shlex.quote(card_helper)} preflight "
                f"--bdf {shlex.quote(entry['bdf'])}"
            )
        tcl = f"{scripts_dir}/program_fpga_fleet.tcl"
        operation_token = secrets.token_hex(16)
        final_bitstream_checks = " && ".join(
            f"({self._remote_extracted_bitstream_check_command(slotno)})"
            for slotno in range(len(self.parent_node.sim_slots))
        )
        vivado_command = (
            f"{final_bitstream_checks} && {environment} && "
            f"{shlex.quote(vivado)} -mode batch "
            f"-source {shlex.quote(tcl)} -tclargs "
            f"-map_file {shlex.quote(map_file)} "
            f"-disconnect_helper {shlex.quote(card_helper)} "
            f"-operation_token {shlex.quote(operation_token)}"
        )

        self._program_with_guaranteed_reconnect(
            entries,
            card_helper,
            operation_token,
            vivado_command,
        )

    def change_pcie_perms(self) -> None:
        """Grant the invoking user access to only the selected card nodes."""
        if not self.instance_assigned_simulations():
            return
        _, entries = self._read_selected_fpga_db()
        helper = (
            f"{self.get_remote_sim_dir_for_slot(0)}/scripts/" "firesim-xb10-card.py"
        )
        for entry in entries:
            run(
                f"sudo {shlex.quote(helper)} grant "
                f"--bdf {shlex.quote(entry['bdf'])}"
            )

    def _remove_stale_fased_runtime_profile(self, slotno: int) -> None:
        """Remove only the contracted profile before extracting a fresh bundle."""
        serv = self.parent_node.sim_slots[slotno]
        hwcfg = serv.get_resolved_server_hardware_config()
        profile = hwcfg.fased_runtime_profile
        if profile is None:
            return
        remote_profile = os.path.join(
            self.get_remote_sim_dir_for_slot(slotno), profile.filename
        )
        run(f"rm -f -- {shlex.quote(remote_profile)}")

    def _verify_remote_fased_runtime_profile(self, slotno: int) -> None:
        """Bind the extracted remote profile to the locally validated contract."""
        serv = self.parent_node.sim_slots[slotno]
        hwcfg = serv.get_resolved_server_hardware_config()
        profile = hwcfg.fased_runtime_profile
        if profile is None:
            return
        remote_profile = os.path.join(
            self.get_remote_sim_dir_for_slot(slotno), profile.filename
        )
        run(
            "set -euo pipefail; "
            f"profile={shlex.quote(remote_profile)}; "
            f"expected_sha={shlex.quote(profile.sha256)}; "
            '[[ -f "$profile" && ! -L "$profile" && -r "$profile" && -s "$profile" ]]; '
            'actual_sha="$(sha256sum -- "$profile" | awk \'{print $1}\')"; '
            '[[ "$actual_sha" == "$expected_sha" ]]'
        )

    def _verify_remote_artifact_archive(self, slotno: int, artifact_name: str) -> None:
        """Verify a contracted archive on the run host before it is consumed."""
        if artifact_name not in ("bitstream_tar", "driver_tar"):
            raise ValueError(f"Unsupported FPGA artifact {artifact_name!r}")
        serv = self.parent_node.sim_slots[slotno]
        hwcfg = serv.get_resolved_server_hardware_config()
        contract = getattr(hwcfg, "artifact_sha256", None)
        if contract is None:
            return

        expected_sha256 = getattr(contract, artifact_name)
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise RuntimeError(
                f"Unresolved {artifact_name} SHA-256 placeholder for XB10 slot {slotno}"
            )
        filename = (
            hwcfg.get_bitstream_tar_filename()
            if artifact_name == "bitstream_tar"
            else hwcfg.get_driver_tar_filename()
        )
        remote_archive = os.path.join(
            self.get_remote_sim_dir_for_slot(slotno), filename
        )
        run(
            "set -euo pipefail; "
            f"archive={shlex.quote(remote_archive)}; "
            f"expected_sha={shlex.quote(expected_sha256)}; "
            '[[ -f "$archive" && ! -L "$archive" && -r "$archive" && -s "$archive" ]]; '
            'actual_sha="$(sha256sum -- "$archive" | awk \'{print $1}\')"; '
            '[[ "$actual_sha" == "$expected_sha" ]]'
        )

    def _require_xb10_artifact_contracts(self) -> None:
        """Reject physical XB10 setup before remote work if any hash is absent."""
        for slotno, serv in enumerate(self.parent_node.sim_slots):
            hwcfg = serv.get_resolved_server_hardware_config()
            contract = getattr(hwcfg, "artifact_sha256", None)
            if contract is None:
                raise RuntimeError(
                    f"Physical XB10 slot {slotno} requires an artifact_sha256 contract"
                )
            for artifact_name in ("bitstream_tar", "driver_tar"):
                expected_sha256 = getattr(contract, artifact_name, None)
                if (
                    not isinstance(expected_sha256, str)
                    or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
                ):
                    raise RuntimeError(
                        f"Physical XB10 slot {slotno} has an unresolved or invalid "
                        f"{artifact_name} SHA-256"
                    )

    def _remote_extracted_bitstream_check_command(self, slotno: int) -> str:
        """Return a fail-closed check binding the extracted bit to its archive."""
        serv = self.parent_node.sim_slots[slotno]
        hwcfg = serv.get_resolved_server_hardware_config()
        contract = getattr(hwcfg, "artifact_sha256", None)
        expected_sha256 = (
            getattr(contract, "bitstream_tar", None) if contract is not None else None
        )
        if (
            not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise RuntimeError(
                f"Physical XB10 slot {slotno} has no resolved bitstream_tar SHA-256"
            )

        remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
        remote_archive = os.path.join(
            remote_sim_dir, hwcfg.get_bitstream_tar_filename()
        )
        remote_bit = os.path.join(remote_sim_dir, self.PLATFORM_NAME, "firesim.bit")
        archive_member = f"{self.PLATFORM_NAME}/firesim.bit"
        return (
            "set -euo pipefail; "
            f"archive={shlex.quote(remote_archive)}; "
            f"bit={shlex.quote(remote_bit)}; "
            f"member={shlex.quote(archive_member)}; "
            f"expected_archive_sha={shlex.quote(expected_sha256)}; "
            '[[ -f "$archive" && ! -L "$archive" && -r "$archive" && -s "$archive" ]]; '
            'actual_archive_sha="$(sha256sum -- "$archive" | awk \'{print $1}\')"; '
            '[[ "$actual_archive_sha" == "$expected_archive_sha" ]]; '
            '[[ -f "$bit" && ! -L "$bit" && -r "$bit" && -s "$bit" ]]; '
            '[[ "$(stat -c %h -- "$bit")" == 1 ]]; '
            'actual_bit_sha="$(sha256sum -- "$bit" | awk \'{print $1}\')"; '
            'archive_bit_sha="$(tar -xOzf "$archive" -- "$member" | '
            'sha256sum | awk \'{print $1}\')"; '
            '[[ "$actual_bit_sha" == "$archive_bit_sha" ]]'
        )

    def _verify_remote_extracted_bitstream(self, slotno: int) -> None:
        """Verify extracted bit metadata and exact bytes on the run host."""
        run(self._remote_extracted_bitstream_check_command(slotno))

    def infrasetup_instance(self, uridir: str) -> None:
        """Set up selected cards without unloading/reloading XDMA."""
        if self.instance_assigned_simulations():
            if not self.parent_node.metasimulation_enabled:
                self._require_xb10_artifact_contracts()
            for slotno in range(len(self.parent_node.sim_slots)):
                self.copy_sim_slot_infrastructure(slotno, uridir)
                self._verify_remote_artifact_archive(slotno, "driver_tar")
                self._verify_remote_artifact_archive(slotno, "bitstream_tar")
                self._remove_stale_fased_runtime_profile(slotno)
                self.extract_driver_tarball(slotno)
                self._verify_remote_fased_runtime_profile(slotno)

            if not self.parent_node.metasimulation_enabled:
                self.flash_fpgas()
                self.change_pcie_perms()

        if self.instance_assigned_switches():
            for slotno in range(len(self.parent_node.switch_slots)):
                self.copy_switch_slot_infrastructure(slotno)

        if self.instance_assigned_pipes():
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.copy_pipe_slot_infrastructure(slotno)

    def enumerate_fpgas(self, uridir: str) -> None:
        raise RuntimeError(
            "XB10 enumeration changes host-global XDMA state; use an explicitly "
            "coordinated FPGA database instead"
        )

    def create_fpga_database(self, uridir: str) -> None:
        raise RuntimeError(
            "XB10 FPGA database creation is disabled on shared hosts; use an "
            "explicitly coordinated FPGA database instead"
        )


class RHSResearchNitefuryIIInstanceDeployManager(XilinxAlveoInstanceDeployManager):
    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "rhsresearch_nitefury_ii"


class XilinxVCU118InstanceDeployManager(InstanceDeployManager):
    """This class manages a Xilinx VCU118-enabled instance using the
    garnet shell."""

    PLATFORM_NAME: Optional[str]
    NEED_ENUMERATION = False

    def __init__(self, parent_node: Inst) -> None:
        super().__init__(parent_node)
        self.PLATFORM_NAME = "xilinx_vcu118"

    def load_xdma(self) -> None:
        """load the xdma kernel module."""
        if self.instance_assigned_simulations():
            # load xdma if unloaded
            if run("lsmod | grep -wq xdma", warn_only=True).return_code != 0:
                self.instance_logger("Loading XDMA Driver Kernel Module.")
                # must be installed to this path on sim. machine
                cmd = f"{script_path}/firesim-load-xdma-module"
                check_script(cmd)
                run(f"sudo {cmd}", shell=True)
            else:
                self.instance_logger("XDMA Driver Kernel Module already loaded.")
            cmd = f"{script_path}/firesim-chmod-xdma-perm"
            check_script(cmd)
            run(f"sudo {cmd}")

    def load_xvsec(self) -> None:
        """load the xvsec kernel modules."""
        if self.instance_assigned_simulations():
            if run("lsmod | grep -wq xvsec", warn_only=True).return_code != 0:
                self.instance_logger("Loading XVSEC Driver Kernel Module.")
                # must be installed to this path on sim. machine
                cmd = f"{script_path}/firesim-load-xvsec-module"
                check_script(cmd)
                run(f"sudo {cmd}", shell=True)
            else:
                self.instance_logger("XVSEC Driver Kernel Module already loaded.")

    def flash_fpgas(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("""Flash all FPGA Slots.""")

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                serv = self.parent_node.sim_slots[slotno]
                hwcfg = serv.get_resolved_server_hardware_config()

                bitstream_tar = hwcfg.get_bitstream_tar_filename()
                remote_sim_dir = self.get_remote_sim_dir_for_slot(slotno)
                bitstream_tar_unpack_dir = f"{remote_sim_dir}/{self.PLATFORM_NAME}"
                bit = f"{remote_sim_dir}/{self.PLATFORM_NAME}/firesim.bit"

                # at this point the tar file is in the sim slot
                run(f"rm -rf {bitstream_tar_unpack_dir}")
                run(f"tar xvf {remote_sim_dir}/{bitstream_tar} -C {remote_sim_dir}")

                self.instance_logger(f"""Determine BDF for {slotno}""")
                collect = run("lspci | grep -i xilinx")

                # TODO: is "Partial Reconfig Clear File" useful (see xvsecctl help)?
                bdfs = [
                    # capno is hardcoded to 0x1 otherwise xvsecctl program fails
                    {"busno": "0x" + i[:2], "devno": "0x" + i[3:5], "capno": "0x1"}
                    for i in collect.splitlines()
                    if len(i.strip()) >= 0
                ]
                bdf = bdfs[slotno]

                busno = bdf["busno"]
                devno = bdf["devno"]
                capno = bdf["capno"]

                self.instance_logger(
                    f"""Flashing FPGA Slot: {slotno} (bus:{busno}, dev:{devno}, cap:{capno}) with bit: {bit}"""
                )
                cmd = f"{script_path}/firesim-xvsecctl-flash-fpga"
                check_script(cmd)
                run(f"""sudo {cmd} {busno} {devno} {capno} {bit}""")

    def change_pcie_perms(self) -> None:
        if self.instance_assigned_simulations():
            self.instance_logger("""Change permissions on FPGA slot""")

            for slotno, firesimservernode in enumerate(self.parent_node.sim_slots):
                self.instance_logger(f"""Determine BDF for {slotno}""")
                collect = run("lspci | grep -i xilinx")

                # TODO: is "Partial Reconfig Clear File" useful (see xvsecctl help)?
                bdfs = [
                    # Cannot hardcode capno to 0x1 here, if 0x1 change permissions sometimes cannot find the device in /sys/bus/pci/devices/
                    {"busno": "0x" + i[:2], "devno": "0x" + i[3:5], "capno": "0x" + i[6:7]}
                    for i in collect.splitlines()
                    if len(i.strip()) >= 0
                ]
                bdf = bdfs[slotno]

                busno = bdf["busno"]
                devno = bdf["devno"]
                capno = bdf["capno"]

                self.instance_logger(
                    f"""Changing permissions on FPGA Slot: {slotno} (bus:{busno}, dev:{devno}, cap:{capno})"""
                )
                cmd = f"{script_path}/firesim-change-pcie-perms"
                check_script(cmd)
                run(f"""sudo {cmd} 0000:{busno[2:]}:{devno[2:]}:{capno[2:]}""")

    def infrasetup_instance(self, uridir: str) -> None:
        """Handle infrastructure setup for this platform."""
        if self.instance_assigned_simulations():
            # This is a sim-host node.

            # copy sim infrastructure
            for slotno in range(len(self.parent_node.sim_slots)):
                self.copy_sim_slot_infrastructure(slotno, uridir)
                self.extract_driver_tarball(slotno)

            if not self.parent_node.metasimulation_enabled:
                # load xdma driver
                self.load_xdma()
                self.load_xvsec()
                # flash fpgas
                self.flash_fpgas()
                # change pcie permissions
                self.change_pcie_perms()

        if self.instance_assigned_switches():
            # all nodes could have a switch
            for slotno in range(len(self.parent_node.switch_slots)):
                self.copy_switch_slot_infrastructure(slotno)

        if self.instance_assigned_pipes():
            # all nodes could have a switch
            for slotno in range(len(self.parent_node.pipe_slots)):
                self.copy_pipe_slot_infrastructure(slotno)

    def enumerate_fpgas(self, uridir: str) -> None:
        """FPGAs are enumerated already with VCU118's"""
        return

    def terminate_instance(self) -> None:
        """XilinxVCU118InstanceDeployManager machines cannot be terminated."""
        return

    def start_sim_slot(self, slotno: int) -> None:
        """start a simulation. (same as the default except that you have a mapping from slotno to a specific BDF)"""
        if self.instance_assigned_simulations():
            self.instance_logger(
                f"""Starting {self.sim_type_message} simulation for slot: {slotno}."""
            )
            remote_home_dir = self.parent_node.sim_dir
            remote_sim_dir = f"""{remote_home_dir}/sim_slot_{slotno}/"""
            assert slotno < len(
                self.parent_node.sim_slots
            ), f"{slotno} can not index into sim_slots {len(self.parent_node.sim_slots)} on {self.parent_node.host}"
            server = self.parent_node.sim_slots[slotno]

            if not self.parent_node.metasimulation_enabled:
                self.instance_logger(f"""Determine BDF for {slotno}""")
                collect = run("lspci | grep -i xilinx")
                bdfs = [i[:7] for i in collect.splitlines() if len(i.strip()) >= 0]
                bdf = bdfs[slotno].replace(".", ":").split(":")
                extra_args = f"+domain=0x0000 +bus=0x{bdf[0]} +device=0x{bdf[1]} +function=0x0 +bar=0x0 +pci-vendor=0x10ee +pci-device=0x903f"
            else:
                extra_args = None

            # make the local job results dir for this sim slot
            server.mkdir_and_prep_local_job_results_dir()
            sim_start_script_local_path = server.write_sim_start_script(
                slotno, extra_args
            )
            put(sim_start_script_local_path, remote_sim_dir)

            with cd(remote_sim_dir):
                run("chmod +x sim-run.sh")
                run("./sim-run.sh")
