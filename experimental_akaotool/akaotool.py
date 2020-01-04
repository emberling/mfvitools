#!/usr/bin/env python3
from hashlib import md5
from pubsub import pub
from copy import copy, deepcopy
from collections import namedtuple
import configparser, os, base64

file_target = "ff6ti.smc"

offset_default = {
    "bgmcount": 0x53C5E,
    "bgmptrs": 0x50539,
    "brrptrs": 0x50222,
    "instptr": 0x501E3,
    "loopptr": 0x5041C,
    "pitchptr": 0x5049C,
    "adsrptr": 0x504DE
    }
offset = copy(offset_default)

bgm_names = {}
bgmid_names = {}
imetadata = {}
gc = {}
db = None

class Bgm:
    def __init__(self, rom, id):
        loc = offset["bgmlist"] + id * 3
        self.offset = read_int(rom[loc:loc+3])
        self.length = read_int(rom[self.offset:self.offset+2])
        self.data = rom[self.offset+2:self.offset+2+self.length]
        self.hash = str(base64.b64encode(md5(self.data).digest()), "ascii").rstrip('=')
        loc = offset["inst"] + id * 0x20
        #self.inst = inst_set(rom[loc:loc+0x20])
        self.set_binary_inst(rom[loc:loc+0x20])
        
        self.name = None
        
    def get_name(self):
        if self.name:
            if self.name.startswith("<seq ") and self.name.endswith(">"):
                self.name = None
        if self.name:
            return self.name
        elif self.hash in bgm_names:
            return bgm_names[self.hash]
        else:
            return "<seq {}>".format(self.hash)
            
    def get_binary_inst(self):
        ret = bytearray()
        for i in self.inst:
            ret.append(i & 0xFF)
            ret.append(i >> 8)
        return ret

    def set_binary_inst(self, dat):
        instruments = []
        while len(dat) <= 0x20:
            dat += bytes(1)
        for i in range(0,16):
            instruments.append(read_int(dat[i*2:i*2+2]))
        self.inst = instruments
        return instruments
        
    def set_data(self, dat, name_fallback=""):
        self.data = dat
        self.length = len(dat)
        self.hash = str(base64.b64encode(md5(self.data).digest()), "ascii").rstrip('=')
        if self.hash in bgm_names:
            self.name = bgm_names[self.hash]
        else: self.name = name_fallback
        
    def get_full_data(self):
        #data with header
        #2 length bytes in AKAO3/4, maybe others
        #will need to be flexible for Suzuki, which puts inst data in header
        
        if gc['dialect'].startswith("SUZUKI"):
            return self.data #TODO
        else:
            #AKAO3, AKAO4 - two byte length header
            return write_int(self.length, 2) + self.data
        
