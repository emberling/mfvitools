try:
    import mfvitbl
except ImportError:
    from . import mfvitbl

# Multiply total length by this amount to compensate for any slowdown, etc
FUDGE_FACTOR = 1.005
MAX_TICKS = 255 * 48 * 999
VERBOSE = False

def measure(ticks):
    measures = ticks // 192
    beats = 1 + (ticks % 192) // 48
    ticks = (ticks % 192) % 48
    return f"{measures}.{beats}.{ticks}"
    
class TrackState():
    def __init__(self, id, data, start, addr_base):
        self.addr_base = addr_base
        self.loc = self.addr(start)
        self.stopped = False
        self.data = data
        self.segment = 0
        self.ticks = 0
        self.delta = 0
        self.id = id
        
        self.stack = []
        self.jump_records = {}
        self.last_new_jump = None
        self.jump_records[None] = []
        
    def stop(self):
        self.stopped = True
        self.delta = 0
        self.stack = []
        
    def get_state(self):
        return (self.loc, self.stopped, self.delta, list(self.stack))
        
    def tick(self):
        if not self.stopped:
            self.delta -= 1
            self.ticks += 1
            if self.delta < 0:
                print("somehow, delta < 0")
            if self.delta == 0:
                self.loc += 1
            
    def addr(self, address):
        # Convert a raw address to the equivalent index in "data"
        address -= self.addr_base
        if address < 0:
            address += 0x10000
        return address + 0x24
        
    def acquire_delta(self):
        # Advance the track pointer until the next event which has a
        # nonzero duration (delta-time).
        # Also, return any global tempo changes encountered during that time.
        tempo_changes = [None, None, None]
        if self.stopped or self.delta > 0:
            return tempo_changes
        
        while True:
            loc = self.loc
            bytecode = self.data[loc]
            if bytecode < 0xC4:
                if not self.delta:
                    self.delta = mfvitbl.lengths[bytecode % 14]
                #print(f"[{self.id}] {bytecode:02X} -> delta {self.delta}")
                return tempo_changes
            #print(f"[{self.id}] {self.loc+0x1C02:04X} {bytecode:02X}")
            
            cmdlen = 1
            if bytecode in mfvitbl.codes:
                cmdlen += mfvitbl.codes[bytecode][0]
            next = loc + cmdlen
        
            if bytecode == 0xE2:
                # Loop start
                count = 1
                repeats = self.data[loc+1]
                target = self.loc + 2
                self.stack.append((count, repeats, target))
                #print(f"[{self.id}] loop start")
                
                if len(self.stack) > 4:
                    print(f"[{self.id}] {self.loc+0x1C02:04X} WARNING: Loop stack overflow")
                    self.stack = self.stack[-4:]
                    
            elif bytecode == 0xE3:
                # Loop end
                count, repeats, target = self.stack.pop()
                repeats -= 1
                count += 1
                if repeats >= 0:
                    next = target
                    self.stack.append((count, repeats, target))
                #print(f"[{self.id}] loop end")
                    
            elif bytecode in [0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFD, 0xFE, 0xFF]:
                # End track
                self.stop()
                return tempo_changes
                
            elif bytecode == 0xE8:
                # Set next note duration
                self.delta = self.data[loc+1]
                
            elif bytecode == 0xF0:
                # Set tempo
                tempo_changes[0] = self.data[loc+1]
                
            elif bytecode == 0xF1:
                # Tempo fade
                tempo_changes[1] = self.data[loc+1]
                tempo_changes[2] = self.data[loc+2]
                
            elif bytecode == 0xF5 and self.stack:
                # Loop break / volta
                condition = self.data[loc+1]
                vtarget = self.addr(int.from_bytes(self.data[loc+2:loc+4], "little"))
                count, repeats, ltarget = self.stack.pop()
                if condition == count:
                    next = vtarget
                if condition != count or repeats > 0:
                    self.stack.append((count, repeats, ltarget))
                if VERBOSE:
                    print(f"[{self.id}] {self.loc+0x1C02:04X} volta {count}/{condition} :: {self.stack}")
                    if condition == count:
                        print(f"    Jumping to {vtarget+0x1C02:04X}")
                
            elif bytecode == 0xF6:
                # Jump
                target = self.addr(int.from_bytes(self.data[loc+1:loc+3], "little"))
                next = target
                if VERBOSE:
                    print(f"[{self.id}] {self.loc+0x1C02:04X} jump to {target+0x1C02:04X}")
                    print(f"    {self.ticks - self.segment} ticks since start or last jump")
                self.segment = self.ticks
                
                jump_record = (loc, target, tuple(self.stack))
                #print(jump_record)
                    
                if jump_record in self.jump_records:
                    self.jump_records[jump_record].append(self.ticks)
                else:
                    self.jump_records[jump_record] = [self.ticks]
                    self.last_new_jump = jump_record
                #print(f"{self.jump_records=}")
                
            self.loc = next
        
            
