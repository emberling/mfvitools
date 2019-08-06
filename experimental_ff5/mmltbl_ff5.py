
note_tbl = {
    "c": 0x0,
    "d": 0x2,
    "e": 0x4,
    "f": 0x5,
    "g": 0x7,
    "a": 0x9,
    "b": 0xB,
    "^": 0xC,
    "r": 0xD }
    
length_tbl = { 
    1   : (0, 0xC0),
    "2.": (1, 0x90),
    2   : (2, 0x60),
    3   : (3, 0x40),
    "4.": (4, 0x48),
    4   : (5, 0x30),
    6   : (6, 0x20),
    "8.": (7, 0x24),
    8   : (8, 0x18),
    12  : (9, 0x10),
    16  : (10, 0x0C),
    24  : (11, 0x08),
    32  : (12, 0x06),
    48  : (13, 0x04),
    64  : (14, 0x03) }

r_length_tbl = {
    0: "1",
    1: "2.",
    2: "2",
    3: "3",
    4: "4.",
    5: "4",
    6: "6",
    7: "8.",
    8: "8",
    9: "12",
    10: "", #default
    11: "24",
    12: "32",
    13: "48",
    14: "64" }

CMD_END_TRACK = "\xFE"
CMD_END_LOOP = "\xFA"
CMD_JUMP_IF_LOOP = "\xF9"
CMD_CONDITIONAL_JUMP = "\xFB"

command_tbl = {
    ("@", 1) : 0xEA, #program
    ("|", 1) : 0xEA, #program (hex param)
    ("%a", 0): 0xEF, #reset ADSR
    ("%a", 1): 0xEB, #set attack
    #("%b", 1): 0xF7, #echo feedback (rs3)
    #("%b", 2): 0xF7, #echo feedback (ff6)
    ("%c", 1): 0xDD, #noise clock
    #("%d0", 0): 0xFC,#drum mode off (rs3)
    #("%d1", 0): 0xFB,#drum mode on (rs3)
    ("%e0", 0): 0xE3,#disable echo
    ("%e1", 0): 0xE2,#enable echo
    #("%f", 1): 0xF8, #filter (rs3)
    #("%f", 2): 0xF8, #filter (ff6)
    #("%g0", 0): 0xE7,#disable roll (enable gaps between notes)
    #("%g1", 0): 0xE6,#enable roll (disable gaps between notes)
    #("%k", 1): 0xF6 - jump to marker, segment continues
    ("%k", 1): 0xE7, #set transpose
    #("%l0", 0): 0xE5,#disable legato 
    #("%l1", 0): 0xE4,#enable legato
    ("%n0", 0): 0xDF,#disable noise
    ("%n1", 0): 0xDE,#enable noise
    ("%p0", 0): 0xE1,#disable pitch mod
    ("%p1", 0): 0xE0,#enable pitch mod
    ("%r", 0): 0xEF, #reset ADSR
    ("%r", 1): 0xEE, #set release
    ("%s", 0): 0xEF, #reset ADSR
    ("%s", 1): 0xED, #set sustain
    ("%v", 1): 0xF5, #set echo volume
    ("%v", 2): 0xF6, #echo volume envelope
    ("%x", 1): 0xF8, #set master volume
    ("%y", 0): 0xEF, #reset ADSR
    ("%y", 1): 0xEC, #set decay
    ("%z", 2): 0xF7, #echo feedback and filter (ff5)
    #("j", 1): 0xF5 - jump out of loop after n iterations
    #("j", 2): 0xF5 - jump to marker after n iterations
    ("k", 1): 0xE9,  #set detune
    ("m", 0): 0xD8,  #disable vibrato
    ("m", 1): 0xE8,  #add to transpose
    ("m", 2): 0xD6,  #pitch envelope (portamento)
    ("m", 3): 0xD7,  #enable vibrato
    ("o", 1): 0xE4,  #set octave
    ("p", 0): 0xDC,  #disable pan sweep
    ("p", 1): 0xD4,  #set pan
    ("p", 2): 0xD5,  #pan envelope
    ("p", 3): 0xDB,  #pansweep
    #("s0", 1): 0xE9, #play sound effect with voice A
    #("s1", 1): 0xEA, #play sound effect with voice B
    ("t", 1): 0xF3,  #set tempo
    ("t", 2): 0xF4,  #tempo envelope
    #("u0", 0): 0xFA, #clear output code
    #("u1", 0): 0xF9, #increment output code
    ("v", 0): 0xDA,  #disable tremolo
    ("v", 1): 0xD2,  #set volume
    ("v", 2): 0xD3,  #volume envelope
    ("v", 3): 0xD9,  #set tremolo
    #("&", 1): 0xE8,  #add to note duration
    ("<", 0): 0xE5,  #increment octave
    (">", 0): 0xE6,  #decrement octave
    ("[", 0): 0xF0,  #start loop
    ("[", 1): 0xF0,  #start loop
    ("]", 0): 0xF1  #end loop
    #(":", 1): 0xFC - jump to marker if event signal is sent
    #(";", 1): 0xF6 - jump to marker, end segment
    }

byte_tbl = {
    0xC4: (1, "v"),
    0xC5: (2, "v"),
    0xC6: (1, "p"),
    0xC7: (2, "p"),
    0xC8: (2, "m"),
    0xC9: (3, "m"),
    0xCA: (0, "m"),
    0xCB: (3, "v"),
    0xCC: (0, "v"),
    0xCD: (2, "p0,"),
    0xCE: (0, "p"),
    0xCF: (1, "%c"),
    0xD0: (0, "%n1"),
    0xD1: (0, "%n0"),
    0xD2: (0, "%p1"),
    0xD3: (0, "%p0"),
    0xD4: (0, "%e1"),
    0xD5: (0, "%e0"),
    0xD6: (1, "o"),
    0xD7: (0, "<"),
    0xD8: (0, ">"),
    0xD9: (1, "%k"),
    0xDA: (1, "m"),
    0xDB: (1, "k"),
    0xDC: (1, "@"),
    0xDD: (1, "%a"),
    0xDE: (1, "%y"),
    0xDF: (1, "%s"),
    0xE0: (1, "%r"),
    0xE1: (0, "%y"),
    0xE2: (1, "["),
    0xE3: (0, "]"),
    0xE4: (0, "%l1"),
    0xE5: (0, "%l0"),
    0xE6: (0, "%g1"),
    0xE7: (0, "%g0"),
    0xE8: (1, "&"),
    0xE9: (1, "s0"),
    0xEA: (1, "s1"),
    0xEB: (0, "\n;"),
    0xF0: (1, "t"),
    0xF1: (2, "t"),
    0xF2: (1, "%v"),
    0xF3: (2, "%v"),
    0xF4: (1, "%x"),
    0xF5: (3, "j"),
    0xF6: (2, "\n;"),
    0xF7: (2, "%b"),
    0xF8: (2, "%f"),
    0xF9: (0, "u1"),
    0xFA: (0, "u0"),
    0xFB: (0, '"'),
    0xFC: (2, ":"),
    0xFD: (1, "{FD}")
   }

equiv_tbl = {   #Commands that modify the same data, for state-aware modes (drums)
                #Treats k as the same command as v, though # params is not adjusted
    "v0,0": "v0",
    "p0,0": "p0",
    "v0,0,0": "v",
    "m0,0,0": "m",
    "|0": "@0",
    "%a": "%y",
    "%s": "%y",
    "%r": "%y",
    "|": "@0",
    "@": "@0",
    "o": "o0",
    }