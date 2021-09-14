#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys, time
import numpy as np
import traceback
from typing import List
from kafka import KafkaConsumer
from kafka import TopicPartition
from itertools import zip_longest
from fbs.Data.Detector import EventData
import asyncio

# get the number of partitions of topic
def getNumOfPartitions( brokerIP, topicName ) -> int:
    consumer = KafkaConsumer( bootstrap_servers=[brokerIP], )
    try:
        return len(consumer.partitions_for_topic(topicName))
    except:
        print( "\033[41mERROR: failed to get the number of partitions for %50s" % topicName )
        traceback.print_exc()
        sys.exit(1)


# conver the timestamp the pulseID
def timeToID( standardTime, absTimeStamp, absPulseID ) -> int:
    tarray = time.strptime( standardTime, "%Y-%m-%d %H:%M:%S" )
    stamp  = int( time.mktime(tarray) )
    expectedID = (stamp-absTimeStamp)*25 + absPulseID
    return expectedID


def expOffsetFromID( consumer, partion, numb, protLength, jumpPulseID, absTimeStamp, absPulseID ) -> int:
    deltaID   = absPulseID - jumpPulseID + int(protLength*numb)
    expTime = absTimeStamp - deltaID/25.
    dictStamp = { partion:expTime*1000 }
    T2Offset  = consumer.offsets_for_times( dictStamp )[partion]
    #print( deltaID, expTime, absTimeStamp, dictStamp, T2Offset )
    #print( " ============== The expected offset from ID is: %s ============ " % T2Offset.offset )
    return T2Offset.offset


def createConsumers( IP, nameTopic, Group_ID, numb, Consumers, consumerParasDict ) -> None:
    '''
        This function is used to create multi-consumers and return the consumers list, each one for one partition of a specified topic.

        IP: kafka broker address and port
        nameTopic: the Kafka topic name
        Group_ID : the name of consumer group
        timeout_ms: waiting time for each kafka consumer
        numb: the number of partitions of the topic
        Consumers: the list use to hold all consumers
        protLength: the protect length for message jumping
        jumpPulseID: is the targe position user wanting to jump for each partitions. It will consuming:

        define the expected jump offset:
        1) from the latest msg if jumpPulseID is '-1'
        2) from the beginning for '0' if jumpPulseID is 0
        3) from a specific position if expOffset is an integer larger than 0.
    '''
    TPs = [] # list of topicpartitions
    expOffsets  = [] # list of expected offset for each partition
    timeout_ms  = consumerParasDict['timeout_ms']
    protLength  = consumerParasDict['protLength']
    jumpPulseID = consumerParasDict['jumpPulseID']
    absPulseID  = consumerParasDict['absPulseID']
    absTimeStamp= consumerParasDict['absTimeStamp']

    for i in range(numb):
        consumer = KafkaConsumer(
            bootstrap_servers = [IP],
            group_id = Group_ID,
            consumer_timeout_ms = timeout_ms,
        )
        tp = TopicPartition( nameTopic, i )
        consumer.assign( [tp] )
        TPs.append( tp )
        Consumers.append( consumer )

        if consumerParasDict['filterGate']:
            if jumpPulseID == -2:
                try:
                    realTimeOffset =  consumer.end_offsets([tp])[tp]
                    consumer.seek( tp, realTimeOffset )
                    print("\033[44mINFO: %50s's partition: %d consumes the real-time message from offset: %d" % (nameTopic, i, realTimeOffset), "\033[0m" )
                except:
                    print("\033[41mERROR: Topic: %50s seeks to the real-time message error!\033[0m" % nameTopic)
                    traceback.print_exc()
                    sys.exit(1)

            elif jumpPulseID == -1:
                print("\033[44mINFO: %50s's partition: %d consumes from the latest offset committed position " % (nameTopic, i), "\033[0m" )
                pass

            elif jumpPulseID == 0:
                #Consumers[i].seek( TPs[i], 0 )
                Consumers[i].seek_to_beginning( TPs[i] )
                print("\033[44mINFO: %50s's partition: %d consumes from beginning " % (nameTopic, i), "\033[0m" )

            else:
                temptOffset = expOffsetFromID( consumer, tp, numb, protLength, jumpPulseID, absTimeStamp, absPulseID )
                expOffsets.append( temptOffset )
                if expOffsets[i]>0:
                    try:
                        consumer.seek( tp, (expOffsets[i]-1) )
                        print("\033[44mINFO: %50s's partition: %d consumes from offset: %d " % (nameTopic, i, expOffsets[i]), "\033[0m" )

                    except:
                        traceback.print_exc()
                        exit(1)
                else:
                    try:
                        consumer.seek( tp, 0 )
                    except:
                        traceback.print_exc()
                        exit(1)


