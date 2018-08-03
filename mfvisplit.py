from shutil import copyfile
import StringIO
import random
from mfvitbl import notes, lengths, codes

skipone = {"\xC4", "\xC6", "\xCF", "\xD6", "\xD9", "\xDA", "\xDB", "\xDC", "\xDD", "\xDE", "\xDF", "\xE0",
            "\xE2", "\xE8", "\xE9", "\xEA", "\xF0", "\xF2", "\xF4", "\xFD", "\xFE"}
skiptwo = {"\xC5", "\xC7", "\xC8", "\xCD", "\xF1", "\xF3", "\xF7", "\xF8"}
skipthree = {"\xC9", "\xCB"}

source = raw_input("Please input the file name of your CLEAN music data"
                       "ROM dump, excluding _data.bin:\n> ").strip()

sourcefile = source + "_data.bin"

try:
    fin = open(sourcefile, 'rb')
except IOError:
    raw_input("Couldn't open input file. Press enter to quit. ")
    quit()

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
    
fin.seek(0,2)
size = fin.tell()
assert size <= 0xFFFF

fin.seek(2)
if read_word(fin) != 0x26:
    raw_input("Please clean me2 dump before unrolling")
    quit()

fin.seek(6)
channels = []
for c in xrange(0,16):
    channels.append(read_word(fin))

pieces = [""]
current, skip = 0, 0
jumppoints = {}
origins = [0x26]

pos = 0x26
fin.seek(pos)
while pos < size:
    byte = fin.read(1)
    if not byte: break

    pieces[current] += byte
    if byte in {"\xF6", "\xF5", "\xFA"} and not skip:
        if byte in ["\xF5", "\xFA"]: pieces[current] += fin.read(1)
        pos = fin.tell()
        dest = read_word(fin)
        jumppoints[pos] = dest
        pieces[current] += chr(dest & 0xFF) + chr((dest & 0xFF00) >> 8)
        fin.seek(pos+2)

    if skip:
        skip -= 1
    else:        
        if byte in skipone: skip = 1
        elif byte in skiptwo: skip = 2
        elif byte in skipthree: skip = 3
        elif byte in ["\xF6", "\xEB"]:
            origins.append(fin.tell())
            pieces.append("")
            current += 1
    pos = fin.tell()
    
def convert_jump(old_dest, warn = False):
    global pieces
    global origins
    remainder = old_dest
    target = 0
    
    for s in pieces:
        if remainder >= len(s):
            target += 1
            remainder -= len(s)
    for i, o in enumerate(origins):
        x = i
        if old_dest < o:
            x = i - 1
            break
    remainder = old_dest - origins[x]
    
    if warn and remainder >= 0xFFF: print "warning!! sequence too long (>0xFFF), can't repack jump destinations"
    if warn and x >= 0xF: print "warning!! too many sequences (>0xF), can't repack jump destinations"
    return remainder + ( x << 12 )

for p in jumppoints:
    remainder = p
    target_piece = 0
    
    for s in pieces:
        if remainder >= len(s):
            target_piece += 1
            remainder -= len(s)
    for i, o in enumerate(origins):
        x = i
        if p < o:
            x = i - 1
            break 
    #print "jump point at {} {}".format(x+1, hex(p - origins[x]))
    dest = bytes(convert_jump(jumppoints[p],warn=True))
    print "{} {} {}".format(x, p - origins[x], ord(dest[0])+ord(dest[1]))
    pieces[x] = strmod(pieces[x], p - origins[x], dest)
    #pieces[target_piece] = pieces[target_piece][:remainder] + chr((dest & 0xFF00) >> 8) + chr(dest & 0xFF) + pieces[target_piece][remainder+2:]

try:
    fout = open(source + "00", 'wb')
except IOError:
    raw_input("Couldn't open output file '{}'. Press enter to quit. ".format(fn))
    quit()
for c in channels:
    fout.write(bytes(convert_jump(c)))
fout.close()

scribe = StringIO.StringIO()
asterisks = list("!@#$%^&*+=")
stars = asterisks[:]
random.shuffle(asterisks)
    
