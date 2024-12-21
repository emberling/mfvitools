## bulk BRR-to-SF2 converter
## expands waveforms beyond their original length to
## properly capture the effect BRR filters have on looping
## made with reference to vgmtrans & brrtools source
## and BRR docs/code on wiki.superfamicom.org

import os, sys, configparser, traceback, re
from math import log, modf
import mml2mfvi

SAMPLE_EXTRA_ITERATIONS = 1
SAMPLE_MIN_SIZE = 4000
USE_ID_IN_NAMES = False
USE_LISTFILE_TRANSPOSE = True
SORT_BY_BLOCKSIZE = False

# SPC700 sustain level -> conventional sf2 units (1 = 0.04dB)
attenuation_table = {
    7: 0,
    6: 29,
    5: 63,
    4: 102,
    3: 150,
    2: 213,
    1: 301,
    0: 452,
   -1: 2500    }
    
ATTEN_SILENCE = 2500

attack_table = {
    0: 4100,
    1: 2600,
    2: 1500,
    3: 1000,
    4: 640,
    5: 380,
    6: 260,
    7: 160,
    8: 96,
    9: 64,
    10: 40,
    11: 24,
    12: 16,
    13: 10,
    14: 6,
    15: 0 }
    
decay_table = {
    0: 1200,
    1: 740,
    2: 440,
    3: 290,
    4: 180,
    5: 110,
    6: 74,
    7: 37 }
    
release_table = {
    1: 38000,
    2: 38000,
    3: 24000,
    4: 19000,
    5: 14000,
    6: 12000,
    7: 9400,
    8: 7100,
    9: 5900,
    10: 4700,
    11: 3500,
    12: 2900,
    13: 2400,
    14: 1800,
    15: 1500,
    16: 1200,
    17: 880,
    18: 740,
    19: 590,
    20: 440,
    21: 370,
    22: 290,
    23: 220,
    24: 180,
    25: 150,
    26: 110,
    27: 92,
    28: 74,
    29: 55,
    30: 37,
    31: 28 }
    
pre = 0
prepre = 0

clamp = lambda nmin, n, nmax: nmin if n < nmin else (nmax if n > nmax else n)

def text_clamp(text, length):
    if len(text) > length:
        text = text[:length]
    text = bytearray(text, "latin-1")
    while len(text) < length:
        text += b'\x00'
    return text
    