class Instrument:
    def __init__(self, rom=None, id=None):
        if rom is None or id is None:
            self.offset = None
            self.length = 0
            self.data = None
            self.hash = None
            self.adsr = 0
            self.pitch = 0
            self.loop = 0
            self.is_looped = False
            self.name = "----" if id is None else "index error"
            return
            
        loc = offset["brrlist"] + id * 3
        self.offset = read_int(rom[loc:loc+3])
        self.length = read_int(rom[self.offset:self.offset+2])
        self.data = rom[self.offset+2:self.offset+2+self.length]
        self.hash = str(base64.b64encode(md5(self.get_unlooped()).digest()), "ascii").rstrip('=')
        loc = offset["adsrdata"] + id * 2
        self.adsr = read_int(rom[loc:loc+2], invert=False)
        loc = offset["pitchdata"] + id * 2
        self.pitch = read_int(rom[loc:loc+2], invert=False)
        loc = offset["loopdata"] + id * 2
        self.loop = read_int(rom[loc:loc+2], invert=False)
        self.is_looped = True if self.data[self.length-9] & 0b10 else False
        
        self.name = None
        
    def set_data(self, dat, name_fallback=""):
        if len(dat) % 9:
            if len(dat) % 9 != 2:
                warn("Warning: BRR length not multiple of 9")
            else:
                head = dat[:2]
                dat = dat[2:]
                if read_int(head) < len(dat):
                    print(f"header {head:04X} < size ({len(dat):04X}, interpreting as loop point")
                    self.loop = read_int(head, invert=False)
        # trim data after BRR endpoint
        full = bytearray(dat)
        found = False
        i = 0
        dat = b""
        while i < len(full) and not found:
            chunk = full[i:i+9]
            i += 9
            dat += chunk
            if chunk[0] & 0b1:
                if len(dat) < len(full):
                    warn(f"truncated to ${len(dat):X} bytes (was ${len(full):X} -- found early BRR end bit")
                found = True
                break
        if not found:
            warn("warning: no BRR endpoint found in import data. adding..")
            dat[len(dat)-9] |= 0b1
                
        self.data = dat
        self.length = len(dat)
        self.hash = str(base64.b64encode(md5(self.get_unlooped()).digest()), "ascii").rstrip('=')
        self.is_looped = True if self.data[self.length-9] & 0b10 else False
        if self.hash in imetadata:
            db.imetadata[self.hash] = imetadata[self.hash]
        else:
            db.imetadata[self.hash] = InstrumentMetadata(self.hash)
        db.purge_unused_metadata()
        
    def get_unlooped(self):
        if self.data and len(self.data) >= 9:
            ret = self.data[0:self.length-9]
            ret += bytes([self.data[self.length-9] & 0b11111101])
            ret += self.data[self.length-8:]
            return ret
        else:
            return self.data
            
    def get_looped(self):
        if self.data and len(self.data) >= 9:
            ret = self.data[0:self.length-9]
            ret += bytes([self.data[self.length-9] | 0b00000010])
            ret += self.data[self.length-8:]
            return ret
        else:
            return self.data
            
    def set_loop_state(self, toggle):
        if toggle:
            self.data = self.get_looped()
        else:
            self.data = self.get_unlooped()
        self.is_looped = toggle
            
    def get_blocksize(self):
        if not self.length: return 0
        return int(self.length / 9)
        
    def get_full_data(self):
        return write_int(self.length, 2) + self.data if self.data else b""
        
    def get_loop_point(self):
        #TODO don't invert if suzuki
        lp = (self.loop >> 8) + ((self.loop & 0xFF) << 8)
        return lp
        
    def set_loop_point(self, val):
        #TODO don't invert if suzuki
        self.loop = (val >> 8) + ((val & 0xFF) << 8)
        
class InstrumentMetadata:
    def __init__(self, hash=None):
        self.name = "<brr {}>".format(hash) if hash else None
        self.hash = hash
        self.color = (224,224,224)
        self.category = 0 if self.hash else -1
        self.is_tone = True
        self.octave = 5
        self.midival = 0
        
    def get_name(self):
        if self.name:
            if self.name.startswith("<brr ") and self.name.endswith(">"):
                self.name = None
        if self.name:
            return self.name
        #elif self.hash in bgm_names:
        #    return bgm_names[self.hash]
        else:
            return "<brr {}>".format(self.hash)
    
    def parse(self, entry):
        self.hash, st = entry
        sp = [s.strip() for s in st.split('|')]
        if len(sp) < 1:
            self.name = None
        else:
            self.name = sp[0].strip()
        try:
            color = [s.strip() for s in sp[1].split()]
            self.color = (int(color[0]), int(color[1]), int(color[2]))
        except (IndexError, ValueError):
            self.color = (240, 240, 240)
        try:
            vars = [s.strip() for s in sp[2].split()]
            self.is_tone = True if int(vars[0]) else False
            self.octave = int(vars[1])
            self.category = int(vars[2])
        except (IndexError, ValueError):
            self.is_tone = True
            self.octave = 5
            self.category = 0
        
    def unparse(self):
        return "{:25} | {:3} {:3} {:3} | {} {} {} {}".format(
            self.name,
            self.color[0],
            self.color[1],
            self.color[2],
            (1 if self.is_tone else 0),
            self.octave,
            self.category,
            self.midival)
            
