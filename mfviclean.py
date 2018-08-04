from sys import argv
from shutil import copyfile

args = list(argv)
if len(args) > 2:
    sourcefile = args[1].strip()
else:
    sourcefile = raw_input("Please input the file name of your music data "
                           "ROM dump:\n> ").strip()

try:
    f = open(sourcefile, 'rb')
    data = f.read()
    f.close()
except IOError:
    raw_input("Couldn't open input file. Press enter to quit. ")
    quit()

outfile = sourcefile + "_data.bin"
copyfile(sourcefile, outfile)

try:
    fout = open(outfile, "r+b")
except IOError:
    raw_input("Couldn't open output file. Press enter to quit. ")
    quit()

def read_word(f):
    low, high = 0, 0
    try:
        low = ord(f.read(1))
        high = ord(f.read(1))
    except:
        print "warning: read_word failed, probably unexpected end of file"
    return low + (high * 0x100)

def write_word(i):
    global fout
    low = i & 0xFF
    high = (i & 0xFF00) >> 8
    fout.write(chr(low))
    fout.write(chr(high))
    
fout.seek(0,2)
size = fout.tell()
assert size <= 0xFFFF

ichannels, ochannels = [], []
fout.seek(0x06)
for c in xrange(0,16):
    ichannels.append(read_word(fout))

shift = ichannels[0] - 0x26
for c in ichannels:
    ochannels.append((c if c >= shift else c + 0x10000) - shift)
    
fout.seek(0x06)
for c in ochannels:
    write_word(c)


maxvalue = {"\xCF":0x1F, "\xD6":0x07, "\xDD":0x15, "\xDE":0x07, "\xDF":0x07, "\xE0":0x31}
skipone = {"\xC4", "\xC6", "\xCF", "\xD6", "\xD9", "\xDA", "\xDB", "\xDC", "\xDD", "\xDE", "\xDF", "\xE0",
            "\xE2", "\xE8", "\xE9", "\xEA", "\xF0", "\xF2", "\xF4"}
skiptwo = {"\xC5", "\xC7", "\xC8", "\xCD", "\xF1", "\xF3", "\xF7", "\xF8"}
skipthree = {"\xC9", "\xCB"}
purgeone = {"\xFD", "\xFE"}
purgetwo = set()
instruments = set()
scaleparms = {}

#traverse and gather information
pos = 0x26
fout.seek(pos)
while pos < size:
    byte = fout.read(1)
    if not byte: break
    
    if byte == "\xDC":
        pos = fout.tell()
        instruments.add(ord(fout.read(1)))
        fout.seek(pos)
    elif byte in {"\xC4", "\xC6"}: #one parameter, max 7F
        parm = ord(fout.read(1))
        if parm > 0x7F and byte not in scaleparms:
            print "at {} found command {} {} outside expected maximum 0x7f. scaling enabled".format(hex(pos), hex(ord(byte)), hex(parm))
            scaleparms[byte] = 1
    elif byte in {"\xC5", "\xC7"}: #two parameters, second has max 7F
        parm = ord(fout.read(2)[1])
        if parm > 0x7F and byte not in scaleparms:
            print "at {} found command {} nn {} outside expected maximum 0x7f. scaling enabled".format(hex(pos), hex(ord(byte)), hex(parm))
            scaleparms[byte] = 2
    elif byte in maxvalue:
        parm = ord(fout.read(1))
        if parm > maxvalue[byte]:
            print "WARNING: at {} command {} {} outside expected maximum {}".format(hex(pos), hex(ord(byte)), hex(parm), hex(maxvalue[byte]))
    elif byte in skipone: fout.seek(1,1)
    elif byte in skiptwo or byte in set("\xF6"): fout.seek(2,1)
    elif byte in skipthree or byte == "\xF5": fout.seek(3,1)
    pos = fout.tell()
    
#traverse and edit
pos = 0x26
fout.seek(pos)
while pos < size:
    byte = fout.read(1)
    if not byte: break
    
    if byte in purgetwo:
        pos = fout.tell()
        #print "at {} purging {} {} {}".format(hex(pos), hex(ord(byte)), hex(ord(fout.read(1))), hex(ord(fout.read(1))))
        fout.seek(pos-1)
        #fout.write("\xCC"*3)
        fout.seek(pos+2)
        print "WARNING: at {} found bad {} {} {}".format(hex(pos), hex(ord(byte)), hex(ord(fout.read(1))), hex(ord(fout.read(1))))
        
    elif byte in purgeone:
        pos = fout.tell()
        #print "at {} purging {} {}".format(hex(pos), hex(ord(byte)), hex(ord(fout.read(1))))
        print "WARNING: at {} found bad {} {}".format(hex(pos), hex(ord(byte)), hex(ord(fout.read(1))))
        fout.seek(pos-1)
        #fout.write("\xCC"*2)
        fout.seek(pos+1)
    elif byte in scaleparms:
        pos = fout.tell()
        fout.seek(pos + scaleparms[byte] - 1)
        parm = ord(fout.read(1))
        fout.seek(pos + scaleparms[byte] - 1)
        print "at {} scaling {} {}".format(hex(pos), hex(ord(byte)), hex(parm))
        fout.write(chr(parm/2))
    elif byte in skipthree:
        fout.seek(3,1)
    elif byte in skiptwo:
        fout.seek(2,1)
    elif byte in skipone:
        fout.seek(1,1)
    elif byte in ["\xF5", "\xFA"]:
        fout.seek(1,1)
        pos = fout.tell()
        dest = read_word(fout)
        ndest = (dest if dest >= shift else dest + 0x10000) - shift
        if dest != ndest: print "at {} shifting {} nn {} to {}".format(hex(pos-1), hex(ord(byte)), hex(dest), hex(ndest))
        if ndest > size: print "WARNING: at {} jump destination {} not in file".format(hex(pos-1), hex(ndest))
        fout.seek(pos)
        write_word(ndest)
        fout.seek(pos+2)
    elif byte in ["\xF6", "\xFC"]:
        pos = fout.tell()
        dest = read_word(fout)
        ndest = (dest if dest >= shift else dest + 0x10000) - shift
        if dest != ndest: print "at {} shifting {} {} to {}".format(hex(pos-1), hex(ord(byte)), hex(dest), hex(ndest))
        if ndest > size: print "WARNING: at {} jump destination {} not in file".format(hex(pos-1), hex(ndest))
        fout.seek(pos)
        write_word(ndest)
        fout.seek(pos+2)
    pos = fout.tell()

fout.seek(0,2)
size = fout.tell()
assert size <= 0xFFFF

fout.seek(0)
write_word(size-2)
write_word(0x26)
write_word(size)
fout.close()

print "Found use of instruments {}".format(map(hex, sorted(instruments)))
print


try:
    iout = open(sourcefile + "_inst.bin", "wb")
    iout.write("\x00" * 0x20)
    for i in instruments:
        if i < 0x20:
            continue
        iout.seek((i - 0x20) * 2)
        iout.write("\xFF")
        
    iout.close()
except:
    print "warning: couldn't write instfile. this is probably fine"
    print
    
raw_input("Press enter to quit. ")










