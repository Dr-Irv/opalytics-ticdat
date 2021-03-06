import sys
import unittest
import ticdat.utils as utils
from ticdat.ticdatfactory import TicDatFactory, _ForeignKey, _ForeignKeyMapping
from ticdat.testing.ticdattestutils import dietData, dietSchema, netflowData, netflowSchema, firesException
from ticdat.testing.ticdattestutils import sillyMeData, sillyMeSchema, runSuite, failToDebugger, flaggedAsRunAlone
from ticdat.testing.ticdattestutils import assertTicDatTablesSame, DEBUG, addNetflowForeignKeys, addDietForeignKeys
import itertools

#uncomment decorator to drop into debugger for assertTrue, assertFalse failures
#@failToDebugger
class TestUtils(unittest.TestCase):
    def firesException(self, f):
        e = firesException(f)
        if e :
            self.assertTrue("TicDatError" in e.__class__.__name__)
            return e.message
    def testOne(self):
        def _cleanIt(x) :
            x.foods['macaroni'] = {"cost": 2.09}
            x.foods['milk'] = {"cost":0.89}
            return x
        dataObj = dietData()
        tdf = TicDatFactory(**dietSchema())
        self.assertTrue(tdf.good_tic_dat_object(dataObj))
        dataObj2 = tdf.copy_tic_dat(dataObj)
        dataObj3 = tdf.copy_tic_dat(dataObj, freeze_it=True)
        dataObj4 = tdf.TicDat(**tdf.as_dict(dataObj3))
        self.assertTrue(all (tdf._same_data(dataObj, x) and dataObj is not x for x in (dataObj2, dataObj3, dataObj4)))
        dataObj = _cleanIt(dataObj)
        self.assertTrue(tdf.good_tic_dat_object(dataObj))
        self.assertTrue(all (tdf._same_data(dataObj, x) and dataObj is not x for x in (dataObj2, dataObj3)))
        def hackit(x) :
            x.foods["macaroni"] = 100
        self.assertTrue(self.firesException(lambda :hackit(dataObj3)))
        hackit(dataObj2)
        self.assertTrue(not tdf._same_data(dataObj, dataObj2) and  tdf._same_data(dataObj, dataObj3))

        msg = []
        dataObj.foods[("milk", "cookies")] = {"cost": float("inf")}
        dataObj.boger = object()
        self.assertFalse(tdf.good_tic_dat_object(dataObj) or
                         tdf.good_tic_dat_object(dataObj, bad_message_handler =msg.append))
        self.assertTrue({"foods : Inconsistent key lengths"} == set(msg))
        self.assertTrue(all(tdf.good_tic_dat_table(getattr(dataObj, t), t)
                            for t in ("categories", "nutritionQuantities")))

        dataObj = dietData()
        dataObj.categories["boger"] = {"cost":1}
        dataObj.categories["boger"] = {"cost":1}
        self.assertFalse(tdf.good_tic_dat_object(dataObj) or
                         tdf.good_tic_dat_object(dataObj, bad_message_handler=msg.append))
        self.assertTrue({'foods : Inconsistent key lengths',
                         'categories : Inconsistent data field name keys.'} == set(msg))
        ex = firesException(lambda : tdf.freeze_me(tdf.TicDat(**{t:getattr(dataObj,t)
                                                                for t in tdf.primary_key_fields}))).message
        self.assertTrue("categories cannot be treated as a ticDat table : Inconsistent data field name keys" in ex)

    def _assertSame(self, t1, t2, goodTicDatTable):

        if utils.dictish(t1) or utils.dictish(t2) :
            _ass = lambda _t1, _t2 : assertTicDatTablesSame(_t1, _t2,
                    _goodTicDatTable=  goodTicDatTable,
                    **({} if DEBUG() else {"_assertTrue":self.assertTrue, "_assertFalse":self.assertFalse}))

            _ass(t1, t2)
            _ass(t2, t1)
        else :
            setify = lambda t : set(t) if len(t) and not hasattr(t[0], "values") else {r.values() for r in t}
            self.assertTrue(setify(t1) == setify(t2))

    def testTwo(self):
        objOrig = dietData()
        staticFactory = TicDatFactory(**dietSchema())
        tables = set(staticFactory.primary_key_fields)
        ticDat = staticFactory.freeze_me(staticFactory.TicDat(**{t:getattr(objOrig,t) for t in tables}))
        self.assertTrue(staticFactory.good_tic_dat_object(ticDat))
        for t in tables :
            self._assertSame(getattr(objOrig, t), getattr(ticDat,t),
                                    lambda _t : staticFactory.good_tic_dat_table(_t, t))

    def testThree(self):
        objOrig = netflowData()
        staticFactory = TicDatFactory(**netflowSchema())
        goodTable = lambda t : lambda _t : staticFactory.good_tic_dat_table(_t, t)
        tables = set(staticFactory.primary_key_fields)
        ticDat = staticFactory.freeze_me(staticFactory.TicDat(**{t:getattr(objOrig,t) for t in tables}))
        self.assertTrue(staticFactory.good_tic_dat_object(ticDat))
        for t in tables :
            self._assertSame(getattr(objOrig, t), getattr(ticDat,t), goodTable(t))

        objOrig.commodities.append(12.3)
        objOrig.arcs[(1, 2)] = [12]
        self._assertSame(objOrig.nodes, ticDat.nodes, goodTable("nodes"))
        self._assertSame(objOrig.cost, ticDat.cost, goodTable("cost"))
        self.assertTrue(firesException(lambda : self._assertSame(
            objOrig.commodities, ticDat.commodities, goodTable("commodities")) ))
        self.assertTrue(firesException(lambda : self._assertSame(
            objOrig.arcs, ticDat.arcs, goodTable("arcs")) ))

        ticDat = staticFactory.freeze_me(staticFactory.TicDat(**{t:getattr(objOrig,t) for t in tables}))
        for t in tables :
            self._assertSame(getattr(objOrig, t), getattr(ticDat,t), goodTable(t))

        self.assertTrue(ticDat.arcs[1, 2]["capacity"] == 12)
        self.assertTrue(12.3 in ticDat.commodities)

        objOrig.cost[5]=5

        self.assertTrue("cost cannot be treated as a ticDat table : Inconsistent key lengths" in
            firesException(lambda : staticFactory.freeze_me(staticFactory.TicDat
                                    (**{t:getattr(objOrig,t) for t in tables}))))

        objOrig = netflowData()
        def editMeBadly(t) :
            def rtn() :
                t.cost["hack"] = 12
            return rtn
        def editMeWell(t) :
            def rtn() :
                t.cost["hack", "my", "balls"] = 12.12
            return rtn
        self.assertTrue(all(firesException(editMeWell(t)) and firesException(editMeBadly(t)) for t in
                            (ticDat, staticFactory.freeze_me(staticFactory.TicDat()))))

        def attributeMe(t) :
            def rtn() :
                t.boger="bogerwoger"
            return rtn

        self.assertTrue(firesException(attributeMe(ticDat)) and firesException(attributeMe(
                staticFactory.freeze_me(staticFactory.TicDat()))))

        mutable = staticFactory.TicDat(**{t:getattr(objOrig,t) for t in tables})
        for t in tables :
            self._assertSame(getattr(objOrig, t), getattr(mutable,t), goodTable(t))

        self.assertTrue(firesException(editMeBadly(mutable)))
        self.assertFalse(firesException(editMeWell(mutable)) or firesException(attributeMe(mutable)))
        self.assertTrue(firesException(lambda : self._assertSame(
            objOrig.cost, mutable.cost, goodTable("cost")) ))

    def testFour(self):
        objOrig = sillyMeData()
        staticFactory = TicDatFactory(**sillyMeSchema())
        goodTable = lambda t : lambda _t : staticFactory.good_tic_dat_table(_t, t)
        tables = set(staticFactory.primary_key_fields)
        ticDat = staticFactory.freeze_me(staticFactory.TicDat(**objOrig))
        self.assertTrue(staticFactory.good_tic_dat_object(ticDat))
        for t in tables :
            self._assertSame(objOrig[t], getattr(ticDat,t), goodTable(t))
        pickedData = staticFactory.TicDat(**staticFactory.as_dict(ticDat))
        self.assertTrue(staticFactory._same_data(ticDat, pickedData))
        mutTicDat = staticFactory.TicDat()
        for k,v in ticDat.a.items() :
            mutTicDat.a[k] = v.values()
        for k,v in ticDat.b.items() :
            mutTicDat.b[k] = v.values()[0]
        for r in ticDat.c:
            mutTicDat.c.append(r)
        for t in tables :
            self._assertSame(getattr(mutTicDat, t), getattr(ticDat,t), goodTable(t))

        self.assertTrue("theboger" not in mutTicDat.a)
        mutTicDat.a["theboger"]["aData2"] =22
        self.assertTrue("theboger" in mutTicDat.a and mutTicDat.a["theboger"].values() == (0, 22, 0))

        newSchema = sillyMeSchema()
        newSchema["a"][1] += ("aData4",)
        newFactory = TicDatFactory(**newSchema)
        def makeNewTicDat() : return newFactory.TicDat(a=ticDat.a, b=ticDat.b, c=ticDat.c)
        newTicDat = makeNewTicDat()
        self.assertFalse(staticFactory.good_tic_dat_object(newTicDat))
        self.assertTrue(newFactory.good_tic_dat_object(ticDat))
        self.assertTrue(newFactory._same_data(makeNewTicDat(), newTicDat))
        newTicDat.a[ticDat.a.keys()[0]]["aData4"]=12
        self.assertFalse(newFactory._same_data(makeNewTicDat(), newTicDat))

    def testFive(self):
        tdf = TicDatFactory(**netflowSchema())
        addNetflowForeignKeys(tdf)
        dat = tdf.freeze_me(tdf.TicDat(**{t : getattr(netflowData(), t) for t in tdf.all_tables}))
        obfudat = tdf.obfusimplify(dat, freeze_it=1)
        self.assertFalse(tdf._same_data(dat, obfudat.copy))
        for (s,d),r in obfudat.copy.arcs.items():
            self.assertFalse((s,d) in dat.arcs)
            self.assertTrue(dat.arcs[obfudat.renamings[s][1], obfudat.renamings[d][1]]["capacity"] == r["capacity"])
        obfudat = tdf.obfusimplify(dat, freeze_it=1, skip_tables=["commodities", "nodes"])
        self.assertTrue(tdf._same_data(obfudat.copy, dat))

        tdf = TicDatFactory(**netflowSchema())
        addNetflowForeignKeys(tdf)
        mone, one2one = "many-to-one",  "one-to-one"
        fk, fkm = _ForeignKey, _ForeignKeyMapping
        self.assertTrue(set(tdf.foreign_keys) ==  {fk("arcs", 'nodes', fkm('source',u'name'), mone),
                            fk("arcs", 'nodes', fkm('destination',u'name'), mone),
                            fk("cost", 'nodes', fkm('source',u'name'), mone),
                            fk("cost", 'nodes', fkm('destination',u'name'), mone),
                            fk("cost", 'commodities', fkm('commodity',u'name'), mone),
                            fk("inflow", 'commodities', fkm('commodity',u'name'), mone),
                            fk("inflow", 'nodes', fkm('node',u'name'), mone)})

        tdf.clear_foreign_keys("cost")
        self.assertTrue(set(tdf.foreign_keys) ==  {fk("arcs", 'nodes', fkm('source',u'name'), mone),
                            fk("arcs", 'nodes', fkm('destination',u'name'), mone),
                            fk("inflow", 'commodities', fkm('commodity',u'name'), mone),
                            fk("inflow", 'nodes', fkm('node',u'name'), mone)})

        tdf = TicDatFactory(**dietSchema())
        self.assertFalse(tdf.foreign_keys)
        addDietForeignKeys(tdf)

        self.assertTrue(set(tdf.foreign_keys) == {fk("nutritionQuantities", 'categories', fkm('category',u'name'), mone),
                                                  fk("nutritionQuantities", 'foods', fkm('food',u'name'), mone)})

        tdf.TicDat()
        self.assertTrue(self.firesException(lambda  : tdf.clear_foreign_keys("nutritionQuantities")))
        self.assertTrue(tdf.foreign_keys)
        tdf = TicDatFactory(**dietSchema())
        addDietForeignKeys(tdf)
        tdf.clear_foreign_keys("nutritionQuantities")
        self.assertFalse(tdf.foreign_keys)

        tdf = TicDatFactory(parentTable = [["pk"],["pd1", "pd2", "pd3"]],
                            goodChild = [["gk"], ["gd1", "gd2"]],
                            badChild = [["bk1", "bk2"], ["bd"]],
                            appendageChild = [["ak"], ["ad1", "ad2"]],
                            appendageBadChild = [["bk1", "bk2"], []])
        tdf.add_foreign_key("goodChild", "parentTable", fkm("gd1" , "pk"))
        tdf.add_foreign_key("badChild", "parentTable", ["bk2" , "pk"])
        self.assertTrue("many-to-many" in self.firesException(lambda :
                tdf.add_foreign_key("badChild", "parentTable", ["bd", "pd2"])))
        tdf.add_foreign_key("appendageChild", "parentTable", ["ak", "pk"])
        tdf.add_foreign_key("appendageBadChild", "badChild", (("bk2", "bk2"), ("bk1","bk1")))
        fks = tdf.foreign_keys
        _getfk = lambda t : next(_ for _ in fks if _.native_table == t)
        self.assertTrue(_getfk("goodChild").cardinality == "many-to-one")
        self.assertTrue(_getfk("badChild").cardinality == "many-to-one")
        self.assertTrue(_getfk("appendageChild").cardinality == "one-to-one")
        self.assertTrue(_getfk("appendageBadChild").cardinality == "one-to-one")

        tdf.clear_foreign_keys("appendageBadChild")
        self.assertTrue(tdf.foreign_keys and "appendageBadChild" not in tdf.foreign_keys)
        tdf.clear_foreign_keys()
        self.assertFalse(tdf.foreign_keys)

    def testSix(self):
        tdf = TicDatFactory(plants = [["name"], ["stuff", "otherstuff"]],
                            lines = [["name"], ["plant", "weird stuff"]],
                            line_descriptor = [["name"], ["booger"]],
                            products = [["name"],["gover"]],
                            production = [["line", "product"], ["min", "max"]],
                            pureTestingTable = [[], ["line", "plant", "product", "something"]],
                            extraProduction = [["line", "product"], ["extramin", "extramax"]],
                            weirdProduction = [["line1", "line2", "product"], ["weirdmin", "weirdmax"]])
        tdf.add_foreign_key("production", "lines", ("line", "name"))
        tdf.add_foreign_key("production", "products", ("product", "name"))
        tdf.add_foreign_key("lines", "plants", ("plant", "name"))
        tdf.add_foreign_key("line_descriptor", "lines", ("name", "name"))
        for f in set(tdf.data_fields["pureTestingTable"]).difference({"something"}):
            tdf.add_foreign_key("pureTestingTable", "%ss"%f, (f,"name"))
        tdf.add_foreign_key("extraProduction", "production", (("line", "line"), ("product","product")))
        tdf.add_foreign_key("weirdProduction", "production", (("line1", "line"), ("product","product")))
        tdf.add_foreign_key("weirdProduction", "extraProduction", (("line2","line"), ("product","product")))

        goodDat = tdf.TicDat()
        goodDat.plants["Cleveland"] = ["this", "that"]
        goodDat.plants["Newark"]["otherstuff"] =1
        goodDat.products["widgets"] = goodDat.products["gadgets"] = "shizzle"

        for i,p in enumerate(goodDat.plants):
            goodDat.lines[i]["plant"] = p

        for i,(pl, pd) in enumerate(itertools.product(goodDat.lines, goodDat.products)):
            goodDat.production[pl, pd] = {"min":1, "max":10+i}

        badDat1 = tdf.copy_tic_dat(goodDat)
        badDat1.production["notaline", "widgets"] = [0,1]
        badDat2 = tdf.copy_tic_dat(badDat1)

        fk, fkm = _ForeignKey, _ForeignKeyMapping
        self.assertTrue(tdf.find_foreign_key_failures(badDat1) == tdf.find_foreign_key_failures(badDat2) ==
                        {fk('production', 'lines', fkm('line', 'name'), 'many-to-one'):
                             (('notaline',), (('notaline', 'widgets'),))})
        badDat1.lines["notaline"]["plant"] = badDat2.lines["notaline"]["plant"] = "notnewark"
        self.assertTrue(tdf.find_foreign_key_failures(badDat1) == tdf.find_foreign_key_failures(badDat2) ==
                        {fk('lines', 'plants', fkm('plant', 'name'), 'many-to-one'):
                             (('notnewark',), ('notaline',))})
        tdf.remove_foreign_keys_failures(badDat1, propagate=False)
        tdf.remove_foreign_keys_failures(badDat2, propagate=True)
        self.assertTrue(tdf._same_data(badDat2, goodDat) and not tdf.find_foreign_key_failures(badDat2))
        self.assertTrue(tdf.find_foreign_key_failures(badDat1) ==
                {fk('production', 'lines', fkm('line', 'name'), 'many-to-one'):
                     (('notaline',), (('notaline', 'widgets'),))})

        tdf.remove_foreign_keys_failures(badDat1, propagate=False)
        self.assertTrue(tdf._same_data(badDat1, goodDat) and not tdf.find_foreign_key_failures(badDat1))

        _ = len(goodDat.lines)
        for i,p in enumerate(goodDat.plants.keys() + goodDat.plants.keys()):
            goodDat.lines[i+_]["plant"] = p
        for l in goodDat.lines:
            if i%2:
                goodDat.line_descriptor[l] = i+10

        for i,(l,pl,pdct) in enumerate(sorted(itertools.product(goodDat.lines, goodDat.plants, goodDat.products))):
            goodDat.pureTestingTable.append((l,pl,pdct,i))
        self.assertFalse(tdf.find_foreign_key_failures(goodDat))
        badDat = tdf.copy_tic_dat(goodDat)
        badDat.pureTestingTable.append(("j", "u", "nk", "ay"))
        l = len(goodDat.pureTestingTable)
        self.assertTrue(tdf.find_foreign_key_failures(badDat) ==
         {fk('pureTestingTable', 'plants', fkm('plant', 'name'), 'many-to-one'): (('u',),(l,)),
          fk('pureTestingTable', 'products', fkm('product', 'name'), 'many-to-one'): (('nk',), (l,)),
          fk('pureTestingTable', 'lines', fkm('line', 'name'), 'many-to-one'): (('j',), (l,))})

        obfudat = tdf.obfusimplify(goodDat, freeze_it=True)
        self.assertTrue(all(len(getattr(obfudat.copy, t)) == len(getattr(goodDat, t))
                            for t in tdf.all_tables))
        for n in goodDat.plants.keys() + goodDat.lines.keys() + goodDat.products.keys() :
            self.assertTrue(n in {_[1] for _ in obfudat.renamings.values()})
            self.assertFalse(n in obfudat.renamings)
        self.assertTrue(obfudat.copy.plants['P2']['otherstuff'] == 1)
        self.assertFalse(tdf._same_data(obfudat.copy, goodDat))
        for k,r in obfudat.copy.line_descriptor.items():
            i = r.values()[0] - 10
            self.assertTrue(i%2 and (goodDat.line_descriptor[i].values()[0] == i+10))

        obfudat2 = tdf.obfusimplify(goodDat, {"plants": "P", "lines" : "L", "products" :"PR"})
        self.assertTrue(tdf._same_data(obfudat.copy, obfudat2.copy))

        obfudat3 = tdf.obfusimplify(goodDat, skip_tables=["plants", "lines", "products"])
        self.assertTrue(tdf._same_data(obfudat3.copy, goodDat))

        obfudat4 = tdf.obfusimplify(goodDat, skip_tables=["lines", "products"])
        self.assertFalse(tdf._same_data(obfudat4.copy, goodDat))
        self.assertFalse(tdf._same_data(obfudat4.copy, obfudat.copy))

    def testSeven(self):
        tdf = TicDatFactory(**dietSchema())
        def makeIt() :
            rtn = tdf.TicDat()
            rtn.foods["a"] = {}
            rtn.categories["1"] = {}
            rtn.categories["2"] = [0,1]
            self.assertTrue(rtn.categories["2"]["minNutrition"] == 0)
            self.assertTrue(rtn.categories["2"]["maxNutrition"] == 1)
            rtn.nutritionQuantities['junk',1] = {}
            return tdf.freeze_me(rtn)
        td = makeIt()
        self.assertTrue(td.foods["a"]["cost"]==0 and td.categories["1"].values() == (0,0) and
                        td.nutritionQuantities['junk',1]["qty"] == 0)
        tdf = TicDatFactory(**dietSchema())
        tdf.set_default_values(foods = {"cost":"dontcare"},nutritionQuantities = {"qty":100} )
        td = makeIt()
        self.assertTrue(td.foods["a"]["cost"]=='dontcare' and td.categories["1"].values() == (0,0) and
                        td.nutritionQuantities['junk',1]["qty"] == 100)
        tdf = TicDatFactory(**dietSchema())
        tdf.set_default_value("categories", "minNutrition", 1)
        tdf.set_default_value("categories", "maxNutrition", 2)
        td = makeIt()
        self.assertTrue(td.foods["a"]["cost"]==0 and td.categories["1"].values() == (1,2) and
                        td.nutritionQuantities['junk',1]["qty"] == 0)

    def testEight(self):
        tdf = TicDatFactory(**dietSchema())
        def makeIt() :
            rtn = tdf.TicDat()
            rtn.foods["a"] = 12
            rtn.foods["b"] = None
            rtn.categories["1"] = {"maxNutrition":100, "minNutrition":40}
            rtn.categories["2"] = [10,20]
            for f, p in itertools.product(rtn.foods, rtn.categories):
                rtn.nutritionQuantities[f,p] = 5
            rtn.nutritionQuantities['a', 2] = 12
            return tdf.freeze_me(rtn)
        dat = makeIt()
        self.assertFalse(tdf.find_data_type_failures(dat))

        tdf = TicDatFactory(**dietSchema())
        tdf.set_data_type("foods", "cost", nullable=False)
        tdf.set_data_type("nutritionQuantities", "qty", min=5, inclusive_min=False, max=12, inclusive_max=True)
        tdf.set_default_value("foods", "cost", 2)
        dat = makeIt()
        failed = tdf.find_data_type_failures(dat)
        self.assertTrue(set(failed) == {('foods', 'cost'), ('nutritionQuantities', 'qty')})
        self.assertTrue(set(failed['nutritionQuantities', 'qty'].pks) ==
                        {('b', '1'), ('a', '2'), ('a', '1'), ('b', '2')})
        self.assertTrue(failed['nutritionQuantities', 'qty'].bad_values == (5,))
        ex = self.firesException(lambda : tdf.replace_data_type_failures(tdf.copy_tic_dat(dat)))
        self.assertTrue(all(_ in ex for _ in ("replacement value", "nutritionQuantities", "qty")))
        fixedDat = tdf.replace_data_type_failures(tdf.copy_tic_dat(dat),
                            replacement_values={("nutritionQuantities", "qty"):5.001})
        self.assertFalse(tdf.find_data_type_failures(fixedDat) or tdf._same_data(fixedDat, dat))
        self.assertTrue(all(fixedDat.nutritionQuantities[pk]["qty"] == 5.001 for pk in
                            failed['nutritionQuantities', 'qty'].pks))
        self.assertTrue(fixedDat.foods["a"]["cost"] == 12 and fixedDat.foods["b"]["cost"] == 2 and
                        fixedDat.nutritionQuantities['a', 2]["qty"] == 12)

        tdf = TicDatFactory(**dietSchema())
        tdf.set_data_type("foods", "cost", nullable=False)
        tdf.set_data_type("nutritionQuantities", "qty", min=5, inclusive_min=False, max=12, inclusive_max=True)
        fixedDat2 = tdf.replace_data_type_failures(tdf.copy_tic_dat(dat),
                            replacement_values={("nutritionQuantities", "qty"):5.001, ("foods", "cost") : 2})
        self.assertTrue(tdf._same_data(fixedDat, fixedDat2))

        tdf = TicDatFactory(**dietSchema())
        tdf.set_data_type("foods", "cost", nullable=True)
        tdf.set_data_type("nutritionQuantities", "qty",number_allowed=False)
        failed = tdf.find_data_type_failures(dat)
        self.assertTrue(set(failed) == {('nutritionQuantities', 'qty')})
        self.assertTrue(set(failed['nutritionQuantities', 'qty'].pks) == set(dat.nutritionQuantities))
        ex = self.firesException(lambda : tdf.replace_data_type_failures(tdf.copy_tic_dat(dat)))
        self.assertTrue(all(_ in ex for _ in ("replacement value", "nutritionQuantities", "qty")))

        tdf = TicDatFactory(**dietSchema())
        tdf.set_data_type("foods", "cost")
        fixedDat = tdf.replace_data_type_failures(tdf.copy_tic_dat(makeIt()))
        self.assertTrue(fixedDat.foods["a"]["cost"] == 12 and fixedDat.foods["b"]["cost"] == 0)

        tdf = TicDatFactory(**netflowSchema())
        addNetflowForeignKeys(tdf)
        dat = tdf.copy_tic_dat(netflowData(), freeze_it=1)
        self.assertFalse(hasattr(dat.nodes["Detroit"], "arcs_source"))

        tdf = TicDatFactory(**netflowSchema())
        addNetflowForeignKeys(tdf)
        tdf.enable_foreign_key_links()
        dat = tdf.copy_tic_dat(netflowData(), freeze_it=1)
        self.assertTrue(hasattr(dat.nodes["Detroit"], "arcs_source"))

        tdf = TicDatFactory(**netflowSchema())
        def makeIt() :
            if not tdf.foreign_keys:
                tdf.enable_foreign_key_links()
                addNetflowForeignKeys(tdf)
            orig = netflowData()
            rtn = tdf.copy_tic_dat(orig)
            for n in rtn.nodes["Detroit"].arcs_source:
                rtn.arcs["Detroit", n] = n
            self.assertTrue(all(len(getattr(rtn, t)) == len(getattr(orig, t)) for t in tdf.all_tables))
            return tdf.freeze_me(rtn)
        dat = makeIt()
        self.assertFalse(tdf.find_data_type_failures(dat))

        tdf = TicDatFactory(**netflowSchema())
        tdf.set_data_type("arcs", "capacity", strings_allowed="*")
        dat = makeIt()
        self.assertFalse(tdf.find_data_type_failures(dat))

        tdf = TicDatFactory(**netflowSchema())
        tdf.set_data_type("arcs", "capacity", strings_allowed=["Boston", "Seattle", "lumberjack"])
        dat = makeIt()
        failed = tdf.find_data_type_failures(dat)
        self.assertTrue(failed == {('arcs', 'capacity'):(("New York",), (("Detroit", "New York"),))})
        fixedDat = tdf.replace_data_type_failures(tdf.copy_tic_dat(makeIt()))
        netflowData_ = tdf.copy_tic_dat(netflowData())
        self.assertFalse(tdf.find_data_type_failures(fixedDat) or tdf._same_data(dat, netflowData_))
        fixedDat = tdf.copy_tic_dat(tdf.replace_data_type_failures(tdf.copy_tic_dat(makeIt()),
                                        {("arcs", "capacity"):80, ("cost","cost") :"imok"}))
        fixedDat.arcs["Detroit", "Boston"] = 100
        fixedDat.arcs["Detroit", "Seattle"] = 120
        self.assertTrue(tdf._same_data(fixedDat, netflowData_))

    def testNine(self):
        for schema in (dietSchema(), sillyMeSchema(), netflowSchema()) :
            d = TicDatFactory(**schema).schema()
            assert d == {k : map(list, v) for k,v in schema.items()}

