#!/usr/bin/env python
'''The taxi module'''

from operator import itemgetter # itemgetter is new in Python 2.4
from agent import Agent
import ConfigParser
import os.path

config = ConfigParser.SafeConfigParser()
config.read(os.path.join('agents','conf','agents','defaults.ini'))
config.read(os.path.join('agents','conf','agents','overrides.ini'))

# dev config values
TRACING = config.getboolean('dev', 'tracing')
DEBUG = config.getboolean('dev', 'debug')
SET_TRACE = config.getboolean('dev', 'setTrace') # for interactive debugging

# runtime config values
SIMTIME = config.getint('runtime', 'simulationTime')
TAXI_RANGE_LOW = config.getfloat('runtime', 'taxiRangeLow')
TAXI_RANGE_MID = config.getfloat('runtime', 'taxiRangeMedium')
TAXI_RANGE_HI = config.getfloat('runtime', 'taxiRangeHigh')
GRID_MIN = config.getint('runtime', 'gridMin')
GRID_MAX = config.getint('runtime', 'gridMax')
SIMTYPE = config.get('runtime', 'simType')

if TRACING:
    from SimPy.SimulationTrace import *
else:
    from SimPy.Simulation import *

if SET_TRACE:
    import pdb

# This is a 2-tuple used by the filter functions.  Looks like (23, 61).
taxi_loc = ()


