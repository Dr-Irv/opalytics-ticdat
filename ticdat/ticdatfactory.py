"""
Create TicDatFactory. Main entry point for ticdat library.
PEP8
"""
import collections as clt
import utils as utils
from utils import verify, freezable_factory, FrozenDict, FreezeableDict
from utils import dictish, containerish, deep_freeze, lupish
from string import uppercase
from collections import namedtuple
import xls
import csvtd as csv
import sqlitetd as sql
import mdb

def _acceptable_default(v) :
    return utils.numericish(v) or utils.stringish(v) or (v is None)

def _keylen(k) :
    if not utils.containerish(k) :
        return 1
    try:
        rtn = len(k)
    except :
        rtn = 0
    return rtn

class _ForeignKey(namedtuple("ForeignKey", ("native_table", "foreign_table", "mapping", "cardinality"))) :
    def nativefields(self):
        return (self.mapping.native_field,) if type(self.mapping) is _ForeignKeyMapping \
                                           else tuple(_.native_field for _ in self.mapping)
    def foreigntonativemapping(self):
        if type(self.mapping) is _ForeignKeyMapping :
            return {self.mapping.foreign_field:self.mapping.native_field}
        else :
            return {_.foreign_field:_.native_field for _ in self.mapping}
    def nativetoforeignmapping(self):
        return {v:k for k,v in self.foreigntonativemapping().items()}

_ForeignKeyMapping = namedtuple("FKMapping", ("native_field", "foreign_field"))

class _TypeDictionary(namedtuple("TypeDictionary", ("number_allowed", "strings_allowed", "nullable",
                                        "min", "max", "inclusive_min", "inclusive_max","must_be_int"))):
    def valid_data(self, data):
        if utils.numericish(data):
            if not self.number_allowed:
                return False
            if (data < self.min) or (data > self.max):
                return False
            if (not self.inclusive_min) and (data == self.min):
                return False
            if (not self.inclusive_max) and (data  == self.max):
                return False
            if (self.must_be_int) and (int(data) != data):
                return False
            return True
        if utils.stringish(data):
            if self.strings_allowed == "*":
                return True
            assert utils.containerish(self.strings_allowed)
            return data in self.strings_allowed
        if data is None:
            return bool(self.nullable)
        return False