class Database:
    def __init__(self):
        global bgm_names
        
        cp = configparser.ConfigParser()
        cp.optionxform = str #make case sensitive
        cp.read(dat('tracknames'))
        cp.read(dat('tracknames_custom'))
        bgm_names = dict(cp['TrackNames'].items())
        
        self.imetadata = {}
        build_imeta_db()
        self.gc = {} #game config
        self.dm, self.dmb = DataManager(), DataManager()
        
        pub.subscribe(self.process_new_file, "newFile")

    def set_bgm_data(self, idx, dat, name_fallback=""):
        self.bgms[idx].set_data(dat, name_fallback=name_fallback)
        self.dm.revise(bgmidx(idx), size=len(self.bgms[idx].get_full_data()), offset=self.bgms[idx].offset)
        
    def set_brr_data(self, idx, dat, name_fallback=""):
        self.instruments[idx].set_data(dat, name_fallback=name_fallback)
        self.dm.revise(insidx(idx), size=len(self.instruments[idx].get_full_data()), offset=self.instruments[idx].offset)
        
    def get_imeta(self, param):
        if type(param) is int:
            hash = self.instruments[param].hash
        else:
            hash = param
        if hash not in self.imetadata:
            self.imetadata[hash] = InstrumentMetadata(hash)
        return self.imetadata[hash]
            
    def has_imeta(self, idx):
        if self.instruments[idx].hash in self.imetadata: return True
        if self.instruments[idx].hash in imetadata: return True
        return False
        
    def purge_unused_metadata(self):
        used_hashes = set([i.hash for i in self.instruments if i is not None])
        for h in list(self.imetadata.keys()):
            if h not in used_hashes:
                print(f"found unused imeta {h}")
                self.imetadata.pop(h)
                
    def save_meta(self):
        global bgm_names
        mcp = configparser.ConfigParser()
        mcp.optionxform = str #make case sensitive
        mcp.read(dat("tracknames"))
        mcp.read(dat("tracknames_custom"))
        if not mcp.has_section("TrackNames"):
            mcp.add_section("TrackNames")
        for bgm in self.bgms:
            #print("{}: {}".format(bgm.hash, bgm.name))
            if bgm.name: mcp['TrackNames'][bgm.hash] = bgm.name
        bgm_names = dict(mcp['TrackNames'].items())
        
        icp = configparser.ConfigParser()
        icp.optionxform = str #make case sensitive
        icp.read(dat("instruments_custom"))
        if not icp.has_section("InstrumentMetadata"):
            icp.add_section("InstrumentMetadata")
        for entry in self.imetadata.values():
            if entry.hash and entry.name:
                icp['InstrumentMetadata'][entry.hash] = entry.unparse()
        try:
            with open(dat("tracknames_custom"), "w") as f:
                mcp.write(f)
            with open(dat("instruments_custom"), "w") as f:
                icp.write(f)
            pub.sendMessage("sendStatus", text="Metadata saved.")
        except IOError:
            pub.sendMessage("sendStatus", text="Failed to save metadata.")
            warn("I/O error")
            
    def write_changes(self):
        #TODO: make tables movable
        #TODO: save changes to adsr, pitch, loop
        
        #Make sure nothing overlaps & everything fits
        self.dm.make_valid()

        #Out with the old
        for b in self.dmb.bounds:
            blank = b"\00" * (b.end-b.start+1)
            print(f"Wiping", end='  ')
            self.rom = splice(self.rom, blank, b.start)
        
        #Write BGM data & instrument sets
        inst, bgmlist = b"", b""
        for idx, bgm in enumerate(self.bgms):
            didx = f"BGM{idx:02X}"
            print(f"Inserting BGM data", end='  ')
            self.rom = splice(self.rom, bgm.get_full_data(), self.dm.get_offset(didx))
            #add alternate inst format (SUZUKI) handling here
            inst += bgm.get_binary_inst()
            bgmlist += write_int(self.dm.get_offset(didx), 3)
        print("Inserting BGM pointer list", end='  ')
        self.rom = splice(self.rom, bgmlist, offset["bgmlist"])
        print("Inserting instrument sets for BGM", end='  ')
        self.rom = splice(self.rom, inst, offset["inst"])
        
        #Write inst BRR data
        brrlist = b""
        for idx, brr in enumerate(self.instruments):
            if self.instruments[idx].offset is not None:
                didx = f"INS{idx-1:02X}"
                print("Inserting BRR data", end='  ')
                self.rom = splice(self.rom, brr.get_full_data(), self.dm.get_offset(didx))
                brrlist += write_int(self.dm.get_offset(didx), 3)
        print("Inserting BRR pointer list", end='  ')
        self.rom = splice(self.rom, brrlist, offset["brrlist"])
        
        #Write inst metadata
        pitch, env, loop = b"", b"", b""
        for idx, ins in enumerate(self.instruments):
            if self.instruments[idx].offset is not None:
                pitch += write_int(ins.pitch, 2, invert=False)
                env += write_int(ins.adsr, 2, invert=False)
                loop += write_int(ins.loop, 2, invert=False)
        #TODO this should be using the datamanager & should be movable
        self.rom = splice(self.rom, pitch, offset["pitchdata"])
        self.rom = splice(self.rom, env, offset["adsrdata"])
        self.rom = splice(self.rom, loop, offset["loopdata"])
        
        #End at complete bank
        rem = len(self.rom) % 0x10000
        print(f"rom length {len(self.rom):06X} - remainder {rem:X}")
        if rem:
            self.rom += (0x10000-rem) * b"\x00"
        print(f"rom length {len(self.rom):06X}")
        #Set new reversion point
        self.dmb = deepcopy(self.dm)
        
    def process_new_file(self, rom, file):
        global bgmid_names
        global offset
        global gc, db
        
        # set some things back to default or empty
        self.imetadata = {}
        build_imeta_db()
        self.dm = DataManager()
        db = self
        
        # global operations
        game = identify_game(rom)
        if not game:
            warn("File not recognized as SNES ROM")
            return
        self.gamemode, self.header, self.hirom = game
        
        self.header_data = b""
        if self.header:
            self.header_data = rom[0:0x200]
            rom = rom[0x200:]
        
        # set game specific settings
        offset = copy(offset_default)
        resolve_pointers(rom, self.gamemode)
        
        cp = configparser.ConfigParser()
        cp.read(dat('gameinfo'))
        mode_params = cp['Mode'+self.gamemode]
        gc = {}
        for k, v in mode_params.items():
            if k not in offset:
                v = v.strip()
                try:
                    if v.startswith("0x") and len(v) > 2:
                        gc[k] = int(v[2:], 16)
                    else:
                        gc[k] = int(v)
                except ValueError:
                    if v == "True": gc[k] = True
                    elif v == "False": gc[k] = False
                    elif v == "None": gc[k] = None
                    else: gc[k] = v
        self.gc = gc
        
        # **BGM operations**
        
        #load vanilla names for each bgm-id
        cp = configparser.ConfigParser()
        cp.read(dat('tracknames'))
        bgmid_names = {}
        if 'IDNames'+self.gamemode in cp:
            for id, name in cp['IDNames'+self.gamemode].items():
                try:
                    idx = int(id,16)
                except ValueError:
                    continue
                bgmid_names[idx] = name
        
        #figure out bgmcount if not specified directly
        if not offset["bgmcount"]:
            #self.bgmcount = (offset["brrlist"] - offset["bgmlist"]) // 3
            #print("BRR {:06X} - BGM {:06X} = # {:X}".format(offset["brrlist"], offset["bgmlist"], self.bgmcount))
            order = [(offset["bgmlist"], "bgmlist"),
                     (offset["brrlist"], "brrlist"),
                     (offset["inst"], "inst"),
                     (offset["loopdata"], "loopdata"),
                     (offset["pitchdata"], "pitchdata"),
                     (offset["adsrdata"], "adsrdata")]
            order = sorted(order, key=lambda x: x[0])
            for i, o in enumerate(order):
                if o[1] == "bgmlist":
                    self.bgmcount = (order[i+1][0] - o[0]) // 3
                    break
                elif o[1] == "inst":
                    self.bgmcount = (order[i+1][0] - o[0]) // 0x20
                    break
        else:
            self.bgmcount = rom[offset["bgmcount"]]
        
        #add bgms to db
        self.bgms = []
        for sid in range(0,self.bgmcount):
            bgm = Bgm(rom, sid)
            self.bgms.append(bgm)
            self.dm.allocate_fast(bgm.offset, bgm.offset+bgm.length+1)
            self.dm.register(f"BGM{sid:02X}", bgm.length+2, bgm.offset)
            
        #for bgm in self.bgms: #temp
        #    print(bgm.hash)
        
        # instrument operations
        brrcount = 255
        metaptrs = sorted([offset["adsrdata"], offset["pitchdata"], offset["loopdata"]])
        brrcount = int(min((brrcount, (metaptrs[1]-metaptrs[0])/2, (metaptrs[2]-metaptrs[1])/2)))
        print(brrcount)
        adsrdata = rom[offset["adsrdata"]:offset["adsrdata"]+(brrcount*2)]
        pitchdata = rom[offset["pitchdata"]:offset["pitchdata"]+(brrcount*2)]
        loopdata = rom[offset["loopdata"]:offset["loopdata"]+(brrcount*2)]
        brrlist = rom[offset["brrlist"]:offset["brrlist"]+(brrcount*3)] 
        for idx in range(0,brrcount):
            # valid instruments have ADSR MSB = 1
            adsr = read_int(adsrdata[idx*2:idx*2+2])
            loop = read_int(loopdata[idx*2:idx*2+2])
            pitch = read_int(pitchdata[idx*2:idx*2+2])
            brr_addr = read_int(brrlist[idx*3:idx*3+3])
            brr_len = read_int(rom[brr_addr:brr_addr+2])
            
            if (adsr == 0 or adsr == 0xFFFF) and (loop == 0 or loop == 0xFFFF) and (pitch == 0 or pitch == 0xFFFF):
                brrcount = idx
                break
            if adsrdata[idx*2] <= 0x80:
                brrcount = idx
                break
            # valid instruments have sample length & loop point multiple of 9
            brr_addr = read_int(brrlist[idx*3:idx*3+3])
            brr_len = read_int(rom[brr_addr:brr_addr+2])
            if brr_len % 9:
                brrcount = idx
                break
            brr_end = rom[brr_addr + 2 + brr_len - 9]
            if brr_end & 0b10:    # loop flag set
                if loop % 9:
                    brrcount = idx
                    #break
                    #temporarily?? disabled due to too many false positives
        self.brrcount = brrcount            
        print(brrcount)
        
        self.instruments = [Instrument()]
        for iid in range(self.brrcount):
            inst = Instrument(rom, iid)
            self.instruments.append(inst)
            self.dm.allocate_fast(inst.offset, inst.offset+inst.length+1)
            self.dm.register(f"INS{iid:02X}", inst.length+2, inst.offset)
            if inst.hash not in self.imetadata:
                if inst.hash in imetadata:
                    self.imetadata[inst.hash] = imetadata[inst.hash]
                else:
                    self.imetadata[inst.hash] = InstrumentMetadata(inst.hash)
        for iid in range(self.brrcount+1,256):
            self.instruments.append(Instrument())
        