class Taxi(Agent):
    '''Taxis are Agents (which are SimPy processes).'''
    hiredMon = Monitor('All Taxis total utilization time', tlab='simulation steps', ylab='in-service times')
    travelMon = Monitor('All Taxis total distance traveled', tlab='simulation steps', ylab='distance')

    fareMon = Monitor('All Taxis total number of Fares served', tlab='simulation steps', ylab='current Fares served')
    fareCount = 0

    wonFareMon = Monitor('Competing Taxis total number of Fares won', tlab='simulation steps', ylab='Fares won')
    wonFareCount = 0

    lostFareMon = Monitor('Competing Taxis total number of Fares lost', tlab='simulation steps', ylab='Fares lost')
    lostFareCount = 0

    def __init__(self, name, np): # negotiation protocol
        '''DOCSTRING'''
        Agent.__init__(self, name)
        self.np=np
        self.lostFares=[]

    def cooperate(self):
        '''
        Coordinate pickups with other Taxis.  A SimPy PEM.

        This is the PEM for cooperative negotiation.  In this
        simulation, Taxis choose a Fare for pickup, and take a
        reference to the Fare at acknowledgment.  The Taxi
        effectively locks out other Taxis from competing for that
        Fare by removing it from the queue of waiting Fares just
        before yield'ing for the ride to the Fare.

        Contrast with the compete() method.
        '''
        global taxi_loc
        while True:
            if len(Agent.waitingFares.theBuffer) > 0:
                if DEBUG:
                    print
                    print("%.2f %s is looking for an eligible Fare:" % (now(), self.name))
                    print(".. waitingFares (pre) ", [x.name for x in Agent.waitingFares.theBuffer])
                taxi_loc = self.loc['curr']

                # 1: Choose a Fare (no representation in observes.txt?)
                #
                # When yield is called in a cooperate simtype, the Fare is
                # removed from the wait queue, and essentially "reserved for
                # pickup" by this Taxi.  The Taxi is GOING_TO_FARE (see
                # observes.txt), and both are unavailable.
                if self.np == 'FIFO':
                    yield get, self, Agent.waitingFares, 1
                elif self.np == 'closestfare':
                    # What's the point of numAgents here? --timc 1/24/2009
                    numAgents=len(Agent.waitingFares.theBuffer)
                    yield get, self, Agent.waitingFares, closestfare_cooperate
                elif self.np == 'mixedmode':
                    yield get, self, Agent.waitingFares, mixedmode_cooperate
                else:
                    print("Something broke in the negotiation protocol!")
                if DEBUG:
                    print(".. waitingFares (post)", [x.name for x in Agent.waitingFares.theBuffer])
                    assert len(self.got) == 1
                # self.got is a list but we restrict it to a single element
                # representing the Fare object that was selected by this Taxi
                fareBeingDriven=self.got[0]
                Taxi.fareCount += 1
                Taxi.fareMon.observe(Taxi.fareCount)
                print("%.2f\t%s chose %s" % (now(), self.name, fareBeingDriven.name))

                # 2: Drive to Fare (transition to GOING_TO_FARE)
                drive_dist=self.map.get_distance(fareBeingDriven.loc['curr'], taxi_loc)
                Taxi.travelMon.observe(drive_dist)
                if DEBUG:
                    print("%.2f\t%s driving to %s" % (now(), self.name, fareBeingDriven.name))
                yield hold, self, drive_dist

                # 3: Pick up Fare (transition to HIRED)
                self.loc=fareBeingDriven.loc     # tuple
                if DEBUG:
                    print("%.2f\t%s arrives to pick up %s" % (now(), self.name, fareBeingDriven.name))

                # 4: Drive to Fare's destination (HIRED)
                drive_dist=self.map.get_distance(self.loc['dest'], self.loc['curr'])
                Taxi.hiredMon.observe(drive_dist)
                Taxi.travelMon.observe(drive_dist)

                # 5: Drop Fare at destination (transition to IDLE)
                #
                # (minor hack) Collect the expected arrival time so that it
                # can be reported accurately even if the simulation ends
                # before arrival.
                dropoffTime=now()+drive_dist
                print("%s dropoffTime for %s: %.2f" % (self.name, fareBeingDriven.name, dropoffTime))
                if DEBUG:
                    print("%.2f\t%s driving to %s's destination" % (now(), self.name, fareBeingDriven.name))
                yield hold, self, drive_dist
                # Drop off Fare
                self.loc['curr'] = fareBeingDriven.loc['dest']
                self.loc['dest'] = ()
                if DEBUG:
                    print("%.2f\t%s dropping off %s" % (now(), self.name, fareBeingDriven.name))
                fareBeingDriven.doneSignal.signal(self.name)
            else:
                print("%.2f\tINFO: %s: There are no eligible Fares for this Taxi." % (now(), self.name))

                # Throttle back the flood of messages.
                #
                # NOTE: I'm using a simple 'yield hold <small-number>' here
                # because there are two main events that can occur, and the
                # Taxi should be able to respond to them promptly.  The first
                # is the arrival of a new Fare into the buffer.  The second is
                # a Fare already in the queue that becomes eligible for
                # inspection by the Taxi.
                yield hold, self, 2


    def compete(self):
        '''
        Compete for Fares against other Taxis.  A SimPy PEM.

        This method differs from cooperate() in a couple important
        ways.  First is that the Taxis are currently competing for
        Fares in an "every man for himself" sort of way.  Second
        is that compete uses the same negotiation protocols, but
        they work a little differently.  Instead of taking a
        reference to a Fare, and removing it from the queue of
        eligible Fares as soon as it is identified, these Taxis
        need to reach the Fare before they can claim it as their
        own.  Also, the Taxis do not communicate with each other
        during the competition.  They mainly communicate with each
        other when one of them claims a Fare, and alerts the
        others that that Fare is no longer available.

        Implementation detail: Every Taxi that competes for a
        particular Fare goes into that Fare's competeQ.  Then the
        Taxi yields for drive_dist time.  If the yield expires,
        that Taxi got there first, and wins the Fare!  The winning
        Taxi pulls the Fare from the queue, and interrupts all
        other members of that Fare's competeQ.   The remaining
        Taxis call self.interruptReset(), and go off to compete
        for another Fare.

        Because the Fares stay in the queue until someone "wins"
        the right to go pick them up, latecomers should have a
        shot at them too.  If they are closer, they may get the
        Fare, even though others are already competing for that
        Fare.

        Contrast with the cooperate() method.
        '''

        global taxi_loc # maybe I should use class G

        while True:
            if len(Agent.waitingFares.theBuffer) > 0:
                if DEBUG:
                    my_curr_pre=self.loc['curr']
                    my_dest_pre=self.loc['dest']

                # Choose a Fare
                if self.np=='FIFO':
                    targetFare=Agent.waitingFares.theBuffer[0]
                elif self.np=='closestfare':
                    numAgents=len(Agent.waitingFares.theBuffer)
                    targetFare=self.closestfare_compete()
                    if DEBUG:
                        assert(numAgents==len(Agent.waitingFares.theBuffer))
                        print("%s targetFare closestfare %s" % (self.name, targetFare.name))
                elif self.np=='mixedmode':
                    numAgents=len(Agent.waitingFares.theBuffer)
                    targetFare=self.mixedmode_compete()
                    if DEBUG:
                        assert(numAgents==len(Agent.waitingFares.theBuffer))
                    if targetFare:
                        if DEBUG:
                            print("%s targetFare closestfare %s" % (self.name, targetFare.name))
                    else:
                        # Not a lot I can do here, since I don't have a Fare
                        # to compete for.  I should never get here, so this
                        # should be an Error.  For now I'll just throttle back
                        # the flood of messages and move on.
                        print("%.2f\tINFO: There are no eligible Fares for %s" % (now(), self.name))
                        yield hold, self, 2
                        continue
                # End choose a Fare

                if DEBUG:
                    assert(self.loc['curr']==my_curr_pre)
                    assert(self.loc['dest']==my_dest_pre)

                # update destination unconditionally
                self.loc['dest']=targetFare.loc['curr']

                if self.loc['curr']==targetFare.loc['curr']:
                    # Taxi and Fare are at the same vertex!  drive_dist is 0!
                    drive_dist=0
                else:
