#!/usr/bin/env python3

# INSERTMFVI - module and command line tool for inserting music and
# music-related data into Final Fantasy VI ROMs

# *** READ THIS BEFORE EDITING THIS FILE ***

# This file is part of the mfvitools project.
# ( https://github.com/emberling/mfvitools )
# mfvitools is designed to be used inside larger projects, e.g.
# johnnydmad, Beyond Chaos, Beyond Chaos Gaiden, or potentially
# others in the future.
# If you are editing this file as part of "johnnydmad," "Beyond Chaos,"
# or any other container project, please respect the independence
# of these projects:
# - Keep mfvitools project files in a subdirectory, and do not modify
#   the directory structure or mix in arbitrary code files specific to
#   your project.
# - Keep changes to mfvitools files in this repository to a minimum.
#   Don't make style changes to code based on the standards of your
#   containing project. Don't remove functionality that you feel your
#   containing project won't need. Keep it simple so that code and
#   changes can be easily shared across projects.
# - Major changes and improvements should be handled through, or at
#   minimum shared with, the mfvitools project, whether through
#   submitting changes or through creating a fork that other mfvitools
#   maintainers can easily see and pull from.

import configparser, argparse, sys, shlex, re, os
from copy import copy

try:
    import mml2mfvi
except ImportError:
    from . import mml2mfvi

DEBUG = False
VERBOSE = False

def clean_end():
    print("Processing ended.")
    input("Press enter to close.")
    quit()

def ifprint(text, condition, **kwargs):
    if condition:
        print(text, **kwargs)
        
def inform(*a, **kw):
    if not args.quiet:
        print(*a, **kw)
        
def warning(*a, **kw):
    # this does nothing special, but categorizing console output this way may
    # be useful in the future
    print(*a, **kw)
    
def initialize():
    global HIROM, CONFIG
    global freespace, spoiler, args, remapbrr, offsets
    global MAX_BLOCKS_BASE, EDL_OFFSET, edl
    HIROM = 0xC00000
    CONFIG = configparser.RawConfigParser({
            'free_rom_space': '310600-380000',
            'brrpointers': '53C5F, 53D1B',
            'brrloops': '53D1C, 53D99',
            'brrpitch': '53D9A, 53E17',
            'brradsr': '53E18, 53E95',
            'songpointers': '53E96, 53F94',
            'instruments': '53F95, 54A34',
            'brrpointerpointer': '50222, 50228, 5022E',
            'brrlooppointer': '5041C',
            'brrpitchpointer': '5049C',
            'brradsrpointer': '504DE',
            'songpointerpointer': '50538',
            'instrumentpointer': '501E3',
            'songdata': '85C7A, 9FDFF',
            })
    freespace = None
    spoiler = {}
    args = None
    remapbrr = None
    offsets = {}
    MAX_BLOCKS_BASE = 3746
    EDL_OFFSET = 0x5076A
    edl = None
initialize()

class FreeSpaceError(Exception):
    pass
    
class SampleIDError(Exception):
    pass
    
class Sequence():
    def __init__(self):
        self.filename = None
        self.instfile = None
        self.filetype = None
        self.sequence = None
        self.mml = None
        self.inst = None
        self.variant = None
        self.is_sfx = False
        self.is_long = False
        self.spcrip = False
        self.imports = {}
        self.edl = edl
        
    def init_from_bin(self, fn):
        self.filename = sanitize_path(fn)
        self.filetype = "bin"
        
    def init_from_mml(self, fn, variant=None):
        self.filename = sanitize_path(fn)
        self.variant = variant
        self.filetype = "mml"
        
    def init_from_listfile(self, text):
        text = [s.strip() for s in text.split(',')]
        if not text:
            return None
        self.filename = sanitize_path(text[0])
        if not os.path.isabs(self.filename):
            self.filename = sanitize_path(os.path.join(args.seqpath, self.filename))
        for item in text[1:]:
            item = item.lower()
            value = ""
            if '=' in item:
                item, value = item.split('=')
            if item == "type":
                if value == "bin" or value == "b":
                    self.filetype = "bin"
                elif value == "mml" or value == "m":
                    self.filetype = "mml"
            elif item == "spc":
                self.spcrip = True
            elif item == "inst":
                self.instfile = value
            elif item == "var":
                self.variant = value
        if not self.filetype:
            if self.filename.endswith(".mml"):
                self.filetype = "mml"
            else:
                self.filetype = "bin"
                
    def init_from_virtlist(self, dat):
        fn, var, is_sfx, is_long, mml = dat
        self.filename = sanitize_path(fn)
        self.filetype = "mml"
        self.variant = var
        self.is_sfx = is_sfx
        self.is_long = is_long
        self.mml = mml
        
    def load(self):
        if self.filetype == "bin":
            try:
                with open(self.filename, "rb") as f:
                    self.sequence = f.read()
            except FileNotFoundError:
                try:
                    with open(self.filename + ".bin", "rb") as f:
                        self.sequence = f.read()
                except FileNotFoundError:
                    try:
                        with open(self.filename + "_data.bin", "rb") as f:
                            self.sequence = f.read()
                    except:
                        warning(f"LOADBIN: couldn't open sequence {filename}")
                        self.filetype = None
                        return None
            if self.spcrip:
                self.sequence = int.to_bytes(len(self.sequence), "little") + self.sequence
            instfile = self.instfile
            if not instfile:
                instfile = self.filename
                if instfile.endswith('.bin'):
                    instfile = instfile[:-4]
                if "_data" in instfile:
                    instfile = instfile.replace('_data', '_inst')
                else:
                    instfile += "_inst"
            try:
                with open(instfile, "rb") as f:
                    self.inst = f.read()
            except FileNotFoundError:
                try:
                    with open(instfile + ".bin", "rb") as f:
                        self.inst = f.read()
                        instfile += ".bin"
                except FileNotFoundError:
                    warning(f"LOADBIN: couldn't open inst table {instfile} for sequence {filename}")
                    self.inst = b"\x00" * 32
        elif self.filetype == "mml":
            if self.mml is None:
                try:
                    with open(self.filename, "r") as f:
                        self.mml = f.readlines()
                except FileNotFoundError:
                    try:
                        with open(self.filename + ".mml", "r") as f:
                            self.mml = f.readlines()
                            self.filename += ".mml"
                    except FileNotFoundError:
                        warning(f"LOADMML: couldn't open file {self.filename}")
                        self.filetype = None
            if self.filetype:
                variants = mml2mfvi.get_variant_list(self.mml)
                if self.variant in variants:
                    v = self.variant
                else:
                    v = "_default_"
                    if self.variant:
                        warning(f"LOADMML: variant '{self.variant}' not found in {self.filename}, using default")
                        self.variant = None
                self.imports = mml2mfvi.get_brr_imports(self.mml, variant=v)
                if self.imports:
                    ifprint(f"DEBUG: got imports {self.imports} for {self.filename}", DEBUG)
                self.sequence, self.inst = mml2mfvi.mml_to_akao(self.mml, self.filename, variant=v, sfxmode=self.is_sfx)
                self.edl = mml2mfvi.get_echo_delay(self.mml, variant=v)
                if self.edl is None:
                    self.edl = edl
            
