#!/usr/bin/env python

import liblo
import sys
import cv2 as cv
from copy import deepcopy
from time import time, sleep
from numpy import *

VERBOSE = False
SHOW_CV = True
WRITE_CV = False

# Input resolution (from camera)
IMAGE_SIZE = [640, 480]

# Projection parameters
PROJECTION_IN = array([[0, 0], [640, 0], [640, 480], [0, 480]], float32)
PROJECTION_OUT = array([[0, 0], [640, 0], [640, 480], [0, 480]], float32)

FRAMENUMBER = 0


#*************#
class TimedPoint(object):
    def __init__(self, point):
        self.point = array(point, float32)
        self.time = time()

#*************#
# Trail class. The base class compares the path to a line
class Trail(object):
    # Constructor of the class
    def __init__(self, maxHistoryLength, maxTime, args = []):
        self._history = []
        self._rawHistory = []
        self._maxLength = maxHistoryLength
        self._maxTime = maxTime
        self._args = args
        self._maxLifetime = 30
        self._updated = False

        self._lifetime = self._maxLifetime
        self._trackLength = 20
        self._trackStep = 20

        self._sol = array([])
        self._res = 0
        self._usedLength = 0
        self._dist = 0

        self._projectionMat = array([])

    # This method is the one which does the computation
    # (comparison between the history and the "equation" of the path, which
    # is nothing more than a linear regression)
    def __trackOnce(self, a, b):
        A = vstack([a.T, ones(len(a))]).T
        result = linalg.lstsq(A, b)
        sol = result[0]
        res = result[1]
        return sol, sqrt(res / len(a))

    def updateProjection(self, inPoints, outPoints):
        self._projectionMat = cv.getPerspectiveTransform(inPoints, outPoints)

    # Adds a new position to the history
    def follow(self, point):
        newPoint = deepcopy(point)
        if len(self._projectionMat) > 0:
            projPoint = array([[point.point]], float32)
            projPoint = cv.perspectiveTransform(projPoint, self._projectionMat)
            newPoint.point = projPoint[0][0]
        newPoint = self.transformPoint(newPoint)
        self._history.append(newPoint)
        self._rawHistory.append(point) # We keep the original points, may be useful

        while len(self._history) > self._maxLength:
            self._history.remove(self._history[0])
            self._rawHistory.remove(self._rawHistory[0])

        while True:
            currentTime = self._history[len(self._history) - 1].time
            if time() - self._history[0].time > self._maxTime:
                self._history.remove(self._history[0])
                self._rawHistory.remove(self._rawHistory[0])
            else:
                break

        self._updated = True

    # Returns the parameters of the path, depending of the shape to follow
    # For the base class, it returns the parameters for the equation of a line
    def identify(self):
        if len(self._args) > 1 and self._args[1] < self._res:
            return array([])
        if len(self._args) > 0 and self._dist < self._args[0]:
            return array([])
        return self._sol

    # Checks is this instance of the class is still in use or not
    def isAlive(self):
        if self._lifetime > 0:
            return True
        else:
            return False

    # Compares the history to the model of a line, and outputs its parameters if
    # a line which fits enough is found.
    def track(self):
        if self._updated == False:
            self._lifetime -= 1
            return self._sol, self._res
        self._lifetime = self._maxLifetime
        self._updated = False

        if len(self._history) < self._trackLength:
            return array([]), 0

        a = []
        b = []
        for i in range(0, self._trackLength):
            index = len(self._history) - 1 - i
            vec = []
            for j in range(0, len(self._history[index].point) - 1):
                vec.append(self._history[index].point[j])
            a.append(vec)
            b.append([self._history[index].point[len(self._history[index].point)-1]])

        sol, res = self.__trackOnce(array(a), array(b))
        usedLength = self._trackLength
        dist = sqrt(sum(power(array(a[len(a)-1][:2])-array(a[0][:2]),2)))

        while len(a) + self._trackStep <= self._maxLength and len(a) + self._trackStep <= len(self._history):
            for i in range(len(a), len(a) + self._trackStep):
                index = len(self._history) - 1 - i
                vec = []
                for j in range(0, len(self._history[index].point) - 1):
                    vec.append(self._history[index].point[j])
                a.append(vec)
                b.append([self._history[index].point[len(self._history[index].point)-1]])

            newSol, newRes = self.__trackOnce(array(a), array(b))
            newUsedLength = len(a)
            newDist = sqrt(sum(power(array(a[len(a)-1][:2])-array(a[0][:2]),2)))            

            if newRes < res:
                sol = newSol
                res = newRes
                usedLength = newUsedLength
            if newDist > dist:
                dist = newDist

        self._sol = sol
        self._res = res
        self._usedLength = usedLength
        self._dist = dist

        return sol, res

    # Transformation of the point, to fit the model in a linear space
    # For a line, there is nothing to do.
    def transformPoint(self, point):
        return point