#                    print('%.2f DEBUG: %s calling get_distance [1]' % (now(), self.name))
                    drive_dist=self.map.get_distance(self.loc['dest'], self.loc['curr'])
                    Taxi.hiredMon.observe(drive_dist)
                    # Total distance traveled with compete() may be hard to
                    # get.  Go for number of lost Fares instead.
                    #Taxi.travelMon.observe(drive_dist)

                # This cannot happen.  I need to figure out how to remove
                # these Graph dead spots before they are added to the
                # database.
                if drive_dist is None: # no path from curr to dest
                    print("INFO: no path from %s to %s" % (self.name, targetFare.name))
                    print("%.2f\t%s is back in service" % (now(), self.name))
                    self.loc['curr']=targetFare.loc['dest']
                    self.loc['dest']=()
                    continue

                # Drive to Fare, try to get there first
                print("%.2f\t%s competing for %s (drive time %s)" % (now(), self.name, targetFare.name, drive_dist))
                yield hold, self, drive_dist

                print("%.2f\t%s arrives at %s's location (drive time %.2f)" %
                    (now(), self.name, targetFare.name, drive_dist))

                # Taxi has now driven to the Fare's pickup location.  Update
                # its location to that of the Fare its competing for.  If Fare
                # is still here, self.loc['dest'] is accurate.  Otherwise,
                # need to reset it after querying the filter function for its
                # new Fare.  Set the global taxi_loc so we can use this value
                # in fare_is_here().
                self.loc['curr']=taxi_loc=targetFare.loc['curr']
                self.loc['dest']=()

                # TEMP DEBUG
                print("%.2f\t%s trying to get %s" % (now(), self.name, targetFare.name))

                # HACK HACK - choose a random small float wait time for
                # reneging.  This is a bit of a hack to get around the fact
                # that ...
                yield_time=random.random()/100
                yield (get, self, Agent.waitingFares, fare_is_here), (hold, self, yield_time)

                # HACK HACK - "absorb" the renege (if it occurs) from the
                # yield above.  The idea is to yield for some semi-random time
                # longer than the length of that yield, to ensure that the
                # renege time has elapsed.
                yield hold, self, yield_time+random.random()/100

                # Got the Fare
                if len(self.got)>0:
                    print("%.2f\t%s picked up %s" % (now(), self.name, self.got[0].name))
                    self.loc['dest']=targetFare.loc['dest']
                    Taxi.wonFareCount+=1
                    Taxi.wonFareMon.observe(Taxi.wonFareCount)
#                   print('%.2f DEBUG: %s calling get_distance [2]' % (now(), self.name))
                    if self.loc['dest']==self.loc['curr']:
                        # TODO WTF!  Fare's destination is the same as it's
                        # current location???  I need to make sure they are
                        # not the same (this also could happen, but probably
                        # wouldn't ... and in any event, I won't let it
                        # happen).  This will do in the meantime.
                        drive_dist=0
                    else:
                        drive_dist=self.map.get_distance(self.loc['dest'], self.loc['curr'])
                    if drive_dist is None: # no path from curr to dest
                        print("INFO: no path from %s to %s" % (self.name, self.got[0].name))
                        print("%.2f\t%s is back in service" % (now(), self.name))
