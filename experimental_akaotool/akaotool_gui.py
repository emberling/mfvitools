#!/usr/bin/env python3
VERSION = "19.03.16-pre"

import wx, os, traceback, math, re
from akaotool import Database
from akaotool import get_bgm_name_by_id, hexify, zeropad, bgmidx, insidx
from pubsub import pub
from preview import play_brr, Sample

#TEMPORARY
from mml2mfvi import mml_to_akao

ADDRESSMODE = 0xC00000

def warn(text):
    warning = wx.MessageDialog(frame, text, "Alert", wx.OK)
    warning.ShowModal()
    warning.Destroy()    
pub.subscribe(warn, "warning")
        
instrument_categories = {
   -2: ("overflow",             wx.Colour(150,150,150) ),
   -1: ("empty",                wx.Colour(224,224,224) ),
    0: ("undefined",            wx.Colour(245,245,245) ),
    1: ("miscellaneous",        wx.Colour(230,225,220) ),
    2: ("other perc.",          wx.Colour(200,210,215) ),
    3: ("drumset perc.",        wx.Colour(238,221,229) ), #330
    4: ("pitched perc.",        wx.Colour(199,192,206) ), #270
    5: ("plucked strings",      wx.Colour(149,233,233) ), #180
    6: ("bowed strings",        wx.Colour(233,191,149) ), #30
    7: ("amplified guitars",    wx.Colour(233,149,149) ), #0
    8: ("chromatic perc.",      wx.Colour(198,198,236) ), #240
    9: ("organs & synths",      wx.Colour(212,170,212) ), #300
    10: ("brass",               wx.Colour(233,233,149) ), #60
    11: ("flutes",              wx.Colour(200,236,200) ), #120
    12: ("reeds",               wx.Colour(191,233,149) ), #90
    13: ("voices",              wx.Colour(149,233,192) ),  #150
    14: ("pianos & zithers",    wx.Colour(159,201,223) ) #210
    }
    
attack_table = {
    0: 4100,
    1: 2600,
    2: 1500,
    3: 1000,
    4: 640,
    5: 380,
    6: 260,
    7: 160,
    8: 96,
    9: 64,
    10: 40,
    11: 24,
    12: 16,
    13: 10,
    14: 6,
    15: 0
    }
    
decay_table = {
    0: 1200,
    1: 740,
    2: 440,
    3: 290,
    4: 180,
    5: 110,
    6: 74,
    7: 37
    }
    
release_table = {
    1: 38000,
    2: 28000,
    3: 24000,
    4: 19000,
    5: 14000,
    6: 12000,
    7: 9400,
    8: 7100,
    9: 5900,
    10: 4700,
    11: 3500,
    12: 2900,
    13: 2400,
    14: 1800,
    15: 1500,
    16: 1200,
    17: 880,
    18: 740,
    19: 590,
    20: 440,
    21: 370,
    22: 290,
    23: 220,
    24: 180,
    25: 150,
    26: 110,
    27: 92,
    28: 74,
    29: 55,
    30: 37,
    31: 28
    }
    
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
    
key_tone_table = {
    "z": -21,
    "s": -20,
    "x": -19,
    "d": -18,
    "c": -17,
    "v": -16,
    "g": -15,
    "b": -14,
    "h": -13,
    "n": -12,
    "j": -11,
    "m": -10,
    ",": -9,
    "l": -8,
    ".": -7,
    ";": -6,
    "/": -5,
    "q": -9,
    "2": -8,
    "w": -7,
    "3": -6,
    "e": -5,
    "r": -4,
    "5": -3,
    "t": -2,
    "6": -1,
    "y": 0,
    "7": 1,
    "u": 2,
    "i": 3,
    "9": 4,
    "o": 5,
    "0": 6,
    "p": 7,
    "[": 8,
    "=": 9,
    "]": 10
    }
    
ROOT_NOTE = 69

## main window

class MainFrame(wx.Frame):
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)
        
        self.initialized = False #if file is loaded & UI fully set up
        
        # menus
        self.status = self.CreateStatusBar()
        
        menu_file = wx.Menu()
        menu_open = menu_file.Append(wx.ID_OPEN, "&Open ROM", "Open a ROM for viewing/editing")
        self.menu_save = menu_file.Append(wx.ID_SAVE, "&Save ROM", "Save the currently loaded ROM, and any metadata changes made")
        self.menu_saveas = menu_file.Append(wx.ID_SAVEAS, "S&ave As...", "Save into a new file")
        self.menu_savemeta = menu_file.Append(wx.ID_ANY, "Save &metadata only", "Save metadata changes without saving ROM")
        menu_file.AppendSeparator()
        menu_exit = menu_file.Append(wx.ID_EXIT, "E&xit", "Terminate the program")
        
        # MRU
        self.filehistory = wx.FileHistory(5)
        self.config = wx.Config("akaotool", style=wx.CONFIG_USE_LOCAL_FILE)
        self.filehistory.Load(self.config)
        self.filehistory.UseMenu(menu_file)
        self.filehistory.AddFilesToMenu()
        
        menu_help = wx.Menu()
        menu_about = menu_help.Append(wx.ID_ABOUT, "&About", "Information about this program")
        
        menubar = wx.MenuBar()
        menubar.Append(menu_file, "&File")
        menubar.Append(menu_help, "&Help")
        
        self.Bind(wx.EVT_MENU, self.OnOpen, menu_open)
        self.Bind(wx.EVT_MENU_RANGE, self.OnHistory, id=wx.ID_FILE1, id2=wx.ID_FILE9)
        self.Bind(wx.EVT_MENU, self.OnExit, menu_exit)
        self.Bind(wx.EVT_MENU, self.OnAbout, menu_about)
        
        self.SetMenuBar(menubar)
        
        # notebook
        self.book = wx.Notebook(self)
        self.SeqPage = SequencePanel(self.book)
        self.InstPage = InstPanel(self.book)
        self.RomPage = wx.Panel(self.book)
        self.book.AddPage(self.SeqPage, "BGM Sequences", select=True)
        self.book.AddPage(self.InstPage, "BRR Instruments")
        self.book.AddPage(self.RomPage, "ROM Layout")
        
        # custom status bar
        self.bar = wx.Panel(self)
        self.bar.filename = wx.StaticText(self.bar, label="No file loaded", style=wx.ALIGN_LEFT)
        self.bar.fileinfo = wx.StaticText(self.bar, label="", style=wx.ALIGN_CENTER)
        self.bar.gamemode = wx.StaticText(self.bar, label="", style=wx.ALIGN_RIGHT)
        self.bar.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.bar.sizer.Add(self.bar.filename, 0, wx.LEFT|wx.RIGHT, 3)
        self.bar.sizer.AddStretchSpacer()
        self.bar.sizer.Add(self.bar.fileinfo, 0, wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER, 3)
        self.bar.sizer.AddStretchSpacer()
        self.bar.sizer.Add(self.bar.gamemode, 0, wx.LEFT|wx.RIGHT|wx.ALIGN_RIGHT, 3)
        self.bar.SetSizer(self.bar.sizer)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.book, 1, wx.EXPAND)
        sizer.Add(self.bar, 0, wx.EXPAND)
        self.SetSizer(sizer)
        
        self.Show(True)
        self.Refresh()
        
        self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.OnPageChanging, self.book)
        self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChange, self.book)
        
        pub.subscribe(self.newFileLoaded, "newFileLoaded")
        pub.subscribe(self.setStatus, "sendStatus")
        
    def setStatus(self, text):
        self.status.SetStatusText(text)
        
    def OnExit(self, e):
        self.Close(True)
        
    def OnAbout(self, e):
        about = wx.MessageDialog(self, "akaotool " + VERSION + "\nby emberling", "About", wx.OK)
        about.ShowModal()
        about.Destroy()
        
    def OnOpen(self, e):
        dia = wx.FileDialog(self, "Choose a ROM file", "", "", "SNES/SFC ROM files (*.smc, *.swc, *.sfc, *.fig)|*.smc;*.swc;*.sfc;*.fig", wx.FD_OPEN)
        if dia.ShowModal() == wx.ID_OK:
            
            self.fileChosen(dia.GetPath())
        dia.Destroy()
        
    def OnSave(self, e):
        self.OnSaveMeta(e)
        db.write_changes()
        
        path = 'out_test.smc'
        try:
            with open(path, 'wb') as f:
                f.write(db.rom)
        except IOError:
            warn("Could not save file")
            
    def OnSaveMeta(self, e):
        db.save_meta()
        
    def OnHistory(self, e):
        self.fileChosen(self.filehistory.GetHistoryFile(e.GetId() - wx.ID_FILE1))
        
    def fileChosen(self, path):
        try:
            with open(path, 'rb') as f:
                rom = f.read()
        except IOError:
            warn("Could not open file")
            return
        
        if not self.initialized:
            self.initialized = True

            self.Bind(wx.EVT_MENU, self.OnSave, self.menu_save)
            self.Bind(wx.EVT_MENU, self.OnSaveMeta, self.menu_savemeta)

            self.SeqPage.whenFileLoaded()
            self.InstPage.whenFileLoaded()
            
        self.filehistory.AddFileToHistory(path)
        self.filehistory.Save(self.config)
        self.config.Flush()
        pub.sendMessage('newFile', rom=rom, file=(os.path.split(path)))
        
    def newFileLoaded(self):
        self.bar.filename.SetLabel("Loaded: {}".format(db.filename))
        info = "HiROM, " if db.hirom else "LoROM, "
        info += "headered" if db.header else "unheadered"
        self.bar.fileinfo.SetLabel(info)
        self.bar.gamemode.SetLabel("Mode: {}".format(db.gamemode))
        self.bar.Layout()
        
    def OnPageChanging(self, e):
        self.Freeze()
        e.Skip()
        
    def OnPageChange(self, e):
        if self.initialized:
            if e.GetSelection() == 0:
                pub.sendMessage("loadBgmInfo", idx=self.SeqPage.bgmlist.idx)
            elif e.GetSelection() == 1:
                pub.sendMessage("loadInstInfo", idx=self.InstPage.instlist.idx)
        self.Thaw()
        e.Skip()
        
