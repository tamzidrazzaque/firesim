# Program multiple FPGAs with potentially different bitstreams in a single
# Vivado session.  Avoids the hw_server wedge caused by back-to-back
# Vivado process launches.
#
# Usage:
#   vivado -mode batch -source program_fpga_fleet.tcl \
#     -tclargs -map_file <path> ?-preflight_only 0|1? \
#       ?-disconnect_helper <path> -operation_token <hex>?
#
# map_file format: one line per target
#   <exact_uid>|<expected_device>|<bdf> <bitstream_path>
# The legacy two-column form, <exact_uid> <bitstream_path>, remains supported.
#
# Example:
#   Digilent/210308B356F7 /path/to/slot0/firesim.bit
#   Digilent/210308B356F1 /path/to/slot1/firesim.bit

proc parse_args {} {
    global argc argv
    set result(-map_file) ""
    set result(-preflight_only) 0
    set result(-disconnect_helper) ""
    set result(-operation_token) ""

    if {$argc % 2 != 0} {
        puts "ERROR: arguments must be option/value pairs"
        exit 1
    }

    for {set i 0} {$i < $argc} {incr i 2} {
        set arg [lindex $argv $i]
        set val [lindex $argv [expr {$i + 1}]]
        if {[info exists result($arg)]} {
            set result($arg) $val
        } else {
            puts "ERROR: unknown argument: $arg"
            exit 1
        }
    }

    if {$result(-map_file) eq ""} {
        puts "ERROR: -map_file is required"
        exit 1
    }
    if {![file exists $result(-map_file)]} {
        puts "ERROR: map file not found: $result(-map_file)"
        exit 1
    }
    if {$result(-preflight_only) ni {0 1}} {
        puts "ERROR: -preflight_only must be 0 or 1"
        exit 1
    }
    if {$result(-disconnect_helper) ne ""
            && ![file executable $result(-disconnect_helper)]} {
        puts "ERROR: disconnect helper is not executable: $result(-disconnect_helper)"
        exit 1
    }
    if {$result(-disconnect_helper) ne ""
            && ![regexp {^[0-9a-f]{32}$} $result(-operation_token)]} {
        puts "ERROR: -operation_token must be 32 lowercase hexadecimal characters"
        exit 1
    }
    return [array get result]
}

proc read_map_file {path} {
    set fd [open $path r]
    set entries {}
    while {[gets $fd line] >= 0} {
        set line [string trim $line]
        if {$line eq "" || [string index $line 0] eq "#"} continue
        set parts [split $line]
        if {[llength $parts] < 2} {
            puts "WARNING: skipping malformed line: $line"
            continue
        }
        set identity [lindex $parts 0]
        set uid $identity
        set expected_device ""
        set bdf ""
        if {[string first "|" $identity] >= 0} {
            set identity_parts [split $identity "|"]
            if {[llength $identity_parts] ni {2 3}
                    || [lindex $identity_parts 0] eq ""
                    || [lindex $identity_parts 1] eq ""} {
                puts "ERROR: malformed UID/device identity: $identity"
                exit 1
            }
            set uid [lindex $identity_parts 0]
            set expected_device [lindex $identity_parts 1]
            if {[llength $identity_parts] == 3} {
                set bdf [lindex $identity_parts 2]
                if {![regexp {^[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]$} $bdf]} {
                    puts "ERROR: malformed BDF: $bdf"
                    exit 1
                }
            }
        }
        set bit [join [lrange $parts 1 end]]
        if {![file exists $bit]} {
            puts "ERROR: bitstream not found: $bit"
            exit 1
        }
        lappend entries [list $uid $expected_device $bdf $bit]
    }
    close $fd
    return $entries
}

array set opts [parse_args]
set entries [read_map_file $opts(-map_file)]

if {[llength $entries] == 0} {
    puts "ERROR: no entries in map file"
    exit 1
}

puts "Will program [llength $entries] target(s):"
foreach e $entries {
    puts "  [lindex $e 0] ([lindex $e 1], [lindex $e 2]) -> [lindex $e 3]"
}

set_param labtools.enable_cs_server false

