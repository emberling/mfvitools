import math
#import simpleaudio as sa
from pydub import AudioSegment, effects
#import pydub.playback as playback
#import pygame
import sounddevice as sd
import numpy as np
#from threading import Thread

#pygame.mixer.pre_init(frequency=32000, size=-16, channels=1)
#pygame.init()

sd.default.samplerate = 32000
sd.default.channels = 1

# class SoundThread(Thread):
    # def __init__(self):
        # Thread.__init__(self)
        # self.stream = sd.OutputStream(dtype='int16')
        # self.stream.start()
        
    # def __del__(self):
        # self.stream.stop()
        # Thread.__del__(self)
        
    # def play(self, sound):
        # self.buffer = sound[self.stream.write_available()
        # self.stream.write(sound)
        
# class Mixer:
    # def __init__(self):
        # threads = []
        # for i in range(8):
            # threads.append(SoundThread())
            
    # def play(self, sound):
        
class Sample:
    def __init__(self, brr):
        self.decode_brr(brr)
        self.scale = 1.0
    
    def play(self, note=None, pmod=None, vxpitch=None, scale=None):
        #TODO note, pmod, vxpitch
        if not scale: scale = self.scale
        # resample with pydub
        aseg = AudioSegment(self.data, sample_width=2, channels=1, frame_rate=32000)
        aseg = resample_aseg(aseg, 2.0)
        aseg = resample_aseg(aseg, scale)
        # play with sounddevice
        a = np.frombuffer(aseg.raw_data, dtype=np.int16)
        sd.play(a, 32000, blocking=False, latency='low')
    
    def play_tone(self, tone, scale=None):
        if not scale: scale = self.scale
        # tone is +/- semitones from A5
        scale = ((2**(1/12))**tone)*scale
        self.play(scale=scale)
        
    def set_pmod(self, pmod, mode="AKAO4"):
        if tune < 0x8000: tune += 0x10000
        self.scale = tune / 65536
    
    def get_note(self, pmod=None, vxpitch=None, scale=None):
        if not scale: scale = self.scale
        delta = math.log10(scale) / math.log10(2) * 12
        cents, tones = math.modf(delta)
        if cents < -0.5:
            cents += 1
            tones -= 1
        key = noteToKey(ROOT_NOTE - int(round(tones)))
        return key
        
    def decode_brr(self, brr):
        pos = 0
        wyrds = []
        last_wyrd, lastest_wyrd = 0, 0
        pcm = bytearray()
        while pos < len(brr)-9:
            block = brr[pos:pos+9]
            header = block[0]
            nybbles = []
            for i in range(1,9):
                nybbles.append(block[i] >> 4)
                nybbles.append(block[i] & 0b1111)
            end = header & 0b1
            loop = (header & 0b10) >> 1
            filter = (header & 0b1100) >> 2
            shift = header >> 4
            for n in nybbles:
                if n >= 8: n -= 16
                if shift <= 0x0C:
                    wyrd = (n << shift) >> 1
                else: wyrd = 1<<11 if n >= 0 else (-1)<<11
                if filter == 1:
                    wyrd += last_wyrd + ((-last_wyrd) >> 4)
                elif filter == 2:
                    wyrd += (last_wyrd << 1) + ((-((last_wyrd << 1) + last_wyrd)) >> 5) - lastest_wyrd + (lastest_wyrd >> 4)
                elif filter == 3:
                    wyrd += (last_wyrd << 1) + ((-(last_wyrd + (last_wyrd << 2) + (last_wyrd << 3))) >> 6) - lastest_wyrd + (((lastest_wyrd << 1) + lastest_wyrd) >> 4)
                if wyrd > 0x7FFF: wyrd = 0x7FFF
                elif wyrd < -0x8000: wyrd = -0x8000
                if wyrd > 0x3FFF: wyrd -= 0x8000
                elif wyrd < -0x4000: wyrd += 0x8000
                
                lastest_wyrd = last_wyrd
                last_wyrd = wyrd
                pcm.extend(wyrd.to_bytes(4, byteorder='little', signed=True))
            pos += 9
            if end: break
        self.data = pcm

def play_brr(brr, scale=1.0):
    # resample with pydub
    aseg = AudioSegment(decode_brr(brr), sample_width=2, channels=1, frame_rate=32000)
    aseg = resample_aseg(aseg, 2.0)
    aseg = resample_aseg(aseg, scale)
    
    # play with simpleaudio
    #sa.play_buffer(aseg.raw_data, 1, 2, 32000)

    # play with pygame
    #s = pygame.mixer.Sound(buffer=aseg.raw_data)
    #pygame.mixer.Sound.play(s)
    
    # play with sounddevice
    a = np.frombuffer(aseg.raw_data, dtype=np.int16)
    sd.play(a, 32000, blocking=False, latency='low')
    #sout.play(a)
    
def resample_aseg(aseg, scale=1.0):
    newseg = aseg._spawn(aseg.raw_data, overrides={"frame_rate": int(aseg.frame_rate * scale)})
    return newseg.set_frame_rate(32000)

def noteToKey(note):
    octave = note // 12
    key = semitone_table[note % 12]
    return "{}{}".format(key, octave)
    
semitone_table = {
    0: "C" ,
    1: "C+",
    2: "D" ,
    3: "D+",
    4: "E" ,
    5: "F" ,
    6: "F+",
    7: "G" ,
    8: "G+",
    9: "A" ,
    10:"A+",
    11:"B" 
    }
    
#sout = SoundThread()
#mixer = Mixer()