# Development tool to check if and where any changes to mml2mfvi cause changes to output of existing mml files
# Expected directory structure:
#       ./testing/mml2mfvi_ref.py -- reference script, baseline for comparison
#       ./testing/mml2mfvi_alt.py -- altered script
#       ../johnnydmad/custom/ -- location of mml files used for comparison

VERBOSE = True
mmlpath = "../johnnydmad/custom/"

from os import path as ospath
from glob import glob
from difflib import diff_bytes, unified_diff
from contextlib import redirect_stdout

import testing.mml2mfvi_ref
import testing.mml2mfvi_alt
from mfvi2mml import akao_to_mml

sourceglob = glob(ospath.join(mmlpath, "**", "*.mml"), recursive=True)

srccount = len(sourceglob)
count = 0

report_lines = []

print()

def report(src, msg):
    report_lines.append(f"{src}: {msg}")

def report_diff_bytes(generator):
    for line in generator:
        if line.startswith(b"---") or line.startswith(b"+++") or line.startswith(b"@"):
            report_line = str(line, encoding="utf-8")
        else:
            report_line = str(line[0:1], encoding="utf-8")
            for byte in line[1:]:
                report_line += f" {byte:02X}"
        report_lines.append(f"    {report_line}")
        
def report_diff_str(generator):
    for line in generator:
        #report_lines.append(f"    {line}")
        print(line)
        
def linify(blob):
    output = []
    while len(blob) > 16:
        output.append(blob[:16])
        blob = blob[16:]
    output.append(blob)
    return output
    
def split_mml(mml):
    output = []
    for line in mml:
        sublines = line.split('\n')
        for sl in sublines:
            while len(sl) > 75:
                output.append(sl[:75] + "...")
                sl = " ..." + sl[75:]
            output.append(sl)
    output = [line for line in output if not line.isspace()]
    return output

def diff_mml(mml_ref, mml_alt):
    def tokenize_mml_line(line):
        output = []
        token = ""
        for i in range(len(line)):
            if token == "" or token == "%" or line[i] in "1234567890,-":
                token += line[i]
            else:
                output.append(token)
                token = line[i]
        output.append(token)
        return output
    
    def split_at_returns(lines):
        output = []
        for line in lines:
            split_line = line.split('\n')
            output.extend(split_line)
        return output
        
    def equalize_lists(first, second):        
        while len(first) < len(second):
            first.append("")
        while len(first) > len(second):
            second.append("")
        
    def make_diff_text(reftok, alttok, hpos, vpos):
        danger = "Prob. OK"
        if sorted(reftok) != sorted(alttok):
            danger = "WARNING"
        if VERBOSE:
            text = f"[{danger}] At {vpos}: {hpos}: {''.join(reftok)} --> {''.join(alttok)}\n"
            line_ref = tokenize_mml_line(mml_ref[vpos])
            line_alt = tokenize_mml_line(mml_alt[vpos])
            equalize_lists(line_ref, line_alt)
            text += f"-- {''.join(line_ref[:hpos])} --> {''.join(reftok)} <-- {''.join(line_ref[hpos+len(reftok):])}\n"
            text += f"++ {''.join(line_alt[:hpos])} --> {''.join(alttok)} <-- {''.join(line_alt[hpos+len(alttok):])}"
        else:
            text = f"[{danger}] At {vpos}: {hpos}: {''.join(reftok)} --> {''.join(alttok)}"
        # text = f"[{danger}] At {vpos}: {hpos}: {''.join(reftok)} --> {''.join(alttok)}\nRef: {mml_ref[vpos]}\nAlt: {mml_alt[vpos]}"
        return text
        
    diffs = []
    mml_ref = split_at_returns(mml_ref)
    mml_alt = split_at_returns(mml_alt)
    equalize_lists(mml_ref, mml_alt)
    
    for i in range(len(mml_ref)):
        line_ref = tokenize_mml_line(mml_ref[i])
        line_alt = tokenize_mml_line(mml_alt[i])
        equalize_lists(line_ref, line_alt)
        
        ref_tokens = []
        alt_tokens = []
        diffpos = None
        for hpos in range(len(line_ref)):
            if line_ref[hpos] != line_alt[hpos]:
                if diffpos is None:
                    diffpos = hpos
                ref_tokens.append(line_ref[hpos])
                alt_tokens.append(line_alt[hpos])
            elif diffpos is not None:
                diffs.append(make_diff_text(ref_tokens, alt_tokens, diffpos, i))
                diffpos = None
                ref_tokens = []
                alt_tokens = []
        if diffpos is not None:
            diffs.append(make_diff_text(ref_tokens, alt_tokens, diffpos, i))
    
    report_lines.extend(diffs)
                
for source in sourceglob:
    with open(source, "r") as f:
        file = f.read()
        
    #if VERBOSE:
    #    print(f"ref: {source}")
    ref = testing.mml2mfvi_ref.mml_to_akao(file)
    #if VERBOSE:
    #    print(f"alt: {source}")
    alt = testing.mml2mfvi_alt.mml_to_akao(file)
    
    variants = set(ref.keys()).union(set(alt.keys()))
    for v in variants:
        pv = "(default)" if v == "_default_" else f"[{v}]"
        
        # check vs. calling mml_to_akao with a specific variant
        specific_variant_ref = testing.mml2mfvi_ref.mml_to_akao(file, variant=v)
        specific_variant_alt = testing.mml2mfvi_alt.mml_to_akao(file, variant=v)
        if ref[v] != specific_variant_ref:
            report(source, f"{pv}: Mismatch between reference process(variant={v}) and process()[{v}]")
        if alt[v] != specific_variant_alt:
            report(source, f"{pv}: Mismatch between alternate process(variant={v}) and process()[{v}]")
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
        
        if v not in ref.keys():
            report(source, f"Testing produced variant {pv} not found in reference")
        elif v not in alt.keys():
            report(source, f"Testing lacks variant {pv} found in reference")
        else:
            if ref[v][0] != alt[v][0]:
                report(source, f"{pv}: Sequence mismatch")
                if VERBOSE:
                    with redirect_stdout(None):
                        ref_mml = akao_to_mml(ref[v][0], ref[v][1])
                        alt_mml = akao_to_mml(alt[v][0], alt[v][1])
                    #diff = unified_diff(split_mml(ref_mml), split_mml(alt_mml))
                    #report_diff_str(diff)
                    diff_mml(ref_mml, alt_mml)
            if ref[v][1] != alt[v][1]:
                report(source, f"{pv}: Instrument mismatch")
                if VERBOSE:
                    diff = diff_bytes(unified_diff, linify(ref[v][1]), linify(alt[v][1]))
                    report_diff_bytes(diff)
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
        #print(f"{display:80}", end="\n")
        print(f"{display:80}", end="\r")
    else:
        print(f"{display:80}", end="\r")
    
print("\n\n")
for line in report_lines:
    print(line)
    
print("\n[done.]")
input()
            