#                       self.loc['curr']=self.got[0].loc['dest']
#                       self.loc['dest']=()
                        continue

                    # Drive to Fare's destination, then continue
                    print("%.2f\t%s driving to %s's destination (drive time %.2f)" %
                        (now(), self.name, targetFare.name, drive_dist))
                    yield hold, self, drive_dist

                    # BUGBUG this was missing from compete() !!
                    targetFare.doneSignal.signal(self.name)
                    Taxi.fareCount += 1
                    Taxi.fareMon.observe(Taxi.fareCount)

                    print("%.2f\t%s is back in service" % (now(), self.name))
                    self.loc['curr']=targetFare.loc['dest']
                    self.loc['dest']=()
                    continue

                # Too late, Fare already picked up
                else:
                    print("%.2f\t%s lost %s" % (now(), self.name, targetFare.name))
                    print("%.2f\t%s back in service" % (now(), self.name))
                    self.loc['dest']=()
                    Taxi.lostFareCount+=1
                    Taxi.lostFareMon.observe(Taxi.lostFareCount)

            else:
                print("%.2f\tINFO: There are no eligible Fares for %s" % (now(), self.name))
                # Throttle back the flood of messages.
                #
                # NOTE: I'm using a simple 'yield hold <small-number>' here
                # because there are two main events that can occur, and the
                # Taxi should be able to respond to them promptly.  The first
                # is the arrival of a new Fare into the buffer.  The second is
                # a Fare already in the queue that becomes eligible for
                # inspection by the Taxi.
                yield hold, self, 2


    def closestfare_compete(self, not_a_magic_buffer=None):
        '''
        TODO UPDATE DOCSTRING

        Filter: return the Fare that is geographically closest to
        the calling Taxi.

        NOTE: The Fare is returned as a single-element list,
        because that (a list) is what SimPy's yield is expecting.
        This is a filter function for the Store, and should not be
        called directly.  This is the second of the Taxi's three
        negotiation protocols.
        '''
        tmp=[]
        if not not_a_magic_buffer:
            not_a_magic_buffer=Agent.waitingFares.theBuffer
        if DEBUG:
            if buffer==Agent.waitingFares.theBuffer:
                print('the buffers are equal')
            if buffer is Agent.waitingFares.theBuffer:
                print('the buffers are the same')
        if not len(not_a_magic_buffer)>0:
            print('Buffer is empty!')
            return
        for fare in not_a_magic_buffer:

            # DEBUG
            #
            # Try to figure out why graph get_distance() sometimes triggers a
            # TypeError.  It's here:
            #   for lon,lat in self.mkgraph.shortest_path(here,there):
            # TypeError: 'int' object is not iterable
            #
            # HEY!  Look what jumped out!  The Taxi and Fare current locations
            # are the same!  Zzzzzap!!!  Something's broken!  (And my note
            # about forgetting to reset a loc seems to be pointing in the
            # right direction.)
            #
            #((u'-149169424', u'64331706'), (u'-149169424', u'64331706'))
            #Too short?  Maybe I forgot to reset a loc?
            #
#           print(self.name, self.loc['curr'], fare.name, fare.loc['curr'])
            if self.loc['curr']==fare.loc['curr']:
                # Taxi and Fare are at the same vertex!  Short circuit the
                # whole deal and just take the Fare.
                print("Taxi and Fare are at the same vertex!")
                return fare
            else:
                d=self.map.get_distance(fare.loc['curr'], self.loc['curr'])

            if DEBUG:
                print("Distance from %s to %s: %.2f" % (self.name, fare.name, d))
            tmp.append((fare, d))
        tmp2=sorted(tmp, key=itemgetter(1))
        result=map(itemgetter(0), tmp2)[0]

        # Critical difference between the competition and cooperative
        # closestfares: cooperative cf returns the Fare, and removes it from
        # waitingFares.theBuffer immediately.  Competition cf just returns the
        # Fare, without taking it out of the buffer until later.  Note also,
        # this method returns a single Fare, not (a list containing) a single
        # Fare.
        return result


    # Third of the Taxi's three negotiation protocols.  See notes in
    # ~/finalproject/agents/docs/daily_status/2007/04/08.txt
    def mixedmode_compete(self, not_a_magic_buffer=None):
        '''
        Find the Fare with the lowest aggregate score.

        The Taxi uses a combination of the Fare's time in the
        waitingFares buffer plus their distance from the Taxi to
        determine which Fares to inspect.  If there are any Fares
        in this list, then the one with the lowest score (cost) is
        returned to the caller.

        If the list is empty, in other words, if there are no
        Fares which meet the time and space (distance)
        requirements of this Taxi, the Taxi goes into a getQ, and
        stays there until at least one suitable Fare comes along.
        Fortunately, there don't seem to be any restrictions from
        SimPy on when a Taxi can get out of the queue.  It's just
        a matter of satisfying the filter function.

        NOTE: This method is explicitly not a SimPy filter
        function.  It behaves similarly, but is used for
        competition only, which has different requirements, since
        only the first Taxi to reach the Fare may remove the Fare
        from the queue, and all others have to renege out.
        '''

        def __printFareDetails(taxiRange):
            '''DOCSTRING'''
            PRETTY_PRINT = config.getboolean('runtime', 'prettyPrint')
            print
            if PRETTY_PRINT:
                # TODO [lopri] This is unclear.  For example, what does range
                # even mean in this context?  It should refer to the range
                # that a Taxi is looking for Fares.  I am using it to mean the
                # distance (reach) of the Fare's broadcast.  Sort this out.
                #
                # I need to use as many words as it takes
                # to_make_things_clear.  I can shorten them later, but not
                # until things are simpler.
                print("  %.2f\tFare %s broadcast stats:" % (now(), fare.name))
                print("    range: %s (based on Fare's time in queue)" % broadcastRange)
                print("    time in queue: %.2f" % TIQ)
                print("    distance from Taxi: %.2f" % d)
                print("    Taxi's range: %.2f (= TAXI_RANGE_XXX * GRID_MAX)" % (taxiRange*GRID_MAX))
                print("    weight: %.2f\t(= SIMTIME - TIQ)" % weight)
                print("    score: %.2f\t(= weight + distance)" % score)
            else:
                print("  %.2f\t%s's broadcast stats: range: %s, time in queue: %.2f, Taxi's range: %.2f, distance from Taxi: %.2f, weight: %.2f, score: %.2f" %
                        (now(), fare.name, broadcastRange, TIQ, taxiRange*GRID_MAX, d, weight, score))

        # start of mixedmode_compete()
        tmp = []
        if not not_a_magic_buffer:
            not_a_magic_buffer = Agent.waitingFares.theBuffer
        VERBOSE = config.getboolean('runtime', 'verbose')
        # I should never hit this, but it can't hurt to leave it in.
        if not len(Agent.waitingFares.theBuffer) > 0:
            print('Buffer is empty!')
            return
        for fare in not_a_magic_buffer:
            TIQ = (now() - fare.ts['mkreq'])

            # TODO This is broken in a familiar way.  If I recall correctly
            # (and you'd think I would, with all the headache this caused), it
            # means that the Taxi and the Fare are at the same location!
            # Whether this is a "happy coincidence", or whether another Taxi
            # got here first (something which was disproven in
            # closestfare_compete) is unclear so far.
            #
            # At any rate, it's easy to fix since I've fixed it in three
            # places in closestfare_compete already.
            #