#
# from ticdat import TicDatFactory
# import itertools
#
# tdf = TicDatFactory(plants = [["name"], ["stuff", "otherstuff"]],
#                             lines = [["name"], ["plant", "weird stuff"]],
#                             products = [["name"],["gover"]],
#                             production = [["line", "product"], ["min", "max"]],
#                             extraProduction = [["line", "product"], ["extramin", "extramax"]],
#                             weirdProduction = [["line1", "line2", "product"], ["weirdmin", "weirdmax"]],
#                             pureTestingTable = [[], ["line", "plant", "product"]])
#
# tdf.add_foreign_key("production", "lines", {"line" : "name"})
# tdf.add_foreign_key("production", "products", {"product" : "name"})
# tdf.add_foreign_key("lines", "plants", {"plant" : "name"})
# for f in tdf.data_fields["pureTestingTable"]:
#     tdf.add_foreign_key("pureTestingTable", "%ss"%f, {f:"name"})
# tdf.add_foreign_key("extraProduction", "production", {"line" : "line", "product":"product"})
# tdf.add_foreign_key("weirdProduction", "production", {"line1" : "line", "product":"product"})
# tdf.add_foreign_key("weirdProduction", "extraProduction", {"line2" : "line", "product":"product"})
#
# goodDat = tdf.TicDat()
# goodDat.plants["Cleveland"] = ["this", "that"]
# goodDat.plants["Newark"]["otherstuff"] =1
# goodDat.products["widgets"] = goodDat.products["gadgets"] = "shizzle"
#
# for i,p in enumerate(goodDat.plants):
#     goodDat.lines[i]["plant"] = p
# for i,(pl, pd) in enumerate(itertools.product(goodDat.lines, goodDat.products)):
#     goodDat.production[pl, pd] = {"min":1, "max":10+i}
#
# for l,pl,pdct in itertools.product(goodDat.lines, goodDat.plants, goodDat.products) :
#     goodDat.pureTestingTable.append((l,pl,pdct))
#
#
# boger = tdf.obfusimplify(goodDat)

def runTheTests(fastOnly=True) :
    runSuite(TestUtils, fastOnly=fastOnly)

# Run the tests.
if __name__ == "__main__":
    runTheTests()