# Read an AKAO4 (FF6) binary sequence and return its approximate length in seconds
def mfvi_trace(data, iterations=2, long_header=False):
    if long_header:
        data = data[2:]
    
    addr_base = int.from_bytes(data[0:2], "little")
    addr_end =  int.from_bytes(data[2:4], "little")
    tracks = []
    tempo_sets = {}
    tempo_fades = {}
    loop_ticks = {}
    loop_lengths = {}
    initial_segments = {}
    for trackid in range(8):
        loc = 4 + trackid * 2
        addr = int.from_bytes(data[loc:loc+2], "little")
        track = TrackState(trackid+1, data, addr, addr_base)
        if addr == addr_end:
            track.stop()
        tracks.append(track)
    
    for track in tracks:
        ticks = 0
        tempo_sets[track.id] = {}
        tempo_fades[track.id] = {}
        while ticks < MAX_TICKS:
            tempo_cmds = track.acquire_delta()
            
            # Test if we've encountered the endpoint
            if track.stopped or len(track.jump_records[track.last_new_jump]) >= iterations:
                if track.stopped:
                    segment = 0
                elif iterations < 2:
                    segment = track.jump_records[track.last_new_jump][0]
                else:
                    segment = track.jump_records[track.last_new_jump][-1] - track.jump_records[track.last_new_jump][-2]
                print(f"breaking track {track.id} at {ticks} with delta {segment} ({measure(segment)})")
                loop_ticks[track.id] = segment
                loop_lengths[track.id] = segment
                initial_segments[track.id] = ticks - segment
                break
            
            # Handle tempo changes
            if tempo_cmds[0]:
                tempo_sets[track.id][ticks] = tempo_cmds[0]
            if tempo_cmds[2]:
                tempo_fades[track.id][ticks] = (tempo_cmds[1], tempo_cmds[2])
                
            # Advance time
            ticks += 1
            track.tick()
                    
    # Extend loops until everything is in phase
    longest_ticks = max(loop_ticks.values())
    while longest_ticks < MAX_TICKS:
        shorter_track_found = False
        for id in loop_ticks:
            while 0 < loop_ticks[id] < longest_ticks:
                loop_ticks[id] += loop_lengths[id]
                longest_ticks = max(loop_ticks[id], longest_ticks)
                shorter_track_found = True
            print(f" {loop_ticks[id]:5}  ", end="")
        print()
        if not shorter_track_found:
            print(longest_ticks)
            break
    total_ticks = longest_ticks + max(initial_segments.values())
    print(f"{total_ticks=}")
    
    # Figure out tempo over all ticks
    # first, pull out tempo commands onto a unified timeline
    tempo_timeline = {}
    for id in tempo_sets:
        for tick, tempo in tempo_sets[id].items():
            tempo_timeline[tick] = (tempo, None, None)
            if tick >= initial_segments[id]:
                vtick = tick + loop_lengths[id]
                while vtick < total_ticks:
                    tempo_timeline[tick] = (tempo, None, None)
                    vtick += loop_lengths[id]
    for id in tempo_fades:
        for tick, (dur, target) in tempo_fades[id].items():
            tempo = tempo_timeline[tick][0] if tick in tempo_timeline else None
            tempo_timeline[tick] = (tempo, dur, target)
            if tick >= initial_segments[id]:
                vtick = tick + loop_lengths[id]
                while vtick < total_ticks:
                    tempo = tempo_timeline[tick][0] if tick in tempo_timeline else None
                    tempo_timeline[tick] = (tempo, dur, target)
                    vtick += loop_lengths[id]
    for k in sorted(tempo_timeline):
        print(f"{k:5}:: {tempo_timeline[k]}")
            
    tempo = 0
    tempo_increment = 0
    tick_length = 1.0
    tempo_target = None
    duration = 0.0
    for ticks in range(total_ticks):
        prev_tempo = tempo
        if tempo_target:
            tempo += tempo_increment
            if ((tempo_increment > 0 and tempo >= tempo_target) or
                    (tempo_increment < 0 and tempo <= tempo_target)):
                tempo = tempo_target
                tempo_target = None
                tempo_increment = 0
        if ticks in tempo_timeline:
            tt, dur, target = tempo_timeline[ticks]
            if tt:
                tempo = tt
            if target:
                tempo_increment = (target - tempo) / dur
                tempo_target = target
        if prev_tempo != tempo:
            bpm = 60000000.0 / (48 * (125 * 0x27)) * (tempo / 256.0)
            tick_length = 1 / (bpm * 48 / 60)
        duration += tick_length
    print(duration)
    return min(duration, 999)
            