class BrrSample:
    def __init__(self, idx, text):
        # parse text - from insertmfvi "Sample.init_from_listfile"
        text = [s.strip() for s in text.split(',')]
        if not text:
            return None
        self.filename = os.path.join(listpath, text[0])
        try:
            looptext = text[1].lower().strip()
        except IndexError:
            looptext = "0000"
            print(f"SAMPLEINIT: no loop point specified for sample {text[0]}, using 0000")
        try:
            pitchtext = text[2].lower().strip()
        except IndexError:
            pitchtext = "0000"
            print(f"SAMPLEINIT: no tuning data specified for sample {text[0]}, using 0000")
        try:
            envtext = text[3].lower().strip()
        except IndexError:
            envtext = "ffe0"
            print(f"SAMPLEINIT: no envelope data specified for sample {text[0]}, using 15/7/7/0")
            
        selfloop = mml2mfvi.parse_brr_loop(looptext)
        selftuning = mml2mfvi.parse_brr_tuning(pitchtext)
        selfadsr = mml2mfvi.parse_brr_env(envtext)
        
        try:
            extratext = text[4].strip()
        except IndexError:
            extratext = ""
        extratext = re.sub(r"\{.*\}", "", extratext)
        coarsetune = re.search(r"\[[0-9+-]+\]", extratext)
        extratext = re.sub(r"\[.*\]", "", extratext)
        self.name = extratext.strip()
        if not self.name:
            self.name = self.filename
            if '.' in self.name:
                self.name = self.name.rpartition('.')[0]
            if '/' in self.name:
                self.name = self.name.rpartition('/')[2]
            if '\\' in self.name:
                self.name = self.name.rpartition('\\')[2]
        if coarsetune is not None and USE_LISTFILE_TRANSPOSE:
            coarsetune = coarsetune.group(0)[1:-1].strip()
            try:
                self.coarsetune = int(coarsetune) * -1
            except ValueError:
                self.coarsetune = None
        else:
            self.coarsetune = None
            
        # load data - from insertmfvi "Sample.load()"
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
                        print(f"LOADBRR: couldn't open file {self.filename}")
            if brr:
                if len(brr) % 9 == 2:
                    header = brr[0:2]
                    brr = brr[2:]
                    header_value = int.from_bytes(header, "little")
                    if header_value != len(brr):
                        if header_value % 9 and header_value < len(brr):
                            # looks like an AddmusicK-style loop point header
                            print(f"LOADBRR: Found embedded loop point {header_value:04X} in {self.filename}")
                            if isinstance(brr.loop, bytes):
                                print(f"         Externally specified loop point {int.from_bytes(brr.loop, 'little'):04X} takes precedence")
                            else:
                                print(f"         using this")
                                self.loop = header_value.to_bytes(2, "little")
                if len(brr) % 9:
                    print(f"LOADBRR: {self.filename}: bad file format")
                    print("         BRRs must be a multiple of 9 bytes, with optional 2-byte header")
        self.brr = brr
                
        # cleanup, adapted from ff6spc2sf2
        self.idx = idx
        self.sdta_offset = None
        self.sdta_end = None
        
        self.offset = 0
        self.loffset = int.from_bytes(selfloop, "little")
        ad = selfadsr[0]
        sr = selfadsr[1]
        self.attack = ad & 0x0F
        self.decay = (ad >> 4) & 0b111
        self.sustain = (sr >> 5)
        self.release = sr & 0x1F
        scale = int.from_bytes(selftuning, "big")
        if scale < 0x8000: scale += 0x10000
        self.pitch_scale = scale / 0x10000
        
        loc = self.offset
        while loc < (0xF500 - 9):
            if brr[loc] & 1:
                break
            loc += 9
        self.is_looped = True if brr[loc] & 0b10 else False
        end = loc + 9
        self.length = (end - self.offset) // 9
        self.llength = (end - self.loffset) // 9 if self.is_looped else 0
        self.alength = (self.length - self.llength)
        
        loop = (self.loffset - self.offset) / 9
        print(f"BRR sample {idx:02X}:")
        print(f" end {end} self.loffset {self.loffset:04X}")
        print(f"    @{self.offset:04X} || length {self.length} ({self.length*16})")
        if self.is_looped:
            print(f"    Attack {self.alength} then loop {self.llength} ({self.alength * 16} -> {self.llength * 16})")
        else:
            print(f"    Loop not active")
        print(f"    {self.attack:02} {self.decay} {self.sustain} {self.release:02}")
        print(f"    Pitch mult {self.pitch_scale}")
        
    def is_valid(self):
        # invalidate if negative loop
        if self.loffset < self.offset:
            return False
        # invalidate if loop not multiple of 9 bytes (warn)
        if (self.loffset - self.offset) % 9:
            print("WARNING: Sample {self.idx:02X} loop point is invalid!")
        # invalidate if bad ranges (warn)
        for i in range(self.length):
            brr_range = self.brr[self.offset + i * 9] >> 4
            if brr_range > 12:
                print(f"WARNING: Sample {self.idx:02X} has invalid range nybble {brr_range} at block {i}")
                # return False
        return True
        
    def get_pcm(self):
        global pre, prepre
        pre = 0
        prepre = 0
        # print(f"getpcm {self.idx:02X}")
        
        pcm = bytearray()
        loc = self.offset
        loops = 0
        while True:
            block = self.brr[loc:loc+9]
            if len(block) != 9:
                print(f"WARNING: truncated block at {loc:04X} - expected length 9, got length {len(block)}")
                print(f"aborting processing for this sample, press enter to continue")
                input()
                break
            pcm_samples = decode_block(block)
            print(".", end="")
            for p in pcm_samples:
                pcm.extend(p.to_bytes(2, "little", signed=True))
            
            if block[0] & 0b11 == 0b11:
                if loops >= SAMPLE_EXTRA_ITERATIONS and len(pcm) >= SAMPLE_MIN_SIZE:
                    valid = self.validate_loop(pcm)
                    if valid:
                        self.llength *= valid
                        print(f"\n  Loop extended by {valid}x (total iterations {loops+1})")
                        print(f"  loop size {self.llength}, sample size {len(pcm)}")
                        break
                loops += 1
                loc = self.loffset
                # print(f"  adding {loops+1}rd iteration")
                continue
            elif block[0] & 1:
                break
                
            loc += 9
            if loc > self.offset + self.length * 9:
                print(f"why are we at {loc:04X} when sample {self.idx:02X} at {self.offset:04X} is only {self.length} blocks long? we should have gotten there by {self.offset + self.length * 9:04X}")
                input()
        return pcm
        
    def validate_loop(self, pcm):
        llen = self.llength * 16
        lsp = len(pcm) - llen
        lscale = 1
        while True:
            lsp = len(pcm) - llen * lscale
            prelsp = lsp - llen * lscale
            if prelsp <= self.length:
                break
            #print(f"  trying {lscale}x ({lsp} / {len(pcm)})")
            if pcm[lsp:] == pcm[prelsp:lsp]:
                #print(f"  found match with period {lscale}x original loop size")
                return lscale
            lscale += 1
        return False
            
    def get_tuning(self):
        semitones = 12 * (log(self.pitch_scale, 10) / log(2, 10))
        cents, semitones = modf(semitones)
        key = int(69 - semitones)
        cents = int(round(cents * 100))
        #if cents < 0:
        #    cents += 100
        #    key += 1
        #if cents > 50:
        #    key -= 1
        #    cents = (100 - cents) + 0x80
        return key, cents
        
    def get_key_range(self):
        semitones = 12 * (log(self.pitch_scale, 10) / log(2, 10))
        cents, semitones = modf(semitones)
        key = int(93 - semitones)
        if cents > 0:
            key -= 1
        if self.coarsetune:
            key -= self.coarsetune
        max = clamp(0, key, 127)
        min = clamp(0, 0 - self.coarsetune, max) if self.coarsetune else 0
        return (max << 8) + min
        
