#!/usr/bin/env python3
from datetime import date, timedelta

def decode(q): return q&3,(q>>2)&3,(q>>4)&3,(q>>6)&3
def strict(q):
    m,d,e,l=decode(q); return m==0 and d==0 and l==0
def relaxed(q):
    m,d,e,l=decode(q); return m<=1 and l<=1
def overlap(a,b,c,d): return max(0,(min(b,d)-max(a,c)).days)
def clear_sky_days_from_byte(q): return sum((q>>i)&1 for i in range(8))
def recover_qc(lst_valid,qc_native_valid,qc_value):
    return (0 if not qc_native_valid else qc_value) if lst_valid else None

assert decode(0)==(0,0,0,0) and strict(0) and relaxed(0)
assert decode(1)==(1,0,0,0) and not strict(1) and relaxed(1)
assert decode(17)==(1,0,1,0) and not strict(17) and relaxed(17)
assert decode(65)==(1,0,0,1) and not strict(65) and relaxed(65)
assert decode(145)==(1,0,1,2) and not strict(145) and not relaxed(145)
assert clear_sky_days_from_byte(0)==0 and clear_sky_days_from_byte(5)==2 and clear_sky_days_from_byte(255)==8
assert recover_qc(True,False,None)==0 and recover_qc(False,False,None) is None
assert recover_qc(True,True,65)==65
start=date(2020,5,1); end=date(2020,11,1)
windows=[(date(2020,4,30)+timedelta(days=8*i),date(2020,4,30)+timedelta(days=8*(i+1))) for i in range(25)]
days=[overlap(a,b,start,end) for a,b in windows]
assert sum(days)==184 and all(0<=x<=8 for x in days)
print("PASS: QC bit decoding, Clear_sky bit count, support nesting examples, left-closed/right-open overlap, 184-day conservation")