#*************#
# Class derived from Trail, but... for circles
class Trail_Circle(Trail):
    # The returned parameters are different, as we output circles
    def identify(self):
        if len(self._sol) != 3:
            return array([])

        sol = self._sol
        it = []
        it.append(sol[0])
        it.append(sol[1])
        it.append(sqrt(pow(sol[0], 2.0) + pow(sol[1], 2.0) - sol[2]))

        if len(self._args) > 0 and self._res > self._args[0]:   # resolution
            return array([])
        if len(self._args) > 1 and it[2] > self._args[1]:   # too big radius
            return array([])
        if len(self._args) > 2 and it[2] < self._args[2]:   # too small radius
            return array([])

        # We compute the completeness of the circle
        points = []
        for i in range(len(self._rawHistory) - self._usedLength, len(self._rawHistory)):
            vec = []
            vec.append(self._rawHistory[i].point[0])
            vec.append(self._rawHistory[i].point[1])
            points.append(vec)
        points = array(points)
        center = array([sol[0], sol[1]]).T
        meanDist = sqrt(sum(power(sum(points - center, 0) / self._trackLength, 2)))
        it.append(meanDist / it[2]) # We divide by the radius of the detected circle

        return array(it)

    # The points are transformed into a linear space which makes it
    # easier to detect circles. See http://www.math.sunysb.edu/~scott/Book331/Fitting_circle.html
    def transformPoint(self, point):
        orthoPoint = point.point
        newPoint = []
        newPoint.append(- 2 * orthoPoint[0])
        newPoint.append(- 2 * orthoPoint[1])
        newPoint.append(- pow(orthoPoint[0], 2.0) - pow(orthoPoint[1], 2.0))
        newPoint = TimedPoint(newPoint)
        newPoint.time = point.time
        return newPoint

#*************#
# Callback used by liblo when a new position for a blob is received
def trail_callback(path, args, types, src, user_data):
    blobPos = array([args[0], args[1]])

    # assign blobId depending if callback comes from HOG or BG-Subtractor
    if len(args) == 7:      # detector hog
        blobId = args[4]
    else:                   # detector bg_subtractor
        blobId = args[5]

    trails = user_data[0]
    maxHistory = user_data[1]
    pointLifetime = user_data[2]
    lineDetectionLevel = user_data[3]
    lineMinLength = user_data[4]
    circleDetectionLevel = user_data[5]
    circleMaxRadius = user_data[6]
    circleMinRadius = user_data[7]

    projIN = user_data[8]
    projOUT = user_data[9]

    if trails.has_key(blobId) == False:
        # We set in this list all the shapes we want to detect
        trails[blobId] = [Trail(maxHistory, pointLifetime, [lineDetectionLevel]), 
                          Trail_Circle(maxHistory, pointLifetime, [circleDetectionLevel, circleMaxRadius, circleMinRadius])]
        for i in range(len(trails[blobId])):
            trails[blobId][i].updateProjection(projIN, projOUT)

    tPoint = TimedPoint(blobPos)
    trails[blobId][0].follow(tPoint);
    trails[blobId][1].follow(tPoint);

