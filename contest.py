from pathlib import Path
import re
from collections import Counter
from datetime import date
from hamutils import adif
import maidenhead as mh
from dateutil.parser import parse
from geopy.distance import distance
from qrz import QRZ, CallsignNotFound
import json
import requests

GRIDRE = "[A-Z]{2}[0-9]{2}[A-Z]{0,2}"
CALLRE = "[0-9]{0,1}[A-Z]+[0-9]+[A-Z]+"

qrzcache = {}

def guess_call(text, debug=False):

    # Look for explicit declarations of call first
    for line in text.splitlines():
        if line.startswith("CALLSIGN"):
            callsign = line.split()[1]
            if debug: print("Found CALLSIGN: " + callsign)
            return callsign
        elif line.startswith("<OPERATOR"):
            callsign = line.split(">")[1]
            if debug: print("Found CALLSIGN: " + callsign)
            return callsign

    # ok lets try and figure it out
    grids = re.findall(GRIDRE, text)
    calls = re.findall(CALLRE, text)

    words_to_count = [x for x in calls if x not in grids]
    c = Counter(words_to_count)
    return c.most_common(1)[0][0]


def guess_locator(text, debug=False):

    # Look for explicit declarations of call first
    for line in text.splitlines():
        if line.startswith("GRID"):
            grid = line.split()[1]
            if debug: print("Found GRID: " + grid)
            return grid
        elif line.startswith("<LOCATOR_ID"):
            grid = line.split(">")[1]
            if debug: print("Found GRID: " + grid)
            return grid

    c = Counter(re.findall(GRIDRE, text))
    return c.most_common(1)[0][0]


class MismatchError(Exception):
    """Base class for exceptions in this module."""
    pass


class QSO(object):
    def __init__(self, dup=False, valid=True, call="", dx_call="", locator="", dx_locator="", qrz_locator="",
                 dx_qrz_locator="", serial="", dx_serial="", rpt="", dx_rpt="", freq="", mode="", date="", time="",
                 score=""):
        self.dup = False
        self.valid = True
        self.call = call
        self.dx_call = dx_call
        self.locator = locator
        self.dx_locator = dx_locator
        self.qrz_locator = qrz_locator
        self.qrz_dx_locator = dx_qrz_locator
        self.serial = serial
        self.dx_serial = dx_serial
        self.rpt = rpt
        self.dx_rpt = dx_rpt
        self.freq = freq
        self.mode = mode
        self.date = date
        self.time = time
        self.score = score
        self.distance = 0
        self.verified = False
        self.inqrz = False
        self.dx_inqrz = False

    def _verified(self):
        if self.verified == True:
            return "verified"
        else:
            return ""

    def __repr__(self):
        return self.call + "->" + self.dx_call + ":" + str(self.locator) + "->" + str(self.dx_locator) + \
               ":" + str(self.mode) + ":" + str(self.serial) + "->" + str(self.dx_serial) + ":" + str(self.distance) + ":" + self._verified()

    def match(self, other):
        serialmismatch=True
        locatormismatch=True
        # First check the callsigns

        if self.call == other.dx_call and self.dx_call == other.call:
            # Next check the serial
            if not (self.serial == other.dx_serial and self.dx_serial == other.serial) and not \
                    (self.serial == other.serial and self.dx_serial == other.dx_serial):
                # We'll be leniant in case we misparsed which was sent and received
                if self.mode == "FM":
                    raise MismatchError("Serials don't match.")

            if not (self.locator[0:4] == other.dx_locator[0:4] and self.dx_locator[0:4] == other.locator[0:4]) and not \
                    (self.locator[0:4] == other.locator[0:4] and self.dx_locator[0:4] == other.dx_locator[0:4]):
                # We'll be leniant in case we misparsed which was sent and received
                raise MismatchError("Locators don't match.")
            else:
                self.verified = True
                other.verified = True
        else:
            return False

    def update_qrz_locators(self):
        """ Look for qrz locator if we dont have a 6char one already"""
        qrzcachefile = Path("qrzcache.txt")

        if qrzcachefile.is_file():
                    qrzcache = json.load(open(qrzcachefile))
        else:
            qrzcache = {}

        for call in [self.call, self.dx_call]:
            if call not in qrzcache:
                qrz = QRZ()
                try:
                    qrzcache[call] = qrz.callsign(call)
                except CallsignNotFound:
                    qrzcache[call] = {'grid': ""}

        if self.call in qrzcache:
            self.qrz_locator = qrzcache[self.call]['grid'].upper()

        if self.dx_call in qrzcache:
            self.qrz_dx_locator = qrzcache[self.dx_call]['grid'].upper()

        with open('qrzcache.txt', 'w') as outfile:
            json.dump(qrzcache, outfile)

    def __hash__(self):
        return hash((self.call, self.dx_call, self.mode))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def compute4chardist(self):
        l1 = self.locator[0:4]
        l2 = self.dx_locator[0:4]
        if l1 == l2:
            self.distance  = 50
        else:
            self.distance =  round(distance(mh.toLoc(self.locator[0:4]), mh.toLoc(self.dx_locator[0:4])).km)