class Sample():
    def __init__(self):
        self.filename = None
        self.brr = None
        self.adsr = None
        self.tuning = None
        self.loop = None
        self.blocksize = None
        self.internalid = None
        self.data_location = None
        
    def init_dummy(self):
        self.filename = "dummy"
        self.brr = b"\x09\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
        self.adsr = b"\xFF\xFF"
        self.tuning = b"\xAC\xAB"
        self.loop = b"\x00\x00"
        self.blocksize = 1
        
    def init_from_listfile(self, text):
        text = [s.strip() for s in text.split(',')]
        if not text:
            return None
        self.filename = sanitize_path(text[0])
        if not os.path.isabs(self.filename):
            self.filename = sanitize_path(os.path.join(args.brrpath, self.filename))
        try:
            looptext = text[1].lower().strip()
        except IndexError:
            looptext = "0000"
            warning(f"SAMPLEINIT: no loop point specified for sample {text[0]}, using 0000")
        try:
            pitchtext = text[2].lower().strip()
        except IndexError:
            pitchtext = "0000"
            warning(f"SAMPLEINIT: no tuning data specified for sample {text[0]}, using 0000")
        try:
            envtext = text[3].lower().strip()
        except IndexError:
            envtext = "ffe0"
            warning(f"SAMPLEINIT: no envelope data specified for sample {text[0]}, using 15/7/7/0")
            
        self.loop = mml2mfvi.parse_brr_loop(looptext)
        self.tuning = mml2mfvi.parse_brr_tuning(pitchtext)
        self.adsr = mml2mfvi.parse_brr_env(envtext)
            
    def init_internal(self, inrom, id):
        self.internalid = id
        
        loc = offsets['brrtable'] + (id-1) * 3
        offset = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
        header = inrom[offset:offset+2]
        length = int.from_bytes(header, "little")
        self.brr = inrom[offset:offset+2+length]
        self.blocksize = len(self.brr) // 9
        
        loc = offsets['loopdata'] + (id-1) * 2
        self.loop = inrom[loc:loc+2]
        loc = offsets['pitchdata'] + (id-1) * 2
        self.tuning = inrom[loc:loc+2]
        loc = offsets['adsrdata'] + (id-1) * 2
        self.adsr = inrom[loc:loc+2]
        
        self.data_location = offset
        ifprint(f"DEBUG: internal sample {id:02X}: {self.blocksize}blk L={self.loop.hex().upper()} T={self.tuning.hex().upper()} E={self.adsr.hex().upper()}", DEBUG)
        
    def init_from_import(self, importinfo, basepath=""):
        self.filename = os.path.join(basepath, sanitize_path(importinfo[0]))
        self.loop = mml2mfvi.parse_brr_loop(importinfo[1])
        self.tuning = mml2mfvi.parse_brr_tuning(importinfo[2])
        self.adsr = mml2mfvi.parse_brr_env(importinfo[3])
        
    def load(self):
        if not self.internalid and not self.brr:
            brr = None
            try:
                with open(self.filename, "rb") as f:
                    brr = f.read()
            except FileNotFoundError:
                try:
                    with open(self.filename + ".brr", "rb") as f:
                        brr = f.read()
                        self.filename += ".brr"
                except FileNotFoundError:
                    try:
                        with open(self.filename.strip(), "rb") as f:
                            brr = f.read()
                            self.filename = self.filename.strip()
                    except FileNotFoundError:
                        try:
                            with open(self.filename.strip() + ".brr", "rb") as f:
                                brr = f.read()
                                self.filename = self.filename.strip() + ".brr"
                        except:
                            warning(f"LOADBRR: couldn't open file {self.filename}")
            if brr:
                if len(brr) % 9 == 2:
                    header = brr[0:2]
                    brr = brr[2:]
                    header_value = int.from_bytes(header, "little")
                    if header_value != len(brr):
                        if header_value % 9 and header_value < len(brr):
                            # looks like an AddmusicK-style loop point header
                            ifprint(f"LOADBRR: Found embedded loop point {header_value:04X} in {self.filename}", VERBOSE)
                            if isinstance(brr.loop, bytes):
                                ifprint(f"         Externally specified loop point {int.from_bytes(brr.loop, 'little'):04X} takes precedence", VERBOSE)
                            else:
                                ifprint(f"         using this", VERBOSE)
                                self.loop = header_value.to_bytes(2, "little")
                if len(brr) % 9:
                    warning(f"LOADBRR: {self.filename}: bad file format")
                    warning("         BRRs must be a multiple of 9 bytes, with optional 2-byte header")
                self.brr = len(brr).to_bytes(2, "little") + brr
                self.blocksize = (len(self.brr) - 2) // 9
                    
def sanitize_path(in_path):
    drive, path = os.path.splitdrive(in_path)
    sep = os.path.sep if (path and path[0] in ['\\', '/']) else ""
    path = path.split('\\')
    path = os.path.join('', *path)
    path = path.split('/')
    path = os.path.join(drive, sep, *path)
    return os.path.normpath(path)
    
def relpath(in_path):
    # NOTE may not produce a valid path, this is for text representation
    if not os.path.isabs(in_path):
        return in_path
    p = os.path.normpath(in_path)
    if hasattr(sys, "_MEIPASS"):
        mei = os.path.normpath(sys._MEIPASS)
        if "_MEI" in os.path.commonprefix([p, mei]):
            r = os.path.relpath(p, start=mei)
            return f"MEI::{r}"
    return os.path.relpath(p)
        
def from_rom_address(addr):
    # NOTE ROM offset 7E0000-7E7FFF and 7F000-7F7FFF are inaccessible.
    # This is not handled by this program and it will treat them like 7E8000, etc
    if addr >= 0xC00000:
        addr -= 0xC00000
    elif addr < 0x400000 and addr >= 0x3E0000:
        addr += 0x400000
    return addr
    
def to_rom_address(addr):
    if addr < 0x400000:
        addr += 0xC00000
    elif addr >= 0x7E0000 and addr < 0x800000:
        addr -= 0x400000
    return addr
    
def byte_insert(data, position, newdata, maxlength=0, end=0):
    while position > len(data):
        data += (b"\x00" * (position - len(data)))
    if end:
        maxlength = end - position + 1
    if maxlength and len(data) > maxlength:
        newdata = newdata[:maxlength]
    return data[:position] + newdata + data[position + len(newdata):]

def int_insert(data, position, newdata, length, reversed=True):
    n = int(newdata)
    l = []
    while len(l) < length:
        l.append(n & 0xFF)
        n = n >> 8
    if n:
        warning(f"WARNING: tried to insert {hex(newdata)} into ${length:X} bytes, truncated")
    if not reversed: l.reverse()
    return byte_insert(data, position, bytes(l), length)

