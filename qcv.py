# -*- coding: utf-8 -*-
import sys, csv, os, xlrd, zipfile, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, Float, Unicode, Boolean, DateTime, PickleType


# DB def with Sqlalchemy
# ----------------------

db_file = os.path.join('db', 'db.sqlite')
engine = create_engine('sqlite:///'+db_file, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Art(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    ga_code = Column(Unicode, unique=True, index=True, nullable=False)
    itemid = Column(Unicode, default=u'') 

    qty = Column(PickleType, default=None) # hold PyDict of quantities
    extra_qty = Column(Integer, default=0)
    # case extra_qty of
    # >= 0: ebay_qty = qty+extra_qty
    # < 0:  not to publish on ebay

    prc = Column(PickleType, default=None) # hold PyDict of prices
    extra_prc = Column(Float, default=0.0)

    notes = Column(Unicode, default=u'')
    qty_changed = Column(Boolean, default=False)
    prc_changed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow) # don't know how behave    

class Sequence(Base):
    __tablename__ = 'sequences'

    id = Column(Integer, primary_key=True)
    number = Column(Integer, default=0)

Base.metadata.create_all(engine)


# A csv.DictWriter specialized with Fx csv
# ----------------------------------------

class EbayFx(csv.DictWriter):
    '''Subclass csv.DictWriter, define delimiter and quotechar and write headers'''
    def __init__(self, filename, fieldnames):
        self.fobj = open(filename, 'wb')
        csv.DictWriter.__init__(self, self.fobj, fieldnames, delimiter=';', quotechar='"')
        self.writeheader()
    def close(self,):
        self.fobj.close()
       
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()


# Constants
# ---------

DATA_PATH = os.path.join('data')
ACTION = '*Action(SiteID=Italy|Country=IT|Currency=EUR|Version=745|CC=UTF-8)' # smartheaders CONST


# Fruitful functions
# ------------------

def price(p, m='1'):
    '''Return float price from string.
        Strip and convert italian format and consider the moltiplicatore m.
        Empty values default to 0 (for price) an 1 (for moltiplicatore).'''
    p = p.strip()
    p = 0.0 if p=='' else float(p.replace('.','').replace(',','.'))
    m = m.strip()
    m = 1.0 if m=='' else float(m)
    return p/m


def get_fname_in(folder):
    'Return the filename inside folder'

    t = os.listdir(folder)
    if len(t) == 0: 
        raise Exception('No file found')
    elif len(t) == 1:
        el = os.path.join(folder, t[0])
        if os.path.isfile(el):
            return el
        else:
            raise Exception('No file found')
    else:
        raise Exception('More files or folders found')



def ebay_qty(qties, extra_q = 0):
    'Compute ebay quantity'
    excluded_stores = {'m93':'closing',
                       'm94':'closing',
                       'm95':'closing',
                       'm97':'closing',
                       'm9a':'small and highly unreliable',
                       'mgt':'small and particular'}
    q = 0
    if extra_q >= 0:
        for m in qties:
            if m in excluded_stores: continue
            q += qties[m]-1 if qties[m]>=1 else 0
        q += extra_q
    return q



def ebay_prc(prcs, extra_p = 0):
    'Compute ebay price'

    p = extra_p
    if (extra_p == 0) & (prcs != None):
        # B line price (all prices >= 0)
        if prcs['b'] == 0: prcs['b'] = max(prcs['c'], prcs['d'], prcs['dr'])
        if prcs['b'] < 30: p = prcs['b']
        elif prcs['b'] < 50: p = prcs['b'] + 2.44
        else: p = prcs['b']
    return p         



def fx_fname(action_name):
    'Build & return Fx filename with a sequence number suffix'

    seq = s.query(Sequence).first()
    if seq: seq.number += 1
    else: seq = Sequence(number=0)      
    s.add(seq)
    s.commit()
    
    return action_name+'_'+str(seq.number).zfill(4)+'.csv'


# Void functions
# --------------

def ebay_link_n_check():
    '''Read Fx report "attivo" and perform on DB
        - overwriting itemid with a value or blank 
        - setting qty_changed to True or False
    finally 
        - check if there are ads out of DB
        - check if there are ads with OutOfStockControl=false'''

    folder = os.path.join(DATA_PATH, 'attivo_report')
    fname = get_fname_in(folder)

    # Reset all itemid and qty_changed fields
    all_arts = s.query(Art)
    for art in all_arts:
        art.itemid = u''
        art.qty_changed = False
        s.add(art)

    for ebay_report_line in ebay_report_datasource(fname):
        try:
            art = s.query(Art).filter(Art.ga_code == ebay_report_line['ga_code']).first()
            if art: # exsits, check values
                if ebay_qty(art.qty, art.extra_qty) != ebay_report_line['qty']: art.qty_changed = True
                if abs(ebay_prc(art.prc, art.extra_prc) - ebay_report_line['prc']) > 0.05: art.prc_changed = True
                art.itemid = ebay_report_line['itemid']
                s.add(art)
            else: # not exsist, items out of DB
                print 'itemid:'+ebay_report_line['itemid'], 'customlabel:'+ebay_report_line['ga_code'], 'out of local DB'
                    
            if ebay_report_line['OutOfStockControl'] == 'false':
                print 'itemid:'+ebay_report_line['itemid'], 'customlabel:'+ebay_report_line['ga_code'], 'has OutOfStockControl=false'
            
        except ValueError:
            print 'rejected line:'
            print ebay_report_line
            print sys.exc_info()[0]
            print sys.exc_info()[1]
            print sys.exc_info()[2]

    os.remove(fname)
    s.commit()

def db_cleaner():
    'Remove from db 3+ months old row with zero qty'
    s.query(Art).filter(datetime.datetime.utcnow() - art.timestamp >= datetime.timedelta(90),
                                ebay_qty(qty, extra_qty) == 0).delete()
    s.commit()



# Datasources
# -----------

def qty_datasource(fxls):
    'Return a dict ga_code --> dict(store-qty)'
    # Note: this can't be a generator, because I need to read all
    # the excel lines before producing the first element. So must
    # be loaded all in system's memory.

    qty = dict() # dict of dicts

    # Load xls file in a dict of dicts
    with xlrd.open_workbook(fxls) as wbk:
        sh = wbk.sheet_by_index(0)
        for r in range(sh.nrows):
            try:
                c = str(int(sh.row_values(r)[4])).zfill(7) # ga_code
                m = 'm'+sh.row_values(r)[11].lower() # i.e. m9a                  
                q = int(sh.row_values(r)[9]) # never find q=0            

                # initialization
                if c not in qty:
                    qty[c] = dict()
   
                # increment
                qty[c][m] = qty[c].get(m,0) + q
               
            except ValueError:
                pass # discard line with no quantity
            except:
                print sys.exc_info()[0]
                print sys.exc_info()[1]

    # stats
    print 'C/V stores stats'
    print '----------------', '\n'

    print 'Num of items in all stores:', len(qty), '\n'

    store_stats = dict()

    for gacode in qty:
        for m in qty[gacode]:
            # init
            if m not in store_stats:
                store_stats[m] = {'itms':0, 'pcs':0}
            # inc    
            store_stats[m]['itms'] = store_stats[m]['itms'] + 1
            store_stats[m]['pcs'] = store_stats[m]['pcs'] + qty[gacode][m]
    
    all_pcs = 0
    for m in store_stats:
        all_pcs += store_stats[m]['pcs']
    
    print 'Num of pieces in all stores:', all_pcs, '\n'
    print '%-5s %-8s%-8s' % ('Store', 'items','pcs')
    print '%-5s %-8s%-8s' % ('-----', '-----', '---')

    for m in store_stats:
        print '%-5s %-8s%-8s' % (m, store_stats[m]['itms'], store_stats[m]['pcs'])

    return qty

def prc_datasource(fcsv):
    '''Return a dict ga_code --> dict(listino-price)'''

    # To Improve: trasform this func in a generator to save system's memory

    prc = dict() # dict of dicts

    # Load csv file in a dict of dict
    with open(fcsv, 'rb') as f:
        dsource_rows = csv.reader(f, delimiter=';', quotechar='"')
        dsource_rows.next()
        for row in dsource_rows:
            try:
                prc[row[0]] = dict() # ga_code
                prc[row[0]]['b'] = price(row[1][14:], row[1][:6])
                prc[row[0]]['c'] = price(row[2][14:], row[2][:6])
                prc[row[0]]['d'] = price(row[3][14:], row[3][:6])
                prc[row[0]]['dr'] = price(row[4][14:], row[4][:6])

            except ValueError:
                print 'rejected line:'
                print row
                print sys.exc_info()[0]
                print sys.exc_info()[1]
                print sys.exc_info()[2]    
    return prc  


def ebay_report_datasource(fcsv):
    'Yield a dict of values from ebay report attivo, ga_code included'

    ebay_report_line = dict()

    with open(fcsv, 'rb') as f:
        dsource_rows = csv.reader(f, delimiter=';', quotechar='"')
        dsource_rows.next()
        for row in dsource_rows:
            try:
                ebay_report_line['ga_code'] = row[1][:-3] if len(row[1])>7 else row[1]
                ebay_report_line['qty'] = int(row[5])
                ebay_report_line['prc'] = float(price(row[8].replace('EUR', '')))
                ebay_report_line['itemid'] = row[0].strip()
                ebay_report_line['OutOfStockControl'] = row[22].lower()

                yield ebay_report_line
                
            except ValueError:
                print 'rejected line:'
                print row
                print sys.exc_info()[0]
                print sys.exc_info()[1]
                print sys.exc_info()[2]




# Loaders from data Sources
# -------------------------
        
def qty_loader():
    "Load ('ga_code', 'qty') into DB"

    folder = os.path.join(DATA_PATH, 'quantities')

    # unzip
    fname = get_fname_in(folder)
    with zipfile.ZipFile(fname, 'r') as zipf:
        zipf.extractall(folder)
    os.remove(fname)

    # get dict of dict from file.xls
    fname = get_fname_in(folder)
    qty = qty_datasource(fname)
    os.remove(fname)

    # add to ds missing zero-qty item
    for i in s.query(Art.ga_code): # for each DB row
        if not qty.has_key(i[0]): # not in ds
            qty[i[0]] = {} # add in ds with qty zero

    for ga_code in qty:
        try:
            art = s.query(Art).filter(Art.ga_code == ga_code).first()                    
            if art: # exsists
                if art.qty != qty[ga_code]: # qty changed
                    if art.itemid != u'': # ad is online
                        if ebay_qty(art.qty) != ebay_qty(qty[ga_code]): # online qty changed
                            art.qty_changed = True # set qty_changed

                    art.qty = qty[ga_code]
                    art.timestamp = datetime.datetime.utcnow() # refresh the row
                    s.add(art)

            else: # not exsists, create
                art = Art()
                art.ga_code = ga_code
                art.qty = qty[ga_code]
                # TIMESTAMP goes by default
                s.add(art)
        except ValueError:
            print 'rejected line:'
            print ga_code
            print sys.exc_info()[0]
            print sys.exc_info()[1]
            print sys.exc_info()[2]

    s.commit()



def price_loader():
    "Load ('ga_code', 'prc') into DB"
    
    folder = os.path.join(DATA_PATH, 'prices')

    fname = get_fname_in(folder)
    #prc_rows = prc_datasource(fname) # get dict of dict from file.csv
    prc_rows = prc_ds_migration(fname)
    for ga_code in prc_rows:
        try:
            art = s.query(Art).filter(Art.ga_code == ga_code).first()
            if art: # exsits, possible update
                if art.prc != prc_rows[ga_code]: # if prc is to update
                    art.prc = prc_rows[ga_code]
                    if (art.itemid != u''): # if it is online
                        art.prc_changed=True # set  prc_changed
                    s.add(art)
            
            else: # not exsists, create
                art = Art()
                art.ga_code = ga_code
                art.prc = prc_rows[ga_code]
                s.add(art)
        except ValueError:
            print 'rejected line:'
            print ga_code
            print sys.exc_info()[0]
            print sys.exc_info()[1]
            print sys.exc_info()[2]
    os.remove(fname)
    s.commit()
            


# FX csv file creators
# --------------------

def revise_qty():
    'Fx revise quantity action'
    smartheaders = (ACTION, 'ItemID', '*Quantity')
    arts = s.query(Art).filter(Art.itemid != u'', Art.qty_changed)
    fout_name = os.path.join(DATA_PATH, fx_fname('revise_qty'))
    with EbayFx(fout_name, smartheaders) as wrt:
        for art in arts:
            fx_revise_row = {ACTION: 'Revise',
                             'ItemID': art.itemid,
                             '*Quantity': ebay_qty(art.qty, art.extra_qty),}
            wrt.writerow(fx_revise_row)
            art.qty_changed = False
            s.add(art)
        s.commit()


def revise_prc():
    'Fx revise price'
    smartheaders=(ACTION, 'ItemID', '*StartPrice')
    arts = s.query(Art).filter(Art.itemid != u'', Art.prc_changed)
    fout_name = os.path.join(DATA_PATH, fx_fname('revise_prc'))
    with EbayFx(fout_name, smartheaders) as wrt:
        for art in arts:
            fx_revise_row = {ACTION: 'Revise',
                             'ItemID': art.itemid,
                             '*StartPrice': ebay_prc(art.prc, art.extra_prc),}
            wrt.writerow(fx_revise_row)
            art.prc_changed = False
            s.add(art)
        s.commit()

           

# Composed actions
# ----------------    
        
def update_qty():
    global s 
    s = Session()
    qty_loader()
    revise_qty()
    s.close()


def allinea():
    ses = Session()
    ebay_link_n_check(ses)
    ses.close()

def dontsell(ga_code, notes=u''):
    'Set extra_qty = -1'
    item = s.query(Art).filter(Art.ga_code == ga_code).first()
    item.extra_qty = -1
    item.notes = notes
    s.add(item)
    s.commit()


# Migration tools

def oldDB_prc_datasource(fcsv):
    'Prices exported from old db datasource'  

    prc = dict() # dict of dicts

    # Load csv file in a dict of dict
    with open(fcsv, 'rb') as f:
        dsource_rows = csv.reader(f, delimiter=',', quotechar='"')
        for row in dsource_rows:
            try:
                prc[row[0]] = dict() # ga_code
                prc[row[0]]['b'] = float(row[1]) # b_price
                prc[row[0]]['c'] = float(row[2]) # c_price
                prc[row[0]]['d'] = float(row[3]) # d_price
                prc[row[0]]['dr'] = float(row[4]) # dr_price

            except ValueError:
                print 'rejected line:'
                print row
                print sys.exc_info()[0]
                print sys.exc_info()[1]
                print sys.exc_info()[2]    
    return prc  


def db_clean():
    'Delete exceding rows from old db'
    # While importing prices from the old db, also obsolete rows
    # are added, they have qty == None.
    s.query(Art).filter(Art.qty == None).delete()
    s.commit()

# Utils

def mark():
    'Set extra_qty = -1 for low price rows'

    all_itms = s.query(Art)
    for itm in all_itms:
        if itm.prc['b'] < 20:
            itm.extra_qty = -1
            s.add(itm)
    s.commit() 

def price_for(ga_code):
    'Show the prices'

    art = s.query(Art).filter(Art.ga_code == ga_code).first()
    if art:
        print str(art.prc), art.extra_prc, ebay_prc(art.prc, art.extra_prc)
    else: print 'art not exsists'

def read_qty_prc_for(itemid):
    'Show qty and price for given itemid'

    art = s.query(Art).filter(Art.itemid == itemid).first()
    if art:
        print str(art.qty), art.extra_qty, str(art.prc), art.extra_prc
    else: print 'art not exsists'
