#!/usr/bin/python

import json
import logging
import requests

class MsgProcess(object):
    def __init__(self, appName):
        self.appName = appName

    def initialize(self, topicParasDict ):
        pass

    def finalize(self, topicParasDict ):
        pass

    def requestPV( self, result ):
        roll = requests.post(self.pushAddress, data=json.dumps(result))
        return roll

    def collecteData( self, resultList, endPoint, Metric, value, time_st ):
        record = {}
        record['endPoint']  = endPoint
        record['step'] = 30
        record['counterType'] = 'GAUGE'
        record['metric'] = Metric
        record['value']  = value
        record['timestamp'] = time_st
        resultList.append( record )

    def setupUserLogger( self, nameTopic, outputFile ):
        level = logging.INFO
        formatter = logging.Formatter( '%(asctime)s:    %(message)s' )
        handler   = logging.FileHandler( outputFile )
        handler.setFormatter( formatter )
        logger = logging.getLogger( nameTopic )
        logger.setLevel( level )
        logger.addHandler( handler )
        self.logger = logger
        self.fileHandler = handler

    def closeLogger(self):
        self.logger.removeHandler( self.fileHandler )
        self.logger = None
        self.fileHandler = None

    def run(self, msg, eventCounter, detectorTypeCode, dataType, dataPipeDict):
        pass
