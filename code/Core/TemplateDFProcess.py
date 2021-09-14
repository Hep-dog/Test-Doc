import requests, json, time

class TemplateDFProcess():
    def __init__(self, name):
        self.name = name
        self.pulseFre   = 25
        self.secFactor  = 30
        self.dataDict   = {"dataList":[], "leftData":[], "idList":[], "leftIDList":[]}
        self.endPoint   = "Jiyizi-test"
        self.metric     = "xxxxx"
        self.pushAddress= 'http://10.1.26.63:1988/v1/push'

    def initialize(self):
        pass

    def finalize(self):
        pass

    def collectData( self, resultList, endPoint, Metric, value, time_st ):
        record = {}
        record['endPoint']      = endPoint
        record['step']          = 30
        record['counterType']   = 'GAUGE'
        record['metric']        = Metric
        record['value']         = value
        record['timestamp']     = time_st
        resultList.append( record )

    def requestPV( self, result ):
        roll = requests.post( self.pushAddress, data=json.dumps(result) )
        return roll

    def onlineDisplay( self, resultList ):
        targetList = []
        time_st = int(time.time())
        for item in resultList:
            self.collectData( targetList, self.endPoint, self.metric, item, time_st )

        roll = self.requestPV(targetList)
        print( " ++++++++++++++++++++++++++++ requests sending status: ", roll.text, " ++++++++++++++++++++++++ "  )

    def processDF(self, df):
        pass