#1090.8933       Taxi-3 is back in service
#.. Pushing (Fare-33, score 2264.4608) onto list
#.. Pushing (Fare-34, score 2272.4847) onto list
#.. Pushing (Fare-38, score 2362.8803) onto list
#.. Pushing (Fare-42, score 2493.7965) onto list
#.. Pushing (Fare-44, score 2539.8396) onto list
#.. Pushing (Fare-54, score 2594.2863) onto list
#.. Pushing (Fare-57, score 2664.5078) onto list
#.. Pushing (Fare-61, score 2731.6690) onto list
#.. Pushing (Fare-63, score 2772.4385) onto list
#Traceback (most recent call last):
#  File "C:\Source\hg\unified\agents_driver.py", line 175, in <module>
#    model()
#  File "C:\Source\hg\unified\agents_driver.py", line 98, in model
#    simulate(until=SIMTIME)
#  File "c:\program files\python25\lib\site-packages\SimPy\Simulation.py", line 2009, in simulate
#    a=_e._nextev()
#  File "c:\program files\python25\lib\site-packages\SimPy\Simulation.py", line 554, in _nextev
#    tt=tempwho._nextpoint.next()
#  File "C:\Source\hg\unified\agents\taxi.py", line 181, in compete
#    targetFare=self.mixedmode_compete()
#  File "C:\Source\hg\unified\agents\taxi.py", line 440, in mixedmode_compete
#    d = self.map.get_distance(fare.loc['curr'], self.loc['curr'])
#  File "C:\Source\hg\unified\agents\graph.py", line 186, in get_distance
#    for lon,lat in self.mkgraph.shortest_path(here,there):
#TypeError: 'int' object is not iterable
            #
            #if fare.loc['curr']==self.loc['curr']:
                #print("Taxi and Fare are at the same vertex!")
                # (followed by a TypeError)
            #
            #d = self.map.get_distance(fare.loc['curr'], self.loc['curr'])

            if fare.loc['curr']==self.loc['curr']:
                # Taxi and Fare are at the same vertex!  drive_dist is 0!
                d=0
            else:
                d=self.map.get_distance(fare.loc['curr'],self.loc['curr'])
                #d=self.map.get_distance(fare.loc['dest'],self.loc['curr'])

            # TODO [eventually] put the weight and scoring routines into a
            # config file.  Major TK.
            weight = SIMTIME - TIQ
            score = weight + d
            f_time_ratio = TIQ/(SIMTIME*1.0)    # force integer division

            # Figure out which category the Fare goes in.  The first part is
            # all about TIME!
            #
            # If Fare has been in the queue long enough for a Global
            # broadcast, calculate score and append to list for further
            # consideration.
            if TAXI_RANGE_MID < f_time_ratio <= TAXI_RANGE_HI:
                broadcastRange = 'GLOBAL'
                if VERBOSE: __printFareDetails(TAXI_RANGE_HI)
                # NB: Taxi names are not available inside this function
                print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
                tmp.append((fare, score))

            # Has the Fare been in the queue long enough to be a Regional?
            elif TAXI_RANGE_LOW < f_time_ratio <= TAXI_RANGE_MID:
                broadcastRange = 'REGIONAL'
                if VERBOSE: __printFareDetails(TAXI_RANGE_MID)

                # Is Fare close enough for Taxi to pickup?
                #
                # If distance from Taxi to Fare is less than or equal to
                # (TAXI_RANGE_MID * GRID_MAX), then broadcast is received by
                # Taxi, and Fare gets added to the queue.
                if d <= (TAXI_RANGE_MID * GRID_MAX):
                # NB: Taxi names are not available inside this function
                    print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
                    tmp.append((fare, score))
                else:
                    # Fare's been around long enough for it's broadcast to be
                    # Regional, but this Taxi is not in range.  Break out of
                    # the loop, and evaluate the next Fare.
                    if DEBUG:
                        print('  %s: regional broadcast, but Fare is out of range:' % fare.name),
                        print("(distance) %.1f > (range) %.1f" % (d, TAXI_RANGE_MID * GRID_MAX))
                    if (d < (TAXI_RANGE_LOW * GRID_MAX)):
                        print('Regional broadcast is broken!')
                    continue

            # It's a local broadcast
            else:
                broadcastRange = 'LOCAL'
                if VERBOSE: __printFareDetails(TAXI_RANGE_LOW)
                # The Fare has only been in the queue long enough to be a Local
                if d <= (TAXI_RANGE_LOW  * GRID_MAX):
                    # NB: Taxi names are not available inside this function
                    print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
                    tmp.append((fare, score))
                else:
                    # Local broadcast, but this Taxi is not in range.  Break
                    # out of the loop, and evaluate the next Fare.
                    if DEBUG:
                        print('  Fare %s: local broadcast, but Fare is out of range:' % fare.name),
                        print("(distance) %.1f > (range) %.1f" % (d, TAXI_RANGE_LOW * GRID_MAX))
                    if (d < TAXI_RANGE_LOW * GRID_MAX):
                        print('Local broadcast is broken!')
                    continue

        # If I hit the continue every time, it's easy to get here and have
        # nothing in tmp2.  I'm not sure this is right, but it seems to me
        # that if there's nothing here, the only thing left to do is return.
        if len(tmp) == 0:
            if DEBUG:
                print("%.2f\tINFO:" % now()),
                print('There are no eligible Fares for this Taxi.  Entering getQ...')