def getID( msg, Invalid_ID ) -> int:
    '''
        This function is used to get the pulse ID of a message.
        The decoding method is automatically generated by flatbuffers serialization.

        Note: since we read messages from all partions, there will be a case that some partitions have messages and others are "None".
        For this case, we set the invalid_ID for the pulse ID for the "None" messages. So the "None" messages will be in the end
        of the messages pool by sorting with the pulse ID, we just left the "None" messages in the pool and don't use them
    '''
    if msg:
        buf  = msg.value
        data = EventData.EventData.GetRootAsEventData( buf, 0 )
        ID   = data.PulseId()
        return ID
    else:
        return ( Invalid_ID )


def zipConsumers( consumerList ):
    '''
        This function is used to zip the consumers list. So that user don't need to
        specify the number of messages and consumers in the data reading procedure now!
    '''
    return zip_longest( *consumerList )

def fillPools( Pool_msg, Pool_ID, msg, Invalid_ID ) -> None:
    '''
         Note: the messges are sorted by its key, whose value is same as the Pulse ID.
         So, the sorting procedure is independent on the flatbuffers encoding/decoding method.

         Pool_msg  :   global messages pool
         Pool_ID   :    global Pulse ID pool
         msg       :   zipped messages
         Invalid_ID: invalid pulse ID for the 'None' messages
    '''
    Pool_msg.append( msg )

    if msg:
        #ID = (struct.unpack('<2L', msg.key))[0]
        ID = getID( msg, Invalid_ID )
        Pool_ID.append( ID )
    else:
        Pool_ID.append( Invalid_ID )

def freeWater( Pool_msg, Pool_ID, sliceSize, Last_msg, Last_ID, sortFlag, filterGate) -> List[List[int]]:
    '''
        Ths function is used to release messages and IDs from the pools when their are full.
        Pool_msg: the fulled messages pool
        Pool_ID : the filled IDs pool
        waterList: the target sorted messages list, which will be used in further by users
        waterIDList: the pulse ID of target sorted messages list, which will be used in further by users
        sliceSize: the length of front messages in the filled messages pool
        Last_msg: the left messages in the pool after the releasing of water from pool
        Last_ID : the left IDs in the pool after the releasing of water from pool
        sortFlag: the flag for message sorting or not
        filterGate: the gate for message filtering or not

    '''
    leftMSG = []
    leftID  = []
    waterList = []
    waterIDList = []
    #print("TempIDlist length is: ", len(Pool_ID), type(Pool_ID) )

    # If sortflag is True, we sort messages firstly and pull the top sliceSize ones to waterList
    if sortFlag:
        # fill the water list
        tempIDlist = list( np.argsort(Pool_ID) )
        for item in tempIDlist[ 0 : sliceSize ]:
            waterList.append( Pool_msg[item] )
            waterIDList.append( Pool_ID[item] )

        # get the left messages and IDs
        for item in tempIDlist[ sliceSize : ]:
            leftMSG.append( Pool_msg[item] )
            leftID .append( Pool_ID[item] )

    # If we don't need to sort the messages, just release all messages to waterList
    else:
        waterList = Pool_msg
        waterIDList = Pool_ID

    Pool_msg = leftMSG
    Pool_ID  = leftID

    Last_msg = leftMSG
    Last_ID  = leftID

    return waterList, waterIDList, Pool_msg, Pool_ID, Last_msg, Last_ID


