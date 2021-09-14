import time, traceback
from threading import Thread
from queue import Queue
import pandas as pd
import sys, os
'''
    The functions below are used for data aggregation
'''
# Checking the residual data valid or not
def checkLeftData(msg, leftDFList):
    buf = msg.value
    ID = EventData.EventData.GetRootAsEventData(buf,0).PulseId()
    for i in range(len(leftDFList)):
        for j in range( leftDFList[i].shape[0] ):
            tempID = int(leftDFList[i].iloc[-1])
            if abs(ID-tempID)>G_DISTDROP:
                leftDFList[i].drop(leftDFList[i].index[-1],inplace=True)


def msgRecvThread( inPipeList, dataQueueDict, runningCtrlQueue, globalQueue ):
    ctrlCNT = 0
    while ctrlCNT<len(inPipeList):
        time.sleep(0.001)
        for i in range(len(inPipeList)):
            if inPipeList[i].poll(0.001):
                recvMsg = inPipeList[i].recv()
                if type(recvMsg) is str:
                    runningCtrlQueue.put("Stop")
                    ctrlCNT += 1
                elif recvMsg is not None:
                    dataQueueDict[i].put( recvMsg )
                    recvMsg = None
                    break
        if not globalQueue.empty():
            break
    time.sleep(1)
    #print( " ============================ Stopping the recv thread =================== " )

def msgAggreThread( outPipe, dataQueueDict, runningCtrlQueue, globalQueue ):
    #start = time.process_time()
    dataframeList= []
    leftDFDict = {}
    eventCNT = 0
    mergedDF = None
    signalDF = None
    leftDF   = None
    quitCNT = 0
    for index in dataQueueDict.keys():
        leftDFDict[index]   = None

    while quitCNT < len(dataQueueDict):
        time.sleep(0.001)
        keepFlag = True
        for dataDF in dataQueueDict.values():
            keepFlag = keepFlag*( not dataDF.empty() )

        # Get data from queue
        if keepFlag:
            for index, dataDF in dataQueueDict.items():
                currentDF = dataDF.get()
                if len(leftDFDict)>0:
                    currentDF = pd.concat( [currentDF, leftDFDict[index]] )
                dataframeList.append(currentDF)

            # Adding the last data which have none values
            if len(dataframeList)>1:
                mergedDF = dataframeList[0].join( dataframeList[1:], how='outer' )
            else:
                mergedDF = dataframeList[0]

            # Splitting the non-none and none values in merged dataframe
            if mergedDF is not None:
                signalDF = mergedDF.dropna( axis=0, how='any' )
                leftDF   = mergedDF[ mergedDF.isnull().T.any() ]
                #print( signalDF )
                outPipe.send( signalDF )
                #print( leftDF )

                # Get the data with none value in this round
                for index in leftDFDict.keys():
                    leftDFDict[index] = (leftDF[leftDF.columns[index]].dropna(axis=0, how='any').to_frame())

                dataframeList.clear()

        # Checking the residual data valid or not
        if not runningCtrlQueue.empty():
            runningCtrlQueue.get()
            for dataDF in dataQueueDict.values():
                if dataDF.empty():
                    quitCNT += 1
        if not globalQueue.empty():
            quitCNT += 1
    outPipe.send( "Stopping" )
    time.sleep(1)
    outPipe.close()
    print( "\033[42mINFO: exiting the aggregation thread \033[0m" )


def procAggregation( inPipeList, outPipe, globalQueue ):
    #start = time.process_time()
    #tracemalloc.start(25)
    dataQueueDict = {}
    runningCtrlQueue = Queue()
    for i in range(len(inPipeList)):
        dataQueueDict[i] = Queue()
    recvThread = Thread( target=msgRecvThread, args=( inPipeList, dataQueueDict, runningCtrlQueue, globalQueue ) )
    aggreThread= Thread( target=msgAggreThread , args=( outPipe, dataQueueDict, runningCtrlQueue, globalQueue ) )

    recvThread.start()
    aggreThread.start()
    recvThread.join()
    aggreThread.join()

    #end=time.process_time()
    #current, peak = tracemalloc.get_traced_memory()
    #print( " Aggregation thread time used: %s " % str(end-start) )
    #print(f"Current memory usage {current/1e6}MB; Peak: {peak/1e6}MB")
    #print( " ============================ Stopping the pipe process thread =================== " )
    #print( " Aggregation thread time used: %s " % str(end-start) )
    #print(f"Current memory usage {current/1e6}MB; Peak: {peak/1e6}MB")
    print( "\033[42mINFO: exiting the aggregation process \033[0m" )