def decode_block(block):
    global pre, prepre
    assert len(block) == 9
    head = block[0]
    filtermode = (head & 0b1100) >> 2
    shiftrange = head >> 4
    # print(f"filter {filtermode} shift {shiftrange}")
    
    nybs = []
    pcms = []
    for byt in block[1:]:
        nybs.append(byt >> 4)
        nybs.append(byt & 0x0F)
    # print(nybs)
    for n in nybs:
        if n >= 8:
            n -= 16
        if shiftrange > 13:
            pcm = (-1 if n < 0 else 1) << 11
        else:
            pcm = n << shiftrange >> 1
        debug_shifted = pcm
        
        if filtermode == 0:
            filter = 0
        elif filtermode == 1:
            filter = pre + ((-1 * pre) >> 4)
        elif filtermode == 2:
            filter = (pre << 1) + ((-1*((pre << 1) + pre)) >> 5) - prepre + (prepre >> 4)
        elif filtermode == 3:
            filter = (pre << 1) + ((-1*(pre + (pre << 2) + (pre << 3))) >> 6) - prepre + (((prepre << 1) + prepre) >> 4)
        pcm += filter
        debug_filtered = pcm
        
        pcm = clamp(-0x8000, pcm, 0x7FFF)
        if pcm > 0x3FFF:
            pcm -= 0x8000
        elif pcm < -0x4000:
            pcm += 0x8000
        # print(f"{debug_shifted} -> {debug_filtered} ({filter}) -> {pcm}")
        pcms.append(pcm)
        prepre = pre
        pre = pcm
    return pcms
    
def chunkify(data, name):
    return bytearray(name, "latin-1") + len(data).to_bytes(4, "little") + data
    
def generator(id, val, signed=True):
    return bytearray(id.to_bytes(2, "little") + val.to_bytes(2, "little", signed=signed))
    
def timecents(ms):
    s = ms / 1000
    tc = int(round(1200 * log(s, 2)))
    return clamp(-0x8000, tc, 0x7FFF)
    