def filterWater( waterList, waterIDList, consumerParasDict ) -> List[List[int]]:
    '''
        This function is used to filter the messages from user specified Pulse ID. Normally,
        the first message ID will be not the target jumping pulse ID, so we need to use this function
        to filter our wanted messages.

        waterList: the target sorted messages list, which will be used in further by user.
        waterIDList: the IDs list of waterList, which is used for the messages filtering
        jumpPulseID: user specified jumping pulse ID
        sortFlag   : gate for sorting messages or not
        filterGate : 'True' or 'False', if the jumpPulseID larger than 0, this parameter should be 'True'
        poolSize   : the size of messages pool
        Invalid_ID : user specified key for the invalid messages, it must not be overlapped with physical message key
    '''
    sortFlag = consumerParasDict['sortFlag']
    poolSize = consumerParasDict['poolSize']
    filterGate = consumerParasDict['filterGate']
    Invalid_ID = consumerParasDict['Invalid_ID']
    jumpPulseID = consumerParasDict['jumpPulseID']
    tempWaterList = []
    tempIDList = []

    if len(waterList) != len(waterIDList):
        print("\033[41mERROR: the length of water list and waterID list are not equal during the filtering!\033[0m")
        sys.exit(1)

    if sortFlag:
        for msg, ID in zip( waterList, waterIDList ):
            if ID >= jumpPulseID and ID < Invalid_ID:
                tempWaterList.append( msg )
                tempIDList.append( ID )
                filterGate = False
    else:
        for msg, ID in zip( waterList, waterIDList ):
            if ID >= ( jumpPulseID ) and ID < Invalid_ID:
                tempWaterList.append( msg )
                tempIDList.append( ID )
            if ID >= ( jumpPulseID + poolSize ):
                filterGate = False


    waterList   = tempWaterList
    waterIDList = tempIDList

    #print( "Two length in filterWater function : ", len(waterList), len(waterIDList) )
    return waterList, waterIDList, filterGate


def checkCutoff( waterList, waterIDList, cutoffFlag, endPulseID ) -> List[List[int]]:
    '''
        This function is used to cut the messages to user specified pulse ID, if cutoffFlag is true
        waterList: the input signal messages list, which has be sorted in most cases.
        waterIDList: the input message IDs list, its length should be same as waterList.
        cutoffFlag : the control flag used to decide cut messages or not.
        endPulseID : user specified end of messages.
    '''
    if not cutoffFlag:
        return waterList, waterIDList
    else:
        if endPulseID <= 0:
            print("\033[41mERROR: the given endPulseID is invalid, please check it!\033[0m")
            exit(1)
        else:
            if len(waterList) != len(waterIDList):
                #print( "Two length: ", len(waterList), len(waterIDList) )
                print("\033[41mERROR: the length of water list and waterID list are not equal after the message filtering!\033[0m")
                sys.exit(1)
            else:
                MSGList = []
                IDList  = []
                for msg, ID in zip( waterList, waterIDList ):
                    if ID <= endPulseID:
                        MSGList.append( msg )
                        IDList .append( ID  )
                    else:
                        exit(0)
                return MSGList, IDList


def releasePool( eventLoop, executor, detectorTypeCode, dataType, Last_msg, Last_ID, consumerParasDict, glbCtrlDict, eventCounter, dataPipeDict, userObjectList ) -> None:
    '''
        This function is used to release the message pool after the final loop.
        Last_msg: list of the message after the final loop
        Last_ID : list of the message ID after the final loop, its size should be equal with the Last_msg
        filterGate : 'True' or 'False', if the jumpPulseID larger than 0, this parameter should be 'True'
        jumpPulseID: the pulse ID used to jump messages. The user's data processing will starting from this number
        cutoffFlag: the flag to control whether stop consuming messages tile endPulseID or not, 'True' or 'Flase'
        endPulseID: the user specified message consuimg end pulse ID

        Note: after the last message loop, the message pool will be not full, which means the size of Last_msg and Last_ID will smaller than the poolSize.
        And there are must be some "None" messages in the Pool_msg and invalid_ID in the Pool_ID, because the number of messages of each partition are not same.
        For this case, we use the addtional "None" messages to full the Pool_msg and Pool_ID, sort the messages and pull the valid ones.

        leftSize : size of left messages and ID in the pools after the final loop.
        blankSize: size of the vacancies of the pools, which is poolSize - leftSize
        mudSize  : size of the "None" messages in the Last_msg, and the size of invalid_ID in the Last_ID
        dataSize : size of target messages in the Last_msg pool

    '''
    if len(Last_msg) != len(Last_ID):
        print( "\033[41mERROR: The number of the left msg %d and ID %d are not same!" % ( len(Last_msg), len(Last_ID) ), "\033[0m" )
        sys.exit(1)

    leftSize = len(Last_ID)
    blankSize= consumerParasDict['poolSize'] - leftSize
    mudSize  = Last_ID.count( consumerParasDict['Invalid_ID'] )
    dataSize = leftSize - mudSize

    for i in range( blankSize ):
        Last_msg.append( None )
        Last_ID .append( consumerParasDict['Invalid_ID'] )

    tempIDlist = list( np.argsort(Last_ID) )

    for item in tempIDlist[ 0 : dataSize ]:
        '''
            User should overload this function or re-write it!!!!!
        '''
        #ID = (struct.unpack('<2L', (Last_msg[item]).key))[0]
        ID = getID( Last_msg[item], consumerParasDict['Invalid_ID'] )

        # For message jumping and cutting off flags
        if consumerParasDict['filterGate'] and (ID < consumerParasDict['jumpPulseID']):
            continue
        elif consumerParasDict['cutoffFlag'] and (ID > consumerParasDict['endPulseID']):
            continue
        else:
            msgRun( consumerParasDict['coroutineFlag'], eventLoop, executor, detectorTypeCode, dataType, Last_msg[item], consumerParasDict['batchModeFlag'], consumerParasDict['runStep'],\
                   glbCtrlDict, eventCounter, dataPipeDict, userObjectList, )

