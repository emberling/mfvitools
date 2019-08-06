#!/usr/bin/env python3

import sys
from mml2akao3 import *

ROMFILE = "ff5test.smc"

ADDRESS = 0x200000
BYTEADR = b"\x00\x00\xE0"

INSTADR = 0x43DAA
PTRADDR = 0x43B97

if len(sys.argv) >= 2:
    MMLFILE = sys.argv[1]
else:
    print("Enter mml file name")
    MMLFILE = input()
    if '.' not in MMLFILE: MMLFILE += ".mml"
    
try:    
    with open(MMLFILE, 'r') as f:
        mml = f.readlines()
        
    variants = mml_to_akao(mml)
    for k, v in variants.items():
        variants[k] = (bytes(v[0],encoding="latin-1"), bytes(v[1],encoding="latin-1"))
    variant_to_use = "akao3" if "akao3" in variants else "_default_"
    data = variants[variant_to_use][0]
    inst = variants[variant_to_use][1]
    
    if len(data) < 0x1000:
        data += b"\x00" * (0x1000 - len(data))
        
    with open(ROMFILE, 'r+b') as f:
        f.seek(ADDRESS)
        f.write(data)
        f.seek(INSTADR)
        f.write(inst)
        f.seek(PTRADDR)
        f.write(BYTEADR)
        
except Exception as e:
    print(e)
    input()
    
input()