import json, time
import traceback, sys, os
import setproctitle
import signal
from functools import partial
from multiprocessing import Pipe

def parseRunParas( jsonFile ):
    try:
        with open( jsonFile, "r", encoding='utf-8' ) as f:
            runParas = json.loads(f.read())
            return runParas
    except:
        traceback.print_exc()
        sys.exit(1)

def initDataBusDict( topicsParseList, appParseList, consuDict, aggreDict, analyDict ):
    for appName in appParseList.keys():
        if appParseList[appName]['AppType'] =='Aggre':
            secondDataPipe = Pipe()
            aggreDict['inDataPipeDict'][appName]  = []
            aggreDict['outDataPipeDict'][appName] = secondDataPipe[1]
            analyDict['inDataPipeDict'][appName]  = secondDataPipe[0]
            analyDict['dfDealFuncDict'][appName]  = appParseList[appName]['DFDealFunc']

    for topicParas in topicsParseList:
        consuDict['outDataPipeDict'][topicParas['TopicName']] = {}
        for aggreName in topicParas['Apps']['Aggre']:
            firstDataPipe = Pipe()
            consuDict['outDataPipeDict'][topicParas['TopicName']][aggreName] = firstDataPipe[1]
            aggreDict['inDataPipeDict'][aggreName].append( firstDataPipe[0] )

    return consuDict, aggreDict, analyDict

def checkModulesImport( topicsParseList ):
    pass

def sigint_handle( stopQueue, signum, frame ):
    if signum == 3:
        stopQueue.put("Stopping")
        print("\033[42mWARNING: Receive the stop signal, the program will be stopped now!\033[0m")
    os.system( "kill -9 %d" % os.getpid() )

#def processAsyner( event, numbOfTopics, progressCounter, asynCounter, signalQueue ):
def processAsyner( numbOfTopics, glbCtrlDict, topicConfName, consumerConfName ):
    setproctitle.setproctitle( "KDP-Control-Process-"+topicConfName.split('.')[0]+"-"+consumerConfName.split('.')[0] )
    signal.signal( signal.SIGQUIT, partial( sigint_handle, glbCtrlDict['queue'] ) )
    print("\033[44mINFO: The program can be killed by start new terminal and enter 'kill -3 %d'\033[0m" % os.getpid())
    print("\033[44mINFO: The program can be killed by start new terminal and enter 'kill -3 %d'\033[0m" % os.getpid())
    print("\033[44mINFO: The program can be killed by start new terminal and enter 'kill -3 %d'\033[0m" % os.getpid())
    while True:
        time.sleep(1)
        if ( glbCtrlDict['asynCNT'].value < numbOfTopics ):
            if glbCtrlDict['progressCNT'].value == numbOfTopics:
                glbCtrlDict['progressCNT'].value=0
                glbCtrlDict['event'].set()
                print( "++++++++++++++++++++++++++ Release the counter ++++++++++++++++++++++++++" )
        else:
            time.sleep(1)
            break
