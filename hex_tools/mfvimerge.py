from mfvitbl import notes, lengths, codes

skipone = {"\xC4", "\xC6", "\xCF", "\xD6", "\xD9", "\xDA", "\xDB", "\xDC", "\xDD", "\xDE", "\xDF", "\xE0",
            "\xE2", "\xE8", "\xE9", "\xEA", "\xF0", "\xF2", "\xF4", "\xFD", "\xFE"}
skiptwo = {"\xC5", "\xC7", "\xC8", "\xCD", "\xF1", "\xF3", "\xF7", "\xF8"}
skipthree = {"\xC9", "\xCB"}

source = raw_input("Please input the prefix file name of your split "
                       "ROM dump\n(before the 00, 01 etc.):\n> ").strip()

def read_word(f):
    low, high = 0, 0
    low = ord(f.read(1))
    high = ord(f.read(1))
    return low + (high * 0x100)

def write_word(i, f):
    low = i & 0xFF
    high = (i & 0xFF00) >> 8
    f.write(chr(low))
    f.write(chr(high))

def strmod(s, p, c): #overwrites part of a string
    while len(s) < p:
        s = s + " "
    if len(s) == p:
        return s[:p] + c
    else:
        return s[:p] + c + s[p+len(c):]

def bytes(n): # int-word to two char-bytes
    low = n & 0xFF
    high = (n & 0xFF00) >> 8
    return chr(high) + chr(low)

channels = []
try:
    f = open(source + "00", 'rb')
    for i in xrange(0,16):
        c = (ord(f.read(1)) << 8) + ord(f.read(1))
        print "{} -- {} {} -- {} {}".format(c, hex(c >> 8), hex(c & 0xFF), hex(c >> 12), hex(c & 0xFFF))
        channels.append(c)
    f.close()
except IOError:
    raw_input("Couldn't open {}00. Press enter to quit. ".format(source))
    quit()

segments = ["\x00"*0x26]
index = 1
while index:
    try:
        fn = source + "%02d" % (index)
        print "reading {}".format(fn)
        f = open(fn, "rb")
        segments.append(f.read())
        f.close()
        index += 1
    except:
        print "found {} segment files".format(index-1)
        if (index-1) <= 0:
            raw_input("Press enter to quit. ")
            quit()
        index = 0
        
origins = []
lastorigin = 0
for s in segments:
    origins.append(lastorigin + len(s))
    lastorigin += len(s)
#length = origins[-1] + len(segments[-1])
#lengthb = chr(length & 0xFF) + chr(length >> 8)

def convert_pointer(ch, po):
    global origins
    pointer = origins[ch] + po
    return chr(pointer & 0xFF) + chr(pointer >> 8)
    
for i, s in enumerate(segments):
    if i == 0: continue
    pos = 0
    while pos < len(s):
        byte = s[pos]
        if byte in {"\xF5", "\xF6", "\xFA", "\xFC"}:
            if byte in {"\xF5", "\xFA"}:
                pos += 1
            target = (ord(s[pos+1]) << 8) + ord(s[pos+2])
            tarc = target >> 12
            tarp = target & 0xFFF
            if tarc >= len(segments):
                print "WARNING: {} {} -- jump to channel {} which does not exist".format(hex(ord(s[pos+1])), hex(ord(s[pos+2])), tarc+1)
                print "using current channel ({}) instead".format(i)
                tarc = i - 1
            tarst = convert_pointer(tarc, tarp)
            segments[i] = strmod(segments[i], pos+1, tarst)
            print "converting jump to ch{} p{} --> p{} {}".format(tarc, tarp, hex(ord(tarst[0])), hex(ord(tarst[1])))
            pos += 2
        elif byte in skipone:
            pos += 1
        elif byte in skiptwo:
            pos += 2
        elif byte in skipthree:
            pos += 3
        pos += 1

length = 0
for s in segments:
    length += len(s)
lengthb = chr(length & 0xFF) + chr(length >> 8)

segments[0] = strmod(segments[0], 0, lengthb)
segments[0] = strmod(segments[0], 2, "\x26\x00")
segments[0] = strmod(segments[0], 4, lengthb)

for i, c in enumerate(channels):
    segments[0] = strmod(segments[0], 6 + 2*i, convert_pointer(c >> 12, c & 0xFFF))

try:
    fout = open(source + "_data.bin", "wb")
except:
    raw_input("Couldn't open output file, press enter to close ")
    quit()

for s in segments:
    fout.write(s)
fout.close()

raw_input("Merge OK. Press enter to close ")
