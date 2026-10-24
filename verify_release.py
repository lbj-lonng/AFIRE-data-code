"""Verify release integrity and frozen numerical identities; standard library only."""
import argparse, csv, hashlib, json, math
from collections import Counter
from pathlib import Path

def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    a=ap.parse_args();root=a.root.resolve();checks=[]
    def ck(name,ok,details=''):
        checks.append({'check':name,'pass':bool(ok),'details':details})
    full=root/'data/source_data/full_results'
    h=rows(full/'health_results.csv')
    ck('135 frozen health estimates',len(h)==135)
    ck('analysis blocks',Counter(r['analysis_block'] for r in h)==dict(A=5,B=25,C=40,D=25,E=40))
    ids={'copd','chronic_lower_respiratory','respiratory_system','circulatory_system','ischemic_heart_disease'}
    ck('five outcomes',set(r['outcome_id'] for r in h)==ids)
    ck('30 imputations per stored fit',all(int(float(r['n_imputations']))==30 for r in h))
    for src,dst in [('beta','percent_estimate'),('beta_CI_lower','percent_CI_lower'),('beta_CI_upper','percent_CI_upper')]:
        delta=max(abs(100*math.expm1(float(r[src]))-float(r[dst])) for r in h)
        ck(src+' exponentiation',delta<1e-9,delta)
    mort=rows(full/'mortality_records.csv')
    suppressed=[r for r in mort if r['death_suppressed'].lower() in ['true','1']]
    ck('15360 mortality records',len(mort)==15360)
    ck('3328 suppressed records remain missing',len(suppressed)==3328 and all(r['deaths']=='' for r in suppressed))
    ck('325 public zeros retained',sum(r['deaths']!='' and float(r['deaths'])==0 for r in mort)==325)
    cy=rows(full/'county_year_exposure.csv')
    ck('3072 unique county-years',len(cy)==3072 and len({(r['county_fips'],r['year']) for r in cy})==3072)
    ck('2009-2020 coverage',set(int(r['year']) for r in cy)==set(range(2009,2021)))
    val=rows(full/'validation_evaluation_records.csv');by={}
    for r in val:by.setdefault(r['method'],[]).append(r)
    keys=[{(r['state_abbr'],r['year'],r['cause_id'],r['county_fips']) for r in group} for group in by.values()]
    ck('four matched validation methods',len(by)==4 and all(len(g)==2128 for g in by.values()) and all(k==keys[0] for k in keys))
    ck('298 groups per method',all(len({r['pseudo_group_id'] for r in g})==298 for g in by.values()))
    ck('public-count validation analogue',all(10<=float(r['true_visible_count'])<=19 and r['support']=='0-19' for r in val))
    ck('no allocation arrays in release',not any(root.rglob('*.npz')) and not any(root.rglob('*.npy')))
    ck('S8-S10 sources included',all(any((root/'data/supplementary_figures_S8_S10').glob('S'+str(n)+'*')) for n in [8,9,10]))
    manifest=root/'SHA256SUMS.csv'
    if manifest.exists():
        entries=rows(manifest);bad=[]
        for r in entries:
            p=root/r['path']
            if not p.is_file() or digest(p)!=r['sha256']:bad.append(r['path'])
        ck('release checksums',not bad,{'files':len(entries),'mismatches':bad})
    report={'passed':all(x['pass'] for x in checks),'checks':checks,'scope':'stored data and archive integrity; not a new model fit or raw-source replication'}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