class TicDatFactory(freezable_factory(object, "_isFrozen")) :
    """
    Primary class for ticdat library. This class is constructed with a schema,
    and can be used to generate TicDat objects, or to write TicDat objects to
    different file types. Analytical code that uses TicDat objects can be used,
    without change, on different data sources.
    """
    @property
    def primary_key_fields(self):
        return self._primary_key_fields
    @property
    def data_fields(self):
        return self._data_fields
    def schema(self):
        """
        :return: a dictionary with table name mapping to a list of lists
                 defining primary key fields and data fields
        """
        return {t: [list(self.primary_key_fields.get(t, [])),
                    list(self.data_fields.get(t, []))]
                for t in set(self.primary_key_fields).union(self.data_fields)}
    @property
    def generator_tables(self):
        return deep_freeze(self._generator_tables)
    @property
    def default_values(self):
        return deep_freeze(self._default_values)
    @property
    def data_types(self):
        return utils.FrozenDict({t : utils.FrozenDict({k :v for k,v in vd.items()})
                                for t,vd in self._data_types.items()})
    def set_data_type(self, table, field, number_allowed = True,
                      inclusive_min = True, inclusive_max = False, min = 0, max = float("inf"),
                      must_be_int = False, strings_allowed= (), nullable = False):
        """
        sets the data type for a field. By default, fields don't have types. Adding a data type doesn't block
        data of the wrong type from being entered. Data types are useful for recognizing errant data entries
        with find_data_type_failures(). Errant data entries can be replaced with replace_data_type_failures().
        :param table: a table in the schema
        :param field: a data field for this table
        :param number_allowed: boolean does this field allow numbers?
        :param inclusive_min: boolean : if number allowed, is the min inclusive?
        :param inclusive_max: boolean : if number allowed, is the max inclusive?
        :param min: if number allowed, the minimum value
        :param max: if number allowed, the maximum value
        :param must_be_int: boolean : if number allowed, must the number be integral?
        :param strings_allowed: if a collection - then a list of the strings allowed.
                                The empty collection prohibits strings.
                                If a "*", then any string is accepted.
        :param nullable : boolean : can this value contain null (aka None)
        :return:
        """
        verify(not self._has_been_used,
               "The data types can't be changed after a TicDatFactory has been used.")
        verify(table in self.all_tables, "Unrecognized table name %s"%table)
        verify(field in self.data_fields[table], "%s does not refer to a data field for %s"%(field, table))

        verify((strings_allowed == '*') or
               (containerish(strings_allowed) and all(utils.stringish(x) for x in strings_allowed)),
"""The strings_allowed argument should be a container of strings, or the single '*' character.""")
        if utils.containerish(strings_allowed):
            strings_allowed = tuple(strings_allowed) # defensive copy
        if number_allowed:
            verify(utils.numericish(max), "max should be numeric")
            verify(utils.numericish(min), "min should be numeric")
            verify(max >= min, "max cannot be smaller than min")
            self._data_types[table][field] = _TypeDictionary(number_allowed=True,
                strings_allowed=strings_allowed,  nullable = bool(nullable),
                min = min, max = max, inclusive_min= bool(inclusive_min), inclusive_max = bool(inclusive_max),
                must_be_int = bool(must_be_int))
        else :
            self._data_types[table][field] = _TypeDictionary(number_allowed=False,
                strings_allowed=strings_allowed,  nullable = bool(nullable),
                min = 0, max = float("inf"), inclusive_min= True, inclusive_max = True,
                must_be_int = False)
    def clear_data_type(self, table, field):
        """
        clears the data type for a field. By default, fields don't types.  Adding a data type doesn't block
        data of the wrong type from being entered. Data types are useful for recognizing errant data entries.
        If no data type is specified (the default) then no errant data will be recognized.
        :param table: table in the schema
        :param field:
        :return:
        """
        if field not in self._data_types.get(table, ()):
            return
        verify(not self._has_been_used,
               "The data types can't be changed after a TicDatFactory has been used.")
        del(self._data_types[table][field])
    def set_default_value(self, table, field, default_value):
        """
        sets the default value for a specific field
        :param table: a table in the schema
        :param field: a field in the table
        :param default_value: the default value to apply
        :return:
        """
        verify(not self._has_been_used,
               "The default values can't be changed after a TicDatFactory has been used.")
        verify(table in self.all_tables, "Unrecognized table name %s"%table)
        verify(field in self.data_fields[table], "%s does not refer to a data field for %s"%(field, table))
        verify(_acceptable_default(default_value), "%s can not be used as a default value"%default_value)
        self._default_values[table][field] = default_value

    def set_default_values(self, **tableDefaults):
        """
        sets the default values for the fields
        :param tableDefaults:
             A dictionary of named arguments. Each argument name (i.e. each key) should be a table name
             Each value should itself be a dictionary mapping data field names to default values
             Ex: tdf.set_default_values(categories = {"minNutrition":0, "maxNutrition":float("inf")},
                         foods = {"cost":0}, nutritionQuantities = {"qty":0})
        :return:
        """
        verify(not self._has_been_used,
               "The default values can't be changed after a TicDatFactory has been used.")
        for k,v in tableDefaults.items():
            verify(k in self.all_tables, "Unrecognized table name %s"%k)
            verify(dictish(v) and set(v).issubset(self.data_fields[k]),
                "Default values for %s should be a dictionary mapping data field names to values"
                %k)
            verify(all(_acceptable_default(_v) for _v in v.values()), "some default values are unacceptable")
            self._default_values[k] = dict(self._default_values[k], **v)
    def set_generator_tables(self, g):
        """
        sets which tables are to be generator tables. Generator tables are represented as generators
        pulled from the actual data store. This prevents them from being fulled loaded into memory.
        Generator tables are only appropriate for truly massive data tables with no primary key.
        :param g:
        :return:
        """
        verify(not self._has_been_used,
               "The generator tables can't be changed after a TicDatFactory has been used.")
        verify(containerish(g) and set(g).issubset(self.all_tables),
               "Generator_tables should be a container of table names")
        verify(not any(self.primary_key_fields.get(t) for t in g),
               "Can not make generators from tables with primary keys")
        self._generator_tables[:] = [_ for _ in g]
    def clear_foreign_keys(self, native_table = None):
        """
        create a TicDatFactory
        :param native_table: optional. The table whose foreign keys should be cleared.
                             If omitted, all foreign keys are cleared.
        """
        verify(not self._has_been_used,
               "The foreign keys can't be changed after a TicDatFactory has been used.")
        verify(native_table is None or native_table in self.all_tables,
               "If provided, native_table should specify a table.")
        deleteme = []
        for nt,ft in self._foreign_keys:
            if nt == (native_table or nt) :
                deleteme.append((nt,ft))
        for nt, ft in deleteme:
            del(self._foreign_keys[nt,ft])
    @property
    def foreign_keys(self):
        rtn = []
        for (native,foreign), nativefieldtuples in self._foreign_keys.items():
            for nativefields in nativefieldtuples :
                mappings = tuple(_ForeignKeyMapping(nf,ff) for nf,ff in
                                 zip(nativefields, self.primary_key_fields[foreign]))
                mappings = mappings[0] if len(mappings)==1 else mappings
                if set(nativefields) == set(self.primary_key_fields.get(native, ())) :
                    cardinality = "one-to-one"
                else:
                   cardinality = "many-to-one"
                rtn.append(_ForeignKey(native, foreign, mappings, cardinality))
        assert len(rtn) == len(set(rtn))
        return tuple(rtn)
    def _foreign_keys_by_native(self):
        rtn = clt.defaultdict(list)
        for fk in self.foreign_keys:
            rtn[fk.native_table].append(fk)
        return utils.FrozenDict({k:frozenset(v) for k,v in rtn.items()})
    def enable_foreign_key_links(self):
        """
        call to enable foreign key links. For ex. a TicDat object made from
        a factory with foreign key enabled will pass the following assert
        assert (dat.foods["chicken"].nutritionQuantities["protein"] is
                dat.categories["protein"].nutritionQuantities["chicken"] is
                dat.nutritionQuantities["chicken", "protein"])
        Note that by default, TicDatFactories don't create foreign key links since doing so
        can slow down TicDat creation.
        :return:
        """
        self._foreign_key_links_enabled[:] = [True]

    def add_foreign_key(self, native_table, foreign_table, mappings):
        """
        Adds a foreign key relationship to the schema.  Adding a foreign key doesn't block
        the entry of child records that fail to find a parent match. It does make it easy
        to recognize such records (with find_foreign_key_failures()) and to remove such records
        (with remove_foreign_keys_failures())
        :param native_table: (aka child table). The table with fields that must match some other table.
        :param foreign_table: (aka parent table). The table providing the matching entries.
        :param mappings: For simple foreign keys, a [native_field, foreign_field] pair.
                         For compound foreign keys an iterable of [native_field, foreign_field]
                         pairs.
        :return:
        """
        verify(not self._has_been_used,
                "The foreign keys can't be changed after a TicDatFactory has been used.")
        for t in (native_table, foreign_table):
            verify(t in self.all_tables, "%s is not a table name"%t)
        verify(lupish(mappings) and mappings, "mappings needs to be a non empty list or a tuple")
        if lupish(mappings[0]):
            verify(all(len(_) == 2 for _ in mappings),
"""when making a compound foreign key, mappings should contain sublists of format
[native field, foreign field]""")
            _mappings = {k:v for k,v in mappings}
        else :
            verify(len(mappings) == 2,
"""when making a simple foreign key, mappings should be a list of the form [native field, foreign field]""")
            _mappings = {mappings[0]:mappings[1]}
        for k,v in _mappings.items() :
            verify(k in self._allFields(native_table),
                   "%s does not refer to one of %s 's fields"%(k, native_table))
            verify(v in self._allFields(foreign_table),
                   "%s does not refer to one of %s 's fields"%(k, foreign_table))
        verify(set(self.primary_key_fields.get(foreign_table, ())) == set(_mappings.values()),
            """%s is not the primary key for %s.
This exception is being thrown because ticDat doesn't currently support many-to-many
foreign key relationships. The ticDat API is forward compatible with re: to many-to-many
relationships. When a future version of ticDat is released that supports many-to-many
foreign keys, the code throwing this exception will be removed.
            """%(",".join(_mappings.values()), foreign_table))
        reverseMapping = {v:k for k,v in _mappings.items()}
        self._foreign_keys[native_table, foreign_table].add(tuple(reverseMapping[pkf]
                            for pkf in self.primary_key_fields[foreign_table]))
    def _trigger_has_been_used(self):
        if self._has_been_used :
            return # idempotent
        def findderivedforeignkey() :
            curFKs = self._foreign_keys_by_native()
            for (nativetable, bridgetable), nativefieldstuples in self._foreign_keys.items():
                for nativefieldtuple in nativefieldstuples :
                    for bfk in curFKs.get(bridgetable,()):
                        nativefields = bfk.nativefields()
                        if set(nativefields)\
                                .issubset(self.primary_key_fields[bridgetable]):
                            bridgetonative = {pkf:nf for pkf,nf in
                                    zip(self.primary_key_fields[bridgetable], nativefieldtuple)}
                            foreigntobridge = bfk.foreigntonativemapping()
                            newnativeft = tuple(bridgetonative[foreigntobridge[pkf]] for pkf in
                                            self.primary_key_fields[bfk.foreign_table])
                            fkSet = self._foreign_keys[nativetable, bfk.foreign_table]
                            if newnativeft not in fkSet :
                                return fkSet.add(newnativeft) or True
        while findderivedforeignkey():
            pass
        for (nativetable, foreigntable), nativeFieldsTuples in self._foreign_keys.items():
            nativeFieldsSet = frozenset(frozenset(_) for _ in nativeFieldsTuples)
            if len(nativeFieldsSet)==1:
                self._linkName[nativetable, foreigntable, next(_ for _ in nativeFieldsSet)] = \
                    nativetable
            else :
                for nativeFields in nativeFieldsSet :
                    trialLinkName = nativeFields
                    for _ in nativeFieldsSet.difference({nativeFields}) :
                        trialLinkName = trialLinkName.difference(_)
                    self._linkName[nativetable, foreigntable, nativeFields] = \
                        "_".join([nativetable] + [x for x in trialLinkName or nativeFields])
        self._has_been_used[:] = [True]
    def as_dict(self, ticdat):
        '''
        Returns the ticdat object as a dictionary.
        Note that, as a nested class, TicDat  objects cannot be pickled
        directly. Instead, the dictionary returned by this function can be pickled.
        For unpickling, first unpickle the pickled dictionary, and then pass it,
        unpacked, to the TicDat constructor.
        :param ticdat: a TicDat object whose data is to be returned as a dict
        :return: A dictionary that can either be pickled, or unpacked to a
                TicDat constructor
        '''
        verify(not self.generator_tables, "as_dict doesn't work with generator tables.")
        rtn = {}
        dict_tables = {t for t,pk in self.primary_key_fields.items() if pk}
        for t in dict_tables:
            rtn[t] = {pk : {k:v for k,v in row.items()} for pk,row in getattr(ticdat,t).items()}
        for t in set(self.all_tables).difference(dict_tables):
            rtn[t] = [{k:v for k,v in row.items()} for row in getattr(ticdat, t)]
        return rtn
    def __init__(self, **init_fields):
        """
        create a TicDatFactory
        :param init_fields: a mapping of tables to primary key fields
                            and data fields. Each field listing consists
                            of two sub lists ... first primary keys fields,
                            than data fields.
        ex: TicDatFactory (categories =  [["name"],["minNutrition", "maxNutrition"]],
                           foods  =  [["name"],["cost"]]
                           nutritionQuantities = [["food", "category"],["qty"]])
        :return: a TicDatFactory
        """
        self._has_been_used = [] # append to this to make it truthy
        self._linkName = {}
        verify(not any(x.startswith("_") for x in init_fields),
               "table names shouldn't start with underscore")
        for k,v in init_fields.items():
            verify(containerish(v) and len(v) == 2 and all(containerish(_) for _ in v),
                   ("Table %s needs to specify two sublists, " +
                    "one for primary key fields and one for data fields")%k)
            verify(all(utils.stringish(s) for _ in v for s in _),
                   "The field names for %s need to be strings"%k)
            verify(v[0] or v[1], "No field names specified for table %s"%k)
            verify(not set(v[0]).intersection(v[1]),
                   "The same field name is both a data field and primary key field for table %s"%k)
        self._primary_key_fields = FrozenDict({k : tuple(v[0])for k,v in init_fields.items()})
        self._data_fields = FrozenDict({k : tuple(v[1]) for k,v in init_fields.items()})
        self._default_values = clt.defaultdict(dict)
        self._data_types = clt.defaultdict(dict)
        self._generator_tables = []
        self._foreign_keys = clt.defaultdict(set)
        self.all_tables = frozenset(init_fields)
        self._foreign_key_links_enabled = [] # using list for truthiness to work around freezing headaches

        datarowfactory = lambda t :  utils.td_row_factory(t, self.primary_key_fields.get(t, ()),
                        self.data_fields.get(t, ()), self.default_values.get(t, {}))

        goodticdattable = self.good_tic_dat_table
        superself = self
        def ticdattablefactory(alldatadicts, tablename, primarykey = (), rowfactory_ = None) :
            assert containerish(primarykey)
            primarykey = primarykey or  self.primary_key_fields.get(tablename, ())
            keylen = len(primarykey)
            rowfactory = rowfactory_ or datarowfactory(tablename)
            if keylen > 0 :
                class TicDatDict (FreezeableDict) :
                    def __init__(self, *_args, **_kwargs):
                        super(TicDatDict, self).__init__(*_args, **_kwargs)
                        alldatadicts.append(self)
                    def __setitem__(self, key, value):
                        verify(containerish(key) ==  (keylen > 1) and
                               (keylen == 1 or keylen == len(key)),
                               "inconsistent key length for %s"%tablename)
                        return super(TicDatDict, self).__setitem__(key, rowfactory(value))
                    def __getitem__(self, item):
                        if (item not in self) and (not getattr(self, "_dataFrozen", False)):
                            self[item] = rowfactory({})
                        return super(TicDatDict, self).__getitem__(item)
                assert dictish(TicDatDict)
                return TicDatDict
            class TicDatDataList(clt.MutableSequence):
                def __init__(self, *_args):
                    self._list = list()
                    self.extend(list(_args))
                def __len__(self): return len(self._list)
                def __getitem__(self, i): return self._list[i]
                def __delitem__(self, i): del self._list[i]
                def __setitem__(self, i, v):
                    self._list[i] = rowfactory(v)
                def insert(self, i, v):
                    self._list.insert(i, rowfactory(v))
                def __repr__(self):
                    return "td:" + self._list.__repr__()
            assert containerish(TicDatDataList) and not dictish(TicDatDataList)
            return TicDatDataList
        def generatorfactory(data, tablename) :
            assert tablename in self.generator_tables
            drf = datarowfactory(tablename)
            def generatorFunction() :
                for row in (data if containerish(data) else data()):
                    yield drf(row)
            return generatorFunction
        class _TicDat(utils.freezable_factory(object, "_isFrozen")) :
            def _freeze(self):
                if getattr(self, "_isFrozen", False) :
                    return
                for t in superself.all_tables :
                    _t = getattr(self, t)
                    if utils.dictish(_t) or utils.containerish(_t) :
                        for v in getattr(_t, "values", lambda : _t)() :
                            if not getattr(v, "_dataFrozen", False) :
                                v._dataFrozen =True
                                v._attributesFrozen = True
                            else : # we freeze the data-less ones off the bat as empties
                                assert (len(v) == 0) and v._attributesFrozen
                        if utils.dictish(_t) :
                            _t._dataFrozen  = True
                            _t._attributesFrozen = True
                        elif utils.containerish(_t) :
                            setattr(self, t, tuple(_t))
                    else :
                        assert callable(_t) and t in superself.generator_tables
                for _t in getattr(self, "_allDataDicts", ()) :
                    if utils.dictish(_t) and not getattr(_t, "_attributesFrozen", False) :
                        _t._dataFrozen  = True
                        _t._attributesFrozen = True
                self._isFrozen = True
            def __repr__(self):
                return "td:" + tuple(superself.all_tables).__repr__()
        class TicDat(_TicDat) :
            def _generatorfactory(self, data, tableName):
                return generatorfactory(data, tableName)
            def __init__(self, **init_tables):
                superself._trigger_has_been_used()
                self._all_data_dicts = []
                self._made_foreign_links = False
                for t in init_tables :
                    verify(t in superself.all_tables, "Unexpected table name %s"%t)
                for t,v in init_tables.items():
                    badticdattable = []
                    if not (goodticdattable(v, t, lambda x : badticdattable.append(x))) :
                        raise utils.TicDatError(t + " cannot be treated as a ticDat table : " +
                                                badticdattable[-1])
                    if superself.primary_key_fields.get(t) :
                     for _k in v :
                        verify((hasattr(_k, "__len__") and
                                (len(_k) == len(superself.primary_key_fields.get(t, ())) > 1)
                                or len(superself.primary_key_fields.get(t, ())) == 1),
                           "Unexpected number of primary key fields for %s"%t)
                     drf = datarowfactory(t) # lots of verification inside the datarowfactory
                     setattr(self, t, ticdattablefactory(self._all_data_dicts, t)(
                                    {_k : drf(v[_k] if utils.dictish(v) else ()) for _k in v}))
                    elif t in superself.generator_tables :
                        setattr(self, t, generatorfactory(v, t))
                    else :
                        setattr(self, t, ticdattablefactory(self._all_data_dicts, t)(*v))
                for t in set(superself.all_tables).difference(init_tables) :
                    if t in superself.generator_tables :
                        # a calleable that returns an empty generator
                        setattr(self, t, generatorfactory((), t))
                    else :
                        setattr(self, t, ticdattablefactory(self._all_data_dicts, t)())
                if init_tables :
                    self._try_make_foreign_links()
            def _try_make_foreign_links(self):
                if not superself._foreign_key_links_enabled:
                    return
                assert not self._made_foreign_links, "call once"
                self._made_foreign_links = True
                can_link_w_me = lambda t : t not in superself.generator_tables and \
                                           superself.primary_key_fields.get(t)
                for fk in superself.foreign_keys :
                    t = fk.native_table
                    if can_link_w_me(t):
                      if can_link_w_me(fk.foreign_table)  :
                        nativefields = fk.nativefields()
                        linkname = superself._linkName[t, fk.foreign_table, frozenset(nativefields)]
                        if linkname not in ("keys", "items", "values") :
                            ft = getattr(self, fk.foreign_table)
                            foreign_pk = superself.primary_key_fields[fk.foreign_table]
                            local_pk = superself.primary_key_fields[t]
                            assert all(pk for pk in (foreign_pk, local_pk))
                            reversemapping  = fk.foreigntonativemapping()
                            if len(nativefields) == 1:
                                assert set(foreign_pk) =={fk.mapping.foreign_field}
                            else:
                                assert set(foreign_pk) == {_.foreign_field for _ in fk.mapping}
                            appendage_fk = fk.cardinality == "one-to-one"
                            tablefields = superself.primary_key_fields.get(t, ()) + \
                                          superself.data_fields.get(t, ())
                            local_posn = {x:tablefields.index(reversemapping[x])
                                             for x in foreign_pk}
                            unused_local_posn = {i for i,_ in enumerate(tablefields) if i not in
                                                    local_posn.values()}
                            if not appendage_fk :
                                new_pk = tuple(x for x in local_pk if x not in nativefields)
                                new_data_dct = ticdattablefactory(self._all_data_dicts, linkname,
                                                new_pk, lambda x : x)
                                for row in ft.values() :
                                    setattr(row, linkname, new_data_dct())
                            for key,row in getattr(self, t).items() :
                                keyrow = ((key,) if not containerish(key) else key) + \
                                         tuple(row[x] for x in superself.data_fields[t])
                                lookup = tuple(keyrow[local_posn[x]] for x in foreign_pk)
                                linkrow = ft.get(lookup[0] if len(lookup) ==1 else lookup, None)
                                if linkrow is not None :
                                    if appendage_fk :
                                        # the attribute is simply a reference to the mapping table
                                        assert not hasattr(linkrow, linkname)
                                        setattr(linkrow, linkname,row)
                                    else :
                                        _key = keyrow[:-len(row)] if row else keyrow
                                        _key = tuple(x for i,x in enumerate(_key)
                                                     if i in unused_local_posn)
                                        getattr(linkrow, linkname)\
                                            [_key[0] if len(_key) == 1 else _key] = row

        self.TicDat = TicDat
        if xls.import_worked :
            self.xls = xls.XlsTicFactory(self)
        if csv.import_worked :
            self.csv = csv.CsvTicFactory(self)
        if sql.import_worked :
            self.sql = sql.SQLiteTicFactory(self)
        if mdb.import_worked:
            self.mdb = mdb.MdbTicFactory(self)
        self._isFrozen=True

    def _allFields(self, table):
        assert table in self.all_tables
        return set(self.primary_key_fields.get(table, ())).union(self.data_fields.get(table, ()))

    def good_tic_dat_object(self, data_obj, bad_message_handler = lambda x : None):
        """
        determines if an object can be can be converted to a TicDat data object.
        :param data_obj: the object to verify
        :param bad_message_handler: a call back function to receive description of any failure message
        :return: True if the dataObj can be converted to a TicDat data object. False otherwise.
        """
        rtn = True
        for t in self.all_tables:
            if not hasattr(data_obj, t) :
                bad_message_handler(t + " not an attribute.")
                return False
            rtn = rtn and  self.good_tic_dat_table(getattr(data_obj, t), t,
                    lambda x : bad_message_handler(t + " : " + x))
        return rtn

    def good_tic_dat_table(self, data_table, table_name, bad_message_handler = lambda x : None) :
        """
        determines if an object can be can be converted to a TicDat data table.
        :param dataObj: the object to verify
        :param table_name: the name of the table
        :param bad_message_handler: a call back function to receive
               description of any failure message
        :return: True if the dataObj can be converted to a TicDat
                 data table. False otherwise.
        """
        if table_name not in self.all_tables:
            bad_message_handler("%s is not a valid table name for this schema"%table_name)
            return False
        if table_name in self.generator_tables :
            assert not self.primary_key_fields.get(table_name), "this should be verified in __init__"
            verify((containerish(data_table) or callable(data_table)) and not dictish(data_table),
                   "Expecting a container of rows or a generator function of rows for %s"%table_name)
            return self._good_data_rows(data_table if containerish(data_table) else data_table(),
                                      table_name, bad_message_handler)
        if self.primary_key_fields.get(table_name) :
            if utils.dictish(data_table) :
                return self._good_ticdat_dict_table(data_table, table_name, bad_message_handler)
            if utils.containerish(data_table):
                return  self._good_ticdat_key_container(data_table, table_name, bad_message_handler)
        else :
            verify(utils.containerish(data_table),
                   "Unexpected ticDat table type for %s."%table_name)
            return self._good_data_rows(data_table, table_name, bad_message_handler)
        bad_message_handler("Unexpected ticDat table type for %s."%table_name)
        return False
    def _good_ticdat_key_container(self, ticdat_table, tablename,
                                  bad_msg_handler = lambda x : None) :
        assert containerish(ticdat_table) and not dictish(ticdat_table)
        if self.data_fields.get(tablename) :
            bad_msg_handler("%s contains data fields, and thus must be represented by a dict"%
                              tablename)
            return False
        if not len(ticdat_table) :
            return True
        if not all(_keylen(k) == len(self.primary_key_fields[tablename])  for k in ticdat_table):
            bad_msg_handler("Inconsistent key lengths")
            return False
        return True
    def _good_ticdat_dict_table(self, ticdat_table, table_name, bad_msg_handler = lambda x : None):
        assert dictish(ticdat_table)
        if not len(ticdat_table) :
            return True
        if not all(_keylen(k) == len(self.primary_key_fields[table_name])
                   for k in ticdat_table.keys()) :
            bad_msg_handler("Inconsistent key lengths")
            return False
        return self._good_data_rows(ticdat_table.values(), table_name, bad_msg_handler)
    def _good_data_rows(self, data_rows, table_name, bad_message_handler = lambda x : None):
        dictishrows = tuple(x for x in data_rows if utils.dictish(x))
        if not all(set(x.keys()).issubset(self.data_fields.get(table_name,())) for x in dictishrows):
            bad_message_handler("Inconsistent data field name keys.")
            return False
        containerishrows = tuple(x for x in data_rows
                                 if utils.containerish(x) and not  utils.dictish(x))
        if not all(len(x) == len(self.data_fields.get(table_name,())) for x in containerishrows) :
            bad_message_handler("Inconsistent data row lengths.")
            return False
        singletonishrows = tuple(x for x in data_rows if not
                                 (utils.containerish(x) or utils.dictish(x)))
        if singletonishrows and (len(self.data_fields.get(table_name,())) != 1)  :
            bad_message_handler(
                "Non-container data rows supported only for single-data-field tables")
            return False
        return True
    def _keyless(self, obj):
        assert self.good_tic_dat_object(obj)
        class _ (object) :
            pass
        rtn = _()
        for t in self.all_tables :
            _rtn = []
            _t = getattr(obj, t)
            if dictish(_t) :
                for pk, dr in _t.items() :
                    _rtn.append(dict(dr, **{_f: _pk for _f,_pk in zip(self.primary_key_fields[t], pk
                                                                if containerish(pk) else (pk,))}))
            else :
                for dr in (_t if containerish(_t) else _t()) :
                    _rtn.append(dict(dr))
            setattr(rtn, t, _rtn)
        return rtn
    def _same_data(self, obj1, obj2):
        assert self.good_tic_dat_object(obj1) and self.good_tic_dat_object(obj2)
        def samerow(r1, r2) :
            if dictish(r1) and dictish(r2):
                if bool(r1) != bool(r2) or set(r1) != set(r2) :
                    return False
                for _k in r1:
                    if r1[_k] != r2[_k] :
                        return False
                return True
            if dictish(r2) and not dictish(r1) :
                return samerow(r2, r1)
            def containerize(_r) :
                if utils.containerish(_r) :
                    return list(_r)
                return [_r,]
            if dictish(r1) :
                return list(r1.values()) == containerize(r2)
            return containerize(r1) == containerize(r2)
        for t in self.all_tables :
            t1 = getattr(obj1, t)
            t2 = getattr(obj2, t)
            if dictish(t1) != dictish(t2) :
                return False
            if dictish(t1) :
                if set(t1) != set(t2) :
                    return False
                for k in t1 :
                    if not samerow(t1[k], t2[k]) :
                        return False
            else :
                _iter = lambda x : x if containerish(x) else x()
                if not len(list(_iter(t1))) == len(list(_iter(t2))) :
                    return False
                for r1 in _iter(t1):
                    if not any (samerow(r1, r2) for r2 in _iter(t2)) :
                        return False
        return True
    def copy_tic_dat(self, tic_dat, freeze_it = False):
        """
        copies the tic_dat object into a new tic_dat object
        performs a deep copy
        :param tic_dat: a ticdat object
        :param freeze_it: boolean. should the returned object be frozen?
        :return: a deep copy of the tic_dat argument
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))
        rtn = self.TicDat(**{t:getattr(tic_dat, t) for t in self.all_tables})
        return self.freeze_me(rtn) if freeze_it else rtn
    def freeze_me(self, tic_dat):
        """
        Freezes a ticdat object
        :param tic_dat: ticdat object
        :return: tic_dat, after it has been frozen
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))
        return freeze_me(tic_dat)
    def find_foreign_key_failures(self, tic_dat):
        """
        Finds the foreign key failures for a ticdat object
        :param tic_dat: ticdat object
        :return: A dictionary constructed as follow:
                 The keys are namedTuples with members "native_table", "foreign_table", "mapping"
                 The key data matches the arguments to add_foreign_key that constructed the foreign key.
                 The values are namedTuples with the following members.
                 --> native_values - the values of the native fields that failed to match
                 --> native_pks - the primary key entries of the native table rows
                                  corresponding to the native_values.
                 That is to say, native_values tells you which values in the native table
                 can't find a foreign key match, and thus generate a foreign key failure.
                 native_pks tells you which native table rows will be removed if you call
                 remove_foreign_keys_failures().
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))
        rtn_values, rtn_pks = clt.defaultdict(set), clt.defaultdict(set)
        for native, fks in self._foreign_keys_by_native().items():
            def getcell(native_pk, native_data_row, field_name):
                 assert field_name in self.primary_key_fields.get(native, ()) + \
                                      self.data_fields.get(native, ())
                 if [field_name] == list(self.primary_key_fields.get(native, ())):
                     return native_pk
                 if field_name in native_data_row:
                     return native_data_row[field_name]
                 return native_pk[self.primary_key_fields[native].index(field_name)]
            for fk in fks:
                foreign_to_native = fk.foreigntonativemapping()
                for native_pk, native_data_row in (getattr(tic_dat, native).items()
                            if dictish(getattr(tic_dat, native))
                            else enumerate(getattr(tic_dat, native))):
                    foreign_pk = tuple(getcell(native_pk, native_data_row, foreign_to_native[_fpk])
                                       for _fpk in self.primary_key_fields[fk.foreign_table])
                    foreign_pk = foreign_pk[0] if len(foreign_pk) == 1 else foreign_pk
                    if foreign_pk not in getattr(tic_dat, fk.foreign_table):
                        rtn_pks[fk].add(native_pk)
                        if type(fk.mapping) is _ForeignKeyMapping :
                            rtn_values[fk].add(getcell(native_pk, native_data_row,
                                                       fk.mapping.native_field))
                        else:
                            rtn_values[fk].add(tuple(getcell(native_pk,
                                    native_data_row, _.native_field) for _ in fk.mapping))
        assert set(rtn_pks) == set(rtn_values)
        RtnType = namedtuple("ForeignKeyFailures", ("native_values", "native_pks"))

        return {k:RtnType(tuple(rtn_values[k]), tuple(rtn_pks[k])) for k in rtn_pks}

    def remove_foreign_keys_failures(self, tic_dat, propagate=True):
        """
        Removes foreign key failures (i.e. child records with no parent table record)
        :param tic_dat: ticdat object
        :param propagate boolean: remove cascading failures? (if removing the child record
                                  results in new failures, should those be removed as well?)
        :return: tic_dat, with the foreign key failures removed
        """
        fk_failures = self.find_foreign_key_failures(tic_dat)
        for fk, (_, failed_pks) in fk_failures.items():
            for failed_pk in failed_pks:
                if failed_pk in getattr(tic_dat, fk.native_table) :
                    del(getattr(tic_dat, fk.native_table)[failed_pk])
        if fk_failures and propagate:
            return self.remove_foreign_keys_failures(tic_dat)
        return tic_dat

    def find_data_type_failures(self, tic_dat):
        """
        Finds the data type failures for a ticdat object
        :param tic_dat: ticdat object
        :return: A dictionary constructed as follow:

                 The keys are namedTuples with members "table", "field". Each (table,field) pair
                 has data values that are inconsistent with its data type. (table, field) pairs
                 with no data type at all are never part of the returned dictionary.

                 The values of the returned dictionary are namedTuples with the following attributes.
                 --> bad_values - the distinct values for the (table, field) pair that are inconsistent
                                  with the data type for (table, field).
                 --> pks - the distinct primary key entries of the table containing the bad_values
                                  data
                 That is to say, bad_values tells you which values in field are failing the data type check,
                 and  tells you which table rows will have their field entry changed if you call
                 replace_data_type_failures().
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))


        rtn_values, rtn_pks = clt.defaultdict(set), clt.defaultdict(set)
        for table, type_row in self._data_types.items():
            for pk, data_row in getattr(tic_dat, table).items():
                for field, data_type in type_row.items():
                    if not data_type.valid_data(data_row[field]) :
                        rtn_values[(table, field)].add(data_row[field])
                        rtn_pks[(table, field)].add(pk)
        assert set(rtn_values) == set(rtn_pks)
        TableField = clt.namedtuple("TableField", ["table", "field"])
        ValuesPks = clt.namedtuple("ValuesPks", ["bad_values", "pks"])
        return {TableField(*tf):ValuesPks(tuple(rtn_values[tf]), tuple(rtn_pks[tf])) for tf in rtn_values}

    def replace_data_type_failures(self, tic_dat, replacement_values = FrozenDict()):
        """
        :param tic_dat:
        :param replacement_values: a dictionary mapping (table, field) to replacement value.
               the default value will be used for (table, field) pairs not in replacement_values
        :return: the tic_dat object with replacements made. The tic_dat object itself will be edited in place.
        Replaces any of the data failures found in find_data_type_failures() with the appropriate
        replacement_value.
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))
        verify(dictish(replacement_values) and all(len(k)==2 for k in replacement_values),
               "replacement_values should be a dictionary mapping (table, field) to valid replacement value")
        for (table,field), v in replacement_values.items():
            verify(table in self.all_tables, "%s is not a table for this schema"%table)
            verify(field in self.data_fields.get(table, ()), "%s is not a data field for %s"%(field, table))

        replacements_needed = self.find_data_type_failures(tic_dat)
        if not replacements_needed:
            return tic_dat

        real_replacements = {}
        for table, type_row in self._data_types.items():
            for field in type_row:
                real_replacements[table, field] = replacement_values.get((table, field),
                        self._default_values.get(table, {}).get(field, 0))
        for (table, field), value in real_replacements.items():
            verify(self._data_types[table][field].valid_data(value),
                   "The replacement value %s is not itself valid for %s : %s"%(value, table, field))

        for (table, field), (_, pks) in replacements_needed.items() :
            for pk in pks:
                getattr(tic_dat, table)[pk][field] = real_replacements[table, field]

        assert not self.find_data_type_failures(tic_dat)
        return tic_dat

    def obfusimplify(self, tic_dat, table_prepends = utils.FrozenDict(), skip_tables = (),
                     freeze_it = False) :
        """
        copies the tic_dat object into a new, obfuscated, simplified tic_dat object
        :param tic_dat: a ticdat object
        :param table_prepends: a dictionary with mapping each table to the prepend it should apply
                               when its entries are renamed.  A valid table prepend must be all caps and
                               not end with I. Should be restricted to entity tables (single field primary
                               that is not a foreign key child)
        :param skip_tables: a listing of entity tables whose single field primary key shouldn't be renamed
        :param freeze_it: boolean. should the returned copy be frozen?
        :return: A named tuple with the following components.
                 copy : a deep copy of the tic_dat argument, with the single field primary key values
                        renamed to simple "short capital letters followed by numbers" strings.
                 renamings : a dictionary matching the new entries to their original (table, primary key value)
                             this entry can be used to cross reference any diagnostic information gleaned from the
                             obfusimplified copy to the original names. For example, "P5 has no production"
                             can easily be recognized as "Product KX12212 has no production".
        """
        msg  = []
        verify(self.good_tic_dat_object(tic_dat, msg.append),
               "tic_dat not a good object for this factory : %s"%"\n".join(msg))
        verify(not self.find_foreign_key_failures(tic_dat),
               "Cannot obfusimplify an object with foreign key failures")
        verify(not self.generator_tables, "Cannot obfusimplify a tic_dat that uses generators")
        verify(not set(table_prepends).intersection(skip_tables),
               "Can't specify a table prepend for an entity that you're skipping")
        verify(self._has_been_used,
               "The cascading foreign keys won't necessarily be present until the factory is used")

        entity_tables = {t for t,v in self.primary_key_fields.items() if len(v) == 1}
        foreign_keys_by_native = self._foreign_keys_by_native()
        # if a native table is one-to-one with a foreign table, it isn't an entity table
        for nt in entity_tables.intersection(foreign_keys_by_native):
            if any(ft.cardinality == "one-to-one" for ft in foreign_keys_by_native[nt]):
                entity_tables.discard(nt)

        verify(entity_tables.issuperset(skip_tables), "should only specify entity tables to skip")
        entity_tables = entity_tables.difference(skip_tables)

        for k,v in table_prepends.items():
            verify(k in self.all_tables, "%s is not a table name")
            verify(len(self.primary_key_fields.get(k, ())) ==1, "%s does not have a single primary key field"%k)
            verify(k in entity_tables, "%s is not an entity table due to child foreign key relationship"%k)
            verify(utils.stringish(v) and  set(v).issubset(uppercase) and not v.endswith("I"),
                   "Your table_prepend string %s is not an all uppercase string ending in a letter other than I")
        verify(len(set(table_prepends.values())) == len(table_prepends.values()),
               "You provided duplicate table prepends")
        table_prepends = dict(table_prepends)
        for t in entity_tables.difference(table_prepends):
            def getname():
                chars = tuple(_ for _ in uppercase if _ != "I")
                from_table = "".join(_ for _ in t.upper() if _ in chars)
                rtnnum = 1
                while True:
                    if rtnnum <= len(from_table):
                        yield from_table[:rtnnum]
                    else :
                        yield from_table + "".join(chars[_] for _ in
                                  utils.baseConverter(rtnnum-len(from_table)-1, len(chars)))
                    rtnnum += 1
            namegetter = getname()
            name = namegetter.next()
            while name in table_prepends.values():
                name = namegetter.next()
            table_prepends[t]=name
        assert set(entity_tables) == set(table_prepends)

        reverse_renamings = {}
        for t in table_prepends :
            for i,k in enumerate(sorted(getattr(tic_dat, t))) :
                reverse_renamings[t, k] = "%s%s"%(table_prepends[t],i+1)
        foreign_keys = {}
        for fk in self.foreign_keys:
            nt = fk.native_table
            if fk.foreign_table in table_prepends:
                foreign_keys = dict(foreign_keys, **{(nt,nf) : fk.foreign_table
                                    for nf, ff in fk.nativetoforeignmapping().items()})
        # remember -- we've used this factory so any cascading foreign keys are present
        rtn_dict  = clt.defaultdict(dict)
        for t in self.all_tables:
            read_table = getattr(tic_dat, t)
            def fix_all_row(all_row):
                return {k: reverse_renamings[foreign_keys[t, k], v] if (t,k) in foreign_keys else v
                           for k,v in all_row.items()}
            if dictish(read_table):
                for pk, data_row in read_table.items():
                    if len(self.primary_key_fields.get(t, ())) == 1:
                        pkf = self.primary_key_fields[t][0]
                        if (t,pkf) in foreign_keys:
                            new_pk = reverse_renamings[foreign_keys[t,pkf], pk]
                        else:
                            new_pk = reverse_renamings.get((t, pk), pk)
                        rtn_dict[t][new_pk] = fix_all_row(data_row)
                    else :
                        assert containerish(pk) and len(pk) == len(self.primary_key_fields[t])
                        new_row = fix_all_row(dict(data_row, **{pkf: pkv for pkf, pkv in
                                                    zip(self.primary_key_fields[t], pk)}))
                        new_pk = tuple(new_row[_] for _ in self.primary_key_fields[t])
                        rtn_dict[t][new_pk] = {k:new_row[k] for k in data_row}
            else :
                rtn_dict[t] = []
                for data_row in read_table:
                    rtn_dict[t].append(fix_all_row(data_row))

        RtnType = namedtuple("ObfusimplifyResults", "copy renamings")

        rtn = RtnType(self.freeze_me(self.TicDat(**rtn_dict)) if freeze_it else self.TicDat(**rtn_dict),
                      {v:k for k,v in reverse_renamings.items()})
        assert not self.find_foreign_key_failures(rtn.copy)
        assert len(rtn.renamings) == len(reverse_renamings)
        return rtn

def freeze_me(x) :
    """
    Freezes a ticdat object
    :param x: ticdat object
    :return: x, after it has been frozen
    """
    verify(hasattr(x, "_freeze"), "x not a freezeable object")
    if not getattr(x, "_isFrozen", False) : #idempotent
        x._freeze()
    assert x._isFrozen
    return x