#            self.dm.allocate_fast(bgm.offset, bgm.offset+bgm.length+1)
#            self.dm.register(f"BGM{sid:02X}", bgm.length+2, bgm.offset)
        #print(self.dm)
        #print("--------------------------------------------")
        #self.dm.cleanup_bounds()
        #print(self.dm)
        
#        for i, ins in enumerate(self.instruments):
#            print("{:2X} {}".format(i, ins.hash))
            
        # finalize
        self.filepath, self.filename = file
        self.rom = rom
        self.dmb = deepcopy(self.dm)
            
        pub.sendMessage("newFileLoaded")

# keep a deepcopied database from the last save or load ROM event
# on saving, use the backup's datamanager to find which areas to zero out
DataBlock = namedtuple('DataBlock', ['offset', 'size'])
Bound = namedtuple('Bound', ['start', 'end'])
class DataManager:    
    def __init__(self):
        self.registry = {}
        self.bounds = set()
        
    def __repr__(self):
        r = "Bounds (Space allocated for this datamanager's use):\n"
        for b in sorted(self.bounds):
            r += f"    {b.start:06X} to {b.end:06X}\n"
        r += "Registry (Space currently in use):\n"
        for k, d in self.registry.items():
            r += f"    {d.offset:06X} to {d.offset+d.size-1:06X} as {k}\n"
        return r
        
    def get_offset(self, id):
        return self.registry[id].offset
        
    def get_size(self, id):
        return self.registry[id].size
        
    def register(self, id, size, offset=None):
        if offset is None:
            offset = self.find_empty_space(size)
        self.registry[id] = DataBlock(offset, size)
        
    def revise(self, id, size=None, offset=None):
        if size is None: size = self.registry[id].size
        self.clear(id)
        if offset is None: offset = self.find_empty_space(size)
        self.register(id, size, offset)
        
    def clear(self, id):
        self.registry.pop(id)
        
    def make_valid(self, cascade=False):
        if cascade:
            new = DataManager()
            for k, v in sorted(self.registry.items()):
                #TODO should be using a user set dict to determine sort order
                new.register(k, v.size, v.offset)
            self.registry = new.registry
        else:
            sr = sorted(self.registry.items(), key=lambda x: x[1])
            for i, (k, v) in enumerate(sr):
                #print(f"({i}) Checking validity of {k} ({v.offset:06X},{v.size:X}) ", end="")
                try: nxt=sr[i+1][1]
                except IndexError: nxt=None
                if not self.is_valid(k, next=nxt):
                    self.revise(k, v.size)
                    #print("~",end='')
                #print(f"--> {self.registry[k].offset:06X} {self.registry[k].size:X}")
                    
    def is_valid(self, id, next=None):
        this = self.registry[id]
        if next is not None:
            if this.offset >= next.offset: return False
            if this.offset+this.size > next.offset: return False
        within_bounds = False
        for b in self.bounds:
            if this.offset >= b.start and this.offset+this.size-1 <= b.end:
                within_bounds = True
                break
        if not within_bounds: return False
        if next is None:
            for k, o in sorted(self.registry.items()):
                if k == id: continue
                if this.offset < o.offset and this.offset+this.size-1 >= o.offset:
                    #print(f"{this.offset:06X} < {o.offset:06X} and {this.offset+this.size-1:06X} >= {o.offset:06X}")
                    return False
                if o.offset < this.offset and o.offset+o.size-1 >= this.offset+this.size-1:
                    #print(f"{o.offset:06X} < {this.offset:06X} and {o.offset+o.size-1:06X} >= {this.offset+this.size-1:06X}")
                    return False
        return True
    
    def cleanup_bounds(self):
        old_bounds = sorted(self.bounds)
        clean_bounds = set()
        this_start, this_end = None, None
        for ostart, oend in old_bounds:
            if this_start is None:
                this_start, this_end = ostart, oend
            elif ostart > this_end+1:
                #close current bound, open new one
                clean_bounds.add(Bound(this_start, this_end))
                this_start, this_end = ostart, oend
            elif ostart <= this_end+1:
                #extend current bound
                this_end = oend
        if this_start is not None:
            #close final bound
            clean_bounds.add(Bound(this_start, this_end))
        self.bounds = clean_bounds
            
    def allocate_fast(self, start, end=None, length=1):
        # INCLUSIVE of end
        if end is not None and end > start:
            newbound = Bound(start, end)
        elif length > 0:
            newbound = Bound(start, start+length-1)
        else: return
        self.bounds.add(newbound)
        
    def allocate(self, start, end=None, length=1):
        self.allocate_fast(start, end, length)
        self.cleanup_bounds()
        
    def deallocate(self, start, end=None, length=1):
        if end is None or end <= start: end = length
        for b in self.bounds:
            if start <= b.start and end >= b.end:
                self.bounds.remove(b)
            elif start <= b.start and end >= b.start:
                self.allocate_fast(end+1, b.end)
                self.bounds.remove(b)
            elif start >= b.start and end <= b.end:
                self.allocate_fast(b.start, start-1)
                self.allocate_fast(end+1, b.end)
                self.bounds.remove(b)
            elif start <= b.end and end >= b.end:
                self.allocate_fast(b.start, start)
                self.bounds.remove(b)
        self.cleanup_bounds()
        
    def find_empty_space(self, min_size=1):
        found = False
        last_bank = None
        while not found:
            space_offsets, limit_offsets = [], []
            for v in self.registry.values():
                space_offsets.append(v.offset+v.size)
                limit_offsets.append(v.offset)
            for b in self.bounds:
                space_offsets.append(b.start)
                limit_offsets.append(b.end+1)
            space_offsets, limit_offsets = sorted(space_offsets), sorted(limit_offsets)
            
            lidx = 0
            for this_offset in space_offsets:
                while limit_offsets[lidx] < this_offset:
                    lidx += 1
                this_size = limit_offsets[lidx] - this_offset
                if this_size >= min_size: return this_offset
                
        #no empty space found, so:
            #print("Attempting to expand allocation...", end='  ')
            last_bank = self.expand_allocation(last_bank)
        
    def expand_allocation(self, last_bank=None):
        #Check between bounds
        last_bound, found = None, False
        sorted_bounds = sorted(self.bounds)
        for b in sorted_bounds:
            #print(".", end='')
            if last_bound is None: last_bound = b.end
            else:
                gap = db.rom[last_bound+1:b.start]
                reject = False
                for g in gap:
                    if g not in [0x00, 0xFF]:
                        reject = True
                        break
                if not reject:
                    found = True
                    new_range = Bound(last_bound+1, b.start-1)
                    break
        if not found:
            #print()
        #TODO check for vanilla unused space (FF6 omen1 dupe)
            #Find a bank with no unallocated data
            bank = 0 if last_bank is None else last_bank+1
            while True:
                bnkstart = bank * 0x10000
                bnkend = bnkstart + 0xFFFF
                print(f"{bank:02X}", end=' ')
                bank_bounds = [b for b in sorted_bounds if bnkstart <= b.start <= bnkend or bnkstart <= b.end <= bnkend]
                if not bank_bounds:
                    unknown_space = [Bound(bnkstart, bnkend)]
                else:
                    unknown_space = []
                    if bnkstart < bank_bounds[0].start-1: unknown_space.append(Bound(bnkstart, bank_bounds[0].start-1))
                    for i, b in enumerate(bank_bounds):
                        if last_bound is not None:
                            unknown_space.append(Bound(last_bound+1, b.start-1))
                        last_bound = b.end
                    if last_bound < bnkend: unknown_space.append(Bound(last_bound+1, bnkend))
                for u in unknown_space:
                    gap = db.rom[u.start:u.end+1]
                    reject = False
                    for g in gap:
                        if g not in [0x00, 0xFF]:
                            reject = True
                            break
                    if reject: break
                if not reject:
                    new_range = Bound(bnkstart, bnkend)
                    break
                bank += 1
                assert bank < 0x80
        #print(f"Allocating ${new_range.start:06X} to ${new_range.end:06X}")
        self.allocate(new_range.start, new_range.end)
        return bank
        #look for empty space (00/FF) between bounds
        #then look for an empty bank and claim it
        #return when the first new space is found
        #should be called when there's no room for a thing
    
