# This script collects paper statistics for compressed logfiles
# By: Roland Green

import os
from sys import argv
import gzip
import copy
import json

# Dictionary of statistics
STATS = {
    "app_path" : None,
    "kernel_ipcs" : None,
    "cta_ipcs" : None,
    "app_ipc" : None,
}

# Returns a list of logfile paths
def get_paths(directory):
    paths = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".log.gz"):
                paths.append(os.path.join(root, f))

    return paths

# Returns a dictionary of the parsed cycles, instructions, and CTAs
# #TODO get other statistics from logfiles later
def filter_lines(path):
    # Dump the lines from the file
    with gzip.open(path, 'rt') as f:
        lines = f.readlines()

    # Get the cycles, instructions, and CTAs counts
    cycles = []
    instructions = []
    ctas = []
    for line in lines:
        if "globalcyclecount" in line:
            cycles.append(int(line.split(':')[1]))
            continue
        if "globalinsncount" in line:
            instructions.append(int(line.split(':')[1]))
            continue
        if "ctas_completed" in line:
            ctas.append(int(line.split(':')[1]))
            continue

    # Return a dictionary prevent growing list of arguments
    return_dict = {
        "cycles" : cycles,
        "instructions" : instructions,
        "ctas" : ctas,
    }
    return return_dict

# Returns cycles and instructions split into kernels
def split_into_kernels(filtered_lines, sample_freq):
    split_cycles = []
    split_instructions = []
    split_ctas = []
    kernel_cycles = []
    kernel_instructions = []
    kernel_ctas = []
    for i in range(len(filtered_lines["cycles"])):
        # Append new list for each new kernel
        # Handle case of first sample
        if (filtered_lines["cycles"][i] == sample_freq) and (len(kernel_cycles) != 0):
            split_cycles.append(kernel_cycles[:])
            split_instructions.append(kernel_instructions[:])
            split_ctas.append(kernel_ctas[:])
            kernel_cycles.clear()
            kernel_instructions.clear()
            kernel_ctas.clear()

        # Append cycle and instruction count for this kernel
        kernel_cycles.append(filtered_lines["cycles"][i])
        kernel_instructions.append(filtered_lines["instructions"][i])
        kernel_ctas.append(filtered_lines["ctas"][i])

    # Append the last recorded kernel
    split_cycles.append(kernel_cycles[:])
    split_instructions.append(kernel_instructions[:])
    split_ctas.append(kernel_ctas[:])

    # Zero out the first entry of each CTAs completed
    # These come from the final CTAs of the last kernel
    for kernel in split_ctas:
        kernel[0] = 0

    # Return a dictionary prevent growing list of arguments
    return_dict = {
        "split_cycles" : split_cycles,
        "split_instructions" : split_instructions,
        "split_ctas" : split_ctas,
    }
    return return_dict

# Returns a list of tuples containing cycle, CTAs completed, and IPC
def extract_cta_ipc(split_lines, k_id):
    cta_tuples = []
    ctas_completed = 0
    for i in range(len(split_lines["split_cycles"][k_id])):
        # Only track if some CTA has completed
        if split_lines["split_ctas"][k_id][i] != 0:
            ctas_completed += split_lines["split_ctas"][k_id][i]
            cycle = split_lines["split_cycles"][k_id][i]
            instructions = split_lines["split_instructions"][k_id][i]
            ipc = instructions / cycle

            # Append a tuple of cycle, # of CTAs completed, and IPC
            cta_tuples.append((cycle, ctas_completed, ipc))

    return cta_tuples

# Return the first CTA IPC that's withing 10% of the kernel IPC
def filter_cta_ipcs(unfiltered_cta_ipcs, kernel_ipcs):
    cta_ipcs = []
    # For each kernel
    for i in range(len(unfiltered_cta_ipcs)):
        # For each CTA IPC in each kernel
        for cta_ipc in unfiltered_cta_ipcs[i]:
            # Move to the next kernel when the first IPC within 10% is found
            abs_diff = abs(cta_ipc[2] - kernel_ipcs[i]) / kernel_ipcs[i]
            if abs_diff < 0.1:
                cta_ipcs.append(cta_ipc)
                break

    return cta_ipcs

def main():
    # Get complete paths to all logs
    script, directory, sample_freq = argv
    paths = get_paths(directory)

    # Get data for each file
    stats = []
    for path in paths:
        # Set the path for this dict
        STATS["app_path"] = path

        # Get list of cycles and instructions
        filtered_lines = filter_lines(path)

        # Split into kernels
        split_lines = split_into_kernels(filtered_lines, int(sample_freq))

        # Calculate kernel IPC
        app_cycles = 0
        app_instructions = 0
        kernel_ipcs = []
        unfiltered_cta_ipcs = []
        for k_id in range(len(split_lines["split_cycles"])):
            # Update app cycles and instruction count
            app_cycles += split_lines["split_cycles"][k_id][-1]
            app_instructions += split_lines["split_instructions"][k_id][-1]

            # Calculate kernel IPC
            kernel_ipcs.append(split_lines["split_instructions"][k_id][-1] / split_lines["split_cycles"][k_id][-1])

            # Extract IPC at CTA completion points
            unfiltered_cta_ipcs.append(extract_cta_ipc(split_lines, k_id))

        # Update kernel IPCs
        STATS["kernel_ipcs"] = kernel_ipcs[:]

        # Get the CTA IPCs from the list of all CTA IPCs
        cta_ipcs = filter_cta_ipcs(unfiltered_cta_ipcs, kernel_ipcs)
        STATS["cta_ipcs"] = cta_ipcs[:]

        # Calculate app IPC
        app_ipc = app_instructions / app_cycles

        # Update app IPC
        STATS["app_ipc"] = app_ipc

        # Copy this apps stats to a list
        stats.append(copy.deepcopy(STATS))

    # Dump the output to a json file (easy to load in later)
    with open("data_out.json", 'w') as f:
        json.dump(stats, f)

if __name__ == "__main__":
    main()