for i, s in enumerate(pieces):
    #record it
    ppos, xpos = 0, 0
    noteline, starline, headline = "", "", ""
    fxlines = [" "]
    measure = "|..........." + "-..........." * 3
    star = "*"
    lastcode = 0
    nest = 0
    looping, lpos = [0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0]
    while ppos < len(s):
        byte = ord(s[ppos])
        if byte <= 0xC3:
            note = notes[int(byte / 14)]
            writepos = int(xpos / 4)
            xpos += lengths[byte % 14]
            noteline = strmod(noteline, writepos, note)
        elif byte in codes:
            writepos = int(xpos/4)
            e = ppos + codes[byte][0]
            args = ""
            while ppos < e:
                ppos += 1
                argval = ord(s[ppos])
                args = args + " " + hex(argval)
            if writepos != lastcode:
                if not stars: stars = asterisks[:]
                star = stars.pop()
                starline = strmod(starline, writepos, star)
            mycode = codes[byte][1]
            if mycode == "LoopEnd" and looping[nest]: mycode = "Loop{}".format([l for l in looping if l > 0])
            fxtxt = star + mycode + args
            for ix, l in enumerate(fxlines):
                nextline = False
                while len(fxlines[ix]) < writepos + len(fxtxt):
                    fxlines[ix] = fxlines[ix] + " "
                if len(set(fxlines[ix][writepos:writepos+len(fxtxt)])) > 1: nextline = True
                if not nextline:
                    fxlines[ix] = strmod(fxlines[ix], writepos, fxtxt)
                    break
            lastcode = writepos
            if byte == 0xE2:
                nest += 1
                looping[nest] = argval
                lpos[nest] = ppos
            elif byte == 0xE3 and nest:
                if looping[nest] > 0:
                    looping[nest] -= 1
                    ppos = lpos[nest]
                else:
                    looping[nest] = 0
                    lpos[nest] = 0
                    nest -= 1
        ppos += 1
        if len(set(fxlines[-1])) > 1: fxlines.append(" ")
        if (len(headline) <= len(noteline)) or (len(headline) <= len(starline)):
            headline = headline + measure
            headline = strmod(headline, writepos, hex(ppos)[2:])
    while len(headline) < len(noteline):
        headline = headline + measure
    headline = strmod(headline, 0, "** SEGMENT {}".format(i+1))
    scribe.write(headline + "\n")
    scribe.write(noteline + "\n")
    scribe.write(starline + "\n")
    for l in fxlines: scribe.write(l + "\n")
    
    #write it
    if len(s):
        fn = source + "%02d" % (i+1)
        try:
            fout = open(fn, 'wb')
        except IOError:
            raw_input("Couldn't open output file '{}'. Press enter to quit. ".format(fn))
            quit()
        fout.write(s)
        fout.close()

# calculate channel duration pre- and post-loop
for i, c in enumerate(channels):
    startpoint = convert_jump(c)
    seg = startpoint >> 12
    ppos = startpoint & 0xFFF
    xpos = 0
    nest = 0
    jumppoint, endpoint = 0, 0
    looping, lpos = [0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0]
    jdescr, edescr = "", ""
    keepgoing = True
    while keepgoing:
        if len(pieces) <= seg:
            keepgoing = False
            break
        if ppos >= len(pieces[seg]):
            keepgoing = False
            if jumppoint:
                edescr += "Ended without re-jumping at "
                endpoint = xpos
            else:
                jdescr += "Ended without jumping at "
                jumppoint = xpos
            break
        byte = ord(pieces[seg][ppos])
        if byte <= 0xC3:
            xpos += lengths[byte % 14]
        elif byte == 0xE2:
            ppos += 1
            nest += 1
            looping[nest] = ord(pieces[seg][ppos])
            lpos[nest] = ppos
        elif byte == 0xE3 and nest:
            looping[nest] -= 1
            ppos = lpos[nest]
            if looping[nest] <= 0:
                looping[nest] = 0
                lpos[nest] = 0
                nest -= 1
        elif byte == 0xF6:
            if not jumppoint:
                jdescr += "First jump occurs after "
                jumppoint = xpos
                args = [ord(pieces[seg][ppos+1]), ord(pieces[seg][ppos+2])]
                print map(hex, args)
                seg = args[0] >> 4
                ppos = args[1] + ((args[0] & 0xF) << 8)
                continue
            else:
                edescr += "Loop lasts "
                endpoint = xpos - jumppoint
                keepgoing = False
        elif byte in codes:
            ppos += codes[byte][0]
        ppos += 1
    print "CHANNEL {}:".format(i+1)
    print jdescr + "{} frames / {} beats / {} measures / {} phrases".format(jumppoint, jumppoint/48, jumppoint/192, jumppoint/768)
    print edescr + "{} frames / {} beats / {} measures / {} phrases".format(endpoint, endpoint/48, endpoint/192, endpoint/768)
    print
    
            
try:
    sout = open(source + ".txt", 'w')
    sout.write(scribe.getvalue())
    sout.close()
except IOError:
    print scribe

scribe.close()

for p in sorted(jumppoints): print "{}   {}    {}".format(hex(p), hex(jumppoints[p]), hex(convert_jump(jumppoints[p])))
raw_input("Press enter to quit. ")
