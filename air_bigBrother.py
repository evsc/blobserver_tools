#!/usr/bin/env python

from trail import *


# A few parameters
VERBOSE = False
OSC = False
SHOW_CV = True

MAX_PATHWAY_HISTORY = 300 # Maximum history length for the Pathway objects
MAX_TRAIL_HISTORY = 120 # Maximum history length for the Trail object
POINT_LIFETIME = 1e6 # Maximum lifetime (in seconds) of a new position
LINE_DETECTION_LEVEL = 64 # Maximum indice of confidence for a line to be detected by Trail
LINE_MIN_LENGTH = 200 # Minimum Length that is required for a line to be detected
CIRCLE_DETECTION_LEVEL = 8192 # Maximum indice of confidence for a circle to be detected by Trail_Circle
CIRCLE_MAX_RADIUS = 256 # Maximum radius of the circles detected by Trail_Circle (with no limit, it will always find a circle)
CIRCLE_MIN_RADIUS = 30 # Minimum radius of the circles detected by Trail_Circle (with no limit, it will always find a circle)

verbose_cntmax = 300    # print output only every 300th frame (SLOW DOWN!)
verbose_cnt = 0


# Input resolution (from camera)
IMAGE_SIZE = [840, 480]

# Projection parameters
PROJECTION_IN = array([[0, 0], [840, 0], [840, 480], [0, 480]], float32)
PROJECTION_OUT = array([[0, 0], [840, 0], [840, 480], [0, 480]], float32)



#*************#
def bigBrother_callback(path, args, types, src, user_data):
    trail_callback(path, args, types, src, user_data["trail"])


 #*************#
def mainLoop(   maxPathwayHistory = MAX_PATHWAY_HISTORY, 
                maxTrailHistory = MAX_TRAIL_HISTORY, 
                pointLifetime = POINT_LIFETIME,
                lineDetectionLevel = LINE_DETECTION_LEVEL, 
                lineMinLength = LINE_MIN_LENGTH,
                circleDetectionLevel = CIRCLE_DETECTION_LEVEL, 
                circleMaxRadius = CIRCLE_MAX_RADIUS,
                circleMinRadius = CIRCLE_MIN_RADIUS):

    # reach blobserver on socket 9000, to receive blob information
    try:
        oscServer = liblo.Server(9000);
    except liblo.AddressError, err:
        print(str(err))
        sys.exit()
    print "listen on socket 9000"

    # create socket 9100, to send out trail/path information
    try:
        oscClient = liblo.Address(9100)
    except liblo.AddressError, err:
        print(str(err))
        sys.exit()
    print "communicate on socket 9100"

    # Dict that will contain instances for all active blob-ids, 
    # reference by blob-id
    # and have [0] a Trail object and [1] a Trail-Circle object
    trails = {}

    verbose_cnt = 0

    user_data = {}
    user_data["trail"] = [trails, maxTrailHistory, pointLifetime, lineDetectionLevel, lineMinLength, circleDetectionLevel, circleMaxRadius, circleMinRadius, PROJECTION_IN, PROJECTION_OUT]

    # The positions of the blobs are updated through this callback
    oscServer.add_method("/blobserver/bgsubtractor", "iiiffiii", bigBrother_callback, user_data)
    # oscServer.add_method("/blobserver/hog", "iiffiii", bigBrother_callback, user_data)
    
    print "added blobserver callback"


    while True:
        if VERBOSE and verbose_cnt == 0:
            print("-----------------------")

        verbose_cnt += 1
        if verbose_cnt > verbose_cntmax:
            verbose_cnt = 0

        # loop and dispatch messages every 33ms
        oscServer.recv(33)

        #-----#
        # cleanLog contains the list of the blob ID which are not active anymore
        cleanLog = []

        for i in trails:
            if trails[i][0].isAlive() == False:
                cleanLog.append(i)
                continue

            # Line trails are updated first
            sol, res = trails[i][0].track()
            eq = trails[i][0].identify().T
            if VERBOSE and verbose_cnt == 0:
                # print(eq, res)
                if len(eq) == 1 and len(res) == 1:  
                    print "%i: LINE \tslope %+07.2f, delta %+07.2f \t\t\t\t\t %07.2f%%" % (i, eq[0][0], eq[0][1], res[0])
            if OSC and len(eq) == 1:
                # OSC message: blobID, slope, delta at x=0
                liblo.send(oscClient, "/bigBrother/trail", "iff", i, eq[0][0], eq[0][1])

            # Then, circle trails
            sol, res = trails[i][1].track()
            eq = trails[i][1].identify().T
            if VERBOSE and verbose_cnt == 0:
                # print(eq, res)
                if len(eq) == 1 and len(res) == 1:
                    print "%i: CIRCLE \tcenter %3d | %3d \t radius %3d \t compl %+05.2f \t\t %05.2f%%" % (i, eq[0][0], eq[0][1], eq[0][2], eq[0][3], res[0])
            if OSC and len(eq) == 1:
                # OSC message: blobID, center_x, center_y, radius, completeness
                liblo.send(oscClient, "/bigBrother/trail_circle", "iffff", i, eq[0][0], eq[0][1], eq[0][2], eq[0][3])

        for i in cleanLog:
            trails.pop(i)

        if SHOW_CV:
            drawTrails(trails, IMAGE_SIZE, True, True, True)

        if SHOW_CV:
            key = cv.waitKey(5)
            if key == 27:
                break;

#*************#
if __name__ == "__main__":

    if len(sys.argv) > 1 and (sys.argv[1] == "-v" or sys.argv[1] == "-V"):
        VERBOSE = True

    mainLoop()