# Read an AKAO4 (FF6) binary sequence and return its approximate length in seconds
# (the time it takes to reach an identical state for the nth time)     
def _mfvi_trace(data, iterations=2, long_header=False):
    if long_header:
        data = data[2:]
    
    addr_base = int.from_bytes(data[0:2], "little")
    addr_end =  int.from_bytes(data[2:4], "little")
    tick = 0
    tracks = []
    tick_tempos = {}
    states = []
    loops_found = 0
    tempo = 1
    tempo_increment = 0
    tempo_target = None
    song_length = 0
    prev_tempo = 0
    tick_length = 0
    for trackid in range(8):
        loc = 4 + trackid * 2
        addr = int.from_bytes(data[loc:loc+2], "little")
        track = TrackState(trackid+1, data, addr, addr_base)
        if addr == addr_end:
            track.stop()
        tracks.append(track)
            
    while tick < MAX_TICKS:
        # Advance each track until delta is nonzero
        for track in tracks:
            tempo_changes = track.acquire_delta()
            
            # Handle tempo changes
            new_tempo, tempo_fade, tempo_new_target = tempo_changes
            if new_tempo:
                tempo = new_tempo
                tick_tempos[tick] = tempo
                tempo_target = None
            if tempo_target:
                tempo += tempo_increment
                if ((tempo_target <= tempo and tempo_increment >= 0) or 
                        (tempo_target >= tempo and tempo_increment <= 0)):
                    tempo = tempo_target
                    tempo_target = None
                tick_tempos[tick] = tempo
            if tempo_fade:
                tempo_target = tempo_new_target
                tempo_increment = (tempo_new_target - tempo) / tempo_fade
            
        # Compare and record states once everything has a delta
        state = [tempo, tempo_increment, tempo_target]
        state += [track.get_state() for track in tracks]
        if state in states:
            loops_found += 1
            if loops_found >= iterations:
                print(tick_tempos)
                break
            states = []
        if VERBOSE:
            print(f"{tick} {state}")
        else:
            if tick % (192 * 32) == 0:
                print()
            if tick % (192 * 8) == 0:
                print(" ", end="", flush=True)
            if tick % 192 == 0:
                print(".", end="", flush=True)
        
        states.append(state)
        tick += 1
        for track in tracks:
            track.tick()
    
        # Calc tempo and increment duration
        if tempo != prev_tempo:
            print(f"Tempo change at {tick} to {tempo}")
            # tempo formula from https://github.com/vgmtrans/vgmtrans/blob/master/src/main/formats/AkaoSnesSeq.cpp
            bpm = 60000000.0 / (48 * (125 * 0x27)) * (tempo / 256.0)
            tick_length = 1 / (bpm * 48 / 60)
            print(f"{bpm=} {tick_length=}")
            prev_tempo = tempo
        song_length += tick_length * FUDGE_FACTOR
        if song_length > 999:
            break
            
    # After tracing entire song, recalculate tick lengths
    song_length = 0
    tempo = 1
    for i in range(tick):
        if i in tick_tempos:
            tempo = tick_tempos[i]
            print(f"Tempo change at {i} to {tempo}")
        # tempo formula from https://github.com/vgmtrans/vgmtrans/blob/master/src/main/formats/AkaoSnesSeq.cpp
            bpm = 60000000.0 / (48 * (125 * 0x27)) * (tempo / 256.0)
            tick_length = 1 / (bpm * 48 / 60)
            print(f"{bpm=} {tick_length=}")
        song_length += tick_length * FUDGE_FACTOR
    print(f"Song length {int(song_length // 60)}:{round(song_length % 60):02} ({song_length} sec.)")
    
    return min(song_length, 999)
        
if __name__ == "__main__":
    import sys
    
    with open(sys.argv[1], "rb") as f:
        spc = f.read()
        
    data = spc[0x1D00:0x4900]
    mfvi_trace(data)
    