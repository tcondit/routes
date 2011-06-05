#!/usr/bin/env python
'''Top-level driver for Taxis and Fares simulation.'''

import ConfigParser
import math
import os.path
import random
from agents.fare import Fare, FareFactory
from agents.taxi import Taxi
from agents.agent import Agent

from Tkinter import *
#from Tkinter import Frame, Tk
from Canvas import Line, CanvasText, Rectangle
from tkMessageBox import *
from tkSimpleDialog import askinteger, askstring, askfloat
from tkFileDialog import *

config=ConfigParser.SafeConfigParser()
config.read(os.path.join('agents','conf','agents','defaults.ini'))
config.read(os.path.join('agents','conf','agents','overrides.ini'))

# dev and runtime config values
TRACING=config.getboolean('dev','tracing')
NUM_TAXIS=config.getint('runtime','numTaxis')
NUM_FARES=config.getint('runtime','numFares')
NP=config.get('runtime','negotiationProtocol')
SIMTIME=config.getint('runtime','simulationTime')
SIMTYPE=config.get('runtime','simType')
USE_GUI=config.getboolean('runtime','useGUI')
SEED=config.getint('runtime','randomSeed')

if TRACING:
    from SimPy.SimulationTrace import *
else:
    from SimPy.Simulation import *

def printHeader(verbose=False):
    '''
    Print all the configuration data for this specific simulation
    run.

    Useful for ensuring we're comparing apples to apples.
    '''

    # What kind of leading information would be useful?  Full path to
    # driver.py?  Timestamp?
    print('---[ Useful information here ]---')

    if verbose:
        print('Sorry, verbose is not working yet.')
    else:
        print('Runtime configuration settings:')
        for k, v in config.items('runtime'):
            # TODO Think about how to compare the values of two dicts here, so
            # I can simply flag those that are changed from one to the other.
            print('  %s=%s' % (k, v))
        print('Development configuration settings:')
        for k, v in config.items('dev'):
            # TODO Think about how to compare the values of two dicts here, so
            # I can simply flag those that are changed from one to the other.
            print('  %s=%s' % (k, v))
    print('---[ No more useful information here ]---')


def model():
    '''
    The main method, where all simulations begin.

    TODO: Use config switch 'useGUI' to decide whether to use
    SimPlot/plotHistogram, or just printHistogram.  There is no
    reason to leave that important data out, even though I don't
    always want to incur the cost/hassle of producing a GUI.
    [Note: The plot code is in method oooh_shiny().  The name of
    the method is a strong hint that it's intended to be developed
    further.]
    '''
    initialize()
    random.seed(SEED)

#    # Create Fares prior to starting the simulation.  Now a TK.
#    for j in range(1,NUM_FARES):
#        # TODO Put this in place later.  grep for "Fare Fare" to see what it's
#        # doing.  It may in fact point to other problems with my strategy.
#        #f=Fare(name='Fare-' + `j`)
##        fname = 'Fare-%s' % j
##        f=Fare(fname)
#        f=Fare(name="Fare-"+str(j))
#        activate(f, f.run())

    # Team 1 - Yellow Cab
    for i in range(NUM_TAXIS):
        tx = Taxi('Taxi-%s' % i, NP)
        if SIMTYPE == 'cooperate':
            activate(tx, tx.cooperate())
        elif SIMTYPE == 'compete':
            activate(tx, tx.compete())
        else:
            print("Error: can't set the simulation type")
            import sys; sys.exit()
    #
    # Team 2 - Checker Cab
    #for i in range(4):
    #    tx=Taxi('Checker-%s' % i)
    #    tx=Taxi('Checker-%s' % i, 'closestfare')
    #    tx=Taxi('Checker-%s' % i, 'mixedmode')
    #    activate(tx, tx.cooperate())
    #    activate(tx, tx.compete())

    ff = FareFactory()
    activate(ff, ff.generate())
#    fare = ff.generate()
#    activate(ff, fare)
#    activate(ff, ff.generate(), datacollector=)
    simulate(until=SIMTIME)
    print('waitingFares', [x.name for x in Agent.waitingFares.theBuffer])

def reportstats():
    '''
    A summary report of various statistics for the current
    simulation run.
    '''
    #print('Fare.waitMon:', Fare.waitMon)
    print('Fare.waitMon.name:', Fare.waitMon.name)
    print('Fare.waitMon.yseries:', Fare.waitMon.yseries())
    print('  * yseries: Elapsed time between when the Fare made a request'),
    print('for pickup, and when the Taxi dropped off the Fare')
    print('Fare.waitMon.tseries():', Fare.waitMon.tseries())
    print('  * tseries: Recorded simtimes when the Taxis dropped off the Fares')
    print('Fare.waitMon.total:', Fare.waitMon.total())
    print('  * total: The total of all times recorded tseries times.  Not'),
    print('all that useful by itself, but used for calculating the mean.')
    print('Fare.waitMon.count:', Fare.waitMon.count())
    print('  * count: The number of Fares that were picked up and dropped off.')
    print('Fare.waitMon.mean:', Fare.waitMon.mean())
    print('  * mean: The mean of the values.  yseries/count')
    print('Fare.waitMon.var:', Fare.waitMon.var())
    print('  * var: The variance of the values.  All I know for certain is'),
    print('that the variance is the square of the standard deviation, which'),
    print('is generally considered a more useful statistic.')
    print('Fare.waitMon.stdDeviation:', math.sqrt(Fare.waitMon.var()))
    print('  * stdDeviation: Not part of SimPy.Monitor, but easy to'),
    print("calculate.  It's the square root of the variance.")
    print('Fare.waitMon.timeAverage:', Fare.waitMon.timeAverage())