def dfRecvThread( inPipe, dfQueueDict, runningCtrlQueue, globalQueue ):
    ctrlCNT = 0
    recvDF = None
    while ctrlCNT<1:
        time.sleep(0.001)
        try:
            if inPipe.poll(0.01):
                recvDF = inPipe.recv()
        except:
            traceback.print_exc()
        if type(recvDF) is str:
            runningCtrlQueue.put("Stop")
            ctrlCNT += 1
        elif recvDF is not None:
            for i in range(len(dfQueueDict)):
                dfQueueDict[i].put(recvDF)
                recvDF = None

        if not globalQueue.empty():
            ctrlCNT += 1
    time.sleep(2)
    #print( " ============================ Stopping the DataFrame recv thread =================== ", recvDF )

def dfDealThread( dfQueue, aggreAppParasDict, runningCtrlQueue, globalQueue ):
    quitCNT = 0

    # Import user's dataframe processing functions
    #aggreFuncImport( aggreAppParasDict )
    userDFProcessClassList = getDFProcessClass( aggreAppParasDict )
    _ = [ item.initialize() for item in userDFProcessClassList ]

    while quitCNT == 0:
        time.sleep(0.001)
        try:
            if not dfQueue.empty():
                df = dfQueue.get()
                #TODO
                # Using each user dataframe process method to deal with the received dataframe
                _ = [ item.processDF(df) for item in userDFProcessClassList ]
                #for eachFunc in aggreAppParasDict["DFDealFunc"]:
                #    funcPath = list(eachFunc.values())[0]
                #    funcName = list(eachFunc.keys())[0]
                #    sys.modules[funcPath].__dict__[funcName]( df )
                #TODO
        except:
            traceback.print_exc()
        # Checking the residual data valid or not
        if not runningCtrlQueue.empty():
            quitCNT += 1
        if (not globalQueue.empty()):
            quitCNT += 1

    _ = [ item.finalize() for item in userDFProcessClassList ]
    time.sleep(2)
    #print( " ============================ Stopping the DataFrame dealing thread =================== " )

def getDFProcessClass( aggreAppParasDict ):
    temptClassList = []
    sys.path.append( os.getcwd() )
    for item in aggreAppParasDict["DFDealFunc"]:
        classDir = list(item.values())[0]
        className= list(item.keys())[0]
        strImport = "from " + classDir + " import " + className
        try:
            exec( strImport )
            temptClassList.append( eval(className)(className) )
        except:
            print( "\033[41mERROR: Facing import error of app: %s with user's dataframe process method: %s\033[0m" % (aggreAppParasDict["ClassName"], className) )
            print( "\033[41mERROR: Facing import error of app: %s with user's dataframe process method: %s\033[0m" % (aggreAppParasDict["ClassName"], className) )
            print( "\033[41mERROR: Facing import error of app: %s with user's dataframe process method: %s\033[0m" % (aggreAppParasDict["ClassName"], className) )
            traceback.print_exc()
            sys.exit(1)
    return temptClassList

def aggreFuncImport( aggreAppParasDict ):
    sys.path.append( os.getcwd() )
    #for funcName in aggreAppParasDict["DFDealFunc"]["ClassName"]:
    #    strImport = "from " + aggreAppParasDict["DFDealFunc"]["ModuleName"] + " import " + funcName
    for item in aggreAppParasDict["DFDealFunc"]:
        strImport = "from " + list(item.values())[0] + " import " + list(item.keys())[0]
        try:
            exec( strImport )
        except:
            print( "================= Import User dataframe process function error, programe will be killed !" )
            sys.exit(1)

#def procAggredDataProcess( inPipe, dealFuncsList, globalQueue ):
def procAggredDataProcess( inPipe, aggreAppParasDict, globalQueue ):
    dfQueueDict = {}
    runningCtrlQueue = Queue(1)

    # Multiple df processing function are performed in only one thread!!
    # TODO
    #for i in range(len(aggreAppParasDict["DFDealFunc"]["ClassName"])):
    #    dfQueueDict[i] = Queue()
    #    print(i)
    dfQueueDict[0] = Queue()
    # TODO

    threadList = []
    threadList.append( Thread(target=dfRecvThread, args=(inPipe, dfQueueDict, runningCtrlQueue, globalQueue)) )
    threadList.append( Thread(target=dfDealThread, args=(dfQueueDict[0], aggreAppParasDict, runningCtrlQueue, globalQueue)) )

    for eachThread in threadList:
        eachThread.start()
    for eachThread in threadList:
        eachThread.join()

    #print( " ============================ Stopping the dfDeal Process =================== " )
