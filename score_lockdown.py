import os
import pprint
from collections import Counter
import json

from contest import get_qsos_from_file, MismatchError

os.environ["QRZ_PASSWORD"] = "}A2KyHXMPFwhEjUPZ@2fZEkf"
os.environ["QRZ_USER"] ="EI6KO"

logs = os.listdir("FM")
debug=False
print(logs)


def process_logs(dir="FM", debug=False):
    qsos = []
    logs = os.listdir(dir)
    for log in logs:
        print(log)
        newqsos = get_qsos_from_file(os.path.join(dir, log), debug=debug, mode=dir)
        if newqsos:
            print(" Callsign:" + newqsos[0].call + " Grid:" + newqsos[0].locator + " QSOs:" + str(len(newqsos)) + " Mode:" +
                  newqsos[0].mode)
            qsos.extend(newqsos)
        else:
            print("No new QSOs in: " + log)

    entrants =  set([x.call for x in qsos])
    realgrids = {}
    for e in entrants:
        grid = [x.locator for x in qsos if e == x.call ][0]
        if len(grid) == 6:
            realgrids[e] = grid

    print(realgrids)
    flag = False
    for qso in qsos:
        for q2 in qsos:
            try:
                pass
                qso.match(q2)
            except MismatchError as e :
                flag = True
                print("Mismatch:" + str(e))
                print(qso)
                print(q2)
                qso.valid = False
                q2.valid = False
        qso.compute4chardist()
        qso.update_qrz_locators()
    if not flag:
        print("No Mismatched QSO's found. All serials and locators correct.")

    print("Valid log QSOs : " + str(len(qsos)))
    print("Verified log QSO's (logged by both parties): " + str(int(len(set([x for x in qsos if x.verified==True]))/2)))
    print([x for x in qsos if x.verified==True])
    print("Stations With Submitted logs: " + str(len(set([x.call for x in qsos]))))
    print("Stations in the logs: " + str(len(set([y.dx_call for y in qsos] + [x.call for x in qsos]))))
    print("Grids reported for dx stations:")
    grids = [x.dx_locator for x in qsos]
    pprint.pprint(Counter([x[0:4] for x in grids]))
    entrants = set([x.call for x in qsos])
    results = {}
    for entrant in entrants:
        squares = len(set([x.dx_locator[0:4] for x in qsos if entrant == x.call]))
        kms = sum([x.distance for x in qsos if entrant == x.call])
        eqsos = len(set([x for x in qsos if entrant == x.call]))
        result = squares * kms
        results[entrant] = [result, eqsos, squares, kms]

    #pprint.pprint(qsos)
    print("Stations in logs but not found in QRZ: " + str(set([x.call for x in qsos if x.qrz_locator == "" ] +
                                                              [x.dx_call for x in qsos if x.qrz_dx_locator == "" ])))


    print("Overall Results:")
    results = (sorted(results.items(), key=lambda item: item[1][0], reverse=True))
    print('<figure class="wp-block-table is-style-stripes"><table><tbody>')
    print('<tr><th>Award</th><th>Call</th><th>Valid QSOs</th><th>Grids</th><th>Score</th></tr>')
    for r in results:
#        pprint.pprint(r)
        print("<tr><td></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(r[0], r[1][1],r[1][2],r[1][0]))
    print('</tbody></table></figure>')
    with open(dir + 'qsos.txt', 'w') as outfile:
        json.dump(qsos, outfile, default = lambda o: o.__dict__, sort_keys=True, indent=4)

    return qsos

def qsos2csv(qsos, f):
    with open(f, "w") as fh:
        for qso in qsos:
            fh.write("{},{},{},{},{},{},{},{}\n".format(qso.call, qso.dx_call, qso.locator, qso.serial,qso.dx_locator,qso.dx_serial,qso.verified,qso.distance))

print("=-=-=-=-=-=-=-=-=-=-=-  FMFMFMFMFMFMFM =-=-=-=-=-=-=-=-=-=-=-")
qsos = process_logs("FM", debug)
#qsos2csv(qsos, "fmqsos.csv")


print("\n\n\n\n\n=-=-=-=-=-=-=-=-=-=-=-  FT8FT8FT8FT8FT8FT8 =-=-=-=-=-=-=-=-=-=-=-")
qsos= process_logs("FT8", False)
#qsos2csv(qsos, "ft8qsos.csv")