def oooh_shiny():
    '''Make a histogram plot of Fare wait times.'''

    histoWidth=10
    if USE_GUI:
        from SimPy.SimPlot import SimPlot
        # Include enough bins to make each bar 'histoWidth' time units wide.
        #histo = Fare.waitMon.histogram(low=0.0, high=SIMTIME, nbins=SIMTIME/histoWidth)
        root = Tk()
        plt = SimPlot()
        waitBars = plt.makeBars(Fare.waitMon, color="blue")
        waitHisto = plt.makeHistogram(Fare.waitMon, color="red")
        waitLine = plt.makeLine(Fare.waitMon, color="green")
        #waitScatter = plt.makeScatter(Fare.waitMon, color="pink")
        waitStep = plt.makeStep(Fare.waitMon, color="black")

        hiredBars = plt.makeBars(Taxi.hiredMon, color="red")
        hiredHisto = plt.makeHistogram(Taxi.hiredMon, color="green")
        hiredLine = plt.makeLine(Taxi.hiredMon, color="black")
        #hiredScatter = plt.makeScatter(Taxi.hiredMon, color="pink")
        hiredStep = plt.makeStep(Taxi.hiredMon, color="blue")

        wonFareBars = plt.makeBars(Taxi.wonFareMon, color="red")
        wonFareHisto = plt.makeHistogram(Taxi.wonFareMon, color="green")
        wonFareLine = plt.makeLine(Taxi.wonFareMon, color="black")
        #wonFareScatter = plt.makeScatter(Taxi.wonFareMon, color="pink")
        wonFareStep = plt.makeStep(Taxi.wonFareMon, color="blue")

        lostFareBars = plt.makeBars(Taxi.lostFareMon, color="red")
        lostFareHisto = plt.makeHistogram(Taxi.lostFareMon, color="green")
        lostFareLine = plt.makeLine(Taxi.lostFareMon, color="black")
        #lostFareScatter = plt.makeScatter(Taxi.lostFareMon, color="pink")
        lostFareStep = plt.makeStep(Taxi.lostFareMon, color="blue")

        #graphObject = plt.makeGraphObjects([waitBars, hiredHisto])
        #graphObject = plt.makeGraphObjects([waitLine, hiredStep])
        #graphObject = plt.makeGraphObjects([waitBars, hiredHisto])
        #graphObject = plt.makeGraphObjects([waitLine, hiredStep])

# +     graphObject = plt.makeGraphObjects([waitBars, hiredBars])
        #graphObject = plt.makeGraphObjects([waitLine, hiredLine])
        #graphObject = plt.makeGraphObjects([waitLine, hiredLine, lostFareLine])
# +     graphObject = plt.makeGraphObjects([hiredLine, lostFareLine])
        graphObject = plt.makeGraphObjects([wonFareLine, lostFareLine])


#        plt.plotBars(Taxi.fareMon, color="blue")

        frame = Frame(root)

        graph = plt.makeGraphBase(frame, 500, 300, title = 'Plot 2: 1 makeBars call',
                xtitle = 'time', ytitle = 'pulse [volt]')
        # Set side - by - side plots
        graph.pack(side = LEFT, fill = BOTH, expand = YES)
        graph.draw(graphObject, 'minimal', 'automatic')
        frame.pack()



#        plt.plotHistogram(histo, xlab='Time', ylab='Number of waiting Fares',
#               title='Time waiting for Taxi', color='red', width=2)
        plt.mainloop()
    else:
        #Fare.waitMon.printHistogram(histo, xlab='Time', \
        #        ylab='Number of waiting Fares', \
        #        title='Time waiting for Taxi', color='red', width=2)
        #Fare.waitMon.printHistogram(histo)
        #Fare.waitMon.setHistogram(low=0.0, high=SIMTIME, nbins=20)
        Fare.waitMon.setHistogram(low=0.0, high=SIMTIME, nbins=SIMTIME/histoWidth)
        print(Fare.waitMon.printHistogram(fmt='%6.2f'))
    #print(Agent.waitingFares.theBuffer)

if __name__ == '__main__':
    printHeader()
    model()
    reportstats()
    oooh_shiny()