def warn(text):
    pub.sendMessage("warning", text=text)

def build_imeta_db():
    global imetadata
    cp = configparser.ConfigParser()
    cp.optionxform = str #make case sensitive
    cp.read(dat('instruments'))
    cp.read(dat('instruments_custom'))
    imetadata = {}
    for entry in cp['InstrumentMetadata'].items():
        im = InstrumentMetadata()
        im.parse(entry)
        imetadata[entry[0]] = im
        
def get_bgm_name_by_id(id):
    if id in bgmid_names:
        return bgmid_names[id]
    else:
        return "unknown"
        
# def inst_set(dat):
    # instruments = []
    # for i in range(0,16):
        # instruments.append(read_int(dat[i*2:i*2+2]))
    # return instruments
            
def read_int(dat, invert=True):
    result = 0
    if invert:
        for i, b in enumerate(dat):
            result += (b << (8*i))
        if result >= 0xC00000: result -= 0xC00000
    else:
        for i, b in enumerate(dat):
            result += (b << (8*(len(dat)-1-i)))
    return result
    
def write_int(n, length=None, invert=True, is_offset=True):
    if length is None: length = (n.bit_length() + 7)//8
    if is_offset and n < 0x400000 and length >= 3:
        n += 0xC00000
    result = n.to_bytes(length, byteorder="little" if invert else "big")
    return result
    
