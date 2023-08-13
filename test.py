# Development tool to check if and where any changes to mml2mfvi cause changes to output of existing mml files
# Expected directory structure:
#       ./testing/mml2mfvi_ref.py -- reference script, baseline for comparison
#       ./testing/mml2mfvi_alt.py -- altered script
#       ../johnnydmad/custom/ -- location of mml files used for comparison

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
        
    ref = testing.mml2mfvi_ref.mml_to_akao(file)
    alt = testing.mml2mfvi_alt.mml_to_akao(file)
    
    variants = set(ref.keys()).union(set(alt.keys()))
    for v in variants:
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
    
    count += 1
    display = f"[{len(report_lines)}] Testing file {count} of {srccount} -- {source}"
    print(f"{display:80}", end="\r")
    
print("\n\n")
for line in report_lines:
    print(line)
    
print("\n[done.]")
input()
            