def bytes_to_int(data, reversed=True):
    n = 0
    for i, d in enumerate(data):
        if reversed:
            n = n + (d << (8 * i))
        else:
            n = (n << (8 * i)) + d
    return n
    
def put_somewhere(romdata, newdata, desc, f_silent=False, bank=None):
    global freespace, spoiler
    if freespace is None:
        init_freespace()
    success = False
    if bank is not None:
        min_start = bank * 0x10000
        max_end = bank * 0x10000 + 0x10000
    for i, (start, end) in enumerate(freespace):
        if bank is not None:
            if end < min_start or start > max_end:
                continue
            start = max(start, min_start)
            bank_end = min(end, max_end)
            room = bank_end - start
        else:
            room = end - start
        if room < len(newdata):
            continue
        else:
            romdata = byte_insert(romdata, start, newdata)
            freespace[i] = (start + len(newdata), end)
            if 'ROM Map' not in spoiler: spoiler['ROM Map'] = []
            spoiler['ROM Map'].append("  0x{:x} -- {}".format(start, desc))
            success= True
            break
    if not success:
        if not f_silent:
            warning("ERROR: not enough free space to insert {}\n\n".format(desc))
        raise FreeSpaceError
    return (romdata, start, end)
            
def init_freespace():
    global freespace
    fs = CONFIG.get('DEFAULT', 'free_rom_space').split()
    freespace = []
    while not freespace:
        for t in fs:
            if '-' not in t: continue
            try:
                start, end = [int(n,16) for n in t.split('-')[0:2]]
            except ValueError:
                continue
            if start >= end: continue
            freespace.append((start, end))
        if not freespace:
            #to_default('free_rom_space')
            CONFIG['DEFAULT']['free_rom_space'] = "300000-3FFFFF"
            continue
        break

def free_space(start, end):
    global freespace
    if freespace is None:
        init_freespace()
    freespace.append((start, end))
    
    newfs = []
    for i, (start, end) in enumerate(sorted(freespace)):
        if newfs:
            laststart, lastend = newfs[-1][0], newfs[-1][1]
            if start <= lastend + 1:
                newfs[-1] = (laststart, max(end, lastend))
            else:
                newfs.append((start, end))
        else:
            newfs.append((start, end))
    freespace = newfs

def claim_space(startc, endc):
    global freespace
    if freespace is None: return
    if startc > endc: return
    newfs = []
    for i, (start, end) in enumerate(sorted(freespace)):
        if startc <= start and endc >= end:
            pass
        elif startc <= start and endc >= start:
            newstart = endc+1
            if newstart < end:
                newfs.append((newstart, end))
        elif startc <= end and endc >= end:
            newend = startc-1
            if newend > start:
                newfs.append((start, newend))
        elif startc >= start and endc <= end:
            newend = startc-1
            newstart = endc+1
            if newend > start:
                newfs.append((start, newend))
            if newstart > end:
                newfs.append((newstart, end))
        else:
            newfs.append((start, end))
    freespace = newfs
    
def repr_freespace():
    text = ""
    for f in freespace:
        text += f"{f[0]:06X} - {f[1]:06X} (0x{f[1]-f[0]:X}), "
    return text.rpartition(',')[0]
    
### Testing ASM hack from Myria for per-song EDL loading
def load_edl_hack(outrom):
    global edl_table_address
    
    edl_table = bytes([edl]) * 256
    outrom, edl_table_address, _ = put_somewhere(outrom, edl_table, "EDL Table")
    
    hack = b"\xE2\x30\x9C\x43\x21\x9C\x42\x21\xA6\x01\xBF" + to_rom_address(edl_table_address).to_bytes(3, "little") +  b"\xC2\x10\x8D\x41\x21\xA9\xFC\x8D\x40\x21\xCD\x40\x21\xD0\xFB\x1A\x29\x7F\x85\x1E\xA5\x02\x5C\xA8\x01\xC5"
    outrom, hack_address, _ = put_somewhere(outrom, hack, "EDL Table Hack Code")
    hook = b"\x5C" + to_rom_address(hack_address).to_bytes(3, "little")
    hook_address = 0x501A4
    
    outrom = byte_insert(outrom, hook_address, hook)
    
    inform(f"Myria's EDL Table hack: code is at {hack_address:06X}, table is at {edl_table_address:06X}")
    
    return outrom
    
### Testing basic ASM hack to avoid dangerous behavior in "shadow" lookahead functions
def load_shadow_hack(outrom):
    spcprg_rel_offset = 0x50510
    hackmode = "ffmode"
    
    if hackmode == "safeshadow":
        # Dummy out E3 and F5 commands in shadow command switch
        outrom = byte_insert(outrom, 0x50B06, b"\xEB")
        outrom = byte_insert(outrom, 0x50B0F, b"\xEB")
        inform(f"Safer shadow hack loaded.")
    elif hackmode == "ffmode":
        # Disable E3 and F5 shadowing after E2 is shadowed
        hackblob = b"\x78\xFF\xC5\xF0\x19\x68\xE2\xD0\x03\x8F\xFF\xC5\x68\xE3\xD0\x05\x3F\x25\x17\x2F\xD4\x68\xF5\xD0\x05\x3F\x95\x16\x2F\xCB\x68\xE5\xD0\x05\x3F\xCF\x15\x2F\xC2\x68\xE7\xD0\x0B\x3F\xF3\x15\x2F\xB9\x00\x00\x00\x00\x00\x00"
        outrom = byte_insert(outrom, 0x50B05, hackblob)
        inform(f"Shadow safe mode hack loaded.")
    elif hackmode == "noshadow":
        # Dummy out entire shadow command switch
        outrom = byte_insert(outrom, spcprg_rel_offset + 0x05D4, b"\6F")
        # Add disable slur to jump table
        outrom = byte_insert(outrom, spcprg_rel_offset + 0x18C3, b"\xCF\x15")
        # Add disable roll to jump table
        outrom = byte_insert(outrom, spcprg_rel_offset + 0x18C7, b"\xDE\x15")
        inform(f"No shadowing hack loaded (unsafe??)")
        
    return outrom
    