## sequence page

class SequencePanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        
        self.bgmlist = BgmList(self, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)

        self.detail = SeqDetailPanel(self)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.bgmlist, 0, wx.EXPAND|wx.ALL, 3)
        sizer.Add(self.detail, 1, wx.EXPAND|wx.ALL, 3)
        self.SetSizer(sizer)
        
        self.bgmlist.Hide()
        self.detail.Hide()
        
    def whenFileLoaded(self):
        self.bgmlist.Show()
        self.detail.Show()
        self.Layout()
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyPress)
        
    def OnKeyPress(self, e):
        if e.GetKeyCode() == wx.WXK_PAGEUP:
            pub.sendMessage("bgmSelect", inc=-1)
        elif e.GetKeyCode() == wx.WXK_PAGEDOWN:
            pub.sendMessage("bgmSelect", inc=1)
        else:
            e.Skip()
            
class BgmList(wx.ListCtrl):
    def __init__(self, *args, **kwargs):
        style = kwargs.pop('style','') | wx.LC_REPORT
        wx.ListCtrl.__init__(self, style=style, *args, **kwargs)
        
        self.idx = 0
        
        self.SetMinSize((320,320))
        self.InsertColumn(0, "ID", width=32)
        self.InsertColumn(1, "Name", width=216)
        self.InsertColumn(2, "Size (B)", width=64)
                
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelect, self)
        
        pub.subscribe(self.refreshBgmList, "newFileLoaded")
        pub.subscribe(self.refreshBgmSingle, "seqNameUpdated")
        pub.subscribe(self.modifyIndex, "bgmSelect")
        
    def modifyIndex(self, inc):
        goal = self.idx + inc
        if goal < 0: goal = 0
        if goal >= self.GetItemCount(): goal = self.GetItemCount()
        self.Select(goal)
        self.EnsureVisible(goal)
        
    def refreshBgmList(self):
        self.DeleteAllItems()
        for i, m in enumerate(db.bgms):
            self.Append(("{:02X}".format(i), m.get_name(), "${:X}".format(m.length)))
        self.Select(0)
        self.Focus(0)
        self.arrangeBgmList()

    def refreshBgmSingle(self, idx):
        self.SetItem(idx, 1, db.bgms[idx].get_name())
        self.SetItem(idx, 2, "${:X}".format(db.bgms[idx].length))
                
    def arrangeBgmList(self):
        self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self.SetColumnWidth(2, wx.LIST_AUTOSIZE)
        if self.GetColumnWidth(2) <= 52:
            self.SetColumnWidth(2, 52)
        width = self.GetSize()[0]
        self.SetColumnWidth(1, width - (self.GetColumnWidth(0) + self.GetColumnWidth(2) + 20))
        
    def OnSelect(self, e):
        self.idx = e.GetIndex()
        pub.sendMessage("loadBgmInfo", idx=self.idx)
        
class SeqDetailPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        self.idx = 0
        
        data_panel = wx.Panel(self)
        self.label_id = wx.StaticText(data_panel, label="ID:")
        self.disp_id = wx.TextCtrl(data_panel, value="<ph>", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_loc = wx.StaticText(data_panel, label="Data offset:")
        self.disp_loc = wx.TextCtrl(data_panel, value="0xC078PH", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_size = wx.StaticText(data_panel, label="Data size:")
        self.disp_size = wx.TextCtrl(data_panel, value="0x<ph> (<PH>) bytes", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_hash = wx.StaticText(data_panel, label="MD5:")
        self.disp_hash = wx.TextCtrl(data_panel, value="61883215h", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_orig = wx.StaticText(data_panel, label="Original BGM name:")
        self.disp_orig = wx.TextCtrl(data_panel, value="Theme of Placeholder", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_name = wx.StaticText(data_panel, label="Sequence name:")
        self.disp_name = wx.TextCtrl(data_panel, value="<unknown custom bgm>", size=(320,24))

        data_sizer = wx.FlexGridSizer(2, 2, 2)
        data_sizer.Add(self.label_id,   0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_id,    0, wx.RIGHT, 0)
        data_sizer.Add(self.label_loc,  0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_loc,   0, wx.RIGHT, 0)
        data_sizer.Add(self.label_size, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_size,  0, wx.RIGHT, 0)
        data_sizer.Add(self.label_hash, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_hash,  0, wx.RIGHT, 0)
        data_sizer.Add(self.label_orig, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_orig,  0, wx.RIGHT, 0)
        data_sizer.Add(self.label_name, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_name,  0, wx.EXPAND)
        data_panel.SetSizer(data_sizer)
    
        class ProgramPanel(wx.Panel):
            def __init__(self, parent, program, *args, **kwargs):
                wx.Panel.__init__(self, parent, *args, **kwargs)
                
                self.pid = program
                self.idx = 0
                self.SetMinSize((80,self.GetMinSize()[1]))
                
                shelf = wx.Panel(self)
                
                label_id = wx.StaticText(shelf, label="{:0X}".format(program))
                self.label_used = wx.StaticText(shelf, label="--")
                #self.entry = wx.ComboBox(shelf, size=(48,24), style=wx.TE_PROCESS_ENTER)
                self.entry = wx.ComboCtrl(shelf, size=(48,24))
                self.label_name = wx.StaticText(shelf, label="", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
                self.label_size = wx.StaticText(shelf, label="", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
                
                entry_popup = InstSelectComboPopup()
                self.entry.SetPopupControl(entry_popup)
                self.entry.SetPopupExtents(0, 192)
                
                id_sizer = wx.BoxSizer(wx.HORIZONTAL)
                id_sizer.Add(label_id, 1, wx.ALIGN_LEFT|wx.ALL|wx.EXPAND, 1)
                id_sizer.Add(self.label_used, 0, wx.ALIGN_RIGHT|wx.ALL, 1)
                
                sizer = wx.BoxSizer(wx.VERTICAL)
                sizer.Add(id_sizer, 0, wx.ALIGN_CENTER|wx.ALL|wx.EXPAND, 1)
                sizer.Add(self.entry, 1, wx.ALIGN_CENTER|wx.ALL, 1)
                sizer.Add(self.label_name, 1, wx.ALIGN_CENTER|wx.ALL|wx.EXPAND, 1)
                sizer.Add(self.label_size, 0, wx.ALIGN_CENTER|wx.ALL|wx.EXPAND, 1)
                shelf.SetSizer(sizer)
            
                outsizer = wx.BoxSizer(wx.VERTICAL)
                outsizer.Add(shelf, 1, wx.ALL|wx.EXPAND, 3)
                self.SetSizer(outsizer)
                self.shelf = shelf
                
                self.label_name.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                
                self.entry.Bind(wx.EVT_TEXT, self.OnTyping, self.entry)
                self.entry.Bind(wx.EVT_TEXT_ENTER, self.OnUpdate, self.entry)
                self.entry.Bind(wx.EVT_KILL_FOCUS, self.OnUpdate, self.entry)
                self.entry.Bind(wx.EVT_KEY_DOWN, self.OnEntryKeyPress, self.entry)
                
                pub.subscribe(self.whenBgmInfo, "loadBgmInfo")
    
            def OnEntryKeyPress(self, e):
                cur = int(self.entry.GetValue(),16)
                if e.GetKeyCode() == wx.WXK_UP and cur > 0:
                    self.entry.SetValue(f"{cur-1:02X}")
                elif e.GetKeyCode() == wx.WXK_DOWN and cur < 0x100:
                    self.entry.SetValue(f"{cur+1:02X}")
                self.OnUpdate(e)
                    
            def whenBgmInfo(self, idx):
                self.bgm = db.bgms[idx]
                self.idx = self.bgm.inst[self.pid-0x20]
                self.entry.SetValue("{:02X}".format(self.idx))
                self.whenUpdated()
                
            def OnTyping(self, e):
                cursor = self.entry.GetInsertionPoint()
                #entry = self.entry.GetValue().upper()
                #entry = ''.join([c for c in entry if c in "0123456789ABCDEF"])
                entry = hexify(self.entry.GetValue())
                if len(entry) > 2: entry = entry[0:2]
                self.entry.ChangeValue(entry)
                self.entry.SetInsertionPoint(cursor)
                
            def OnUpdate(self, e):
                self.OnTyping(e)
                text = self.entry.GetValue()
                appended = False
                while len(text) < 2:
                    appended = True
                    text = "0" + text
                #self.idx = int(text,16)
                self.bgm.inst[self.pid-0x20] = int(text,16)
                if appended: self.entry.SetValue(text)
                self.whenUpdated()
                e.Skip()
                
            def whenUpdated(self):
                self.idx = self.bgm.inst[self.pid-0x20]
                md = db.get_imeta(self.idx)
                name = md.get_name()
                if self.idx == 0:
                    name = "----"
                elif self.idx > db.brrcount:
                    name = "invalid instrument id"
                elif name.startswith("<brr "): name = "unnamed instrument"
                self.label_name.SetLabel("{}".format(name))
                self.label_name.Wrap(self.GetSize()[0])
                self.label_size.SetLabel("{}".format(db.instruments[self.idx].get_blocksize()))
                
                pub.sendMessage("programUpdate")
                
                if self.idx > db.brrcount:
                    col = wx.Colour(*(instrument_categories[-2][1]))
                    ocol = wx.Colour((250,50,50))
                elif md.category not in instrument_categories:
                    col = wx.Colour(*(instrument_categories[-1][1]))
                    ocol = wx.Colour(*md.color)
                else:
                    col = wx.Colour(*(instrument_categories[md.category][1]))
                    ocol = wx.Colour(*md.color)
                self.shelf.SetBackgroundColour(col)
                self.SetBackgroundColour(ocol)
                self.Refresh()
                
        prog_panel = wx.Panel(self)
        progs = []
        for i in range(0x20,0x30):
            progs.append(ProgramPanel(prog_panel, program=i, style=wx.BORDER_SIMPLE))
        self.prog_size = wx.StaticText(prog_panel, label="X of Y blocks used  (Z free)", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
        prog_sizer = wx.FlexGridSizer(8, 5, 3)
        for i in range(16):
            prog_sizer.Add(progs[i])
        prog_outsizer = wx.BoxSizer(wx.VERTICAL)
        prog_outsizer.Add(prog_sizer, 1, wx.EXPAND)
        prog_outsizer.AddSpacer(3)
        prog_outsizer.Add(self.prog_size, 0, wx.EXPAND|wx.ALIGN_CENTER)
        prog_panel.SetSizer(prog_outsizer)
        self.progs = progs
        
        control_panel = wx.Panel(self)
        butt_load_binary = wx.Button(control_panel, label="Import\nbinary\nsequence")
        butt_load_inst = wx.Button(control_panel, label="Import\n inst file")
        butt_load_mml = wx.Button(control_panel, label="Import sequence\nfrom MML")
        butt_save_binary = wx.Button(control_panel, label="Export to\nbinary")
        butt_save_mml = wx.Button(control_panel, label="Export\nto MML")
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        control_sizer.Add(butt_load_binary, 0, wx.ALIGN_CENTER|wx.ALL, 16)
        control_sizer.Add(butt_load_inst, 0, wx.ALIGN_CENTER|wx.ALL, 16)
        control_sizer.Add(butt_load_mml, 0, wx.ALIGN_CENTER|wx.ALL, 16)
        control_sizer.Add(butt_save_binary, 0, wx.ALIGN_CENTER|wx.ALL, 16)
        control_sizer.Add(butt_save_mml, 0, wx.ALIGN_CENTER|wx.ALL, 16)
        control_panel.SetSizer(control_sizer)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(data_panel, 0, wx.ALIGN_LEFT)
        sizer.AddSpacer(10)
        sizer.Add(prog_panel, 0, wx.ALIGN_CENTER)
        sizer.AddSpacer(32)
        sizer.Add(control_panel, 0, wx.ALIGN_CENTER)
        self.SetSizer(sizer)

        self.disp_name.Bind(wx.EVT_TEXT, self.updateName, self.disp_name)
        
        butt_save_binary.Bind(wx.EVT_BUTTON, self.onExportBin, butt_save_binary)
        butt_save_mml.Bind(wx.EVT_BUTTON, self.onExportMml, butt_save_mml)
        butt_load_binary.Bind(wx.EVT_BUTTON, self.onImportBin, butt_load_binary)
        butt_load_mml.Bind(wx.EVT_BUTTON, self.onImportMml, butt_load_mml)
        
        pub.subscribe(self.onBgmInfo, "loadBgmInfo")
        pub.subscribe(self.onProgramUpdate, "programUpdate")
        
    def onBgmInfo(self, idx):
        self.idx = idx
        bgm = db.bgms[idx]
        self.disp_id.SetValue("{:02X}".format(idx))
        if db.dm.is_valid(bgmidx(self.idx)):
            self.disp_loc.SetValue("0x{:06X}".format(bgm.offset))
        else:
            self.disp_loc.SetValue("(0x{:06X})**".format(bgm.offset))
        self.disp_size.SetValue("${0:X} ({0}) bytes".format(bgm.length))
        self.disp_hash.SetValue(bgm.hash)
        self.disp_orig.SetValue(get_bgm_name_by_id(idx))
        self.disp_name.SetValue(bgm.get_name())
        self.onProgramUpdate()
        
        foc = self.FindFocus()
        if isinstance(foc, wx.TextEntry) or isinstance(foc, wx.SpinCtrl):
            foc.SetSelection(-1,-1)
        
    def onProgramUpdate(self):
        blocks = 0
        for i in range(16):
            blocks += db.instruments[self.progs[i].idx].get_blocksize()
        if ('max_blocks' in db.gc) and db.gc['max_blocks']:
            freetext = "free" if blocks <= db.gc['max_blocks'] else "overflow"
            text = "{} of {} blocks used        ({} {})".format(blocks, db.gc['max_blocks'], abs(db.gc['max_blocks']-blocks), freetext)
        else: text = "{} blocks used".format(blocks)
        self.prog_size.SetLabel(text)
        
    def updateName(self, e):
        name = e.GetEventObject().GetValue()
        e.GetEventObject().ChangeValue(name)
        if not (name.startswith("<seq") and name.endswith(">")):
            db.bgms[self.idx].name = name
        pub.sendMessage("seqNameUpdated", idx=self.idx)
        e.Skip()
        
    def onExportBin(self, e):
        bgm = db.bgms[self.idx]
        default = ''.join([c for c in bgm.get_name() if c not in '*<>"/\\:|?']) + "_data.bin"
        dia = wx.FileDialog(self, message="Choose a filename for binary export. Note: _data.bin will be added if not already present.", defaultFile=default, wildcard="DATA_BIN files (*_data.bin)|*_data.bin|BIN files(*.bin)|*.bin|All files|*.*", style=wx.FD_SAVE)
        if dia.ShowModal() == wx.ID_CANCEL: return
        path = dia.GetPath()
        if path.endswith('_data.bin'): path = path[:-9]
        try:
            with open(f"{path}_data.bin", 'wb') as f:
                f.write(bgm.data)
            with open(f"{path}_inst.bin", 'wb') as f:
                f.write(bgm.get_binary_inst())
        except IOError:
            warn("I/O error, export failed")
            
    def onImportBin(self, e):
        bgm = db.bgms[self.idx]
        dia = wx.FileDialog(self, message="Choose a file for binary sequence import. Instrument file will also be imported if filenames match", wildcard="DATA_BIN files (*_data.bin)|*_data.bin|BIN files (*.bin)|*.bin|All files|*.*", style=wx.FD_OPEN)
        if dia.ShowModal() == wx.ID_CANCEL: return
        path = dia.GetPath()
        ipath = path[:-9] if path.endswith('_data.bin') else path
        ipath += "_inst.bin"
        dir, fi = os.path.split(path)
        if fi.endswith(".bin"): fi = fi[:-4]
        if fi.endswith("_data"): fi = fi[:-5]
        #bgm.name = fi
        try:
            with open(path, 'rb') as f:
                db.set_bgm_data(self.idx, f.read(), name_fallback=fi)
        except IOError:
            warn(f"Error reading file {path}")
            return
        try:
            with open(ipath, 'rb') as f:
                bgm.set_binary_inst(f.read())
        except IOError:
            pass
        pub.sendMessage("loadBgmInfo", idx=self.idx)
            
    def onImportMml(self, e):
        # temporary, using the old mfvitools engine
        if "FF6" not in db.gamemode:
            warn("Note: MML import is currently only compatible with FF6")
        bgm = db.bgms[self.idx]
        dia = wx.FileDialog(self, message="Choose an MML file.", wildcard="MML files (*.mml)|*.mml|All files|*.*", style=wx.FD_OPEN)
        if dia.ShowModal() == wx.ID_CANCEL: return
        path = dia.GetPath()
        dir, fi = os.path.split(path)
        if fi.endswith(".mml"): fi = fi[:-4]
        try:
            with open(path, 'r') as f:
                mml = f.read()
        except IOError:
            warn(f"Error reading file {path}")
        title = re.search("(?<=#TITLE )([^;\n]*)", mml, re.IGNORECASE)
        #bgm.name = title.group(0) if title else fi
        print(f"{bgm.name} -- {fi} -- {title}")
        akao = mml_to_akao(mml, fi)["_default_"]
        db.set_bgm_data(self.idx, bytes(akao[0], encoding='latin-1')[2:], name_fallback = title.group(0) if title else fi)
        bgm.set_binary_inst(bytes(akao[1], encoding='latin-1'))
        pub.sendMessage("loadBgmInfo", idx=self.idx)
        
    def onExportMml(self, e):
        warn("MML export not yet implemented")
        
## instrument page

class InstPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        
        self.instlist = InstList(self, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        self.detail = InstDetailPanel(self)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.instlist, 0, wx.EXPAND|wx.ALL, 3)
        sizer.Add(self.detail, 1, wx.EXPAND|wx.ALL, 3)
        self.SetSizer(sizer)
        
        self.instlist.Hide()
        self.detail.Hide()

    def whenFileLoaded(self):
        self.instlist.Show()
        self.detail.Show()
        self.Layout()
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyPress)
        
    def OnKeyPress(self, e):
        if e.GetKeyCode() == wx.WXK_PAGEUP:
            pub.sendMessage("instSelect", inc=-1)
        elif e.GetKeyCode() == wx.WXK_PAGEDOWN:
            pub.sendMessage("instSelect", inc=1)
        elif e.GetKeyCode() == wx.WXK_F5:
            #play_brr(db.instruments[self.instlist.idx].data, self.detail.tune_scale)
            Sample(db.instruments[self.instlist.idx].data).play(scale=self.detail.tune_scale)
        else:
            e.Skip()
                
class InstList(wx.ListCtrl):
    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)
        
        self.idx = 1
        
        self.SetMinSize((320,320))
        self.InsertColumn(0, "ID", width=25)
        self.InsertColumn(1, "Name", width=226)
        self.InsertColumn(2, "Blocks", width=50)
                
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelect, self)
        
        pub.subscribe(self.refreshInstList, "newFileLoaded")
        pub.subscribe(self.refreshInstSingle, "instNameUpdated")        
        pub.subscribe(self.modifyIndex, "instSelect")
        
    def modifyIndex(self, inc):
        goal = self.idx + inc - 1
        if goal < 0: goal = 0
        if goal >= self.GetItemCount(): goal = self.GetItemCount()
        self.Select(goal)
        self.EnsureVisible(goal)
        
    def refreshInstList(self):
        self.DeleteAllItems()
        for i, m in enumerate(db.instruments):
            if i == 0 or i > db.brrcount: continue
            md = db.get_imeta(m.hash)
            self.Append(("{:02X}".format(i), md.get_name(), "{}".format(m.get_blocksize())))
        self.Select(0)
        self.Focus(0)
        
        pub.sendMessage("instListUpdated")
        
    def refreshInstSingle(self, idx):
        self.SetItem(idx-1, 1, db.get_imeta(idx).get_name())
        self.SetItem(idx-1, 2, "{}".format(db.instruments[idx].get_blocksize()))
        
        pub.sendMessage("instListUpdated")
        
    def OnSelect(self, e):
        self.idx = e.GetIndex()+1
        pub.sendMessage("loadInstInfo", idx=self.idx)

class InstDetailPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)

        # Basic data, name, ID, etc.
        
        data_panel = wx.Panel(self)
        self.label_id = wx.StaticText(data_panel, label="ID:")
        self.disp_id = wx.TextCtrl(data_panel, value="<ph>", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_loc = wx.StaticText(data_panel, label="Data offset:")
        self.disp_loc = wx.TextCtrl(data_panel, value="0xC078PH", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_size = wx.StaticText(data_panel, label="Data size:")
        self.disp_size = wx.TextCtrl(data_panel, value="0x<ph> (<PH>) bytes -- <ph> blocks", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_hash = wx.StaticText(data_panel, label="MD5:")
        self.disp_hash = wx.TextCtrl(data_panel, value="61883215h", style=wx.TE_READONLY|wx.BORDER_NONE, size=(320,16))
        self.label_name = wx.StaticText(data_panel, label="Sample name:")
        self.disp_name = wx.TextCtrl(data_panel, value="<unknown sample>", size=(320,24))

        data_sizer = wx.FlexGridSizer(2, 2, 2)
        data_sizer.Add(self.label_id,   0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_id,    0, wx.RIGHT, 0)
        data_sizer.Add(self.label_loc,  0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_loc,   0, wx.RIGHT, 0)
        data_sizer.Add(self.label_size, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_size,  0, wx.RIGHT, 0)
        data_sizer.Add(self.label_hash, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_hash,  0, wx.RIGHT, 0)
        data_sizer.Add(self.label_name, 0, wx.RIGHT, 3)
        data_sizer.Add(self.disp_name,  0, wx.EXPAND)
        data_panel.SetSizer(data_sizer)
        
        # Category and color
        
        meta_panel = wx.Panel(self)
        color_outline_panel = wx.Panel(meta_panel)
        color_main_panel = wx.Panel(color_outline_panel)
        category_choice = wx.Choice(color_main_panel, size=(120,24))
        color_choice = wx.ColourPickerCtrl(color_main_panel)#, size=(64,24))
                
        color_main_sizer = wx.BoxSizer(wx.VERTICAL)
        color_outline_sizer = wx.BoxSizer(wx.VERTICAL)
        color_main_sizer.Add(wx.Panel(color_main_panel), 1, wx.EXPAND)
        color_main_sizer.Add(category_choice, 0, wx.ALIGN_CENTER|wx.ALL, 4)
        color_main_sizer.Add(wx.Panel(color_main_panel), 1, wx.EXPAND)
        color_main_sizer.Add(color_choice, 0, wx.ALIGN_CENTER|wx.ALL, 4)
        color_main_sizer.Add(wx.Panel(color_main_panel), 1, wx.EXPAND)
        color_main_panel.SetSizer(color_main_sizer)
        color_outline_sizer.Add(color_main_panel, 1, wx.EXPAND|wx.ALL, 4)
        color_outline_panel.SetSizer(color_outline_sizer)
        meta_sizer = wx.BoxSizer(wx.HORIZONTAL)
        meta_sizer.Add(wx.Panel(meta_panel), 1, wx.EXPAND)
        meta_sizer.Add(color_outline_panel, 0, wx.ALIGN_CENTER|wx.ALL, 3)
        meta_sizer.Add(wx.Panel(meta_panel), 1, wx.EXPAND)
        meta_panel.SetSizer(meta_sizer)
        
        for idx, ic in instrument_categories.items():
            if idx > 0:
                category_choice.Append(ic[0])
        
        self.category_choice = category_choice
        self.color_choice = color_choice
        self.category_panel = color_main_panel
        self.color_panel = color_outline_panel
        
        # Top layer
        
        mdata_sizer = wx.BoxSizer(wx.HORIZONTAL)
        mdata_sizer.Add(data_panel, 1, wx.EXPAND)
        mdata_sizer.Add(meta_panel, 1, wx.EXPAND)
        
        # Pitch
        
        pitch_panel = wx.Panel(self)
        pitch_sizer = wx.StaticBoxSizer(wx.VERTICAL, pitch_panel, "Pitch")
        pitch_box = pitch_sizer.GetStaticBox()
        self.tune_entry = wx.TextCtrl(pitch_box)
        self.tune_entry.SetMaxLength(4)
        self.tune_coarse = wx.SpinButton(pitch_box, size=(16,24))
        self.tune_fine = wx.SpinButton(pitch_box, size=(16,24))
        self.tune_coarse.SetRange(-0x80,0x7F)
        self.tune_fine.SetRange(-1,0x100)        
        self.note_label = wx.StaticText(pitch_box, label="Root: A5 + 0 cents", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
        self.vx_label = wx.StaticText(pitch_box, label="vxPitch: $1000 (4096)", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
        self.octave_spin = wx.SpinCtrl(pitch_box, size=(40,24))
        self.octave_label = wx.StaticText(pitch_box, label="plays N octave(s) higher\nthan listed notes", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
        
        tune_sizer = wx.BoxSizer(wx.HORIZONTAL)
        tune_sizer.Add(self.tune_entry, 0)
        tune_sizer.Add(self.tune_coarse, 0)
        tune_sizer.Add(self.tune_fine, 0)
        pitch_sizer.Add(tune_sizer, 0, wx.ALIGN_CENTER)
        pitch_sizer.AddSpacer(8)
        pitch_sizer.Add(self.note_label, 0, wx.ALIGN_CENTER|wx.EXPAND)
        pitch_sizer.AddSpacer(3)
        pitch_sizer.Add(self.vx_label, 0, wx.ALIGN_CENTER|wx.EXPAND)
        pitch_sizer.Add(wx.Panel(pitch_box), 1, wx.EXPAND)
        octave_sizer = wx.BoxSizer(wx.HORIZONTAL)
        octave_sizer.Add(self.octave_spin, 0)
        octave_sizer.Add(self.octave_label, 0)
        pitch_sizer.Add(octave_sizer, 0, wx.ALIGN_CENTER)
        pitch_sizer.Add(wx.Panel(pitch_box), 1, wx.EXPAND)
        pitch_panel.SetSizer(pitch_sizer)
        
        # ADSR
        
        adsr = ["A", "D", "S", "R"]
        env_max = [15, 7, 7, 31]
        adsr_panel = wx.Panel(self)
        adsr_sizer = wx.StaticBoxSizer(wx.VERTICAL, adsr_panel, "Envelope")
        adsr_box = adsr_sizer.GetStaticBox()
        envs_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.adsr_entry = wx.TextCtrl(adsr_box)
        self.adsr_entry.SetMaxLength(4)
        self.adsr_spin = {}
        self.adsr_text = {}
        for i, env in enumerate(adsr):
            self.adsr_spin[env] = wx.SpinCtrl(adsr_box, size=(40,24))
            self.adsr_spin[env].SetRange(0, env_max[i])
            self.adsr_text[env] = wx.StaticText(adsr_box, label = "N ms", style=wx.ALIGN_CENTER_HORIZONTAL|wx.ST_NO_AUTORESIZE)
            self.adsr_text[env].SetMinSize((64,20))
            
            envsizer = wx.BoxSizer(wx.VERTICAL)
            envsizer.Add(wx.StaticText(adsr_box, label=env, style=wx.ALIGN_CENTER), 0, wx.ALIGN_CENTER)
            envsizer.AddSpacer(3)
            envsizer.Add(self.adsr_spin[env], 0, wx.ALIGN_CENTER_HORIZONTAL)
            envsizer.AddSpacer(3)
            envsizer.Add(self.adsr_text[env], 0, wx.ALIGN_CENTER_HORIZONTAL)
            
            envs_sizer.Add(envsizer, 0, wx.EXPAND)
            if env != "R": envs_sizer.AddSpacer(3)
        
        adsr_sizer.Add(self.adsr_entry, 0, wx.ALIGN_CENTER)
        adsr_sizer.Add(wx.Panel(adsr_box), 1, wx.EXPAND)
        adsr_sizer.Add(envs_sizer, 0, wx.ALIGN_CENTER)
        adsr_sizer.Add(wx.Panel(adsr_box), 1, wx.EXPAND)
        adsr_panel.SetSizer(adsr_sizer)
        
        # Loop
        
        loop_panel = wx.Panel(self)
        loop_sizer = wx.StaticBoxSizer(wx.VERTICAL, loop_panel, "Looping")
        loop_box = loop_sizer.GetStaticBox()
        self.loop_entry = wx.TextCtrl(loop_box)
        self.loop_entry.SetMaxLength(4)
        self.loop_readable = wx.TextCtrl(loop_box)
        self.loop_spin = wx.SpinButton(loop_box, size=(16,24))
        self.loop_mode_blocks = wx.RadioButton(loop_box, style=wx.RB_GROUP, label="Blocks")
        self.loop_mode_samples = wx.RadioButton(loop_box, label="Samples")
        self.loop_toggle = wx.CheckBox(loop_box, label="Enable loop")
        
        loop_sizer.Add(self.loop_entry, 0, wx.ALIGN_CENTER)
        loop_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_sizer.Add(wx.StaticText(loop_box, label="Loop at:"), 0, wx.ALIGN_CENTER)
        loop_sizer.AddSpacer(2)
        loop_spinner_sizer = wx.BoxSizer(wx.HORIZONTAL)
        loop_spinner_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_spinner_sizer.Add(self.loop_readable, 0, wx.ALIGN_CENTER)
        loop_spinner_sizer.Add(self.loop_spin, 0, wx.ALIGN_CENTER)
        loop_spinner_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_sizer.Add(loop_spinner_sizer, 1, wx.EXPAND)
        loop_sizer.AddSpacer(2)
        loop_mode_sizer = wx.BoxSizer(wx.HORIZONTAL)
        loop_mode_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_mode_sizer.Add(self.loop_mode_blocks, 0, wx.EXPAND|wx.ALIGN_CENTER)
        loop_mode_sizer.Add(self.loop_mode_samples, 0, wx.EXPAND|wx.ALIGN_CENTER)
        loop_mode_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_sizer.Add(loop_mode_sizer, 1, wx.EXPAND)
        loop_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_sizer.Add(self.loop_toggle, 0, wx.ALIGN_CENTER)
        loop_sizer.Add(wx.Panel(loop_box), 1, wx.EXPAND)
        loop_panel.SetSizer(loop_sizer)
        
        # Middle layer
        
        spcmeta_sizer = wx.BoxSizer(wx.HORIZONTAL)
        spcmeta_sizer.Add(pitch_panel, 1, wx.EXPAND|wx.ALL, 1)
        spcmeta_sizer.Add(adsr_panel, 1, wx.EXPAND|wx.ALL, 1)
        spcmeta_sizer.Add(loop_panel, 1, wx.EXPAND|wx.ALL, 1)
        
        # Other info, e.g. list of BGM using this sample
        
        info_panel = wx.Panel(self)
        self.usage_label = wx.StaticText(info_panel, label="Used in:")
        self.usage_list = wx.ListCtrl(info_panel, style=wx.LC_LIST)
        
        info_sizer = wx.BoxSizer(wx.VERTICAL)
        info_sizer.Add(self.usage_label, 0)
        info_sizer.Add(self.usage_list, 1, wx.EXPAND)
        info_panel.SetSizer(info_sizer)
        
        # Controls
        
        control_panel = wx.Panel(self)
        import_button = wx.Button(control_panel, label="Import BRR")
        export_button = wx.Button(control_panel, label="Export BRR")
        play_button = wx.Button(control_panel, label="Play (A5)")
        audition_button = wx.Button(control_panel, label="Audition")
        
        control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        control_sizer.Add(import_button, 0, wx.ALL|wx.ALIGN_CENTER, 4)
        control_sizer.Add(export_button, 0, wx.ALL|wx.ALIGN_CENTER, 4)
        control_sizer.AddStretchSpacer(1)
        control_sizer.Add(play_button, 0, wx.ALL|wx.ALIGN_CENTER, 4)
        control_sizer.Add(audition_button, 0, wx.ALL|wx.ALIGN_CENTER, 4)
        control_panel.SetSizer(control_sizer)
        
        # Bottom layer
        
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)
        controls_sizer.Add(info_panel, 1, wx.EXPAND)
        controls_sizer.Add(control_panel, 2, wx.EXPAND)
        
        # Main layout
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(mdata_sizer, 0, wx.EXPAND|wx.ALL, 2)
        sizer.Add(spcmeta_sizer, 1, wx.EXPAND|wx.ALL, 2)
        sizer.Add(controls_sizer, 1, wx.EXPAND|wx.ALL, 2)
        self.SetSizer(sizer)
        
        pub.subscribe(self.whenInstInfo, "loadInstInfo")
        pub.subscribe(self.refreshColor, "instColorUpdated")
                
        self.disp_name.Bind(wx.EVT_TEXT, self.updateName, self.disp_name)
        
        self.category_choice.Bind(wx.EVT_CHOICE, self.updateCategory, self.category_choice)
        self.color_choice.Bind(wx.EVT_COLOURPICKER_CHANGED, self.onSelectColor, self.color_choice)
        
        self.tune_entry.Bind(wx.EVT_KILL_FOCUS, self.OnEnterPitch, self.tune_entry)
        self.tune_entry.Bind(wx.EVT_TEXT, self.forceHexTyping, self.tune_entry)
        self.adsr_entry.Bind(wx.EVT_KILL_FOCUS, self.updateEnvelope, self.adsr_entry)
        self.adsr_entry.Bind(wx.EVT_TEXT, self.forceHexTyping, self.adsr_entry)
        
        self.tune_coarse.Bind(wx.EVT_SPIN, self.coarseSpin, self.tune_coarse)
        self.tune_coarse.Bind(wx.EVT_MOUSEWHEEL, self.coarseWheel, self.tune_coarse)
        self.tune_fine.Bind(wx.EVT_SPIN, self.fineSpin, self.tune_fine)
        self.tune_fine.Bind(wx.EVT_MOUSEWHEEL, self.fineWheel, self.tune_fine)
        
        self.loop_entry.Bind(wx.EVT_TEXT, self.forceHexTyping, self.loop_entry)
        self.loop_entry.Bind(wx.EVT_KILL_FOCUS, self.enterLoop, self.loop_entry)
        self.loop_readable.Bind(wx.EVT_TEXT, self.forceDecTyping, self.loop_readable)
        self.loop_readable.Bind(wx.EVT_KILL_FOCUS, self.enterLoopReadable, self.loop_readable)
        self.loop_spin.Bind(wx.EVT_SPIN, self.spinLoop, self.loop_spin)
        self.loop_spin.Bind(wx.EVT_MOUSEWHEEL, self.wheelLoop, self.loop_spin)
        self.loop_mode_blocks.Bind(wx.EVT_RADIOBUTTON, self.calcLoop, self.loop_mode_blocks)
        self.loop_mode_samples.Bind(wx.EVT_RADIOBUTTON, self.calcLoop, self.loop_mode_samples)
        self.loop_toggle.Bind(wx.EVT_CHECKBOX, self.toggleLoop, self.loop_toggle)
        
        for e in self.adsr_spin.keys():
            self.adsr_spin[e].Bind(wx.EVT_SPINCTRL, self.combineEnvelope, self.adsr_spin[e])
            
        import_button.Bind(wx.EVT_BUTTON, self.brrimport, import_button)
        export_button.Bind(wx.EVT_BUTTON, self.brrexport, export_button)
        play_button.Bind(wx.EVT_BUTTON, self.play, play_button)
        audition_button.Bind(wx.EVT_SET_FOCUS, self.audition_help, audition_button)
        audition_button.Bind(wx.EVT_KILL_FOCUS, self.audition_end, audition_button)
        audition_button.Bind(wx.EVT_CHAR_HOOK, self.audition, audition_button)
        
    def whenInstInfo(self, idx):
        self.idx = idx
        
        ins = db.instruments[idx]
        md = db.get_imeta(idx)
        self.disp_id.SetValue("{:02X}".format(idx))
        self.disp_loc.SetValue("{:06X}".format(ins.offset))
        self.disp_size.SetValue("0x{0:X} ({0}) bytes -- {1} blocks".format(ins.length, ins.get_blocksize()))
        self.disp_hash.SetValue("{}".format(ins.hash))
        self.disp_name.SetValue(md.get_name())
        
        self.tune_entry.SetValue("{:04X}".format(ins.pitch))
        self.adsr_entry.SetValue("{:04X}".format(ins.adsr))
        self.loop_entry.SetValue("{:04X}".format(ins.loop))
        self.loop_toggle.SetValue(ins.is_looped)
        self.calcPitch()
        self.splitEnvelope()
        self.calcLoop()
        
        self.refreshColor()
        
        foc = self.FindFocus()
        if isinstance(foc, wx.TextEntry) or isinstance(foc, wx.SpinCtrl):
            foc.SetSelection(-1,-1)
        
        self.populateUsageList()
    
    def forceHexTyping(self, e):
        ctrl = e.GetEventObject()
        cursor = ctrl.GetInsertionPoint()
        ctrl.ChangeValue(hexify(e.GetString()))
        ctrl.SetInsertionPoint(cursor)
        e.Skip()
        
    def forceDecTyping(self, e):
        ctrl = e.GetEventObject()
        if e.GetString() != "invalid":
            cursor = ctrl.GetInsertionPoint()
            ctrl.ChangeValue(''.join([c for c in e.GetString() if c in "0123456789"]))
            ctrl.SetInsertionPoint(cursor)
        e.Skip()
        
    def brrimport(self, e):
        dia = wx.FileDialog(self, message="Choose a sample file.", wildcard="BRR files (*.brr)|*.brr|All files|*.*", style=wx.FD_OPEN)
        if dia.ShowModal() == wx.ID_CANCEL: return
        path = dia.GetPath()
        dir, fi = os.path.split(path)
        try:
            with open(path, 'rb') as f:
                db.set_brr_data(self.idx, f.read(), name_fallback=fi)
        except IOError:
            warn(f"Error reading file {path}")
            return
        pub.sendMessage("loadInstInfo", idx=self.idx)
        
    def brrexport(self, e):
        default = ''.join([c for c in db.get_imeta(self.idx).name if c not in '*<>"/\\:|?']) + ".brr"
        dia = wx.FileDialog(self, message="Choose a filename for export.", defaultFile=default, wildcard="BRR files (*.brr)|*.brr|All files|*.*", style=wx.FD_SAVE)
        if dia.ShowModal() == wx.ID_CANCEL: return
        path = dia.GetPath()
        try:
            with open(path, 'wb') as f:
                f.write(db.instruments[self.idx].data)
        except IOError:
            warn("I/O error, export failed")
        
    def updateName(self, e):
        name = e.GetEventObject().GetValue()
        name = ''.join([c for c in name if c != '|'])
        e.GetEventObject().ChangeValue(name)
        if not (name.startswith("<brr") and name.endswith(">")):
            db.get_imeta(self.idx).name = name
        pub.sendMessage("instNameUpdated", idx=self.idx)
        e.Skip()
        
    def updateCategory(self, e):
        db.get_imeta(self.idx).category = e.GetEventObject().GetCurrentSelection()+1
        pub.sendMessage("instColorUpdated")
        e.Skip()
        
    def updateEnvelope(self, e):
        env = zeropad(e.GetEventObject().GetValue(), 4)
        e.GetEventObject().SetValue(env)
        db.instruments[self.idx].adsr = int(env,16)
        self.splitEnvelope()
        e.Skip()
        
    def onSelectColor(self, e):
        md = db.get_imeta(self.idx)
        md.color = e.GetEventObject().GetColour()
        self.refreshColor()
        e.Skip()
        
    def refreshColor(self):
        md = db.imetadata[db.instruments[self.idx].hash]
        cat = instrument_categories[md.category]
        self.category_choice.SetSelection(md.category-1)
        self.category_panel.SetBackgroundColour(cat[1])
        self.color_panel.SetBackgroundColour(wx.Colour(*md.color))
        self.color_choice.SetColour(wx.Colour(*md.color))
        self.color_panel.Refresh()
        
    def splitEnvelope(self, e=None):
        env = db.instruments[self.idx].adsr
        
        a = (env >> 8) & 0b1111
        d = (env >> 12) & 0b111
        s = (env >> 5) & 0b111
        r = env & 0b11111
        self.adsr_spin["A"].SetValue(a)
        self.adsr_spin["D"].SetValue(d)
        self.adsr_spin["S"].SetValue(s)
        self.adsr_spin["R"].SetValue(r)
        self.calcEnvelope()
        
    def combineEnvelope(self, e):
        a = self.adsr_spin["A"].GetValue() << 8
        d = self.adsr_spin["D"].GetValue() << 12
        s = self.adsr_spin["S"].GetValue() << 5
        r = self.adsr_spin["R"].GetValue()
        
        env = a + d + s + r + 0x8000
        db.instruments[self.idx].adsr = env
        self.adsr_entry.SetValue("{:04X}".format(env))
        self.calcEnvelope()
        e.Skip()
        
    def calcEnvelope(self):
        env = db.instruments[self.idx].adsr
        a = (env >> 8) & 0b1111
        d = (env >> 12) & 0b111
        s = (env >> 5) & 0b111
        r = env & 0b11111
        av = attack_table[a]
        sv = (s + 1) / 8
        dv = decay_table[d] * (1-sv)
        if r == 0:
            rt = "infinite"
        else:
            rv = release_table[r]
            if rv >= 9999:
                rt = "{:g} s".format(rv / 1000)
            else:
                rt = "{} ms".format(rv)
            
        self.adsr_text["A"].SetLabel("{} ms".format(av))
        self.adsr_text["D"].SetLabel("{:.4g} ms".format(dv))
        self.adsr_text["S"].SetLabel("{:.1%}".format(sv))
        self.adsr_text["R"].SetLabel(rt)
        
    def calcPitch(self):
        tune = db.instruments[self.idx].pitch
        if tune < 0x8000: tune += 0x10000
        scale = tune / 65536
        vxpitch = int(scale * 4096)
        delta = math.log10(scale) / math.log10(2) * 12
        cents, tones = math.modf(delta)
        if cents < -0.5:
            cents += 1
            tones -= 1
        key = noteToKey(ROOT_NOTE - int(round(tones)))
        
        self.vx_label.SetLabel("A5 vxPitch: ${0:X} ({0})".format(vxpitch))
        self.note_label.SetLabel("Root: {} {} {:.3g} cents".format(key, "-" if cents < 0 else "+", abs(cents)))
        
        tune = db.instruments[self.idx].pitch
        self.tune_entry.ChangeValue("{:04X}".format(tune))
        coarse, fine = (tune >> 8), (tune & 255)
        if coarse > 0x7F: coarse -= 0x100
        self.tune_coarse.SetValue(coarse)
        self.tune_fine.SetValue(fine)
        self.tune_scale = scale
        
    def OnEnterPitch(self, e):
        db.instruments[self.idx].pitch = int(e.GetEventObject().GetValue(),16)
        self.calcPitch()
        e.Skip()
        
    def coarseSpin(self, e):
        spin = e.GetEventObject()
        coarse = spin.GetValue()
        if coarse < 0: coarse += 0x100
        fine = db.instruments[self.idx].pitch & 255
        db.instruments[self.idx].pitch = (coarse << 8) + fine
        self.calcPitch()
        
    def coarseWheel(self, e):
        e.GetEventObject().SetValue(e.GetEventObject().GetValue() + (e.GetWheelRotation() // e.GetWheelDelta()))
        self.coarseSpin(e)
        
    def fineSpin(self, e):
        spin = e.GetEventObject()
        coarse = db.instruments[self.idx].pitch >> 8
        if coarse >= 0x80: coarse -= 0x100
        fine = spin.GetValue()
        print("{:02X} {:02X}".format(coarse, fine))
        if fine < 0:
            if coarse <= -0x80:
                fine = 0
            else:
                fine = 0xFF
                coarse -= 1
        if fine > 0xFF:
            if coarse >= 0x7F:
                fine = 0xFF
            else:
                fine = 0
                coarse += 1
        if coarse < 0: coarse += 0x100
        db.instruments[self.idx].pitch = (coarse << 8) + fine
        self.calcPitch()

    def fineWheel(self, e):
        e.GetEventObject().SetValue(e.GetEventObject().GetValue() + (e.GetWheelRotation() // e.GetWheelDelta()))
        self.fineSpin(e)
        
    def calcLoop(self, e=None):
        ins = db.instruments[self.idx]
        loop_bytes = ins.get_loop_point()
        loop_blocks = min(loop_bytes // 9, ins.get_blocksize())
        loop_samples = loop_blocks * 16
        if loop_bytes % 9:
            text = "invalid"
        elif self.loop_mode_blocks.GetValue():
            text = f"{loop_blocks}"
        elif self.loop_mode_samples.GetValue():
            text = f"{loop_samples}"
            
        self.loop_entry.SetValue("{:04X}".format(ins.loop))
        self.loop_readable.SetValue(text)
        self.loop_spin.SetRange(0, ins.get_blocksize())
        self.loop_spin.SetValue(loop_blocks)
            
    def enterLoop(self, e):
        ins = db.instruments[self.idx]
        ins.loop = int(e.GetEventObject().GetValue(), 16)
        self.calcLoop()
        e.Skip()
        
    def enterLoopReadable(self, e):
        ins = db.instruments[self.idx]
        try:
            loop_point = int(e.GetEventObject().GetValue())
        except ValueError:
            e.Skip()
            return
        if self.loop_mode_blocks.GetValue():
            loop_point *= 9
        elif self.loop_mode_samples.GetValue():
            loop_point = (loop_point // 16) * 9
        else:
            e.Skip()
            return
        ins.set_loop_point(loop_point)
        self.calcLoop()
        e.Skip()
        
    def spinLoop(self, e):
        spin = e.GetEventObject()
        ins = db.instruments[self.idx]
        block_point = spin.GetValue()
        byte_point = block_point * 9
        old_point = ins.get_loop_point()
        while byte_point - old_point > 9: byte_point -= 9
        while old_point - byte_point > 9: byte_point += 9
        ins.set_loop_point(byte_point)
        self.calcLoop()
        
    def wheelLoop(self, e):
        spin = e.GetEventObject()
        ins = db.instruments[self.idx]
        spin.SetValue(spin.GetValue() + (e.GetWheelRotation() // e.GetWheelDelta()))
        block_point = spin.GetValue()
        byte_point = block_point * 9
        ins.set_loop_point(byte_point)
        self.calcLoop()
        
    def toggleLoop(self, e):
        check = e.GetEventObject()
        ins = db.instruments[self.idx]
        ins.set_loop_state(check.IsChecked())
            
    def populateUsageList(self):
        self.usage_list.ClearAll()
        for i, bgm in enumerate(db.bgms):
            if self.idx in bgm.inst:
                self.usage_list.Append(["{:02X} ({:02X}) {}".format(i, bgm.inst.index(self.idx)+0x20, bgm.get_name())])
        self.usage_label.SetLabel("Used in ({}):".format(self.usage_list.GetItemCount()))
        
    def play(self, e=None, tone=0):
        smp = Sample(db.instruments[self.idx].data)
        smp.play_tone(tone, scale=self.tune_scale)

    def audition(self, e):
        key = e.GetUnicodeKey()
        if not key or key is wx.WXK_NONE:
            e.Skip()
            return
        key = chr(key).lower()
        if key in key_tone_table:
            self.play(tone=key_tone_table[key])
        
    def audition_help(self, e):
        pub.sendMessage("sendStatus", text="Audition sample using the typing keyboard")
        
    def audition_end(self, e):
        pub.sendMessage("sendStatus", text="")
        
class InstSelectComboPopup(wx.ComboPopup):
    def __init__(self, *args, **kwargs):
        wx.ComboPopup.__init__(self, *args, **kwargs)
        self.lc = None
        self.curitem = 0
        self.value = 0
        
    def Create(self, parent):
        self.lc = self.InstSelectListCtrl(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL | wx.SIMPLE_BORDER)
        self.lc.SetItemCount(0)
        self.lc.InsertColumn(0, "ID", width=24)
        self.lc.InsertColumn(1, "Name", width=162)
        self.lc.InsertColumn(2, "Blocks", width=36)
        self.lc.Bind(wx.EVT_MOTION, self.OnMotion)
        self.lc.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        
        pub.subscribe(self.whenFileLoaded, "newFileLoaded")
        
        return True
                
    def OnMotion(self, evt):
        item, flags = self.lc.HitTest(evt.GetPosition())
        if item >= 0:
            self.lc.Select(item)
            self.curitem = item

    def OnLeftDown(self, evt):
        self.value = self.curitem
        self.Dismiss()
        
    def GetControl(self):
        return self.lc
        
    def GetStringValue(self):
        return f"{self.value:02X}"
        
    def whenFileLoaded(self):
        self.lc.SetItemCount(db.brrcount+1)
        
    class InstSelectListCtrl(wx.ListCtrl):
        def __init__(self, *args, **kwargs):
            wx.ListCtrl.__init__(self, *args, **kwargs)
            self.attr = wx.ListItemAttr()

        def OnGetItemText(self, idx, column):
            if column == 1:
                return db.get_imeta(idx).get_name()
            elif column == 2:
                return f"{db.instruments[idx].get_blocksize()}"
            else:
                return f"{idx:02X}"
                
        def OnGetItemAttr(self, idx):
            #attr = wx.ListItemAttr()
            col = list(db.get_imeta(idx).color)
            for i, c in enumerate(col): col[i] = (c//3)*2
            self.attr.SetTextColour(wx.Colour(col))
            self.attr.SetBackgroundColour(wx.Colour(instrument_categories[db.get_imeta(idx).category][1]))
            self.attr.SetFont(wx.Font(wx.FontInfo(8).Bold()))
            return self.attr
            
def noteToKey(note):
    octave = note // 12
    key = semitone_table[note % 12]
    return "{}{}".format(key, octave)
        
## execution
try:
    db = Database()
    app = wx.App()
    frame = MainFrame(None, title='akaotool ' + VERSION, size=wx.Size(1024,600), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
    icon = wx.Icon(os.path.join('dat','icon.png'))
    frame.SetIcon(icon)
except Exception:
    traceback.print_exc()
    input()
    quit()
try:
    app.MainLoop()
except Exception:
    tb = traceback.format_exc()
    warn(tb)
input()