def parse_qso(l, year=date.today().year, call=None, locator=None, debug=False):
    q = QSO()
    q.call = call
    q.locator = locator

    # Flag needed as the station and dx can have same locator
    locatorflag = False
    serial = 0

    if not re.search(CALLRE, l):
        # We can't even find a callsign in the line
        return None
    if "<" in l:
        # Assume ADIF
        print("looks like ADIF. Ignoring for now.")
        return None
    # Take everything to CSV
    if not "," in l:
        l = re.sub("\s+", ",", l.strip())

    fields = l.split(",")
    for field in fields:
        field = field.upper()
        if field == "":
            # Empty cvs field
            continue
        if field == "QSO:":
            # Cabrillo
            continue
        elif field.startswith(str(year)):
            # Date is likely to be an early field
            try:
                if parse(field):
                    q.date = field
            except ValueError:
                pass
        elif re.match("\d{2}:*\d{2}:*(\d{2})*", field):
            # match likely time strings
            q.time = field
        elif field in ["FM", "PH", "SSB", "FT8", "FT"]:
            # Explicitly look for mode
            q.mode = field
        elif field in ["145", "144", "2M"] or field.startswith("145") or field.startswith("144"):
            q.freq = field
        elif re.match(GRIDRE, field):
            if locator == field and not locatorflag:
                locatorflag = True
                pass
            elif locator:
                q.dx_locator = field
            else:
                locator = field
                q.locator = locator
        elif re.match(CALLRE, field):
            if call == field:
                pass
            elif call and call != field:
                q.dx_call = field
            else:
                call = field
                q.call = call
        elif field.startswith("+") or field.startswith("-") or re.search("5[1-9]", field):
            # Need to come up with better for FT8
            if q.rpt:
                q.dx_rpt = field
            else:
                q.rpt = field
        elif re.match("^\d+$", field):
            if q.serial and q.dx_serial:
                if debug:
                    print("Not sure what this is..." + str(field) + " perhaps a score?")
                continue
            # Going to assume this is serials
            if serial:
                q.serial = serial
            else:
                serial = int(field)
            q.dx_serial = int(field)

        elif debug:
            print("Unparsed: " + field)

    # If we only found one locator and it matched the station, we may have misinterpreed it as the dx_locator
    if q.locator and locatorflag and not q.dx_locator:
        q.dx_locator = q.locator

    if debug: print("parse_qso qso: " + str(q.__dict__))
    # Last check that we can identify 2 stations
    if q.call and q.dx_call:
        return q
    else:
        return None

def adif2qso(qso, call=None, locator=None, debug=False):
    if not call:
        try:
            call = qso["operator"]
        except KeyError:
            call = "XXXX"

    if not locator:
        try:
            locator = qso["my_gridsquare"]
        except KeyError:
            locator = "YYYY"

    if qso['mode'] in ['FM', 'PH']:
        try:
            serial=int(qso['stx'])
        except KeyError:
            serial = int(qso['stx_string'])

        try:
            dx_serial=int(qso['srx'])
        except KeyError:
            dx_serial = int(qso['srx_string'])

    try:
        if qso['mode'] in ['FM', 'PH']:
            q = QSO(dx_call=qso['call'], call=call, locator=locator, mode=qso['mode'], serial=serial, dx_serial=dx_serial, dx_locator=qso['gridsquare'])
        else:
            q = QSO(dx_call=qso['call'], call=call, locator=locator, mode=qso['mode'], dx_locator=qso['gridsquare'])
        if debug: print(q)
        return(q)
    except Exception as e:
        print(qso)
        print(e)

def get_qsos_from_file(f, debug=False, mode="FM"):

    logfd = open(f)
    try:
        logtext = logfd.read().upper()
    except UnicodeDecodeError:
        print("Cant decode file:" + f)
        return None
    logfd.close()

    qsos = []


    callsign = guess_call(logtext, debug=debug)
    if debug: print("Guessed callsign: " + callsign)

    locator = guess_locator(logtext, debug=debug)
    if debug: print("Guessed locator: " + locator)

    if "ADIF" in logtext:
        if debug: print("ADIF detected. parsing with ADIreader...")
        logqsos = adif.ADIReader(open(f, "r", encoding="utf-8"))
        for qso in logqsos:
            try:
                qso = adif2qso(qso, call=callsign, locator=locator, debug=debug)
                if debug: print(qso)
                if hash(qso) in [hash(x) for x in qsos]:
                    print("DUP ignoring: " + qso.call + " " + qso.dx_call)  #
                else:
                    qsos.append(qso)
            except Exception as e:
                print("Exception" +  str(e))
                print(qso)
                print(e)
        return qsos


    for line in logtext.splitlines():
        if "EMAIL" in line or "CATEGORY" in line or "OPERATORS" in line or "CREATED-BY" in line \
                or "LOCATION" in line or "CONTEST" in line:
            continue
        if debug: print("Checking line:" + line)
        qso = parse_qso(line, call=callsign, locator=locator, debug=debug)
        if debug: print("Got QSO:" + str(qso))
        if qso:
            if hash(qso) in [hash(x) for x in qsos]:
                print("DUP ignoring: " + qso.call + " " + qso.dx_call)  #
            else:
                qsos.append(qso)
        else:
            if debug: print(line)

    if mode=="FT8":
        qsos = [x for x in qsos if x.mode == "FT8"]
    else:
        qsos = [x for x in qsos if x.mode != "FT8"]
    return qsos