open_hw_manager
connect_hw_server -allow_non_jtag
close_hw_target

set all_targets [get_hw_targets]
puts "Available hw_targets: $all_targets"

# Resolve every UID, and optionally its expected device, before any PCI
# endpoint is removed by the caller.  Ambiguous substring matches are not
# accepted: the UID property must be an exact, unique match.
set resolved_entries {}
set selected_targets {}
set resolution_failures {}

foreach entry $entries {
    set uid [lindex $entry 0]
    set expected_device [lindex $entry 1]
    set bdf [lindex $entry 2]
    set bit [lindex $entry 3]

    set matches {}
    foreach t $all_targets {
        if {![catch {set target_uid [get_property UID $t]}]
                && $target_uid eq $uid} {
            lappend matches $t
        }
    }

    if {[llength $matches] != 1} {
        puts "ERROR: expected exactly one hw_target with UID '$uid'; found [llength $matches]"
        lappend resolution_failures $uid
        continue
    }
    set matched [lindex $matches 0]
    if {$matched in $selected_targets} {
        puts "ERROR: hw_target '$matched' was selected more than once"
        lappend resolution_failures $uid
        continue
    }

    if {$expected_device ne ""} {
        set live_device ""
        if {[catch {
            open_hw_target $matched
            set live_devices [get_hw_devices]
            if {[llength $live_devices] != 1} {
                error "expected one device, found [llength $live_devices]"
            }
            set live_device [lindex $live_devices 0]
            close_hw_target
        } err]} {
            puts "ERROR: cannot inspect '$uid': $err"
            catch {close_hw_target}
            lappend resolution_failures $uid
            continue
        }
        if {$live_device ne $expected_device} {
            puts "ERROR: UID '$uid' expected device '$expected_device', found '$live_device'"
            lappend resolution_failures $uid
            continue
        }
    }

    lappend selected_targets $matched
    lappend resolved_entries [list $matched $uid $bdf $bit]
}

if {[llength $resolution_failures] > 0} {
    disconnect_hw_server
    close_hw_manager
    exit 1
}

if {$opts(-preflight_only)} {
    puts "Preflight passed for [llength $resolved_entries] target(s); no FPGA was programmed."
    disconnect_hw_server
    close_hw_manager
    exit 0
}

if {$opts(-disconnect_helper) ne ""} {
    foreach entry $resolved_entries {
        set uid [lindex $entry 1]
        set bdf [lindex $entry 2]
        if {$bdf eq ""} {
            puts "ERROR: UID '$uid' has no BDF for card-scoped disconnect"
            disconnect_hw_server
            close_hw_manager
            exit 1
        }
        if {[catch {
            exec sudo -- $opts(-disconnect_helper) disconnect --bdf $bdf \
                --token $opts(-operation_token)
        } err]} {
            puts "ERROR: failed to disconnect BDF '$bdf': $err"
            disconnect_hw_server
            close_hw_manager
            exit 1
        }
    }
}

set total [llength $resolved_entries]
set idx 0
set failures {}

foreach entry $resolved_entries {
    set matched [lindex $entry 0]
    set uid [lindex $entry 1]
    set bit [lindex $entry 3]
    incr idx

    puts "\n========== \[$idx/$total\] $matched ($uid) =========="
    set start_time [clock seconds]

    if {[catch {
        open_hw_target $matched
        set dev [lindex [get_hw_devices] 0]
        current_hw_device $dev
        set_property PROGRAM.FILE $bit $dev
        program_hw_devices $dev
        refresh_hw_device $dev
        close_hw_target
    } err]} {
        puts "ERROR on $matched: $err"
        lappend failures $uid
        catch {close_hw_target}
    } else {
        set dur [expr {[clock seconds] - $start_time}]
        puts "OK $matched (${dur}s)"
    }
}

disconnect_hw_server
close_hw_manager

puts "\n================ Summary ================"
puts "Programmed: [expr {$total - [llength $failures]}] / $total"
if {[llength $failures] > 0} {
    puts "FAILED targets:"
    foreach f $failures { puts "  $f" }
    exit 1
}

exit 0
