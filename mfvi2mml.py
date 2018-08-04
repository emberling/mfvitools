import sys, traceback
import mfvitbl
from mmltbl import *

jump_bytes = [0xF5, 0xF6, 0xFC]

def byte_insert(data, position, newdata, maxlength=0, end=0):
    while position > len(data):
        data = data + "\x00"
    if end:
        maxlength = end - position + 1
    if maxlength and len(data) > maxlength:
        newdata = newdata[:maxlength]
    return data[:position] + newdata + data[position+len(newdata):]

    
def int_insert(data, position, newdata, length, reversed=True):
    n = int(newdata)
    l = []
    while len(l) < length:
        l.append(chr(n & 0xFF))
        n = n >> 8
    if not reversed: l.reverse()
    return byte_insert(data, position, "".join(l), length)

def warn(fileid, cmd, msg):
    print "{}: WARNING: in {:<10}: {}".format(fileid, cmd, msg)

def clean_end():
    print "Processing ended."
    raw_input("Press enter to close.")
    quit()

def akao_to_mml(data, inst=None, fileid='akao'):
    
    def unskew(base):
        base -= unskew.addr
        if base < 0: base += 0x10000
        return base + 0x26
        
    mml = ["# Converted from binary by mfvitools", ""]
    
    ## process inst
    if inst is not None:
        for slot in xrange(0,0x10):
            if len(inst) < slot*2: break
            byte = inst[slot*2]
            if byte == "\x00": continue
            line = "#WAVE 0x{:02X} -- 0x{:02X}".format(slot+0x20, ord(byte))
            mml.append(line)
        mml.append("")
    
    ## process header
    #ROM storage needs an extra two-byte header (38 total), SPCrips do not have this
    #we can't reliably tell whether the header is included in all cases, but the
    #common custom song address base (26 00) is an impossible ROM header so if
    #this is the first two bytes, we know it's an SPCrip.
    if data[0:2] == "\x26\x00":
        data = int_insert("  ", 0, len(data), 2) + data
    
    unskew.addr = ord(data[2]) + (ord(data[3]) << 8)
    print "unskew.addr {}".format(hex(unskew.addr))
    
    channels, r_channels = {}, {}
    for c in xrange(0,16):
        caddr = unskew(ord(data[6 + c*2]) + (ord(data[7 + c*2]) << 8))
        if c >= 8:
            if caddr == channels[c-8]: continue
        channels[c] = caddr
    for k, v in channels.items():
        r_channels[v] = k
        
    #some padding so we don't read beyond end of data
    data += "\x00\x00\x00"
    
    loc = 0x26
    jumps = {}
    nextjump = 1
    while loc < len(data)-3:
        byte = data[loc]
        if byte in ["\xF5", "\xF6", "\xFC"]:
            jloc = loc+2 if byte == "\xF5" else loc+1
            target = unskew(ord(data[jloc]) + (ord(data[jloc+1]) << 8))
            jumps[target] = nextjump
            nextjump += 1
        bytelen = 1
        if ord(byte) in byte_tbl: bytelen += byte_tbl[ord(byte)][0]
        loc += bytelen
    for j, i in jumps.items():
        print "jump id {} is at {}".format(i, hex(j))
    
    loc = 0x26
    measure = 0
    sinceline = 0
    line = ""
    foundjumps = []
    while loc < len(data)-3:
        byte = ord(data[loc])
        bytelen = 1
        # IF channel points here
        if loc in r_channels:
            line += "\n{%d}\nl16" % (r_channels[loc]+1)
        # IF jump points here
        if loc in jumps:
            line += " $%d " % jumps[loc]
            foundjumps.append(jumps[loc])
        # IF this is a jump
        if byte in jump_bytes:
            paramlen = byte_tbl[byte][0]
            s = byte_tbl[byte][1]
            params = []
            late_add_param = None
            if byte == 0xF5:
                params.append(ord(data[loc+1]))
                tloc = loc + 2
            else: tloc = loc + 1
            dest = unskew(ord(data[tloc]) + (ord(data[tloc+1]) << 8))
            bytelen += paramlen
            if dest in jumps:
                params.append(jumps[dest])
            else:
                params.append("{N/A}")
                warn(fileid, map(hex, map(ord, data[loc:loc+bytelen])), "Error parsing jump to {}".format(hex(dest)))
            while params:
                s += str(params.pop(0))
                if params:
                    s += ","
            line += s
            if byte in [0xEB, 0xF6]: #segment enders
                line += "\n\nl16"
            else:
                line += " "
        #
        elif byte in byte_tbl:
            paramlen = byte_tbl[byte][0]
            s = byte_tbl[byte][1]
            params = []
            for p in xrange(1,paramlen+1):
                params.append(ord(data[loc+p]))
            while params:
                if byte == 0xE2: #loop
                    params[0] += 1
                s += str(params.pop(0))
                if params:
                    s += ","
                    if byte == 0xC8: #portamento
                        if params[0] >= 128:
                            s += "-"
                            params[0] = 256 - params[0]
                        else:
                            s += "+"
            line += s
            if byte in [0xEB, 0xF6]: #segment enders
                line += "\n\nl16"
            bytelen += paramlen
        elif byte <= 0xC3:
            note = mfvitbl.notes[int(byte/14)].lower()
            length = r_length_tbl[byte%14]
            line += note + length
            measure += mfvitbl.lengths[byte%14]
            if measure >= 0xC0:
                line += "  "
                sinceline += measure
                measure = 0
                if sinceline >= 0xC0 * 4 or len(line) >= 64:
                    mml.append(line)
                    line = ""
                    sinceline = 0
        loc += bytelen
    mml.append(line)
    
    for k, v in jumps.items():
        if v not in foundjumps:
            warn(fileid, "{} {}".format(k,v), "Jump destination never found")
    return mml
    
if __name__ == "__main__":
    
    print "mfvitools AKAO SNESv4 to MML converter"
    print
    
    if len(sys.argv) >= 2:
        fn = sys.argv[1]
    else:
        print "If you have both data and instrument set files, named *_data.bin"
        print "and *_inst.bin respectively, you can enter only the prefix"
        print
        print "Enter AKAO filename.."
        fn = raw_input(" > ").replace('"','').strip()

    if fn.endswith("_data.bin"): fn = fn[:-9]
    prefix = False
    try:
        with open(fn + "_data.bin", 'rb') as df:
            data = df.read()
            prefix = True
    except:
        try:
            with open(fn, 'rb') as df:
                data = df.read()
        except IOError:
            print "Couldn't open {}".format(fn)
            clean_end()
    inst = None
    if prefix:
        try:
            with open(fn + "_inst.bin", 'rb') as instf:
                inst = instf.read()
        except IOError:
            pass
    
    try:
        mml = akao_to_mml(data, inst)
    except Exception:
        traceback.print_exc()
        clean_end()
    
    try:
        with open(fn + ".mml", 'w') as mf:
            for line in mml:
                mf.write(line + "\n")
    except IOError:
        print "Error writing {}.mml".format(fn)
        clean_end()
        
    print "OK"
    clean_end()
