# -*- coding: utf-8 -*-
import sys, csv, os, xlrd, zipfile, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import load_only
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, Unicode, Boolean, DateTime, PickleType


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

    qty = Column(PickleType, default=None) # to hold PyDict of qties
    extra_qty = Column(Integer, default=0)
    # case extra_qty of
    # >= 0: ebay_qty = qty+extra_qty
    # <0:   ebay_qty = 0

    notes = Column(Unicode, default=u'')
    changed = Column(Boolean, default=False)
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
                       'm9a':'small and highly unreliable'}
    q = 0
    if extra_q >= 0:
        for m in qties:
            if m in excluded_stores: continue
            q += qties[m]-1
        q += extra_q
    return q


def fx_fname(action_name, session):
    'Build & return Fx filename with a sequence number suffix'

    seq = session.query(Sequence).first()
    if seq: seq.number += 1
    else: seq = Sequence(number=0)      
    session.add(seq)
    session.commit()
    
    return action_name+'_'+str(seq.number).zfill(4)+'.csv'


# Void functions
# --------------

def qty_alignment(session):
    '''Read Fx report "attivo" and on DB
    - overwrite itemid with a value or blank 
    - set changed to True or False
    finally 
    - check if there are ads out of DB
    - check if there are ads with OutOfStockControl=false'''

    folder = os.path.join(DATA_PATH, 'attivo_report')
    fname = fname_in(folder)

    # Reset all itemid and changed fields
    all_arts = session.query(Art)
    for art in all_arts:
        art.itemid = u''
        art.changed = False
        session.add(art)

    with open(fname, 'rb') as f:
        all_rows = csv.reader(f, delimiter=';', quotechar='"')
        all_rows.next()
        for row in all_rows:
            ga_code_from_ebay = row[1][:-3] if len(row[1])>7 else row[1]
            qty_from_ebay = int(row[5])
            itemid_from_ebay = row[0].strip()
            try:
                art = session.query(Art).filter(Art.ga_code == ga_code_from_ebay).first()
                if art:
                    if ebay_qty(art.qty, art.extra_qty) != qty_from_ebay:
                        art.changed =True # set changed if different
                    art.itemid = itemid_from_ebay
                    session.add(art)
                else: # alert for items out of DB
                    print 'Ad with itemID', row[0], 'out of local db'
                        
                if row[22].lower() == 'false':
                    print 'Ad with itemID', row[0], 'has OutOfStockControl=false'
                
            except ValueError:
                print 'rejected line:'
                print row
                print sys.exc_info()[0]
                print sys.exc_info()[1]
                print sys.exc_info()[2]
    os.remove(fname)
    session.commit()


def qty_datasource(fxls):
    'Return a dict of dict of store-qty'

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

def db_cleaner(session):
    'Remove from db 3+ months old row with zero qty'
    session.query(Art).filter(datetime.datetime.utcnow() - art.timestamp >= datetime.timedelta(90),
                                ebay_qty(qty, extra_qty) == 0).delete()




# Loaders from data Sources
# -------------------------
        
def qty_loader(session):
    "Load ('ga_code', 'qty') into DB"

    folder = os.path.join(DATA_PATH, 'quantities')

    fname = get_fname_in(folder)
    with zipfile.ZipFile(fname, 'r') as zipf:
        zipf.extractall(folder)
    os.remove(fname)


    # init with all DB ids
    zero_qty_row_ids = [id_tuple[0] for id_tuple in session.query(Art.id).all()]
    # Missing zero qty rows hack
    #  step by step remove all qty>0 rows id
    #  in the end will remain all zero row ids

    fname = get_fname_in(folder)
    qty_rows = qty_datasource(fname)
    for ga_code in qty_rows:
        try:
            art = session.query(Art).filter(Art.ga_code == ga_code).first()                    
            if art: # exsist, update
                if art.qty != qty_rows[ga_code]: # if qty is to update
                    art.qty = qty_rows[ga_code]
                    art.timestamp = datetime.datetime.utcnow() # touched the row
                    if (art.itemid != u''): # if it is online
                        art.changed=True # set a qty change
                    session.add(art)
                zero_qty_row_ids.remove(art.id) # zero qty hack: qty>0, remove

            else: # not exsist, create
                art = Art()
                art.ga_code = ga_code
                art.qty = qty_rows[ga_code]
                # TIMESTAMP goes by default
                session.add(art)
        except ValueError:
            print 'rejected line:'
            print ga_code
            print sys.exc_info()[0]
            print sys.exc_info()[1]
            print sys.exc_info()[2]
    os.remove(fname)        
    session.commit()

    # for remaining ids set qty=0
    for id in zero_qty_row_ids:
        art_zero_qty = session.query(Art).filter(Art.id == id).first() # surely exsist in DB
        if art_zero_qty.qty != {}: # if it is already 0 do nothing, exit
            art_zero_qty.qty = {} # set to 0
            art_zero_qty.timestamp = datetime.datetime.utcnow() # touched the row
            if (art_zero_qty.itemid != u''): # if online               
                art_zero_qty.changed=True # set a qty change                                
            session.add(art)
    session.commit()
            


# FX csv file creators
# --------------------

def revise_qty(session):
    'Fx revise quantity action'
    smartheaders = (ACTION, 'ItemID', '*Quantity')
    arts = session.query(Art).filter(Art.itemid != u'', Art.changed)
    fout_name = os.path.join(DATA_PATH, fx_fname('revise_qty', session))
    with EbayFx(fout_name, smartheaders) as wrt:
        for art in arts:
            fx_revise_row = {ACTION:'Revise',
                             'ItemID':art.itemid,
                             '*Quantity':ebay_qty(art.qty, art.extra_qty),}
            wrt.writerow(fx_revise_row)
            art.changed = False
            session.add(art)
        session.commit()

           

# Composed actions
# ----------------    
        
def update_qty():
    ses = Session()
    qty_loader(ses)
    revise_qty(ses)
    ses.close()


def allinea():
    ses = Session()
    qty_alignment(ses)
    ses.close()

def dontsell(ga_code, notes=u''):
    'Set extra_qty = -1'
    s = Session()
    item = s.query(Art).filter(Art.ga_code == ga_code).first()
    item.extra_qty = -1
    item.notes = notes
    s.add(item)
    s.commit()
    s.close()