#                print("%.2f\tINFO: There are no eligible Fares for %s" % (now(), self.name))
            return

        tmp2 = sorted(tmp, key=itemgetter(1))
        result = map(itemgetter(0), tmp2)[0]
        # Borrowed from the bottom of closestfare.  Applies here as well.
        #
        # Critical difference between the competition and cooperative
        # closestfares: cooperative cf returns the Fare, and removes it from
        # waitingFares.theBuffer immediately.  Competition cf just returns the
        # Fare, without taking it out of the buffer until later.  Note also,
        # this method returns a single Fare, not (a list containing) a single
        # Fare.
        return result


def closestfare_cooperate(buffer):
    '''
    Filter: return the Fare that is geographically closest to the
    calling Taxi.

    Implementation detail: I think the name 'buffer' is mentioned
    in the documentation as being a special trigger for SimPy, to
    ensure "magic behavior".

    NOTE: The Fare is returned as a single-element list, because
    that (a list) is what SimPy's yield is expecting.  This is a
    filter function for the Store, and should not be called
    directly.  This is the second of the Taxi's three negotiation
    protocols.
    '''
    tmp=[]
    if not len(Agent.waitingFares.theBuffer) > 0:
        print('Buffer is empty!')
        return
    if DEBUG:
        if buffer==Agent.waitingFares.theBuffer:
            print('the buffers are equal')
        if buffer is Agent.waitingFares.theBuffer:
            print('the buffers are the same')
    for fare in buffer:
        d=Agent.map.get_distance(fare.loc['curr'], taxi_loc)
        if DEBUG:
            print("Distance from Taxi to Fare %s: %.2f" % (fare.name, d))
        tmp.append((fare, d))
    tmp2=sorted(tmp, key=itemgetter(1))
    result=map(itemgetter(0), tmp2)[0]
    return [result]


