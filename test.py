# Development tool to check if and where any changes to mml2mfvi cause changes to output of existing mml files
# Expected directory structure:
#       ./testing/mml2mfvi_ref.py -- reference script, baseline for comparison
#       ./testing/mml2mfvi_alt.py -- altered script
#       ../johnnydmad/custom/ -- location of mml files used for comparison

VERBOSE = False
mmlpath = "../johnnydmad/custom/"

from os import path as ospath
from glob import glob

import testing.mml2mfvi_ref
import testing.mml2mfvi_alt

sourceglob = glob(ospath.join(mmlpath, "**", "*.mml"), recursive=True)

srccount = len(sourceglob)
count = 0

report_lines = []

print()

def report(src, msg):
    report_lines.append(f"{src}: {msg}")

for source in sourceglob:
    with open(source, "r") as f:
        file = f.read()
        
    if VERBOSE:
        print(f"ref: {source}")
    ref = testing.mml2mfvi_ref.mml_to_akao(file)
    if VERBOSE:
        print(f"alt: {source}")
    alt = testing.mml2mfvi_alt.mml_to_akao(file)
    
    variants = set(ref.keys()).union(set(alt.keys()))
    for v in variants:
        # mimic insertmfvi's "init_from_import"
        brr_imports_ref = testing.mml2mfvi_ref.get_brr_imports(file, v)
        for k, importinfo in brr_imports_ref.items():
            importinfo[1] = testing.mml2mfvi_ref.parse_brr_loop(importinfo[1])
            importinfo[2] = testing.mml2mfvi_ref.parse_brr_tuning(importinfo[2])
            importinfo[3] = testing.mml2mfvi_ref.parse_brr_env(importinfo[3])
        brr_imports_alt = testing.mml2mfvi_alt.get_brr_imports(file, v)
        for k, importinfo in brr_imports_alt.items():
            importinfo[1] = testing.mml2mfvi_alt.parse_brr_loop(importinfo[1])
            importinfo[2] = testing.mml2mfvi_alt.parse_brr_tuning(importinfo[2])
            importinfo[3] = testing.mml2mfvi_alt.parse_brr_env(importinfo[3])
        
        pv = "(default)" if v == "_default_" else f"[{v}]"
        if v not in ref.keys():
            report(source, f"Testing produced variant {pv} not found in reference")
        elif v not in alt.keys():
            report(source, f"Testing lacks variant {pv} found in reference")
        else:
            if ref[v][0] != alt[v][0]:
                report(source, f"{pv}: Sequence mismatch")
            if ref[v][1] != alt[v][1]:
                report(source, f"{pv}: Instrument mismatch")
            if brr_imports_ref != brr_imports_alt:
                report(source, f"{pv}: BRR import mismatch")
                if VERBOSE:
                    print(brr_imports_ref)
                    print()
                    print(brr_imports_alt)
                    print()
    
    count += 1
    display = f"[{len(report_lines)}] Tested file {count} of {srccount} -- {source}"
    if VERBOSE:
        print(f"{display:80}", end="\n")
    else:
        print(f"{display:80}", end="\r")
    
print("\n\n")
for line in report_lines:
    print(line)
    
print("\n[done.]")
input()
            