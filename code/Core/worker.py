#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import sys, time, os
import traceback
import setproctitle
import asyncio
#from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from multiprocessing import Process
from Core.consumerFuncs import getID
from Core.consumerFuncs import msgRun
from Core.consumerFuncs import timeToID
from Core.consumerFuncs import fillPools
from Core.consumerFuncs import freeWater
from Core.consumerFuncs import filterWater
from Core.consumerFuncs import checkCutoff
from Core.consumerFuncs import releasePool
from Core.consumerFuncs import createConsumers
from Core.consumerFuncs import getNumOfPartitions


def dataConsuming( eventLoop, executor, eventCounter, topicParasDict, consumerParasDict, userObjectList, glbCtrlDict, dataPipeDict ):
		   #batchModeFlag, event, lock, runStep, progressCounter, eventCounter, asynCounter, signalQueue, dataPipeDict ):
    detectorTypeCode    = topicParasDict["DetectorCode"]
    brokerIP            = topicParasDict["BrokerIP"]
    nameTopic           = topicParasDict["TopicName"]
    group_ID            = topicParasDict["Group_ID"]
    dataType            = topicParasDict["DataType"]
    numParts            = topicParasDict["numParts"]

    Consumers   = []
    Pool_msg    = []
    Pool_ID     = []
    Last_msg    = []
    Last_ID     = []
    waterList   = []
    waterIDList = []

    # ============================ Start to create consumers and receive messages ===============================
    # create consumers according to the number of partitions, and use the list 'Consumers' to hold them
    createConsumers( brokerIP, nameTopic, group_ID, numParts, Consumers, consumerParasDict )
    ConsZip = zip_longest( *Consumers )
    time.sleep(1)

    # ============== Main loop procedure to consumer messages and sort them for users ====================
    for msgList in ConsZip:
        for msg in msgList:
            # ============================== Not filting the messages  =====================================
            if not consumerParasDict['filterGate']:
                # ========================== User message processing   =====================================
                eventCounter = msgRun( consumerParasDict['corotineFlag'], eventLoop, executor, detectorTypeCode, dataType, msg, consumerParasDict['batchModeFlag'], consumerParasDict['runStep'], \
                                      glbCtrlDict, eventCounter, dataPipeDict, userObjectList, )
                                      #glbCtrlDict, eventCounter, dataPipeDict, userModuleList, userFuncList, )
                if  consumerParasDict['cutoffFlag']:
                    currentID = getID(msg, consumerParasDict['Invalid_ID'])
                    if currentID == consumerParasDict['endPulseID']:
                        break
            # ============================== Filting the messages      =====================================
            else:
                # ========== Step 1:  collect data, save messages and ID to pools =======================================
                fillPools( Pool_msg, Pool_ID, msg, consumerParasDict['Invalid_ID'] )

                # ========== Step 2:  when the pools are full, sort all messages and release the fix number of messages ==
                if( len(Pool_ID) == consumerParasDict['poolSize'] ):
                    waterList, waterIDList, Pool_msg, Pool_ID, Last_msg, Last_ID = freeWater(
                        Pool_msg, Pool_ID, consumerParasDict['sliceSize'], Last_msg, Last_ID, consumerParasDict['sortFlag'], consumerParasDict['filterGate'] )

                # ========== Step 3:  when the pools are full, sort all messages and release the fix number of messages ==
                    if( consumerParasDict['filterGate'] ):
                        waterList, waterIDList, consumerParasDict['filterGate'] = filterWater( waterList, waterIDList, consumerParasDict )

                # ========== Step 4:  Now the messages are ready for user's data processing  =============================
                    signalMSGList = []
                    signalMSGIDList = []
                    signalMSGList, signalMSGIDList = checkCutoff( waterList, waterIDList, consumerParasDict['cutoffFlag'], consumerParasDict['endPulseID'] )

                    for item in signalMSGList:
                        eventCounter = msgRun( consumerParasDict['corotineFlag'], eventLoop, executor, detectorTypeCode, dataType, msg, consumerParasDict['batchModeFlag'], consumerParasDict['runStep'], \
                                              glbCtrlDict, eventCounter, dataPipeDict, userObjectList )

                # clear the waterList and waterIDList for next time
                del waterList[:]
                del waterIDList[:]

            # Commit the offset for consumer groups
            if consumerParasDict['handCommitFlag']:
                for consumer in Consumers:
                    consumer.commit()

        #  ELSE for the inner loop
        else:
            if glbCtrlDict['queue'].empty():
                continue
            else:
                print( "\033[43WARNING:  Getting the stopping signal, consuming process will be stopped now !\033[0m" )
                for consumer in Consumers:
                    consumer.close()
        break

    # ============================================================================================================
    # For multi partitions running case
    # ============== Final Step: after the last message loop, release the left messages in the pool ==================
    releasePool( eventLoop, executor, detectorTypeCode, dataType, Last_msg, Last_ID, consumerParasDict, glbCtrlDict, eventCounter, dataPipeDict, userObjectList,
                )

    # Accumulating the asynCounter for this process, to finish the asyn process
    glbCtrlDict['lock'].acquire()
    glbCtrlDict['asynCNT'].value += 1
    glbCtrlDict['lock'].release()

    # closing the consumers, sending the finishing message the receive process
    try:
        for consumer in Consumers:
            consumer.close()

        for dataPipe in dataPipeDict.values():
            time.sleep(10)
            dataPipe.send("StopConsuming")
            dataPipe.close()
    except:
        traceback.print_exc()

    print( "\033[45mINFO: %s total consumed message: %s\033[0m" % ( nameTopic, eventCounter ) )