# Third of the Taxi's three negotiation protocols.  See notes in
# ~/finalproject/agents/docs/daily_status/2007/04/08.txt
def mixedmode_cooperate(buffer):
    '''
    Filter: find the Fare with the lowest aggregate score.

    The Taxi uses a combination of the Fare's time in the
    waitingFares buffer plus their distance from the Taxi to
    determine which Fares to inspect.  If there are any Fares in
    this list, then the one with the lowest score (cost) is
    returned to the caller.

    If the list is empty, in other words, if there are no Fares
    which meet the time and space (distance) requirements of this
    Taxi, the Taxi goes into a getQ, and stays there until at
    least one suitable Fare comes along.  Fortunately, there don't
    seem to be any restrictions from SimPy on when a Taxi can get
    out of the queue.  It's just a matter of satisfying the filter
    function.

    NOTE: The Fare is returned as a single-element list, because
    that's what SimPy's yield is expecting.  This is a filter
    function for the Store, and should not be called directly.
    This is the third of the Taxi's three negotiation protocols.
    '''
    def __printFareDetails(taxiRange):
        '''DOCSTRING'''
        PRETTY_PRINT = config.getboolean('runtime', 'prettyPrint')
        print
        if PRETTY_PRINT:
            # TODO [lopri] This is unclear.  For example, what does range even
            # mean in this context?  It should refer to the range that a Taxi
            # is looking for Fares.  I am using it to mean the distance
            # (reach) of the Fare's broadcast.  Sort this out.
            #
            # I need to use as many words as it takes to_make_things_clear.  I
            # can shorten them later, but not until things are simpler.
            print("  %.2f\tFare %s broadcast stats:" % (now(), fare.name))
            print("    range: %s (based on Fare's time in queue)" % broadcastRange)
            print("    time in queue: %.2f" % TIQ)
            print("    distance from Taxi: %.2f" % d)
            print("    Taxi's range: %.2f (= TAXI_RANGE_XXX * GRID_MAX)" % (taxiRange*GRID_MAX))
            print("    weight: %.2f\t(= SIMTIME - TIQ)" % weight)
            print("    score: %.2f\t(= weight + distance)" % score)
        else:
            print("  %.2f\tFare %s broadcast stats: range: %s, time in queue: %.2f, Taxi's range: %.2f, distance from Taxi: %.2f, weight: %.2f, score: %.2f" %
                (now(), fare.name, broadcastRange, TIQ, taxiRange*GRID_MAX, d, weight, score))

    # start of mixedmode_cooperate()
    tmp = []
    VERBOSE = config.getboolean('runtime', 'verbose')
    # I should never hit this, but it can't hurt to leave it in.
    if not len(Agent.waitingFares.theBuffer) > 0:
        print('Buffer is empty!')
        return
    for fare in buffer:
        TIQ = (now() - fare.ts['mkreq'])

        # Race condition?  Nope.  Taxi and Fare are at the same location
        # (again), and I'm fixing it for at least the third time.  This needs
        # a refactoring.
        #
