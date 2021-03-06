import os
import unittest
import ticdat.utils as utils
from ticdat.ticdatfactory import TicDatFactory
from ticdat.testing.ticdattestutils import dietData, dietSchema, netflowData, netflowSchema, firesException
from ticdat.testing.ticdattestutils import sillyMeData, sillyMeSchema, makeCleanDir, failToDebugger, runSuite
import shutil

#uncomment decorator to drop into debugger for assertTrue, assertFalse failures
#@failToDebugger
class TestXls(unittest.TestCase):
    def firesException(self, f):
        e = firesException(f)
        if e :
            self.assertTrue("TicDatError" in e.__class__.__name__)
            return e.message
    def testDiet(self):
        tdf = TicDatFactory(**dietSchema())
        ticDat = tdf.freeze_me(tdf.TicDat(**{t:getattr(dietData(),t) for t in tdf.primary_key_fields}))
        filePath = os.path.join(_scratchDir, "diet.xls")
        tdf.xls.write_file(ticDat, filePath)
        xlsTicDat = tdf.xls.create_tic_dat(filePath)
        self.assertTrue(tdf._same_data(ticDat, xlsTicDat))
        xlsTicDat.categories["calories"]["minNutrition"]=12
        self.assertFalse(tdf._same_data(ticDat, xlsTicDat))

        self.assertFalse(tdf.xls.get_duplicates(filePath))

        ex = self.firesException(lambda :
                                 tdf.xls.create_tic_dat(filePath, row_offsets={t:1 for t in tdf.all_tables}))
        self.assertTrue("field names could not be found" in ex)
        xlsTicDat = tdf.xls.create_tic_dat(filePath, row_offsets={t:1 for t in tdf.all_tables}, headers_present=False)
        self.assertTrue(tdf._same_data(xlsTicDat, ticDat))
        xlsTicDat = tdf.xls.create_tic_dat(filePath, row_offsets={t:2 for t in tdf.all_tables}, headers_present=False)
        self.assertFalse(tdf._same_data(xlsTicDat, ticDat))
        self.assertTrue(all(len(getattr(ticDat, t))-1 == len(getattr(xlsTicDat, t)) for t in tdf.all_tables))

    def testNetflow(self):
        tdf = TicDatFactory(**netflowSchema())
        ticDat = tdf.freeze_me(tdf.TicDat(**{t:getattr(netflowData(),t) for t in tdf.primary_key_fields}))
        filePath = os.path.join(_scratchDir, "netflow.xls")
        tdf.xls.write_file(ticDat, filePath)
        xlsTicDat = tdf.xls.create_tic_dat(filePath, freeze_it=True)
        self.assertTrue(tdf._same_data(ticDat, xlsTicDat))
        def changeIt() :
            xlsTicDat.inflow['Pencils', 'Boston']["quantity"] = 12
        self.assertTrue(self.firesException(changeIt))
        self.assertTrue(tdf._same_data(ticDat, xlsTicDat))

        xlsTicDat = tdf.xls.create_tic_dat(filePath)
        self.assertTrue(tdf._same_data(ticDat, xlsTicDat))
        self.assertFalse(self.firesException(changeIt))
        self.assertFalse(tdf._same_data(ticDat, xlsTicDat))

        self.assertFalse(tdf.xls.get_duplicates(filePath))

        pkHacked = netflowSchema()
        pkHacked["nodes"][0] = ["nimrod"]
        tdfHacked = TicDatFactory(**pkHacked)
        self.assertTrue(self.firesException(lambda : tdfHacked.xls.write_file(ticDat, filePath)))
        tdfHacked.xls.write_file(ticDat, filePath, allow_overwrite =True)
        self.assertTrue("nodes : name" in self.firesException(lambda  :tdf.xls.create_tic_dat(filePath)))

    def testSilly(self):
        tdf = TicDatFactory(**sillyMeSchema())
        ticDat = tdf.TicDat(**sillyMeData())
        schema2 = sillyMeSchema()
        schema2["b"][0] = ("bField2", "bField1", "bField3")
        schema3 = sillyMeSchema()
        schema3["a"][1] = ("aData2", "aData3", "aData1")
        schema4 = sillyMeSchema()
        schema4["a"][1] = ("aData1", "aData3")
        schema5 = sillyMeSchema()
        _tuple = lambda x : tuple(x) if utils.containerish(x) else (x,)
        for t in ("a", "b") :
            schema5[t][1] = _tuple(schema5[t][1]) + _tuple(schema5[t][0])
        schema5["a"][0], schema5["b"][0] =  (),  []
        schema6 = sillyMeSchema()
        schema6["d"] =  [["dField"],()]

        tdf2, tdf3, tdf4, tdf5, tdf6 = (TicDatFactory(**x) for x in (schema2, schema3, schema4, schema5, schema6))
        tdf5.set_generator_tables(("a","c"))
        filePath = os.path.join(_scratchDir, "silly.xls")
        tdf.xls.write_file(ticDat, filePath)

        ticDat2 = tdf2.xls.create_tic_dat(filePath)
        self.assertFalse(tdf._same_data(ticDat, ticDat2))

        ticDat3 = tdf3.xls.create_tic_dat(filePath)
        self.assertTrue(tdf._same_data(ticDat, ticDat3))

        ticDat4 = tdf4.xls.create_tic_dat(filePath)
        for t in ["a","b"]:
            for k,v in getattr(ticDat4, t).items() :
                for _k, _v in v.items() :
                    self.assertTrue(getattr(ticDat, t)[k][_k] == _v)
                if set(v) == set(getattr(ticDat, t)[k]) :
                    self.assertTrue(t == "b")
                else :
                    self.assertTrue(t == "a")

        ticDat5 = tdf5.xls.create_tic_dat(filePath)
        self.assertTrue(tdf5._same_data(tdf._keyless(ticDat), ticDat5))
        self.assertTrue(callable(ticDat5.a) and callable(ticDat5.c) and not callable(ticDat5.b))

        ticDat6 = tdf6.xls.create_tic_dat(filePath)
        self.assertTrue(tdf._same_data(ticDat, ticDat6))
        self.assertTrue(firesException(lambda : tdf6._same_data(ticDat, ticDat6)))
        self.assertTrue(hasattr(ticDat6, "d") and utils.dictish(ticDat6.d))

        def writeData(data, write_header = True):
            import xlwt
            book = xlwt.Workbook()
            for t in tdf.all_tables :
                sheet = book.add_sheet(t)
                if write_header :
                    for i,f in enumerate(tdf.primary_key_fields.get(t, ()) + tdf.data_fields.get(t, ())) :
                        sheet.write(0, i, f)
                for rowInd, row in enumerate(data) :
                    for fieldInd, cellValue in enumerate(row):
                        sheet.write(rowInd+ (1 if write_header else 0), fieldInd, cellValue)
            if os.path.exists(filePath):
                os.remove(filePath)
            book.save(filePath)

        writeData([(1, 2, 3, 4), (1, 20, 30, 40), (10, 20, 30, 40)])
        ticDatMan = tdf.xls.create_tic_dat(filePath, freeze_it=True)
        self.assertTrue(len(ticDatMan.a) == 2 and len(ticDatMan.b) == 3)
        self.assertTrue(ticDatMan.b[1, 20, 30]["bData"] == 40)
        rowCount = tdf.xls.get_duplicates(filePath)
        self.assertTrue(set(rowCount) == {'a'} and set(rowCount["a"]) == {1} and rowCount["a"][1]==2)

        writeData([(1, 2, 3, 4), (1, 20, 30, 40), (10, 20, 30, 40)], write_header=False)
        self.assertTrue(self.firesException(lambda  : tdf.xls.create_tic_dat(filePath, freeze_it=True)))
        ticDatMan = tdf.xls.create_tic_dat(filePath, freeze_it=True, headers_present=False)
        self.assertTrue(len(ticDatMan.a) == 2 and len(ticDatMan.b) == 3)
        self.assertTrue(ticDatMan.b[1, 20, 30]["bData"] == 40)
        rowCount = tdf.xls.get_duplicates(filePath, headers_present=False)
        self.assertTrue(set(rowCount) == {'a'} and set(rowCount["a"]) == {1} and rowCount["a"][1]==2)

        ticDat.a["theboger"] = (1, None, 12)
        tdf.xls.write_file(ticDat, filePath, allow_overwrite=True)
        ticDatNone = tdf.xls.create_tic_dat(filePath, freeze_it=True)
        # THIS IS A FLAW - but a minor one. None's are hard to represent. It is turning into the empty string here.
        # not sure how to handle this, but documenting for now.
        self.assertFalse(tdf._same_data(ticDat, ticDatNone))
        self.assertTrue(ticDatNone.a["theboger"]["aData2"] == "")

        writeData([(1, 2, 3, 4), (1, 20, 30, 40), (10, 20, 30, 40), (1,20,30,12)])
        rowCount = tdf.xls.get_duplicates(filePath)
        self.assertTrue(set(rowCount) == {'a', 'b'} and set(rowCount["a"]) == {1} and rowCount["a"][1]==3)
        self.assertTrue(set(rowCount["b"]) == {(1,20,30)} and rowCount["b"][1,20,30]==2)


    def testRowOffsets(self):
        tdf = TicDatFactory(boger = [[],["the", "big", "boger"]],
                            woger = [[], ["the", "real", "big", "woger"]])
        td = tdf.freeze_me(tdf.TicDat(boger = ([1, 2, 3], [12, 24, 36], tdf.data_fields["boger"], [100, 200, 400]),
                              woger = ([[1, 2, 3, 4]]*4) + [tdf.data_fields["woger"]] +
                                      ([[100, 200, 300, 400]]*5)))
        filePath = os.path.join(_scratchDir, "rowoff.xls")
        tdf.xls.write_file(td, filePath)

        td1= tdf.xls.create_tic_dat(filePath)
        td2 = tdf.xls.create_tic_dat(filePath, {"woger": 5})
        td3 = tdf.xls.create_tic_dat(filePath, {"woger":5, "boger":3})
        self.assertTrue(tdf._same_data(td, td1))
        tdCheck = tdf.TicDat(boger = td2.boger, woger = td.woger)
        self.assertTrue(tdf._same_data(td, tdCheck))
        self.assertTrue(all (td2.woger[i]["big"] == 300 for i in range(5)))
        self.assertTrue(all (td3.woger[i]["real"] == 200 for i in range(5)))
        self.assertTrue(td3.boger[0]["big"] == 200 and len(td3.boger) == 1)


_scratchDir = TestXls.__name__ + "_scratch"

def runTheTests(fastOnly=True) :
    td = TicDatFactory()
    if not hasattr(td, "xls") :
        print "!!!!!!!!!FAILING XLS UNIT TESTS DUE TO FAILURE TO LOAD XLS LIBRARIES!!!!!!!!"
        return
    makeCleanDir(_scratchDir)
    runSuite(TestXls, fastOnly=fastOnly)
    shutil.rmtree(_scratchDir)
# Run the tests.
if __name__ == "__main__":
    runTheTests()