#*************#
# Draws all recognized shapes
def drawTrails(trails):
    img = zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3))
    for i in trails:
        line = trails[i][0].identify()
        if len(line) == 0:
            continue
        start = (0, line[1])
        end = (IMAGE_SIZE[0], line[0] * IMAGE_SIZE[0] + line[1])
        cv.line(img, start, end, (255, 255, 0))

    for i in trails:
        circle = trails[i][1].identify()
        if len(circle) == 0:
            continue
        center = (circle[0], circle[1])
        radius = circle[2]
        cv.circle(img, center, radius, (255, 255, 255))

        cv.putText(img, str(circle[3][0]), (circle[0], circle[1]), cv.FONT_HERSHEY_PLAIN, 1, (255, 255, 255))

        contours = []
        #for index in range(0, len(trails[i][1]._rawHistory)):
        for index in range(len(trails[i][1]._rawHistory) - trails[i][1]._usedLength, len(trails[i][1]._rawHistory)):
            vec = []
            for j in range(0, len(trails[i][1]._rawHistory[index].point)):
                vec.append(trails[i][1]._rawHistory[index].point[j])
            contours.append(vec)
        if len(contours) > 0:
            cv.polylines(img, [array(contours, int32)], False, (0, 0, 255))

        contours = []
        for index in range(0, len(trails[i][1]._rawHistory) - trails[i][1]._usedLength):
            vec = []
            for j in range(0, len(trails[i][1]._rawHistory[index].point)):
                vec.append(trails[i][1]._rawHistory[index].point[j])
            contours.append(vec)
        if len(contours) > 0:
            cv.polylines(img, [array(contours, int32)], False, (255, 0, 0))

    cv.imshow("Trails", img)

    if WRITE_CV:
        cv.imwrite("img_" + str(FRAMENUMBER) + ".png", img)

#*************#
def mainLoop(maxHistory = 50, pointLifetime = 1e6, lineDetectionLevel = 64, lineMinLength = 100, circleDetectionLevel = 8192, circleMaxRadius = 256, circleMinRadius = 30):
    global FRAMENUMBER
    try:
        oscServer = liblo.Server(9000);
    except liblo.AddressError, err:
        print(str(err))
        sys.exit()

    trails = {}
    user_data = [trails, maxHistory, pointLifetime, lineDetectionLevel, lineMinLength, circleDetectionLevel, circleMaxRadius, circleMinRadius, PROJECTION_IN, PROJECTION_OUT]
    # Position of the blobs is set using a callback of liblo
    oscServer.add_method("/blobserver/bgsubtractor", "iiiffiii", trail_callback, user_data)
    oscServer.add_method("/blobserver/hog", "iiffiii", trail_callback, user_data)
    
    while True:
        if VERBOSE:
            print("--------------------------")
        oscServer.recv(33)

        cleanLog = []
        for i in trails:
            if trails[i][0].isAlive() == False:
                cleanLog.append(i)
                continue

            # Line trails are updated first, then circles
            sol, res = trails[i][0].track()
            if VERBOSE:
                print(trails[i][0].identify().T, res)
            sol, res = trails[i][1].track()
            if VERBOSE:
                print(trails[i][1].identify().T, res)

        for i in cleanLog:
            trails.pop(i)

        if SHOW_CV:
            drawTrails(trails, IMAGE_SIZE)

        cv.waitKey(5)
        FRAMENUMBER += 1

#*************#
def usage():
    print("Usage: trail.py [maxHistory [pointLifetime [lineDetectionLevel [ lineMinLength [circleDetectionLevel [circleMaxRadius[circleMinRadius]]]]]]]")

#*************#
if __name__ == "__main__":
    if len(sys.argv) > 1 and (sys.argv[1] == "-h" or sys.argv[1] == "--help"):
        print("Trail, a small script to follow trails from blobserver")
        usage()
        sys.exit()

    maxHistory = 150
    pointLifetime = 1e6
    lineDetectionLevel = 5
    lineMinLength = 200
    circleDetectionLevel = 500
    circleMaxRadius = 200
    circleMinRadius = 30

    try:
        maxHistory = float(sys.argv[1])
        pointLifetime = float(sys.argv[2])
        lineDetectionLevel = float(sys.argv[3])
        lineMinLength = float(sys.argv[4])
        circleDetectionLevel = float(sys.argv[5])
        circleMaxRadius = float(sys.argv[6])
        circleMinRadius = float(sys.arg[7])
    except:
        usage()

    mainLoop(maxHistory, pointLifetime, lineDetectionLevel, lineMinLength, circleDetectionLevel, circleMaxRadius, circleMinRadius)