def splice(bin, new_data, offset):
    print(f"splicing 0x{len(new_data):X} bytes at ${offset:06X}")
    r = bin[:offset]
    r += new_data
    try:
        r += bin[len(r):]
    except KeyError:
        pass
    return r
    
def resolve_pointers(rom, mode):
    cp = configparser.ConfigParser()
    cp.read(dat('gameinfo'))
    mode_params = cp['Mode'+mode]
    for k, v in offset.items():
        if k in mode_params:
            try:
                offset[k] = int(mode_params[k].strip(), 16)
            except ValueError: 
                if mode_params[k].strip() == "True":
                    offset[k] = True
                elif mode_params[k].strip() == "False":
                    offset[k] = False
                elif mode_params[k].strip() == "None":
                    offset[k] = None
                else:
                    offset[k] = mode_params[k].strip()

    loc = offset["bgmptrs"]
    offset["bgmlist"] = read_int(rom[loc:loc+3])
    loc = offset["instptr"]
    offset["inst"] = read_int(rom[loc:loc+3])
    loc = offset["brrptrs"]
    offset["brrlist"] = read_int(rom[loc:loc+3])
    loc = offset["loopptr"]
    offset["loopdata"] = read_int(rom[loc:loc+3])
    loc = offset["pitchptr"]
    offset["pitchdata"] = read_int(rom[loc:loc+3])
    loc = offset["adsrptr"]
    offset["adsrdata"] = read_int(rom[loc:loc+3])
    
