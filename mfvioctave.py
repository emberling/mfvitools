from mfvitbl import notes, lengths, codes
skipone = {"\xC4", "\xC6", "\xCF", "\xD6", "\xD9", "\xDA", "\xDB", "\xDC", "\xDD", "\xDE", "\xDF", "\xE0",
            "\xE2", "\xE8", "\xE9", "\xEA", "\xF0", "\xF2", "\xF4", "\xFD", "\xFE"}
skiptwo = {"\xC5", "\xC7", "\xC8", "\xCD", "\xF1", "\xF3", "\xF7", "\xF8"}
skipthree = {"\xC9", "\xCB"}

print "Quick and Dirty Octave Adjuster"
print
source = raw_input("Enter filename prefix: ")
print "INSTRUCTIONS: Enter an instrument number (in hex) and one or more + or - symbols"
print "WARNING: May cause havoc with or around loops"
print
print "Basic functionality: program changes TO or FROM the selected instrument will"
print "be bracketed by octave up/down commands. Explicit octave commands while the"
print "instrument is active will be raised or lowered."
print
print "Be careful! This operation is not its own inverse. Running multiple times"
print "will result in a morass of extraneous octave changes."
print
mode = raw_input("Change: ")

plus = len([c for c in mode if c == '+'])
minus = len([c for c in mode if c == '-'])
mode = "".join([c for c in mode.lower() if c in "1234567890abcdef"])
try:
    inst = int(mode, 16)
    assert inst <= 0x30
except:
    print "that input didn't work."
    raw_input("Exiting.. ")
    quit()

delta = plus - minus
print
if not delta:
    print "there's not much point to that, is there?"
    raw_input("Exiting.. ")
    quit()
if delta > 0:
    onstring = "\xD7" * delta
    offstring = "\xD8" * delta
    print "increasing {} by {}".format(hex(inst), delta)
else:
    onstring = "\xD8" * abs(delta)
    offstring = "\xD7" * abs(delta)
    print "decreasing {} by {}".format(hex(inst), delta)

print " ".join(map(hex, map(ord, onstring)))
print " ".join(map(hex, map(ord, offstring)))

    
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
        if byte in {"\xF5", "\xF6", "\xFC"}:
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
    active = False
    while loc < len(d):
        byte = d[loc]
        if byte in {"\xF5", "\xF6", "\xFC"}:
            if byte in {"\xF5", "\xFA"}:
                newdata += d[loc]
                loc += 1
            elif active:
                active = False
                newdata += offstring
            newdata += d[loc:loc+3]
            loc += 2
        elif byte == "\xDC":
            program = ord(d[loc+1])
            if active and program != inst:
                active = False
                newdata += offstring + d[loc:loc+2]
                for j, t in enumerate(targets):
                    if t >> 12 == i and t & 0xFFF > loc:
                        targets[j] += len(offstring)
            elif not active and program == inst:
                active = True
                newdata += onstring + d[loc:loc+2]
                for j, t in enumerate(targets):
                    if t >> 12 == i and t & 0xFFF > loc:
                        targets[j] += len(onstring)
            else:
                newdata += d[loc:loc+2]
            loc += 1
        elif byte == "\xD6" and active:
            newoct = ord(d[loc+1]) + delta
            while newoct < 0: newoct += 0xFF
            newdata += d[loc] + chr(newoct)
            loc += 1
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
        if byte in {"\xF5", "\xF6", "\xFC"}:
            if byte in {"\xF5", "\xFC"}:
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
        with open(source + "o%02d" % (i+1), 'wb') as f:
            f.write(d)
    except IOError:
        print "couldn't write file #{}".format(i)

raw_input("finished ")