async def asynDataProcess( eventLoop, executor, msg, eventCounter, detectorTypeCode, dataType, dataPipeDict, userObject ):
    await eventLoop.run_in_executor(  executor, userObject.run, msg, eventCounter, detectorTypeCode, dataType, dataPipeDict )
    return 0

#def msgRun( loop, executor, detectorTypeCode, dataType, msg, batchModeFlag, runStep, glbCtrlDict, eventCounter, dataPipeDict, moduleName, funcName ):
def msgRun( coroutineFlag, eventLoop, executor, detectorTypeCode, dataType, msg, batchModeFlag, runStep, glbCtrlDict, eventCounter, dataPipeDict, userObjectList ):
    if msg:
        if not batchModeFlag:
            eventCounter += 1
            ## TODO
            taskList = []
            if coroutineFlag:
                for i in range(len(userObjectList)):
                    taskList.append( asynDataProcess( eventLoop, executor, msg, eventCounter, detectorTypeCode, dataType, dataPipeDict, userObjectList[i] ) )
                eventLoop.run_until_complete( asyncio.gather(*taskList) )
            else:
                for i in range(len(userObjectList)):
                    userObjectList[i].run( msg, eventCounter, detectorTypeCode, dataType, dataPipeDict  )
        else:
            if not glbCtrlDict['event'].is_set():
                eventCounter += 1
                ## TODO
                taskList = []
                if coroutineFlag:
                    for i in range(len(userObjectList)):
                        taskList.append( asynDataProcess( eventLoop, executor, msg, eventCounter, detectorTypeCode, dataType, dataPipeDict, userObjectList[i] ) )
                    eventLoop.run_until_complete( asyncio.gather(*taskList) )
                else:
                    for i in range(len(userObjectList)):
                        userObjectList[i].run( msg, eventCounter, detectorTypeCode, dataType, dataPipeDict  )
                if( eventCounter.value % runStep == 0 ):
                    print("\033[46mINFO: Step msgRun running ! \033[0m", (eventCounter.value , glbCtrlDict['progressCNT'].value) )
                    glbCtrlDict['lock'].acquire()
                    glbCtrlDict['progressCNT'].value += 1
                    glbCtrlDict['lock'].release()
                    glbCtrlDict['event'].wait()
            else:
                eventCounter += 1
                if( eventCounter.value % runStep == 0 ):
                    print("\033[46mINFO: Step msgRun running ! \033[0m", (eventCounter.value , glbCtrlDict['progressCNT'].value) )
                    glbCtrlDict['lock'].acquire()
                    glbCtrlDict['progressCNT'].value += 1
                    glbCtrlDict['event'].clear()
                    glbCtrlDict['lock'].release()
                    glbCtrlDict['event'].wait()
    else:
        print("\033[42mWARNING: facing the 'None' message!\033[0m")

    return eventCounter

