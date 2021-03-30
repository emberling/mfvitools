import os
import sys
import traceback

DIR_BASE = "spcbrr"

def clean_end():
    print("Processing ended.")
    input("Press enter to close.")
    quit()
    
class Sample:
    def __init__(self, id, spc, dirloc):
        dirloc += id * 4
        
        self.id = id
        self.addr = int.from_bytes(spc[dirloc:dirloc+2], "little")
        self.loop_pos = int.from_bytes(spc[dirloc+2:dirloc+4], "little") - self.addr
        self.loop_flag = False
        self.warning = None
        # check for invalid locations
        if self.addr < 0x200:
            self.warning = "Sample address in zero page memory"
            self.data = bytearray()
            self.blocks = 0
            return
        # grab BRR data
        brr = bytearray()
        loc = self.addr
        while True:
            brr += spc[loc:loc+9]
            # END bit
            if spc[loc] & 1:
                # LOOP bit
                if spc[loc] & 0b10:
                    self.loop_flag = True
                    if self.loop_pos % 9:
                        self.warning = "Loop point misaligned with block boundaries"
                break
            
            loc += 9    
            if loc > (len(spc) - 9):
                self.warning = "Unterminated BRR"
                break
        self.data = brr
        self.blocks = len(self.data) // 9
        
#### main execution block

try:
    if len(sys.argv) >= 2:
        infilename = sys.argv[1]
    else:
        print("SPC filename:")
        infilename = input()
    
    try:
        with open(infilename, "rb") as f:
            spc = f.read()[0x100:]
    except IOError:
        print(f"couldn't open file {infilename}, aborting")
        clean_end()
        
    out_dir = os.path.join(DIR_BASE, os.path.splitext(os.path.basename(infilename))[0])
    
    while True:
        print("Maximum sample ID to rip (hex):")
        max_id = input()
        try:
            max_id = int(max_id, 16)
            break
        except ValueError:
            print("Invalid input, try again")
            
    spc_dir = spc[0x1005D] * 0x100
    samples = []
    for i in range(max_id):
        samp = Sample(i, spc, spc_dir)
        print(f"SRCN {i:02X}: ", end="")
        if samp.warning:
            print(f"{samp.warning} (loc {samp.addr:04X}, size {samp.blocks})")
        else:
            print(f"Sample found: loc {samp.addr:04X}, loop {samp.loop_pos:X}, size {samp.blocks}")
            samples.append(samp)
        
    if not samples:
        print("No files to write.")
        clean_end()
        
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        
    samplist = []
    for samp in samples:
        samplist.append((f"{samp.id:02X}", f"BRR{samp.id:02X}", f"@0x{samp.loop_pos:X}", "0000", "F 7 7 0 ", f"{{{samp.blocks}}}", f"idx{samp.id:02X} @ {samp.addr:04X}"))
        
    id_len = max([len(s[0]) for s in samplist])
    fn_len = max([len(s[1]) for s in samplist])
    lp_len = max([len(s[2]) for s in samplist])
    tn_len = max([len(s[3]) for s in samplist])
    nv_len = max([len(s[4]) for s in samplist])
    bk_len = max([len(s[5]) for s in samplist])
    tx_len = max([len(s[6]) for s in samplist])
    
    listfile = ""
    for i, samp in enumerate(samples):
        id, fn, loop, tune, env, block, text = samplist[i]
        listfile += f"{id:<{id_len}}: {fn:<{fn_len}}, {loop:<{lp_len}}, {tune:<{tn_len}}, {env:<{nv_len}}, {block:<{bk_len}} [   ] {text}\n"
        with open(os.path.join(out_dir, fn+".brr"), "wb") as f:
            f.write(samp.data)
        
    with open(os.path.join(out_dir, "spcbrr.txt"), "w") as f:
        f.write(listfile)
    print(f"Wrote listfile to {os.path.join(out_dir, 'spcbrr.txt')}")
    
    clean_end()
except SystemExit:
    pass
except:
    traceback.print_exc()
    input()