class Run ( Process ):
    def __init__( self, topicParasDict, consumerParasDict, glbCtrlDict, appParasDict, dataPipeDict ):
        super( Run, self ).__init__()
        self.topicParasDict     = topicParasDict
        self.appsList           = sum(list(topicParasDict['Apps'].values()), [])
        self.appParasDict       = appParasDict
        self.moduleName         = appParasDict[sum(list(topicParasDict['Apps'].values()), [])[0]]["ModuleName"]
        self.funcName           = appParasDict[sum(list(topicParasDict['Apps'].values()), [])[0]]["ClassName"]
        self.dataPipeDict       = dataPipeDict
        self.glbCtrlDict        = glbCtrlDict
        self.consumerParasDict  = consumerParasDict
        self.eventCounter       = 0
        self.eventLoop          = None
        self.executor           = None
        self.userObjectList     = []

    def getUserObjects(self):
        sys.path.append( os.getcwd() )
        for appName in self.appsList:
            strImport = "from " + self.appParasDict[appName]["ModuleName"] + " import " + self.appParasDict[appName]["ClassName"]
            try:
                exec( strImport )
                self.userObjectList.append(eval( self.appParasDict[appName]['ClassName'])(appName))
                print( "\033[45mINFO: %50s imported user's application module: %40s: %s\033[0m" %
                      ( self.topicParasDict["TopicName"], self.appParasDict[appName]["ModuleName"],   self.appParasDict[appName]["ClassName"]  ) )
            except:
                print( "\033[41mERROR: failed in import topic: %45s App module: %s \033[0m" % (self.topicParasDict["TopicName"], appName) )
                traceback.print_exc()
                sys.exit(1)

    def checkParas( self ):

        #setproctitle.setproctitle( self.topicParasDict["TopicName"] )
        self.topicParasDict["numParts"] = getNumOfPartitions(self.topicParasDict["BrokerIP"], self.topicParasDict["TopicName"])

        if self.topicParasDict["numParts"] == 1:
            print("\033[45mINFO: %50s parition is 1, the sortFlag, poolSize, sliceSize, protLength are set to False and 1\033[0m" % self.topicParasDict["TopicName"])
            self.consumerParasDict['sortFlag']  = False
            self.consumerParasDict['poolSize']  = 1
            self.consumerParasDict['sliceSize'] = 1

        if self.consumerParasDict['TimeToIDFlag']:
            self.consumerParasDict['jumpPulseID'] = timeToID( self.consumerParasDict['startTime'], self.consumerParasDict['absTimeStamp'], self.consumerParasDict['absPulseID'] )
            self.consumerParasDict['endPulseID']  = timeToID( self.consumerParasDict['endTime'],   self.consumerParasDict['absTimeStamp'], self.consumerParasDict['absPulseID'] )
            print( "\033[42mINFO: %s start consuming time: %s, ID: %d" % ( self.topicParasDict['TopicName'], self.consumerParasDict['startTime'], self.consumerParasDict['jumpPulseID'] ) )
            print( "\033[42mINFO: %s end   consuming time: %s, ID: %d" % ( self.topicParasDict['TopicName'], self.consumerParasDict['endTime'],   self.consumerParasDict['endPulseID']  ) )

    def run(self):
        self.eventLoop = asyncio.get_event_loop()
        self.checkParas()
        self.getUserObjects()

        for userObject in self.userObjectList:
            userObject.initialize( self.topicParasDict )

        dataConsuming( self.eventLoop, self.executor, self.eventCounter, self.topicParasDict, self.consumerParasDict, self.userObjectList, self.glbCtrlDict, self.dataPipeDict )

        for userObject in self.userObjectList:
            userObject.finalize( self.topicParasDict )