def remap_brr(outrom, newloc):
    if newloc > 0xFFFF or newloc < 0:
        warning(f"invalid memory offset for remap-BRR: {newloc:04X}, cancelling remap operation")
        return outrom
    if newloc > 0xF500 or newloc < 0x1C26:
        warning(f"WARNING: Memory offset for remap-BRR ({newloc:04X}) is significantly outside expected range. High probability of extreme corruption or game freezes.")
    offset1 = 0x50020
    offset2 = 0x50108
    original1 = int.from_bytes(outrom[offset1:offset1+2], "little")
    original2 = int.from_bytes(outrom[offset2:offset2+2], "little")
    if original1 != original2:
        warning(f"WARNING: remap-BRR: Original ROM's SPC sample memory offsets don't match ({original1:04X} / {original2:04X}). This may mean that a hack was applied to your ROM that isn't compatible with remap-BRR. If so, expect corruption and/or game freezes.")
    newbytes = newloc.to_bytes(2, "little")
    outrom = byte_insert(outrom, offset1, newbytes)
    outrom = byte_insert(outrom, offset2, newbytes)
    
    ## Adjust SFX BRR pointers
    o_ptrblock = 0x52018
    ptrblock = outrom[o_ptrblock:o_ptrblock+0x20]
    new_ptrblock = bytearray()
    for i in range(0x10):
        ptr = int.from_bytes(ptrblock[i*2:i*2+2], "little") - original1 + newloc
        new_ptrblock.extend(ptr.to_bytes(2, "little"))
    outrom = byte_insert(outrom, o_ptrblock, new_ptrblock)
    
    inform(f"SPC sample memory remapped to {newloc:04X}")
    return outrom
    
def max_blocks(edl):
    base = MAX_BLOCKS_BASE    
    brr_ram_size = MAX_BLOCKS_BASE * 9
    brr_ram_size -= (edl - 5) * 0x800
    if remapbrr:
        brr_ram_size += 0x4800 - remapbrr
    return brr_ram_size // 9
    
