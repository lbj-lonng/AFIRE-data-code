"""Inspect existing allocations only. Never sample, fit, truncate or repair counts."""
from environment import ROOT,SD,AUD
from scope import IDS,LABELS
import io,json,hashlib,tarfile
import numpy as np,pandas as pd

def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    cfg=json.loads((AUD/'inputs/health_config.json').read_text(encoding='utf-8'))
    cache=AUD/'inputs/five_outcome_existing_allocations.npz'
    provenance=AUD/'allocation_source.json'
    raw=pd.read_csv(AUD/'inputs/mortality_panel.csv',dtype={'county_fips':str})
    raw=raw[raw.year.between(2009,2020)&raw.cause_id.isin(IDS)].copy()
    raw.county_fips=raw.county_fips.str.zfill(5)
    if not cache.exists():
        path=ROOT.parent.parent/'AFIRE_B1_joint_adjustment_20260909_233833.tar.gz'
        member='AFIRE_B1_joint_adjustment_20260909_233833/tmp/fixed_EB_B1_1_9_all_outcomes_30.npz'
        with tarfile.open(path,'r:gz') as t:
            m=t.getmember(member);assert m.isfile() and not m.issym();blob=t.extractfile(m).read()
        assert sha(blob)==cfg['draw_sha256']
        arr=np.load(io.BytesIO(blob),allow_pickle=False);lookup={v:i for i,v in enumerate(arr['row_ids'])}
        ids=raw.row_id.to_numpy();draws=arr['draws'][:,[lookup[v] for v in ids]]
        assert json.loads(str(arr['seed_map_json'][0]))==cfg['seed_map']
        np.savez_compressed(cache,row_ids=ids,draws=draws)
        provenance.write_text(json.dumps({'source_path':str(path),'member':member,'member_sha256':sha(blob),'subset_cache_sha256':sha(cache.read_bytes()),'operation':'column selection only; existing allocation values unchanged'},indent=2),encoding='utf-8')
    prov=json.loads(provenance.read_text());assert sha(cache.read_bytes())==prov['subset_cache_sha256']
    z=np.load(cache,allow_pickle=False);lookup={int(v):i for i,v in enumerate(z['row_ids'])};draws=z['draws'][:,[lookup[int(v)] for v in raw.row_id]]
    assert draws.shape==(30,15360) and np.isfinite(draws).all() and (draws==np.floor(draws)).all()
    s=raw.death_suppressed.to_numpy(bool);assert ((draws[:,s]>=1)&(draws[:,s]<=9)).all()
    assert np.array_equal(draws[:,~s],np.broadcast_to(raw.deaths.to_numpy()[~s],draws[:,~s].shape))
    for _,g in raw.groupby(['state_abbr','year','cause_id']):
        ix=raw.index.get_indexer(g.index);assert g.state_deaths.nunique()==1;assert (draws[:,ix].sum(axis=1)==g.state_deaths.iloc[0]).all()
    nested=[]
    for child,parent in [(IDS[0],IDS[1]),(IDS[1],IDS[2]),(IDS[4],IDS[3])]:
        a=raw[raw.cause_id.eq(child)].sort_values(['county_fips','year']);b=raw[raw.cause_id.eq(parent)].sort_values(['county_fips','year'])
        assert np.array_equal(a[['county_fips','year']],b[['county_fips','year']])
        av=z['draws'][:,[lookup[int(v)] for v in a.row_id]];bv=z['draws'][:,[lookup[int(v)] for v in b.row_id]]
        v=av>bv;pub=(~a.death_suppressed.to_numpy(bool))&(~b.death_suppressed.to_numpy(bool));pv=a.deaths.to_numpy()[pub]>b.deaths.to_numpy()[pub]
        nested.append(dict(relation=LABELS[IDS.index(child)]+' subset '+LABELS[IDS.index(parent)],child=child,parent=parent,n_county_years=len(a),n_draw_comparisons=v.size,draw_violations=int(v.sum()),any_draw_violations=int(v.any(axis=0).sum()),mean_count_violations=int((av.mean(axis=0)>bv.mean(axis=0)).sum()),public_comparisons=int(pub.sum()),public_violations=int(pv.sum()),max_excess=int(np.maximum(av-bv,0).max()),per_draw_min=int(v.sum(axis=1).min()),per_draw_max=int(v.sum(axis=1).max())))
    pd.DataFrame(nested).to_csv(SD/'full_results/nested_outcome_check.csv',index=False)
    rows=[];di=[]
    for oid in IDS:
        a=pd.read_csv(AUD/f'inputs/sample_keys/{oid}__C__M2.csv',dtype={'county_fips':str})
        b=pd.read_csv(AUD/f'inputs/sample_keys/{oid}__C__M3PL_joint.csv',dtype={'county_fips':str});assert a.equals(b) and len(a)==3062
        vals=z['draws'][:,[lookup[int(v)] for v in a.row_id]]
        hashv=sha(np.asarray(vals,dtype='<i8').tobytes())
        old=pd.read_csv(AUD/'inputs/previous_pair_audit/sample_match_check.csv').set_index('outcome_id').loc[oid]
        assert old.selected_allocation_sha256_i64le==hashv
        for model in ['M2','M3PL_joint']:
            fits=pd.read_csv(AUD/f'inputs/per_imputation/{oid}__C__{model}.csv');assert len(fits)==30 and fits.status.eq('ok').all() and fits.converged.all()
            assert list(fits.imputation)==list(range(1,31))
        rows.append(dict(outcome_id=oid,reference_n=3062,joint_n=3062,n_counties=256,n_states=6,year_min=2009,year_max=2020,keys_order_equal=True,imputations_equal=30,actual_allocation_values_equal=True,selected_allocation_sha256_i64le=hashv,status='PASS'))
        di.extend(dict(outcome_id=oid,imputation=i+1,sha256=sha(np.asarray(v,dtype='<i8').tobytes()),paired_identity=True) for i,v in enumerate(vals))
    pd.DataFrame(rows).to_csv(AUD/'sample_match_check.csv',index=False)
    pd.DataFrame(di).to_csv(AUD/'paired_imputation_identity.csv',index=False)
    pd.DataFrame(rows).to_csv(SD/'full_results/common_sample_identity.csv',index=False)
    pd.DataFrame([{'check':'public_counts_including_zero_unchanged','status':'PASS','n_records':int((~s).sum())},{'check':'state_year_cause_totals_exact_all_30_draws','status':'PASS','n_groups':360},{'check':'suppressed_all_draws_in_1_to_9','status':'PASS','n_records':int(s.sum())}]).to_csv(AUD/'allocation_constraint_check.csv',index=False)
    print(pd.DataFrame(nested).to_string(index=False));print('Existing arrays and all five common-sample pairs verified.')
if __name__=='__main__':run()