#        print("DEBUG fare.loc['curr']: %s" % str(fare.loc['curr']))
#        print("DEBUG taxi_loc: %s" % str(taxi_loc))
        ###
        # 340.99 pushing (Fare-99, score 414.31) onto list
        #  Fare-101: local broadcast, but Fare is out of range: (distance) 121.7 > (range) 35.0
        #340.99 pushing (Fare-102, score 443.31) onto list
        #  Fare-103: local broadcast, but Fare is out of range: (distance) 75.5 > (range) 35.0
        #340.99 pushing (Fare-104, score 475.22) onto list
        #Traceback (most recent call last):
        #  File "C:\Source\hg\unified-animations\agents_driverdriver.py", line 136, in <module>
        #    model_cooperate_mixedmode(); print
        #  File "C:\Source\hg\unified-animations\agents_driverdriver.py", line 67, in model_cooperate_mixedmode
        #    simulate(until=SIMTIME)
        #  File "C:\Program Files\Python26\lib\site-packages\simpy-2.0.1-py2.6.egg\SimPy\Globals.py", line 60, in simulate
        #    return sim.simulate(until = until)
        #  File "C:\Program Files\Python26\lib\site-packages\simpy-2.0.1-py2.6.egg\SimPy\Simulation.py", line 700, in simulate
        #
        #    dispatch[command](a)
        #  File "C:\Program Files\Python26\lib\site-packages\simpy-2.0.1-py2.6.egg\SimPy\Simulation.py", line 863, in getfunc
        #    a[0][2]._get(a)
        #  File "C:\Program Files\Python26\lib\site-packages\simpy-2.0.1-py2.6.egg\SimPy\Lib.py", line 884, in _get
        #    movCand = filtfunc(self.theBuffer)
        #  File "C:\Source\hg\unified-animations\agents\taxi.py", line 667, in mixedmode_cooperate
        #    d = Agent.map.get_distance(fare.loc['curr'], taxi_loc)
        #  File "C:\Source\hg\unified-animations\agents\graph.py", line 212, in get_distance
        #    for lon,lat in self.shortest_path(here,there):
        #TypeError: 'int' object is not iterable

        if taxi_loc==fare.loc['curr']:
            # Taxi and Fare are at the same vertex!  Short circuit the whole
            # deal and just take the Fare.
            print("Taxi and Fare are at the same vertex!")
            d = 0
        else:
            d = Agent.map.get_distance(fare.loc['curr'], taxi_loc)

        # TODO [eventually] put the weight and scoring routines into a config
        # file.  Major TK.
        weight = SIMTIME - TIQ
        score = weight + d
        f_time_ratio = TIQ/(SIMTIME*1.0)    # force integer division

        # Figure out which category the Fare goes in.  The first part is all
        # about TIME!
        #
        # If Fare has been in the queue long enough for a Global broadcast,
        # calculate score and append to list for further consideration.
        if TAXI_RANGE_MID < f_time_ratio <= TAXI_RANGE_HI:
            broadcastRange = 'GLOBAL'
            if VERBOSE: __printFareDetails(TAXI_RANGE_HI)
            # NB: Taxi names are not available inside this function
            print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
            tmp.append((fare, score))

        # Has the Fare been in the queue long enough to be a Regional?
        elif TAXI_RANGE_LOW < f_time_ratio <= TAXI_RANGE_MID:
            broadcastRange = 'REGIONAL'
            if VERBOSE: __printFareDetails(TAXI_RANGE_MID)

            # Is Fare close enough for Taxi to pickup?
            #
            # If distance from Taxi to Fare is less than or equal to
            # (TAXI_RANGE_MID * GRID_MAX), then broadcast is received by Taxi,
            # and Fare gets added to the queue.
            if d <= (TAXI_RANGE_MID * GRID_MAX):
                # NB: Taxi names are not available inside this function
                print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
                tmp.append((fare, score))
            else:
                # Fare's been around long enough for it's broadcast to be
                # Regional, but this Taxi is not in range.  Break out of the
                # loop, and evaluate the next Fare.
                if DEBUG:
                    print('  %s: regional broadcast, but Fare is out of range:' % fare.name),
                    print("(distance) %.1f > (range) %.1f" % (d, TAXI_RANGE_MID * GRID_MAX))
                if (d < (TAXI_RANGE_LOW * GRID_MAX)):
                    print('Regional broadcast is broken!')
                continue

        # It's a local broadcast
        else:
            broadcastRange = 'LOCAL'
            if VERBOSE: __printFareDetails(TAXI_RANGE_LOW)
            # The Fare has only been in the queue long enough to be a Local
            if d <= (TAXI_RANGE_LOW  * GRID_MAX):
                # NB: Taxi names are not available inside this function
                print("%.2f pushing (%s, score %.2f) onto list" % (now(), fare.name, score))
                tmp.append((fare, score))
            else:
                # Local broadcast, but this Taxi is not in range.  Break out
                # of the loop, and evaluate the next Fare.
                if DEBUG:
                    print('  %s: local broadcast, but Fare is out of range:' % fare.name),
                    print("(distance) %.1f > (range) %.1f" % (d, TAXI_RANGE_LOW * GRID_MAX))
                if (d < TAXI_RANGE_LOW * GRID_MAX):
                    print('Local broadcast is broken!')
                continue

    # If I hit the continue every time, it's easy to get here and have nothing
    # in tmp2.  I'm not sure this is right, but it seems to me that if there's
    # nothing here, the only thing left to do is return.
    if len(tmp) == 0:
        if DEBUG:
            print("%.2f\tINFO:" % now()),
            print("There are no eligible Fares for this Taxi.  Entering getQ...")
        return
    tmp2 = sorted(tmp, key=itemgetter(1))
    result = map(itemgetter(0), tmp2)[0]
    return [result]


def fare_is_here(buffer):
    '''
    Filter: if there is a Fare at this location, return it, else
    None.
    '''
    tmp=[]
    for fare in buffer:
        # return first Fare at taxi_loc or None
        if fare.loc['curr']==taxi_loc:
            tmp.append(fare)
            break
    return tmp


if __name__ == '__main__':
    t = Taxi('Terence', 'FIFO')
    #t.cooperate()
    t.compete()
    print("updating negotiation protocol to 'closestfare' and running again")
    t.np = 'closestfare'
    #t.cooperate()
    t.compete()
    # TODO [eventually] add in the rest of the simulation runs