def attenuate(pct):
    if pct >= 1:
        return 0
    if pct <= 0:
        return ATTEN_SILENCE
    p_ref = 0.00002
    db_ref = 20 * log(1 / p_ref, 10)
    db_pct = 20 * log(pct / p_ref, 10)
    return int((db_ref - db_pct) // .04)
    
## -----------------------------

## if len(sys.argv) >= 2:
##     spcfn = sys.argv[1]
## else:
##     print("spc filename: ")
##     spcfn = input()
##     
## spcfn = spcfn.strip('"')
## with open(spcfn, "rb") as f:
##     spc = f.read()[0x100:]
##     
## brrs = {}
## for i in range(32, 48):
##     s = BrrSample(i)
##     if s.is_valid():
##         brrs[i] = s
##         
## print (f"Accepted samples: {[f'{k:02X}' for k in brrs.keys()]}")

try:
    print("mfvitools brr2sf2")
    print("usage: brr2sf2.py LISTFILE [sort] [id] [@SAMPLEPATH]")
    print()
    
    if len(sys.argv) >= 2:
        listfn = sys.argv[1]
    else:
        print("BRR list filename:")
        listfn = input()
    listfn = listfn.strip('"').strip()
    listpath, listname = os.path.split(listfn)
    
    if len(sys.argv) >= 3:
        if "sort" in [a.strip() for a in sys.argv[2:]]:
            SORT_BY_BLOCKSIZE = True
        if "id" in [a.strip() for a in sys.argv[2:]]:
            USE_ID_IN_NAMES = True
        for arg in [a.strip() for a in sys.argv[2:]]:
            if len(arg) and arg[0] == "@":
                listpath = arg[1:]
            
    #listfile = configparser.ConfigParser()
    #listfile.read(listfn)
    with open(listfn, "r") as f:
        listfile = f.readlines()
    listfile = [l for l in listfile if len(l) and l[0] != '[' and l[0] != '#' and l[0] != ';']
    listdefs = {}
    #if 'Samples' in listfile:
    #    listdefs.update(listfile['Samples'])
    #if 'BRR' in listfile:
    #    listdefs.update(listfile['BRR'])
    #if 'BRRs' in listfile:
    #    listdefs.update(listfile['BRRs'])
    #if 'Instruments' in listfile:
    #    listdefs.update(listfile['Instruments'])
    
    brrs = {}
    used_ids = set()
    for full_line in listfile:
        if not full_line.strip():
            continue
        id, _, line = full_line.partition(':')
        id = id.strip()
        
    #brrs = {}
    #for id, line in listdefs.items():
        if 'k' in id:
            id = ''.join(d for d in id if d.isdigit())
            try:
                id = int(id) * 128
            except ValueError:
                id = 0
        else:
            try:
                id = int(id, 16)
            except ValueError:
                print(f"LISTFILES: invalid sample id {id}")
                id = None
        if id is None:
            id = 0
        if id in used_ids:
            for i in range((id // 0x80) * 128, (id // 0x80) * 128 + 0x7F):
                print(i)
                if i not in used_ids:
                    id = i
                    break
        if id in used_ids:
            for i in range(128 * 128):
                if i not in used_ids:
                    id = i
                    break
        if id in used_ids:
            print(f"no free id for {line}")
            continue
        used_ids.add(id)
        brrs[id] = BrrSample(id, line)
    # brrs = {k: v for k, v in brrs.items() if v.is_valid() and len(v.brr)}
    
    if SORT_BY_BLOCKSIZE:
        brrs_sorted = {}
        for i in range(128):
            bank = []
            for j in range(128):
                if (i * 128) + j in brrs:
                    bank.append(brrs[i * 128 + j])
            bank = sorted(bank, key=lambda x: x.length)
            for j in range(len(bank)):
                bank[j].idx = i * 128 + j
                brrs_sorted[i * 128 + j] = bank[j]
        brrs = brrs_sorted
                
    ##### Build sample data chunk

    smp_data = bytearray()

    print("Building waveforms")
    for k, s in brrs.items():
        print(f"\nconverting BRR to PCM: {k:02X}", end="")
        s.sdta_offset = len(smp_data) // 2
        smp_data.extend(s.get_pcm())
        s.sdta_end = len(smp_data) // 2
        smp_data.extend(b"\x00\x00" * 46)
        if len(smp_data) % 2:
            smp_data.append(b"\x00")
         
    sdta_chunk = chunkify(smp_data, "sdtasmpl")
    sdta_list = chunkify(sdta_chunk, "LIST")

    ##### Build articulation data chunk

    sfPresetHeader = bytearray()
    sfPresetBag = bytearray()
    sfModList = chunkify(b"\x00" * 10, "pmod")
    sfGenList = bytearray()
    sfInst = bytearray()
    sfInstBag = bytearray()
    sfInstModList = chunkify(b"\x00" * 10, "imod")
    sfInstGenList = bytearray()
    sfSample = bytearray()

    i = -1
    print("Building soundfont")
    for s in brrs.values():
        if s is None:
            continue
        i += 1
        # name = text_clamp(f"brr{s.idx:02X} ({s.length})", 20)
        if USE_ID_IN_NAMES:
            name_id = f"{s.idx:02X}"
            name_block = f"{s.length}"
            name_freespace = 18 - len(name_id) - len(name_block)
            name = f"{name_id} {s.name[:name_freespace].strip()} {name_block}"
        else:
            name_block = f"{s.length}"
            name_freespace = 19 - len(name_block)
            name = f"{s.name[:name_freespace].strip()} {name_block}"
        print(name)
        name = text_clamp(name, 20)
        
        # sfSample.achSampleName
        sample = bytearray(name)
        # sfSample.dwStart
        sample += s.sdta_offset.to_bytes(4, "little")
        # sfSample.dwEnd
        sample += s.sdta_end.to_bytes(4, "little")
        # sfSample.dwStartloop
        if s.is_looped:
            lst = (s.sdta_end - 16) - (s.llength * 16)
        else:
            lst = s.sdta_offset
        sample += lst.to_bytes(4, "little")
        # sfSample.dwEndloop
        if s.is_looped:
            sample += (s.sdta_end - 16).to_bytes(4, "little")
        else:
            sample += s.sdta_offset.to_bytes(4, "little")
        # sfSample.dwSampleRate
        sample += int(32000).to_bytes(4, "little")
        # sfSample.byOriginalPitch
        key, cents = s.get_tuning()
        sample.append(key)
        # sfSample.chPitchCorrection
        sample += cents.to_bytes(1, "little", signed=True)
        # sfSample.wSampleLink
        # sfSample.sfSampleType
        sample += b"\x00\x00\x01\x00"
        
        sfSample += sample
        
        # build instrument generators
        # two zone operation to mimic SPC700 sustain rate (2nd decay)
        dgen, rgen, hgen, common = bytearray(), bytearray(), bytearray(), bytearray()
        # ADSR
        hold = 0
        common += generator(38, timecents(9.75)) # true release
        if attack_table[s.attack]:
            common += generator(34, timecents(attack_table[s.attack]))
        if s.sustain < 7:
            decay_share = 1 - (s.sustain + 1) * (1/8)
            decay_time = decay_table[s.decay] * decay_share
            dgen += generator(37, ATTEN_SILENCE) # sf2 sustain = silence
            dgen += generator(36, timecents(decay_time)) # sf2 decay
            if s.release > 0:
                hold += decay_time
                rgen += generator(35, timecents(decay_time)) # sf2 hold
        if s.release > 0:
            rgen += generator(37, ATTEN_SILENCE) # sf2 sustain = silence
            hgen += generator(37, ATTEN_SILENCE)
            rgen += generator(36, timecents(release_table[s.release]*2))
            hgen += generator(36, timecents(release_table[s.release]*2))
            hgen += generator(35, timecents(hold + release_table[s.release]*2//3))
        # attenuation
        dgen_share = 1 - ((s.sustain + 1) * 1/8)
        hgen_share = (1 - dgen_share) * 1/8 if s.release else 0
        rgen_share = 1 - (dgen_share + hgen_share)
        dgen += generator(48, attenuate(dgen_share))
        rgen += generator(48, attenuate(rgen_share))
        hgen += generator(48, attenuate(hgen_share))
        # vibrato delay 500ms (1 beat at 120bpm)
        common += generator(23, timecents(500))
        vfreq = 1 / ((9.75 * 18) / 1000)
        vfreq = timecents(vfreq * 1000 / 8.176)
        common += generator(24, vfreq)
        # loop state (sampleModes)
        common += generator(54, 1 if s.is_looped else 0)
        # sampleID
        common += generator(53, i)
        
        dgen += common
        rgen += common
        hgen += common
        dgen_bagindex = len(sfInstGenList) // 4
        sfInstGenList += dgen
        hgen_bagindex = len(sfInstGenList) // 4
        sfInstGenList += hgen
        rgen_bagindex = len(sfInstGenList) // 4
        sfInstGenList += rgen
        
        # instrument bag
        sfInstBag += (dgen_bagindex).to_bytes(2, "little") + b"\x00\x00"
        sfInstBag += (hgen_bagindex).to_bytes(2, "little") + b"\x00\x00"
        sfInstBag += (rgen_bagindex).to_bytes(2, "little") + b"\x00\x00"
        
        # instrument header
        sfInst += name
        sfInst += (i * 3).to_bytes(2, "little")
        
        # build preset generators
        pgen = bytearray()
        # max range root+2oct, min c at octave 0
        pgen += generator(43, s.get_key_range(), signed=False)
        # transpose if specified in listfile
        if s.coarsetune:
            pgen += generator(51, s.coarsetune)
        # instrumentID
        pgen += generator(41, i)
        
        pgen_bagindex = len(sfGenList) // 4
        sfGenList += pgen
        
        # preset bag
        sfPresetBag += pgen_bagindex.to_bytes(2, "little") + b"\x00\x00"
        
        # preset header
        sfPresetHeader += name
        # preset ID
        sfPresetHeader += (s.idx % 0x80).to_bytes(2, "little")
        # bank ID
        sfPresetHeader += (s.idx // 0x80).to_bytes(2, "little")
        # preset bag index
        sfPresetHeader += i.to_bytes(2, "little")
        # trash
        sfPresetHeader += b"\x00" * 12
        
    # add terminal elements
    sfPresetHeader += bytes("EOP", "latin-1") + b"\x00" * 21 + (i+1).to_bytes(2, "little") + b"\x00" * 12
    sfInst += bytes("EOI", "latin-1") + b"\x00" * 17 + (i*3+3).to_bytes(2, "little")
    sfSample += bytes("EOS", "latin-1") + b"\x00" * 43
    sfInstBag += (len(sfInstGenList) // 4).to_bytes(4, "little")
    sfPresetBag += (len(sfGenList) // 4).to_bytes(4, "little")
    sfInstGenList += b"\x00" * 4
    sfGenList += b"\x00" * 4

    # pack 'em up
    pdta_chunk = chunkify(sfPresetHeader, "pdtaphdr")
    pdta_chunk += chunkify(sfPresetBag, "pbag")
    pdta_chunk += sfModList
    pdta_chunk += chunkify(sfGenList, "pgen")
    pdta_chunk += chunkify(sfInst, "inst")
    pdta_chunk += chunkify(sfInstBag, "ibag")
    pdta_chunk += sfInstModList
    pdta_chunk += chunkify(sfInstGenList, "igen")
    pdta_chunk += chunkify(sfSample, "shdr")
    pdta_list = chunkify(pdta_chunk, "LIST")

    # INFO_list
    info_chunk = bytearray()
    info_chunk += chunkify(b"\x02\x00\x04\x00", "INFOifil")
    info_chunk += chunkify(bytes("EMU8000", "latin-1") + b"\x00", "isng")
    
    listname = listname.rpartition('.')[0]
    outfn = listname + ".sf2"
    listname = bytes(listname, "latin-1") + b"\x00"
    if len(listname) % 2:
        listname += b"\x00"
    info_chunk += chunkify(listname, "INAM")
    info_list = chunkify(info_chunk, "sfbkLIST")

    sfbk_chunk = info_list + sdta_list + pdta_list
    sfbk_riff = chunkify(sfbk_chunk, "RIFF")

    with open(outfn, "wb+") as f:
        f.write(sfbk_riff)
        
    print("done.")
    input()
except:
    traceback.print_exc()
    input()