def identify_game(rom):
    lu = rom[0x7FB0:0x8000]
    lh = rom[0x81B0:0x8200]
    hu = rom[0xFFB0:0x10000]
    hh = rom[0x101B0:0x10200]
    possible_headers = [hu, hh, lu, lh]
    expected_hirom = [True, True, False, False]
    has_header = [False, True, False, True]
    
    found = False
    for i, h in enumerate(possible_headers):
        title = h[0x10:0x25]
        mode = h[0x25] & 0b1
        abort = False
        for ch in title:
            if ch <= 0x1F or ch >= 0x7F:
                abort = True
                break
            if abort: break
        if abort: continue
        title = str(title, encoding='ascii').upper()
        if mode == 1:
            if not expected_hirom[i]: continue
            else: hirom = True
        if mode == 0:
            if expected_hirom[i]: continue
            else: hirom = False
        header = has_header[i]
        found = True
        break
    if not found:
        ## satellaview?
        for i, h in enumerate(possible_headers):
            if h[:0x2] != b"\x43\x33" and h[0x29:0x2A] != b"\x10\x33":
                continue
            mode = h[0x28] & 0b1
            if mode == 1:
                if not expected_hirom[i]: continue
                else: hirom = True
            if mode == 0:
                if expected_hirom[i]: continue
                else: hirom = False
            header = has_header[i]
            found = True
            title = "BS "
            for b in h[0x10:0x1F]:
                title += f"{b:02X} "
            print(title)
    if not found:
        return False
    cp = configparser.ConfigParser()
    cp.read(dat('gameinfo'))
    gamemode = ''
    for k, v in cp['SNESHeader'].items():
        k = k.strip().upper()
        if title.startswith(k):
            gamemode = v
            break
    if not gamemode:
        warn("game not recognized, defaulting to FF6")
        gamemode = "FF6"
    return (gamemode, header, hirom)
    
