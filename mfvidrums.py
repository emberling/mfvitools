from mfvitbl import notes, lengths, codes
skipone = {"\xC4", "\xC6", "\xCF", "\xD6", "\xD9", "\xDA", "\xDB", "\xDC", "\xDD", "\xDE", "\xDF", "\xE0",
            "\xE2", "\xE8", "\xE9", "\xEA", "\xF0", "\xF2", "\xF4", "\xFD", "\xFE"}
skiptwo = {"\xC5", "\xC7", "\xC8", "\xCD", "\xF1", "\xF3", "\xF7", "\xF8"}
skipthree = {"\xC9", "\xCB"}

print "Drum Mode Unroller"
print
print "NOTE: All drums will be automatically set to octave 5, adjust as necessary."
print "This program will attempt to set the octave back to its previous value"
print "after drum mode ends, but it may get confused, especially if octave"
print "changes during a loop."
print
print "As this is generally to be used with Chrono Trigger imports, 0xFA will be"
print "interpreted as a conditional jump (CT) instead of 'Clear Output Code' (FF6)"
source = raw_input("Enter filename prefix: ")
nextdrum = raw_input("Lowest free instrument slot (default 30): ")
try:
    nextdrum = int(nextdrum, 16)
except ValueError:
    nextdrum = 0x30
print "using slots beginning from {}".format(hex(nextdrum))

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

data = []
for index in xrange(1, 17):
    try:
        with open(source + "%02d" % (index), 'rb') as f:
            data.append(f.read())
    except IOError:
        pass
print "{} files found".format(len(data))

if not len(data):
    raw_input("Failed, exiting... ")
    
drumdb = {}

for i, d in enumerate(data):
    print "checking segment {}".format(i+1)
    loc = 0
    drum = False
    lastdrum = None
    targets = []
    newdata = ""
    # first we need to know all the jumps
    while loc < len(d):
        byte = d[loc]
        if byte in {"\xF5", "\xF6", "\xFA", "\xFC"}:
            if byte in {"\xF5", "\xFA"}:
                loc += 1
            targets.append((ord(d[loc+1]) << 8) + ord(d[loc+2]))
            loc += 2
        elif byte in skipone:
            loc += 1
        elif byte in skiptwo:
            loc += 2
        elif byte in skipthree:
            loc += 3
        loc += 1
    # then we can change stuff
    loc = 0
    octave = None
    while loc < len(d):
        byte = d[loc]
        if byte in {"\xF5", "\xF6", "\xFA", "\xFC"}:
            if byte in {"\xF5", "\xFA"}:
                newdata += d[loc]
                loc += 1
            newdata += d[loc:loc+3]
            loc += 2
        elif byte == "\xFB":
            drum = True
            lastdrum = None
            newdata += "\xD6\x05"
            for j, t in enumerate(targets):
                if t >> 12 == i and t & 0xFFF > loc:
                    targets[j] += 1
        elif byte == "\xFC":
            drum = False
            if octave:
                newdata += "\xD6" + chr(octave)
                n = 1
            else: n = -1
            for j, t in enumerate(targets):
                if t >> 12 == i and t & 0xFFF > loc:
                    targets[j] += n
        elif byte == "\xD6":
            octave = ord(d[loc+1])
            newdata += d[loc:loc+2]
            loc += 1
        elif byte == "\xD7" and octave:
            octave += 1
            newdata += d[loc]
        elif byte == "\xD8" and octave:
            octave -= 1
            newdata += d[loc]
        elif drum and ord(byte) <= 0xA7:
            thisdrum = int(ord(byte) / 14)
            if thisdrum not in drumdb:
                drumdb[thisdrum] = nextdrum
                nextdrum += 1
            if thisdrum != lastdrum:
                lastdrum = thisdrum
                newdata += "\xDC" + chr(drumdb[thisdrum])
                for j, t in enumerate(targets):
                    if t >> 12 == i and t & 0xFFF > loc:
                        targets[j] += 2
            newdata += d[loc]
        elif byte in skipone:
            newdata += d[loc:loc+2]
            loc += 1
        elif byte in skiptwo:
            newdata += d[loc:loc+3]
            loc += 2
        elif byte in skipthree:
            newdata += d[loc:loc+4]
            loc += 3
        else:
            newdata += d[loc]
        loc += 1
    # then we can update the jumps
    loc = 0
    while loc < len(newdata):
        byte = newdata[loc]
        if byte in {"\xF5", "\xF6", "\xFA", "\xFC"}:
            if byte in {"\xF5", "\xFA"}:
                loc += 1
            newdata = strmod(newdata, loc+1, bytes(targets.pop(0)))
            loc += 2
        elif byte in skipone:
            loc += 1
        elif byte in skiptwo:
            loc += 2
        elif byte in skipthree:
            loc += 3
        loc += 1
    data[i] = newdata
    
for i, d in enumerate(data):
    try:
        with open(source + "d%02d" % (i+1), 'wb') as f:
            f.write(d)
    except IOError:
        print "couldn't write file #{}".format(i)

raw_input("finished ")