def insertmfvi(inrom, argparam=None, virt_sample_list=None, virt_seq_list=None, freespace=None, brrpath=None, validate_only=False, quiet=False):
    global args
    global remapbrr
    
    # fill out a dummy argument object so we can proceed without crashing if bypassing command line
    if argparam:
        args = argparam
        purge_original_samples = False
    else:
        initialize()
        args = argparse.Namespace()
        args.quiet = quiet
        args.mmlfiles = None
        args.binfiles = None
        args.listfiles = None
        args.freespace = freespace
        args.o_seqs = None
        args.o_brrs = None
        args.o_meta = None
        args.o_seqtable = None
        args.o_brrtable = None
        args.o_inst = None
        args.pack_metadata = False
        args.pad_samples = True
        args.edl = None
        args.hack = False
        args.hack2 = True
        args.remapbrr = None
        args.brrcount = "0x3F"
        args.brrpath = "samples"
        args.seqpath = ""
        
        purge_original_samples = True
        
    if brrpath:
        args.brrpath = brrpath
    args.seqpath = sanitize_path(args.seqpath)
    args.brrpath = sanitize_path(args.brrpath)
    
    if not args.freespace:
        args.freespace = ["300000-3FFFFF"]
    CONFIG['DEFAULT']['free_rom_space'] = ""
    for fs in args.freespace:
        CONFIG['DEFAULT']['free_rom_space'] += fs + " "

    # Define basic ROM locations (edit for operation on other games)
    spcengine = b"\x20\xC0\xCd\xFF\xBD\xE8\x00\x5D\xAF\xC8\xF0\xD0\xFB\x1A\xC6\xE8"
    offsets['engine'] = 0x50710
    offsets['bgmcount'] = 0x53C5E
    offsets['bgmptrs'] = 0x50539
    offsets['brrptrs'] = 0x50222
    offsets['instptr'] = 0x501E3
    offsets['loopptr'] = 0x5041C
    offsets['pitchptr'] = 0x5049C
    offsets['adsrptr'] = 0x504DE
    
    # Handle header in input ROM
    romheader = b""
    loc = offsets['engine']
    if inrom[loc+0x200:loc+0x200+len(spcengine)] == spcengine:
        romheader = inrom[0:0x200]
        inrom = inrom[0x200:]
        inform("found headered ROM.")
    elif not inrom[loc:loc+len(spcengine)] == spcengine:
        warning("FATAL ERROR: AKAO sound program not found in ROM")
        warning(" Are you sure this is Final Fantasy VI?")
        clean_end()
    else:
        inform("found unheadered ROM.")
        
    outrom = bytearray(inrom)
    
    # Set up data points in input ROM
    loc = offsets["bgmptrs"]
    offsets['bgmtable'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    loc = offsets["instptr"]
    offsets['insttable'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    loc = offsets["brrptrs"]
    offsets['brrtable'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    loc = offsets["loopptr"]
    offsets['loopdata'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    loc = offsets["pitchptr"]
    offsets['pitchdata'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    loc = offsets["adsrptr"]
    offsets['adsrdata'] = from_rom_address(int.from_bytes(inrom[loc:loc+3], "little"))
    
    bgmcount = inrom[offsets['bgmcount']]
    bgmtable_loc = None
    brrtable_loc = None
    inst_loc = None
    remapbrr = None
    try:
        brrcount = int(args.brrcount, 16)
    except ValueError:
        warning(f"BRRCOUNT: invalid value {args.brrcount}, defaulting to 0x3F")
        brrcount = 0x3F
    try:
        if args.o_seqtable:
            bgmtable_loc = int(args.o_seqtable, 16)
    except ValueError:
        warning(f"SEQTABLE: invalid offset value {args.o_seqtable}")
    try:
        if args.o_brrtable:
            brrtable_loc = int(args.o_brrtable, 16)
    except ValueError:
        warning(f"BRRTABLE: invalid offset value {args.o_brrtable}")
    try:
        if args.o_inst:
            inst_loc = int(args.o_inst, 16)
    except ValueError:
        warning(f"INSTTABLE: invalid offset value {args.o_inst}")
    try:
        if args.remapbrr:
            remapbrr = int(args.remapbrr, 16)
    except ValueError:
        warning(f"REMAPBRR: invalid offset value {args.remapbrr}")
        
    ifprint(f"  Number of BGM: {bgmcount} (0x{bgmcount:02X})", VERBOSE)
    ifprint(f"  Number of BRR: {brrcount} (0x{brrcount:02X})", VERBOSE)
    o = {k: hex(v) for k, v in offsets.items()}
    inform()
    
    # Set default EDL
    global edl
    edl = 5
    if args.edl is not None:
        try:
            edl = int(args.edl)
        except ValueError:
            try:
                edl = int(args.edl, 16)
            except ValueError:
                warning("ERROR: EDL must be an integer between 0 and 15.")
        if edl > 15 or edl < 0:
            warning("requested EDL value too high ({args.edl}), leaving original ROM value")
        else:
            outrom[EDL_OFFSET] = edl
        
    edl_table_address = None
    if args.hack:
        outrom = load_edl_hack(outrom)
    if args.hack2:
        outrom = load_shadow_hack(outrom)
    if remapbrr:
        outrom = remap_brr(outrom, remapbrr)
        
    # Load samples from source ROM into sample_defs
    sample_defs = {}
    if not purge_original_samples:
        for i in range(0, brrcount):
            id = i + 1
            sample_defs[id] = Sample()
            sample_defs[id].init_internal(inrom, id)
        
    # Parse list files
    listfiles = configparser.ConfigParser()
    if args.listfiles:
        for fn in args.listfiles:
            try:
                listfiles.read(fn)
            except FileNotFoundError:
                warning(f"LISTFILES: couldn't read {fn}")
            
    sequence_listdefs = {}
    sample_listdefs = {}
    if 'Seq' in listfiles:
        sequence_listdefs.update(listfiles['Seq'])
    if 'Sequences' in listfiles:
        sequence_listdefs.update(listfiles['Sequences'])
    if 'Songs' in listfiles:
        sequence_listdefs.update(listfiles['Songs'])
    if 'Playlist' in listfiles:
        sequence_listdefs.update(listfiles['Playlist'])
    if 'Samples' in listfiles:
        sample_listdefs.update(listfiles['Samples'])
    if 'BRR' in listfiles:
        sample_listdefs.update(listfiles['BRR'])
    if 'BRRs' in listfiles:
        sample_listdefs.update(listfiles['BRRs'])
    if 'Instruments' in listfiles:
        sample_listdefs.update(listfiles['Instruments'])
    if virt_sample_list:
        sample_listdefs.update(virt_sample_list)
        
    ## List format for sequences:
    # -- Header in brackets must be [Seq], [Sequences], [Playlist], or [Songs] (case sensitive)
    # -- ID: filepath, options
    # example: 07: lavos_data.bin, type=b, spc
    # example: 09: tyrano.mml, var=short
    # -- options is a list of comma separated options:
    #       -- type=mml; type=bin; type=m; type=b
    #           sets file type. if not set, files with ".mml" will be loaded as mml and all others as binary.
    #       -- spc
    #           reads binary data with 36 byte header instead of 38. use for data ripped from SPC files or SPC RAM
    #       -- inst=[filename]; e.g. inst=lavos_inst_alt.bin
    #           set instrument table file for binary import. default is same filename as sequence, with '.bin' and '_data' removed if present, and 'inst.bin' appended
    #       -- var=[variant]; variant=[variant]
    #           for MML, use specified variant instead of default.
    sequence_defs = {}
    for id, line in sequence_listdefs.items():
        try:
            id = int(id, 16)
            if id > 0xFF:
                raise ValueError('ID out of range (max 255)')
        except ValueError:
            warning(f"LISTFILES: invalid sequence id {id:02X}")
            continue
        sequence_defs[id] = Sequence()
        sequence_defs[id].init_from_listfile(line)
    
    if virt_seq_list:
        for id, dat in virt_seq_list.items():
            sequence_defs[id] = Sequence()
            sequence_defs[id].init_from_virtlist(dat)
            
    ## List format for samples:
    # same as beyondchaos for now
    # can use headers [Samples], [BRR], [BRRs], [Instruments]
    # also load files while we're at it
    for id, line in sample_listdefs.items():
        try:
            id = int(id, 16)
            if id > 0xFF:
                raise ValueError('ID out of range (max 255)')
        except ValueError:
            warning(f"LISTFILES: invalid sample id {id:02X}")
            continue
        sample_defs[id] = Sample()
        sample_defs[id].init_from_listfile(line)
        sample_defs[id].load()
        
    # Grab MML and seq info from command line
    if args.mmlfiles:
        for fn, id in args.mmlfiles:
            try:
                id = int(id, 16)
                if id > 0xFF:
                    raise ValueError('ID out of range (max 255)')
            except ValueError:
                warning(f"MMLFILES: invalid sequence id {id:02X}")
                continue
            variant = None
            if '?' in fn:
                fn, _, variant = fn.partition('?')
            sequence_defs[id] = Sequence()
            sequence_defs[id].init_from_mml(fn, variant)
    if args.binfiles:
        for fn, id in args.binfiles:
            try:
                id = int(id, 16)
                if id > 0xFF:
                    raise ValueError('ID out of range (max 255)')
            except ValueError:
                warning(f"BINFILES: invalid sequence id {id:02X}")
                continue
            sequence_defs[id] = Sequence()
            sequence_defs[id].init_from_bin(fn)
        
    # Parse all MMLs / load all sequences
    for id, seq in sequence_defs.items():
        if seq is None:
            warning(f"DEBUG: Warning: Sequence {id} undefined")
            continue
        seq.load()
        if seq.filetype:
            varitext = f" ({seq.variant})" if seq.variant else ""
            inform(f"{id:02X}: Loaded {relpath(seq.filename)}{varitext} as {seq.filetype}")
            
    # Traverse sequences and:
    # - Arrange sample files from MML into free ids
    # - Update sequence inst tables based on final sample id layout
    sampleid_queue = [id for id in range(1,256) if id not in sample_defs]
    for id, seq in sequence_defs.items():
        if seq is None:
            continue
        if seq.imports:
            for k, v in seq.imports.items():
                imported = Sample()
                imported.init_from_import(v, basepath=os.path.dirname(seq.filename))
                imported.load()
                if not imported.brr:
                    continue
                
                this_sampleid = None
                is_duplicate = False
                for sid, smp in sorted(sample_defs.items()):
                    if imported.brr == smp.brr:
                        if imported.loop == smp.loop and imported.tuning == smp.tuning and imported.adsr == smp.adsr:
                            inform(f"BRR-FROM-MML: Note: {relpath(seq.filename)} prg0x{k:02X} duplicates existing sample {sid:02X}")
                            this_sampleid = sid
                            break
                        else:
                            is_duplicate = True
                            imported.internalid = sid
                if is_duplicate and not this_sampleid:
                    inform(f"BRR-FROM-MML: Note: {relpath(seq.filename)} prg0x{k:02X} duplicates existing sample {sid:02X} (metadata differs, shadowing in new ID)")
                if this_sampleid is None:
                    if sampleid_queue:
                        this_sampleid = sampleid_queue.pop(0)
                        sample_defs[this_sampleid] = imported
                    elif imported.internalid is None:
                        warning(f"ERROR: Couldn't insert sample {imported.filename}, no IDs left!")
                        raise SampleIDError
                if this_sampleid:
                    seq.inst = byte_insert(seq.inst, (k-0x20)*2, this_sampleid.to_bytes(2, "little"))
                
    # Pad with empty sample entries if option to do so is selected
    if args.pad_samples:
        pad_brr_id = None
        for i in range(1, max(sample_defs.keys())):
            if i not in sample_defs:
                sample_defs[i] = Sample()
                sample_defs[i].init_dummy()
                if pad_brr_id:
                    sample_defs[i].internalid = pad_brr_id
                else:
                    pad_brr_id = i
            
    # Build metadata tables
    looptable, pitchtable, adsrtable = b"", b"", b""
    for k, v in sample_defs.items():
        if v.brr:
            looptable = byte_insert(looptable, (k-1)*2, v.loop)
            pitchtable = byte_insert(pitchtable, (k-1)*2, v.tuning)
            adsrtable = byte_insert(adsrtable, (k-1)*2, v.adsr)
            
    # Check if metadata needs to be moved
    move_metadata = False
    meta_length = len(adsrtable)
    for metatype in ['loopdata', 'pitchdata', 'adsrdata']:
        o = offsets[metatype]
        for k, v in offsets.items():
            if k != metatype and o < v and o + meta_length - 1 >= v:
                ifprint(f"DEBUG: moving metadata because {k} offset {v} intersects {metatype} {o} to {o+meta_length}", DEBUG)
                move_metadata = True
                break
        if move_metadata:
            break
        for v in [a for a in [args.o_seqs, args.o_brrs, args.o_meta] if a is not None]:
            try:
                v = int(v, 16)
            except ValueError:
                warning(f"ERROR: Invalid offset specified ({v})")
                continue
            if v and o < v and o + meta_length - 1 >= v:
                ifprint(f"DEBUG: moving metadata because requested offset {v} intersects {metatype} {o} to {o+meta_length}", DEBUG)
                move_metadata = True
                break
    if move_metadata:
        for metatype in ['loopdata', 'pitchdata', 'adsrdata']:
            o = offsets[metatype]
            free_space(o, o + brrcount * 2)
            
    # Check if sequence or sample tables need to be expanded
    expand_bgm, expand_brr = False, False
    if len(sequence_defs) and max(sequence_defs.keys()) > bgmcount - 1:
        ifprint(f"Sequences will be expanded. (Original sequence count {bgmcount}, new sequence count {max(sequence_defs.keys())+1})", VERBOSE)
        expand_bgm = True
        o = offsets['bgmtable']
        free_space(o, o + bgmcount * 3)
        o = offsets['insttable']
        free_space(o, o + bgmcount * 0x20)
    if len(sample_defs) and max(sample_defs.keys()) > brrcount:
        ifprint(f"Sample table will be expanded. (Original sample count {brrcount}, new sample count {max(sample_defs.keys())+1})", VERBOSE)
        expand_brr = True
        o = offsets['brrtable']
        free_space(o, o + (brrcount) * 3)
        
    # Determine space required for fixed-location items
    metablock_length, seqblock_length, brrblock_length = 0, 0, 0
    meta_loc, sequence_loc, sample_loc = None, None, None
    if args.o_meta:
        if args.pack_metadata:
            metablock_length = meta_length * 3
        else:
            metablock_length = 0x600
        try:
            meta_loc = int(args.o_meta, 16)
        except ValueError:
            warning(f"WARNING: Invalid metadata location '{args.o_meta}'")
        if meta_loc is not None:
            claim_space(meta_loc, meta_loc + metablock_length - 1)
    if args.o_seqs:
        for k, v in sequence_defs.items():
            if v.filetype and v.sequence:
                seqblock_length += len(v.sequence)
    if args.o_brrs:
        for k, v in sample_defs.items():
            if v.brr and not v.internalid:
                brrblock_length += len(v.brr)
            
    if args.o_seqs:
        try:
            sequence_loc = int(args.o_seqs, 16)
        except ValueError:
            warning(f"WARNING: Invalid sequence location '{args.o_seqs}'")
        if sequence_loc is not None:
            claim_space(sequence_loc, sequence_loc + seqblock_length - 1)
    if args.o_brrs:
        try:
            sample_loc = int(args.o_brrs, 16)
        except ValueError:
            warning(f"WARNING: Invalid sample location '{args.o_brrs}'")
        if sample_loc is not None:
            claim_space(sample_loc, sample_loc + brrblock_length - 1)
            
    # Relocate bgm / brr / inst tables
    o_brrtable = offsets['brrtable']
    o_bgmtable = offsets['bgmtable']
    o_insttable = offsets['insttable']
    
    if brrtable_loc or expand_brr:
        new_brrcount = max(sample_defs.keys())
        ifprint(f"DEBUG: BRR expanded from {brrcount} to {new_brrcount}", DEBUG)
        expansion = b"\x00" * (new_brrcount - brrcount)
        brrtable = inrom[o_brrtable : o_brrtable + (brrcount) * 3] + expansion * 3
        
        if brrtable_loc is None:
            ifprint(f"RELOCATION: Free space before inserting 0x{len(brrtable):X} bytes BRR: {repr_freespace()}", DEBUG)
            try:
                outrom, o_brrtable, e = put_somewhere(outrom, brrtable, "BRR sample pointer table", bank=5)
            except FreeSpaceError:
                if not expand_bgm:
                    inform(f"Relocating inst table to make room for BRR pointers..")
                    expand_bgm = True
                    o = offsets['bgmtable']
                    free_space(o, o + bgmcount * 3)
                    o = offsets['insttable']
                    free_space(o, o + bgmcount * 0x20)
                    try:
                        outrom, o_brrtable, e = put_somewhere(outrom, brrtable, "BRR sample pointer table", bank=5)
                    except FreeSpaceError:
                        warning(f"FATAL ERROR: Not enough free space in bank 5 for BRR pointers.")
                        clean_end()
                else:
                    warning(f"FATAL ERROR: Not enough free space in bank 5 for BRR pointers.")
                    clean_end()
            ifprint(f"RELOCATION: New BRR sample pointer table is at 0x{o_brrtable:06X}", VERBOSE)
        else:
            outrom = byte_insert(outrom, brrtable_loc, brrtable)
            o_brrtable = brrtable_loc
            claim_space(brrtable_loc, brrtable_loc + len(brrtable))
            
        o = offsets['brrptrs']
        outrom = int_insert(outrom, o, to_rom_address(o_brrtable), 3)
        outrom = int_insert(outrom, o+6, to_rom_address(o_brrtable+1), 3)
        outrom = int_insert(outrom, o+12, to_rom_address(o_brrtable+2), 3)    
        
    if bgmtable_loc or expand_bgm:
        if len(sequence_defs):
            new_bgmcount = max(bgmcount, max(sequence_defs.keys()) + 1)
        else:
            new_bgmcount = bgmcount
        ifprint(f"DEBUG: BGM expanded from {bgmcount} to {new_bgmcount}", DEBUG)
        expansion = b"\x00" * (new_bgmcount - bgmcount)
        bgmtable = inrom[o_bgmtable : o_bgmtable + bgmcount * 3] + expansion * 3
        insttable = inrom[o_insttable : o_insttable + bgmcount * 0x20] + expansion * 0x20
        
        if bgmtable_loc is None:
            ifprint(f"RELOCATION: Free space before inserting 0x{len(bgmtable):X} bytes BGM: {repr_freespace()}", DEBUG)
            outrom, o_bgmtable, e = put_somewhere(outrom, bgmtable, "BGM sequence pointer table")
            ifprint(f"RELOCATION: New BGM sequence pointer table is at 0x{o_bgmtable:06X}", VERBOSE)
        else:
            outrom = byte_insert(outrom, bgmtable_loc, bgmtable)
            o_bgmtable = bgmtable_loc
            claim_space(bgmtable_loc, bgmtable_loc + len(bgmtable))
        if inst_loc is None:
            outrom, o_insttable, e = put_somewhere(outrom, insttable, "BGM instrument loadout table")
            ifprint(f"RELOCATION: New BGM instrument table is at 0x{o_insttable:06X}", VERBOSE)
        else:
            outrom = byte_insert(outrom, inst_loc, insttable)
            o_insttable = inst_loc
            claim_space(inst_loc, inst_loc + len(insttable))
            
        o = offsets['bgmptrs']
        outrom = int_insert(outrom, o, to_rom_address(o_bgmtable), 3)
        outrom = int_insert(outrom, o+6, to_rom_address(o_bgmtable+1), 3)
        outrom = int_insert(outrom, o+12, to_rom_address(o_bgmtable+2), 3)
        o = offsets['instptr']
        outrom = int_insert(outrom, o, to_rom_address(o_insttable), 3)
        o = offsets['bgmcount']
        outrom = int_insert(outrom, o, new_bgmcount, 1)
        
    # Insert metadata
    if meta_loc or move_metadata:
        if meta_loc is None:
            outrom, o_looptable, e = put_somewhere(outrom, looptable, "BRR instrument loop table")
            outrom, o_pitchtable, e = put_somewhere(outrom, pitchtable, "BRR instrument pitch table")
            outrom, o_adsrtable, e = put_somewhere(outrom, adsrtable, "BRR instrument ADSR table")
        else:
            if args.pack_metadata:
                metablock = looptable + pitchtable + adsrtable
                o_looptable = meta_loc
                o_pitchtable = o_looptable + len(looptable)
                o_adsrtable = o_pitchtable + len(pitchtable)
            else:
                metablock = b"\x00" * 0x600
                metablock = byte_insert(metablock, 0x2, looptable)
                metablock = byte_insert(metablock, 0x202, pitchtable)
                metablock = byte_insert(metablock, 0x402, adsrtable)
                o_looptable = meta_loc + 0x2
                o_pitchtable = meta_loc + 0x202
                o_adsrtable = meta_loc + 0x402
            outrom = byte_insert(outrom, meta_loc, metablock)
            
        inform(f"METADATA: Output ROM table locations: loop {o_looptable:06X}, tuning {o_pitchtable:06X}, envelope {o_adsrtable:06X}")
        for metapointer, metatable in [('loopptr', o_looptable), ('pitchptr', o_pitchtable), ('adsrptr', o_adsrtable)]:
            loc = offsets[metapointer]
            outrom = byte_insert(outrom, loc, to_rom_address(metatable).to_bytes(3, 'little'))
            
    # Insert BRRs and update BRR pointers
    for id, smp in sample_defs.items():
        if smp.internalid or not smp.brr:
            continue
        if sample_loc is None:
            outrom, s, e = put_somewhere(outrom, smp.brr, f"brr {id:02X}: {smp.filename}")
            inform(f"Inserted sample {relpath(smp.filename)} (0x{len(smp.brr):X} bytes | {len(smp.brr)//9} blocks) at ${s:06X}")
        else:
            outrom = byte_insert(outrom, sample_loc, smp.brr)
            s = sample_loc
            inform(f"Inserted sample {relpath(smp.filename)} (0x{len(smp.brr):X} bytes) at ${s:06X}")
            sample_loc += len(smp.brr)
        smp.data_location = s
        
    for id, smp in sample_defs.items():
        if not smp.data_location and smp.internalid:
            if smp.internalid in sample_defs and sample_defs[smp.internalid].data_location:
                    smp.data_location = sample_defs[smp.internalid].data_location
        if smp.data_location:
            loc = o_brrtable + (id-1) * 3
            outrom = byte_insert(outrom, loc, to_rom_address(smp.data_location).to_bytes(3, "little"))
        else:
            warning(f"Error: no sample data location for sample {id} ({smp.filename})")
    
    # Dump BRRs
    if args.dump_brr:
        print("brr dump test")
        brrdump_listfile = "[Samples]\n"
        for id, smp in sample_defs.items():
            fn = outfile + f"_{id:02X}.brr"
            try:
                with open(fn, "wb") as f:
                    f.write(smp.brr)
            except OSError:
                print(f"I/O error: couldn't write to {fn}")
            brrdump_listfile += f"{id:02X}: {fn}, {smp.loop.hex().upper()}, {smp.tuning.hex().upper()}, {smp.adsr.hex().upper()}\n"
        fn = outfile + f"_BRRdump.txt"
        try:
            with open(fn, "w") as f:
                f.write(brrdump_listfile)
            print(f"Wrote BRR dump list to {fn}")
        except OSError:
            print(f"I/O error: couldn't write to {fn}")
                        
    # Insert sequences, sequence pointers, and instrument tables
    validation_results = []
    for id, seq in sequence_defs.items():
        if not seq.sequence:
            continue
        # Warn for:
        #    -- Sequence data overflow
        #    -- Sample overflow in sequence
        valid_seq, valid_smp = True, True
        if len(seq.sequence) >= 0x1002 and not seq.is_long:
            warning(f"WARNING: seq {id:02X} ({relpath(seq.filename)}) is {len(seq.sequence):04X} bytes")
            valid_seq = False
        brr_blocks_used = 0
        for i in range(16):
            if seq.inst[i*2]:
                try:
                    brr_blocks_used += sample_defs[seq.inst[i*2]].blocksize
                except TypeError:
                    pass
        
        # Write seq data
        if sequence_loc is None:
            outrom, s, e = put_somewhere(outrom, seq.sequence, f"seq {id:02X}: {seq.filename}")
            seqtext = f"Inserted sequence {relpath(seq.filename)} (0x{len(seq.sequence):X} bytes) at ${s:06X}"
        else:
            outrom = byte_insert(outrom, sequence_loc, seq.sequence)
            s = sequence_loc
            seqtext = f"Inserted sequence {relpath(seq.filename)} at ${s:06X}"
            sequence_loc += len(seq.sequence)
        
        if brr_blocks_used > max_blocks(seq.edl):
            warning(seqtext)
            warning(f"**OVERFLOW**: Uses {brr_blocks_used} / {max_blocks(seq.edl)} BRR blocks (EDL {seq.edl})")
            valid_smp = False
        else:
            inform(seqtext)
            inform(f"        Uses {brr_blocks_used} / {max_blocks(seq.edl)} BRR blocks (EDL {seq.edl})")
        
        validation_results.append((seq.filename, valid_seq, valid_smp))
        
        # Write seq pointer
        loc = o_bgmtable + id * 3
        outrom = byte_insert(outrom, loc, to_rom_address(s).to_bytes(3, "little"))
        ifprint(f"DEBUG: seq pointer {id:02X} is {to_rom_address(s).to_bytes(3, 'little').hex().upper()} at {loc:06X}", DEBUG)
        
        # Write inst table
        loc = o_insttable + id * 0x20
        outrom = byte_insert(outrom, loc, seq.inst)
        
        # Write EDL table if applicable
        if edl_table_address:
            outrom[edl_table_address + id] = seq.edl

    if validate_only:
        return validation_results
        
    # Reattach header and write ROM
    inform()
    if len(outrom) % 0x10000:
        outrom += b"\x00" * (0x10000 - (len(outrom) % 0x10000))
        
    if len(outrom) > 0x400000:
        if outrom[0xFFD5] == 0x31:
            outrom = byte_insert(outrom, 0xFFD5, b"\x35")
            outrom = byte_insert(outrom, 0xFFD7, b"\x0D")
            outrom = byte_insert(outrom, 0x400000, outrom[0x0000:0xFFFF])
            warning(f"ROM mapping mode changed to ExHIROM")
    if len(outrom) != len(inrom):
        inform(f"ROM file size is now 0x{len(outrom):06X} bytes")
    outrom = romheader + outrom
    
    return outrom
    
if __name__ == "__main__":
    print("mfvitools Music and Instrument Insertion Tool for Final Fantasy VI")
    print()
    
    parser = argparse.ArgumentParser(description="Inserts a specified set of BRR instrument samples into a Final Fantasy VI ROM.")
    filegroup = parser.add_argument_group("File parameters")
    outgroup = parser.add_argument_group("Output file configuration")
    ingroup = parser.add_argument_group("Input file configuration")
    hackgroup = parser.add_argument_group("Additional ROM patches and hacks")
    
    filegroup.add_argument('-i', '--in', help="set input ROM", dest="infile")
    filegroup.add_argument('-o', '--out', help="set output ROM", dest="outfile")
    filegroup.add_argument('-l', '--list', action="append", help="import samples and/or sequences based on an import list file", metavar="FILENAME", dest="listfiles")
    filegroup.add_argument('-m', '--mml', action="append", nargs=2, help="import a single song from an MML file into a specified song id. To load a variant, add the variant name to the filename separated by '?'. ", metavar=("FILENAME[?VARIANT]", "ID"), dest="mmlfiles")
    filegroup.add_argument('-r', '--raw', action="append", nargs=2, help="import a single song from binary files into a specified song id", metavar=("FILENAME", "ID"), dest="binfiles")
    ##TODO import three songs into a Dancing Mad
    ##TODO import a song from MML with SFX
    outgroup.add_argument('-f', '--freespace', action="append", help="define free space in ROM. Data will be placed somewhere in this space if no specific location has been specified for its data type. Hex values. Default is 300000 to 3FFFFF.", metavar="STARTOFFSET-ENDOFFSET")
    outgroup.add_argument('-q', '--sequence', help="set offset (hex) for sequence data written to ROM", metavar="OFFSET", dest="o_seqs")
    outgroup.add_argument('-b', '--brrdata', help="set offset (hex) for BRR data written to ROM", metavar="OFFSET", dest="o_brrs")
    outgroup.add_argument('-a', '--metadata', help="set offset (hex) for instrument metadata written to ROM", metavar="OFFSET", dest="o_meta")
    outgroup.add_argument('-Q', '--seqtable', help="set offset (hex) for sequence pointer table written to ROM", metavar="OFFSET", dest="o_seqtable")
    outgroup.add_argument('-S', '--brrtable', help="set offset (hex) for BRR sample pointer table written to ROM", metavar="OFFSET", dest="o_brrtable")
    outgroup.add_argument('-I', '--inst', help="set offset (hex) for instrument loading tables written to ROM", metavar="OFFSET", dest="o_inst")
    outgroup.add_argument('-c', '--pack_metadata', action="store_true", help="use the minimum possible amount of space for instrument metadata")
    outgroup.add_argument('-P', '--pad_samples', action="store_true", help="fill gaps in sample IDs with dummy data")
    outgroup.add_argument('--quiet', action="store_true", help="disable informational console output, leaving only warnings and errors")
    hackgroup.add_argument('-e', '--edl', help="set echo delay length in output ROM (affects all game audio)")
    hackgroup.add_argument('-H', '--hack', help="add Myria's EDL ASM hack", action='store_true')
    hackgroup.add_argument('-L', '--hack2', help="add safer subroutines hack", action= 'store_true')
    hackgroup.add_argument('-R', '--remapbrr', help="remap SPC memory location for samples (default 4800)", metavar="OFFSET")
    ingroup.add_argument('-B', '--brrcount', default="0x3F", help="define number of instruments contained in source ROM (default: %(default)s)", metavar="NN")
    filegroup.add_argument('-s', '--brrpath', default="", help="define base path for samples loaded from import list files")
    filegroup.add_argument('-p', '--seqpath', default="", help="define base path for sequences loaded from import list files")
    filegroup.add_argument('-d', '--dump-brr', action="store_true", help="dump all samples in final ROM and create a list file for them")
    
    def print_no_file_selected_help():
        print("No actions selected!")
        print("You must specify at least one file to import or action to take.")
        print("File import options:")
        print("    -l FILENAME             List file with sequences and/or samples")
        print("    -m FILENAME ID          MML file, default variant")
        print("    -m FILENAME?VARIANT ID  MML file, specific variant")
        print("    -r FILENAME ID          Binary sequence file")
        print("Other actions:")
        print("    -d                      Dump samples to BRR and list files")    
            
    argv = list(sys.argv[1:])
    while not argv:
        print_no_file_selected_help()
        text_in = input("> ")
        argv += shlex.split(text_in)
    args, unknown = parser.parse_known_args(argv)
    
    while True:
        if args.listfiles or args.mmlfiles or args.binfiles or args.dump_brr:
            break
        print_no_file_selected_help()
        text_in = input("> ")
        argv += shlex.split(text_in)
        args, unknown = parser.parse_known_args(argv)
            
    if args.infile is None:
        print("Enter source ROM filename.")
        print("Default: ff6.smc")
        infile = input(" > ").strip()
        if not infile:
            infile = "ff6.smc"
    else:
        infile = args.infile
    
    try:
        with open(infile, "br") as f:
            inrom = f.read()
    except FileNotFoundError:
        print(f"Error reading file {infile}")
        clean_end()
        
    if args.outfile is None:
        print()
        outfile_default = infile.split('.')
        outfile_default[0] += "_m"
        outfile_default = ".".join(outfile_default)
        print("Enter destination ROM filename.")
        print(f"Default: {outfile_default}")
        outfile = input(" > ").strip()
        if not outfile:
            outfile = outfile_default
    else:
        outfile = args.outfile
    
    print()
    
    outrom = insertmfvi(inrom, argparam=args)
    
    #snip
    
    try:
        with open(outfile, "wb") as f:
            f.write(outrom)
    except OSError:
        print(f"Couldn't write to output file {outfile}")
        clean_end()
    print(f"Wrote to {outfile} successfully.")
    
    clean_end()
    