def bgmidx(idx):
    return f"BGM{idx:02X}"
    
def insidx(idx):
    return f"INS{idx-1:02X}"
    
def dat(file):
    return os.path.join("dat", file + ".txt")

def hexify(text):
    return ''.join([c for c in text.upper() if c in "1234567890ABCDEF"])
    
def zeropad(text, length):
    if len(text) > length: text = text[0:length]
    while len(text) < length: text = '0' + text
    return text
    
def exec_test():
    try:
        with open(file_target, "br") as f:
            rom = f.read()
    except IOError:
        print("could not open file {}".format(file_target))
        return
        
    resolve_pointers(rom)
    db = Database(rom)
    print({k: hex(v) for k, v in offset.items()})
    print("Bgm count: {}".format(db.bgmcount))
    for i, s in enumerate(db.bgms):
        print("ID {:X}: offset {:X}, length {:X}, md5 {}".format(i, s.offset, s.length, s.hash))
        out = "    "
        count = 0
        for smp in s.inst:
            count += 1
            out += "{:02X} ".format(smp) if smp else "-- "
            if count >= 8:
                print(out)
                count = 0
                out = "    "
                
if __name__ == "__main__":
    try:
        exec_test()
        print()
        input("Press enter to close.")
    except Exception:
        import traceback
        traceback.print_exc()
        print()
        input("Failed -- Press enter to close.")