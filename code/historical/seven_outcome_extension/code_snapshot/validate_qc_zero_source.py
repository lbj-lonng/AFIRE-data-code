#!/usr/bin/env python3
"""Sampled independent source check of GEE-masked MOD11A2 QC_Night zeros."""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import ee, pandas as pd, requests

SITES={
 "CA":(38.58,-121.49), "OR":(44.05,-121.31),
 "AZ":(33.45,-112.07), "WA":(46.60,-120.51),
}
DATES={2015:("2015-05-09","A2015129"),2020:("2020-05-08","A2020129")}
ORNL="https://modis.ornl.gov/rst/api/v1/MOD11A2/subset"

def get_json(url,params,retries=3):
 for i in range(retries):
  try:
   r=requests.get(url,params=params,timeout=120); r.raise_for_status(); return r.json(),r.url
  except Exception:
   if i+1==retries: raise
   time.sleep(3*2**i)

def source_pixel(lat,lon,band,modis_date):
 p={"latitude":lat,"longitude":lon,"band":band,"startDate":modis_date,
    "endDate":modis_date,"kmAboveBelow":0,"kmLeftRight":0}
 j,url=get_json(ORNL,p); assert j["nrows"]==1 and j["ncols"]==1 and len(j["subset"])==1
 z=j["subset"][0]; assert len(z["data"])==1
 return z["data"][0],z["tile"],z["proc_date"],url,j["xllcorner"],j["yllcorner"],j["cellsize"]

def gee_recovery_pixel(date,lat,lon,seed):
 img=ee.ImageCollection("MODIS/061/MOD11A2").filterDate(date,ee.Date(date).advance(1,"day")).first()
 lst=img.select("LST_Night_1km"); qc=img.select("QC_Night"); proj=lst.projection()
 recovery=lst.mask().And(qc.mask().Not()).selfMask()
 stack=ee.Image.cat([
   lst.rename("gee_lst_raw_uint16"), qc.toInt16().unmask(-9999).rename("gee_qc_native_sentinel"),
   qc.mask().unmask(0).rename("gee_qc_native_mask"), qc.unmask(0).updateMask(lst.mask()).rename("v3_recovered_qc"),
   img.select("QC_Day").toInt16().unmask(-9999).rename("gee_day_qc_native_sentinel"),
   img.select("QC_Day").mask().unmask(0).rename("gee_day_qc_native_mask"),
   recovery.unmask(0).rename("recovery_position")]).unmask(-9999)
 fc=stack.sample(region=ee.Geometry.Point([lon,lat]).buffer(150000),projection=proj,
                 numPixels=100,seed=seed,geometries=True,dropNulls=False).filter(ee.Filter.eq("recovery_position",1))
 f=ee.Feature(fc.first()).getInfo(); assert f and f.get("geometry")
 glon,glat=f["geometry"]["coordinates"]; return img.get("system:index").getInfo(),glat,glon,f["properties"]

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); args=ap.parse_args()
 ee.Initialize(); rows=[]
 for si,(state,(lat,lon)) in enumerate(SITES.items()):
  for year,(date,modis_date) in DATES.items():
   image_id,plat,plon,g=gee_recovery_pixel(date,lat,lon,20260907+si*10+year)
   oqc,tile,proc,qurl,x,y,cell=source_pixel(plat,plon,"QC_Night",modis_date)
   olst,tile2,proc2,lurl,*_=source_pixel(plat,plon,"LST_Night_1km",modis_date)
   assert (tile,proc)==(tile2,proc2)
   row={"state":state,"year":year,"collection":"MOD11A2.061","gee_image_id":image_id,
    "modis_date":modis_date,"tile":tile,"source_processing_date":proc,"pixel_lat":plat,"pixel_lon":plon,
    "native_xllcorner":x,"native_yllcorner":y,"native_cellsize_m":cell,
    "gee_lst_raw_uint16":g["gee_lst_raw_uint16"],"gee_qc_native_mask":g["gee_qc_native_mask"],
    "gee_qc_native_sentinel":g["gee_qc_native_sentinel"],"v3_recovered_qc":g["v3_recovered_qc"],
    "source_qc_night_uint8":oqc,"source_lst_night_uint16":olst,
    "gee_day_qc_native_mask":g["gee_day_qc_native_mask"],"gee_day_qc_native_sentinel":g["gee_day_qc_native_sentinel"],
    "source_service":"NASA ORNL DAAC MODIS Web Service","source_qc_request":qurl,"source_lst_request":lurl}
   row["producer_granule_id"]=f"MOD11A2.{modis_date}.{tile}.061.{proc}"
   row["recovery_position_confirmed"]=bool(g["gee_qc_native_mask"]==0 and g["gee_qc_native_sentinel"]==-9999 and g["gee_lst_raw_uint16"]>0)
   row["full_byte_exact_match"]=bool(oqc==g["v3_recovered_qc"]==0)
   row["source_nonzero_at_recovery"]=bool(oqc!=0)
   rows.append(row)
 out=pd.DataFrame(rows); args.output.parent.mkdir(parents=True,exist_ok=True); out.to_csv(args.output,index=False)
 assert len(out)==8 and out.recovery_position_confirmed.all() and out.full_byte_exact_match.all()
 assert out.source_nonzero_at_recovery.sum()==0
 meta={"n_granules":int(len(out)),"n_exact_full_byte_matches":int(out.full_byte_exact_match.sum()),
  "n_source_nonzero_at_recovery":int(out.source_nonzero_at_recovery.sum()),
  "output_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest()}
 args.output.with_suffix(".json").write_text(json.dumps(meta,indent=2))

if __name__=="__main__": main()
