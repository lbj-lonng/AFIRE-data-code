"""Re-express frozen AFIRE records; does not fit, allocate, impute or bootstrap."""
from pathlib import Path
import sys, json, hashlib, shutil
ROOT = Path(__file__).resolve().parents[1]
BASE = Path(r'D:\postgraduate\wildfire\9.10\9.15\AFIRE_Supplement_integrated_20260916_230522')
SRC = BASE/'submission/source_data/full_results'
GEO = BASE/'submission/source_data/geography'
sys.path.insert(0, r'C:\Users\86189\Documents\Codex\2026-09-10\ban\work\pydeps')
sys.path.insert(0, r'C:\Users\86189\.codex\skills\nature-figure\scripts')
sys.path.insert(0, str(ROOT/'scripts/figure_qa_helpers'))
import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, Normalize, TwoSlopeNorm, PowerNorm, to_rgb
from matplotlib.patches import PathPatch, Patch
from matplotlib.path import Path as MPath
from matplotlib.lines import Line2D
import pymupdf as fitz
from audit_panel_alignment import require_matplotlib_panel_alignment
from audit_pdf_text import audit_pdf as text_audit
from audit_figure_collisions import audit_pdf as collision_audit, write_overlay_pdf

for d in ['figures','source_data','audit','previews','scripts']:
    (ROOT/d).mkdir(exist_ok=True)
mpl.rcParams.update({'font.family':'Arial','font.size':7.5,'axes.labelsize':7.5,
    'axes.titlesize':8,'xtick.labelsize':7,'ytick.labelsize':7,
    'axes.linewidth':.6,'lines.linewidth':1.1,'pdf.fonttype':42,
    'svg.fonttype':'none','savefig.facecolor':'white','figure.facecolor':'white',
    'xtick.major.width':.5,'ytick.major.width':.5,'xtick.major.size':2.5,
    'ytick.major.size':2.5,'legend.fontsize':6.8})
STATES = ['AZ','CA','CO','ID','OR','WA']
CAUSES = ['copd','chronic_lower_respiratory','respiratory_system','circulatory_system','ischemic_heart_disease']
SHORT = dict(zip(CAUSES,['COPD','CLRD','RESP','CIRC','IHD']))
METHODS = ['equal','population','loyo_fixed_EB','loyo_hierarchical_EB']
MLAB = dict(zip(METHODS,['Equal','Population','Fixed EB','Hierarchical EB']))
MCOL = dict(zip(METHODS,['#8b98a5','#cc7634','#25789a','#80598e']))
QCOL = ['#294f77','#3e88a1','#89a9ad','#c7956d','#9e5259']
BIV = np.array([['#e5e5e5','#aac7da','#5c99bd'],['#d8abc5','#a8a5c0','#637ba7'],['#be699d','#955d99','#593f80']])
STATUS = ['#a4bbc9','#7d5994','#e8b264']
W,H = 179,230
INPUTS = ['county_map_values.csv','county_year_exposure.csv','mortality_records.csv','validation_evaluation_records.csv','validation.csv']
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
protected = [SRC/f for f in INPUTS] + list(GEO.glob('*.geojson')) + list((BASE/'submission').glob('Supplementary_Information_*')) + list((BASE/'submission/figures').glob('*.pdf'))
before = {str(p):digest(p) for p in protected}
def writejson(obj,p): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')
def outcsv(df,name): df.to_csv(ROOT/'source_data'/name,index=False,encoding='utf-8-sig')
def read(name): return pd.read_csv(SRC/name,dtype={'county_fips':'string'})
county=read(INPUTS[0]); cy=read(INPUTS[1]); mort=read(INPUTS[2]); val=read(INPUTS[3]); metrics=read(INPUTS[4])
for df in [county,cy,mort,val]: df['county_fips']=df.county_fips.str.zfill(5)
assert len(county)==256 and county.county_fips.is_unique
assert len(cy)==3072 and not cy.duplicated(['county_fips','year']).any()
assert len(mort)==15360 and set(mort.cause_id)==set(CAUSES)
assert set(cy.year)==set(range(2009,2021)) and set(mort.year)==set(range(2009,2021))
assert mort.death_suppressed.sum()==3328
assert ((mort.deaths==0)&~mort.death_suppressed).sum()==325
assert set(val.method)==set(METHODS) and len(val)==8512
key=['state_abbr','year','cause_id','county_fips']
keysets=[set(map(tuple,val[val.method==m][key].values)) for m in METHODS]
assert all(s==keysets[0] for s in keysets) and len(keysets[0])==2128
assert not val.duplicated(key+['method']).any()
assert val.true_visible_count.between(10,19).all()
assert set(val.n_draws)=={100} and set(val.support)=={'0-19'}
assert val.groupby('method').pseudo_group_id.nunique().eq(298).all()
smokecol='county_smoke_pm25_annual_burden_y'
chk=cy.groupby('county_fips')[smokecol].mean().reindex(county.county_fips).values
assert np.allclose(chk,county.smoke_mean)
county['population_mean']=cy.groupby('county_fips').population.mean().reindex(county.county_fips).values
county=county.sort_values(['state_abbr','ses','county_fips']).reset_index(drop=True)
county['display_row']=np.arange(1,257)
row_order=county.county_fips.tolist()
state_counts=county.groupby('state_abbr').size().reindex(STATES)
starts=np.r_[0,np.cumsum(state_counts)[:-1]]
mids=starts+(state_counts.to_numpy()-1)/2
geoc=json.loads((GEO/'counties_256_epsg5070.geojson').read_text())
geos=json.loads((GEO/'states_context_epsg5070.geojson').read_text())
assert set(f['properties']['county_fips'] for f in geoc['features'])==set(row_order)
assert len(geoc['features'])==256
for file in ['counties_256_epsg5070.geojson','states_context_epsg5070.geojson','boundary_provenance.json','map_config.json']:
    shutil.copy2(GEO/file,ROOT/'source_data'/file)

def makefig():
    f=plt.figure(figsize=(W/25.4,H/25.4)); return f
def axis(f,x,y,w,h,label,title):
    a=f.add_axes([x/W,y/H,w/W,h/H]); a.set_gid(label)
    a.annotate(label,xy=(0,1),xycoords='axes fraction',xytext=(-12,7),textcoords='offset points',fontweight='bold',fontsize=9,annotation_clip=False)
    a.annotate(title,xy=(0,1),xycoords='axes fraction',xytext=(0,7),textcoords='offset points',fontsize=8,annotation_clip=False)
    for s in ['top','right']: a.spines[s].set_visible(False)
    return a
def pathpatch(geo,**kw):
    polys=geo['coordinates'] if geo['type']=='MultiPolygon' else [geo['coordinates']]
    verts=[]; codes=[]
    for poly in polys:
        for ring in poly:
            verts.extend(ring); codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(ring)-2)+[MPath.CLOSEPOLY])
    return PathPatch(MPath(verts,codes),**kw)
def mapplot(a,colors):
    for ft in geos['features']:
        a.add_patch(pathpatch(ft['geometry'],facecolor='#f3f3f1',edgecolor='#c5c9cc',linewidth=.35,zorder=0))
    for ft in geoc['features']:
        a.add_patch(pathpatch(ft['geometry'],facecolor=colors[ft['properties']['county_fips']],edgecolor='white',linewidth=.16,zorder=1))
    for ft in geos['features']:
        a.add_patch(pathpatch(ft['geometry'],facecolor='none',edgecolor='#717d87',linewidth=.5,zorder=2))
    a.set_xlim(-2630357.142857,-234642.857143);a.set_ylim(800000,3380000)
    a.set_aspect('equal',adjustable='datalim');a.set_axis_off()
def colorbar(f,mappable,x,y,w,label,ticks=None):
    ca=f.add_axes([x/W,y/H,w/W,2.8/H]); cb=f.colorbar(mappable,cax=ca,orientation='horizontal',ticks=ticks)
    cb.outline.set_visible(False);cb.ax.tick_params(labelsize=6.7,pad=1);cb.set_label(label,size=7.5,labelpad=2)
def state_rows(a):
    a.set_yticks(mids,STATES);a.tick_params(axis='y',length=0)
    for y in np.cumsum(state_counts)[:-1]-.5:a.axhline(y,color='white',lw=.8)
    a.set_ylabel('Counties, grouped by state')
def saved(f,n,axes,rows=None,cols=None):
    if len(sys.argv)>1 and str(n) not in sys.argv[1:]:
        plt.close(f);return
    stem=f'Supplementary_Figure_{n}'
    f.canvas.draw()
    require_matplotlib_panel_alignment(f,axes=axes,row_groups=rows,column_groups=cols,
        json_out=ROOT/'audit'/f'{stem}_alignment.json',overlay_svg=ROOT/'audit'/f'{stem}_alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,require_panel_labels=True,strict=True)
    f.savefig(ROOT/'figures'/f'{stem}.pdf')
    f.savefig(ROOT/'figures'/f'{stem}.svg')
    f.savefig(ROOT/'figures'/f'{stem}.png',dpi=600)
    pdf=ROOT/'figures'/f'{stem}.pdf'
    ta=text_audit(pdf.read_bytes(),5.0);writejson(ta,ROOT/'audit'/f'{stem}_text.json')
    ca=collision_audit(pdf);writejson(ca,ROOT/'audit'/f'{stem}_collisions.json')
    write_overlay_pdf(pdf,ROOT/'audit'/f'{stem}_collision_overlay.pdf',ca.get('findings',[]))
    doc=fitz.open(pdf);page=doc[0]
    page.get_pixmap(matrix=fitz.Matrix(180/72,180/72)).save(ROOT/'previews'/f'{stem}.png')
    for a in axes:
        bx=a.get_position(); r=fitz.Rect(max(0,(bx.x0*W-18)*72/25.4),max(0,(H-bx.y1*H-11)*72/25.4),min(W*72/25.4,(bx.x1*W+5)*72/25.4),min(H*72/25.4,(H-bx.y0*H+16)*72/25.4))
        page.get_pixmap(matrix=fitz.Matrix(220/72,220/72),clip=r).save(ROOT/'previews'/f'{stem}_{a.get_gid()}.png')
    print(stem,'text',ta.get('verdict',ta.get('status')),'collisions',ca.get('summary'),flush=True)
    doc.close();plt.close(f)

# S8: all-county bivariate atlas and chronological exposure matrix.
cuts={}
for col,short in [('smoke_mean','exposure'),('ses','disadvantage')]:
    q=county[col].quantile([1/3,2/3]).values
    cuts[short]=q.tolist();county[f'{short}_tertile']=np.searchsorted(q,county[col],side='left')
county['map_colour']=[BIV[d,e] for d,e in zip(county.disadvantage_tertile,county.exposure_tertile)]
outcsv(county,'S8_ab_county_display_values.csv')
outcsv(cy.merge(county[['county_fips','display_row']],on='county_fips',validate='many_to_one'),'S8_c_county_year_exposure.csv')
profiles=cy.groupby(['baseline_ses_quintile','year'])[smokecol].agg(['mean','count']).reset_index()
outcsv(profiles,'S8_d_quintile_year_means.csv')
cells=county.groupby(['disadvantage_tertile','exposure_tertile']).size().unstack().reindex(index=range(3),columns=range(3),fill_value=0)
outcsv(cells.stack().rename('n_counties').reset_index(),'S8_ab_bivariate_cell_counts.csv')
writejson({'cutpoints':cuts,'rule':'linear sample quantiles; lower bin includes upper boundary; display bins only','weights':'equal counties; long-term means equal across 12 years','annual_matrix_colour_normalization':'square root (gamma 0.5), original-unit colourbar, no clipping or winsorization','bivariate_colours_rows_disadvantage_columns_exposure':BIV.tolist()},ROOT/'source_data/S8_display_definitions.json')
f=makefig();a=axis(f,20,142,65,70,'a','Smoke–disadvantage geography');b=axis(f,106,142,65,70,'b','All 256 counties')
c=axis(f,20,32,65,70,'c','Annual exposure atlas');d=axis(f,106,32,65,70,'d','Fixed disadvantage groups')
mapplot(a,county.set_index('county_fips').map_colour.to_dict())
f.text(20/W,135/H,'All study counties retained',fontsize=6.8)
f.text(20/W,131/H,'Pale grey: non-study states',fontsize=6.5)
for cut in cuts['exposure']:b.axvline(cut,color='#b5b5b5',ls=':',lw=.7,zorder=0)
for cut in cuts['disadvantage']:b.axhline(cut,color='#b5b5b5',ls=':',lw=.7,zorder=0)
b.scatter(county.smoke_mean,county.ses,s=15,c=county.map_colour,edgecolors='#52616b',linewidths=.35,alpha=.85)
b.set_xlabel('Long-term smoke PM$_{2.5}$ (μg/m³)');b.set_ylabel('Fixed disadvantage (SD)')
# Explicit, small bivariate key, outside quantitative axes.
k=f.add_axes([59/W,114/H,23/W,13/H]);k.imshow(np.array([[to_rgb(x) for x in r] for r in BIV]),origin='lower',aspect='auto')
for i in range(3):
    for j in range(3):k.text(j,i,str(int(cells.iloc[i,j])),ha='center',va='center',fontsize=6.5,color='white' if i+j>=3 else '#303943')
f.text(20/W,109/H,'Key numbers: county counts',fontsize=6.5)
k.set_xticks([0,2],['Low','High']);k.set_yticks([0,2],['Low','High']);k.tick_params(length=0,labelsize=6.5,pad=1)
k.set_xlabel('Smoke',fontsize=6.5,labelpad=1);k.set_ylabel('Disadvantage',fontsize=6.5,labelpad=1)
for sp in k.spines.values():sp.set_visible(False)
mat=cy.pivot(index='county_fips',columns='year',values=smokecol).reindex(row_order)
im=c.imshow(mat.values,cmap='YlOrBr',aspect='auto',interpolation='none',norm=PowerNorm(.5,vmin=0,vmax=float(mat.max().max())))
c.set_xticks([0,2,4,6,8,11],mat.columns[[0,2,4,6,8,11]],rotation=45,ha='right');state_rows(c)
c.set_xlabel('Year');colorbar(f,im,20,13,65,'Annual smoke PM$_{2.5}$ (μg/m³)',[0,1,3,6,10,18])
for q,g in profiles.groupby('baseline_ses_quintile'):
    d.plot(g.year,g['mean'],color=QCOL[int(q)-1],marker='o',ms=2.3,label=f'Q{q}')
d.set_xticks([2009,2012,2016,2020]);d.tick_params(axis='x',rotation=45)
d.set_xlabel('Year');d.set_ylabel('Mean smoke PM$_{2.5}$ (μg/m³)');d.set_ylim(bottom=0);d.grid(axis='y',color='#eeeeee',lw=.5)
d.legend(ncol=3,loc='upper left',frameon=False,columnspacing=.8,handlelength=1.3,borderaxespad=.3)
f.text(106/W,120/H,'Q1 → Q5: lowest → highest disadvantage',fontsize=6.5)
f.text(106/W,115/H,'Lines: equal-county means; not fitted trends',fontsize=6.5)
saved(f,8,[a,b,c,d],[['a','b'],['c','d']],[['a','c'],['b','d']])

# S9: statuses, not hidden counts or mortality effects.
mort['record_status']=np.where(mort.death_suppressed,2,np.where(mort.deaths.eq(0),1,0))
assert mort.loc[~mort.death_suppressed,'deaths'].notna().all()
assert mort.loc[mort.death_suppressed,'deaths'].isna().all()
sstate=mort.groupby(['state_abbr','cause_id']).agg(n_records=('record_status','size'),suppressed_records=('death_suppressed','sum')).reset_index()
sstate['suppressed_percent']=100*sstate.suppressed_records/sstate.n_records
outcsv(sstate,'S9_b_state_cause_status_summary.csv')
outcsv(mort[['state_abbr','county_fips','year','cause_id','record_status']].merge(county[['county_fips','display_row']],on='county_fips',validate='many_to_one'),'S9_c_all_record_statuses.csv')
outcsv(county[['county_fips','county','state_abbr','n_records','suppressed_records','suppressed_record_percent']],'S9_a_county_suppression.csv')
f=makefig();a=axis(f,20,142,65,70,'a','Geography of suppression');b=axis(f,106,142,65,70,'b','Suppression by state and cause');c=axis(f,20,30,151,72,'c','Complete public-record status matrix')
for txt in c.texts: txt.set_position((txt.get_position()[0],18))
norm=Normalize(0,100);cmap=mpl.colormaps['YlOrBr'];mapplot(a,{r.county_fips:cmap(norm(r.suppressed_record_percent)) for r in county.itertuples()})
colorbar(f,mpl.cm.ScalarMappable(norm=norm,cmap=cmap),20,129,65,'Suppressed year–cause records (%)',[0,25,50,75,100])
v=sstate.pivot(index='state_abbr',columns='cause_id',values='suppressed_percent').reindex(index=STATES,columns=CAUSES)
b.imshow(v.values,cmap=cmap,norm=norm,aspect='auto');b.set_xticks(range(5),[SHORT[x] for x in CAUSES],rotation=45,ha='right');b.set_yticks(range(6),STATES)
for i in range(6):
    for j in range(5):b.text(j,i,f'{v.iloc[i,j]:.1f}',ha='center',va='center',fontsize=7,color='white' if v.iloc[i,j]>60 else '#252d34')
b.tick_params(length=0);b.set_xlabel('Cause-specific record suppression (%)')
cols=pd.MultiIndex.from_product([CAUSES,range(2009,2021)],names=['cause_id','year'])
status=mort.pivot(index='county_fips',columns=['cause_id','year'],values='record_status').reindex(index=row_order,columns=cols)
assert status.notna().all().all()
display=np.full((256,68),np.nan)
for j in range(5):display[:,j*14:j*14+12]=status.values[:,j*12:j*12+12]
assert np.isfinite(display).sum()==15360
status_cmap=ListedColormap(STATUS);status_cmap.set_bad('white')
c.imshow(np.ma.masked_invalid(display),cmap=status_cmap,vmin=-.5,vmax=2.5,aspect='auto',interpolation='none');state_rows(c)
pos=[];labs=[]
for j,cause in enumerate(CAUSES):
    pos += [j*14,j*14+5,j*14+11];labs += ['2009','2014','2020']
    c.text((j*14+6)/68,1.015,SHORT[cause],transform=c.transAxes,ha='center',va='bottom',fontsize=7)
c.set_xticks(pos,labs,rotation=45,ha='right');c.set_xlabel('Year within each mortality category')
f.legend(handles=[Patch(facecolor=STATUS[i],label=l) for i,l in enumerate(['Public positive count','Public zero','Suppressed'])],loc='center',bbox_to_anchor=(.55,114/H),frameon=False,ncol=3,handlelength=1.3,columnspacing=2)
saved(f,9,[a,b,c],[['a','b']],None)

# S10: exact paired frozen evaluation records, no resampling.
unique=val[val.method==METHODS[0]].copy()
vc=unique.groupby('county_fips').size().reindex(row_order,fill_value=0)
vm=county[['county_fips','county','state_abbr']].copy();vm['validation_cells']=vc.values
outcsv(vm,'S10_a_validation_geography.csv')
piv=val.pivot(index=key,columns='method',values='absolute_error').reset_index()
comparisons=[('loyo_fixed_EB','equal','Fixed EB − equal','#25789a'),('loyo_fixed_EB','population','Fixed EB − population','#cc7634'),('loyo_hierarchical_EB','loyo_fixed_EB','Hierarchical − fixed EB','#80598e')]
paired=[];summary=[]
for m1,m0,name,col in comparisons:
    v=piv[m1]-piv[m0];frame=piv[key].copy();frame['comparison']=name;frame['absolute_error_difference']=v;paired.append(frame)
    summary.append({'comparison':name,'n_cells':len(v),'mean_difference':v.mean(),'median_difference':v.median(),'fraction_negative':v.lt(0).mean(),'fraction_zero':v.eq(0).mean(),'fraction_positive':v.gt(0).mean()})
outcsv(pd.concat(paired),'S10_b_paired_error_differences.csv');outcsv(pd.DataFrame(summary),'S10_b_descriptive_summary.csv')
recomputed=[]
for (scope,method),g in pd.concat([val.assign(scope='all_outcomes'),val.assign(scope=val.cause_id)]).groupby(['scope','method']):
    recomputed.append({'scope':scope,'method':method,'n_groups':g.pseudo_group_id.nunique(),'n_cells':len(g),'MAE':g.absolute_error.mean(),'RMSE':np.sqrt(g.squared_error.mean()),'coverage_95':g.interval_covers_truth.mean(),'mean_interval_width':g.interval_width.mean(),'mean_CRPS':g.CRPS.mean(),'mean_interval_score_95':g.interval_score_95.mean()})
rc=pd.DataFrame(recomputed);comparison=rc.merge(metrics,on=['scope','method'],suffixes=('_check','_saved'),validate='one_to_one')
metriccols=['MAE','RMSE','coverage_95','mean_interval_width','mean_CRPS','mean_interval_score_95']
maxdiff={m:float(abs(comparison[m+'_check']-comparison[m+'_saved']).max()) for m in metriccols}
assert max(maxdiff.values())<1e-10
outcsv(metrics,'S10_cd_frozen_performance_metrics.csv')
pool=metrics[metrics.scope=='all_outcomes'].set_index('method').reindex(METHODS)
ratios=pool[['MAE','RMSE','mean_CRPS']].div(pool.loc['equal',['MAE','RMSE','mean_CRPS']].astype(float),axis=1)
outcsv(ratios.reset_index(),'S10_c_loss_ratios_to_equal.csv')
f=makefig();a=axis(f,20,142,65,70,'a','Validation geography');b=axis(f,106,142,65,70,'b','Paired error differences');c=axis(f,20,32,65,70,'c','Relative loss across methods');d=axis(f,106,32,65,70,'d','Coverage–width trade-off')
norm=Normalize(1,max(vc));cmap=mpl.colormaps['Blues']
mapplot(a,{r.county_fips:('#e0e0dc' if r.validation_cells==0 else cmap(norm(r.validation_cells))) for r in vm.itertuples()})
colorbar(f,mpl.cm.ScalarMappable(norm=norm,cmap=cmap),20,129,65,'Eligible validation cells per county')
f.text(20/W,114/H,f'Grey study counties: no eligible cells (n = {(vc==0).sum()})',fontsize=6.5)
for m1,m0,name,col in comparisons:
    vs=np.sort((piv[m1]-piv[m0]).values);b.step(vs,np.arange(1,len(vs)+1)/len(vs),where='post',color=col,label=name)
b.axvline(0,color='#969da3',ls='--',lw=.7);b.set_ylim(0,1.02)
b.set_xlabel('Absolute-error difference (deaths)');b.set_ylabel('Cumulative fraction of paired cells')
b.legend(loc='lower right',frameon=False,fontsize=6.5,handlelength=1.5)
f.text(106/W,125/H,'Negative: first method has smaller error',fontsize=6.5)
f.text(106/W,120/H,'Same 2,128 cells in 298 groups',fontsize=6.5)
im=c.imshow(ratios.values.astype(float),cmap='PuOr_r',norm=TwoSlopeNorm(vmin=.65,vcenter=1,vmax=1.6),aspect='auto')
c.set_xticks(range(3),['MAE','RMSE','CRPS']);c.set_yticks(range(4),['Equal','Population','Fixed EB','Hier. EB']);c.tick_params(length=0)
for i in range(4):
    for j in range(3):c.text(j,i,f'{ratios.iloc[i,j]:.3f}',ha='center',va='center',fontsize=8,color='#242b32')
colorbar(f,im,20,17,65,'Loss / equal-weight loss (lower is better)',[.7,1,1.3,1.6])
markers=['o','s','^','D','P'];causehandles=[]
for cause,mark in zip(CAUSES,markers):
    g=metrics[metrics.scope==cause].set_index('method').reindex(METHODS)
    for method in METHODS:d.scatter(g.loc[method,'mean_interval_width'],100*g.loc[method,'coverage_95'],s=22,marker=mark,c=MCOL[method],linewidths=.35,edgecolors='white',zorder=3)
    causehandles.append(Line2D([],[],color='#586570',marker=mark,linestyle='none',markersize=4,label=SHORT[cause]))
d.axhline(95,color='#7a858f',ls='--',lw=.7);d.set_ylim(55,102);d.set_xlabel('Mean interval width (deaths)');d.set_ylabel('Empirical count-interval coverage (%)')
d.legend(handles=causehandles,loc='lower right',frameon=False,ncol=2,fontsize=6.5,columnspacing=.7,handletextpad=.3)
f.legend(handles=[Line2D([],[],marker='o',color=MCOL[m],linestyle='none',markersize=4,label=MLAB[m]) for m in METHODS],loc='center',bbox_to_anchor=(.57,109/H),ncol=4,frameon=False,columnspacing=1.5,handletextpad=.4)
saved(f,10,[a,b,c,d],[['a','b'],['c','d']],[['a','c'],['b','d']])

after={str(p):digest(p) for p in protected};assert before==after
writejson({'all_protected_inputs_unchanged':before==after,'files':before},ROOT/'audit/source_sha256_before_after.json')
writejson({'counties':256,'county_years':3072,'mortality_records':15360,'suppressed_records':3328,'public_zeros':325,'public_positive_records':11707,'FIPS_exact_matches':256,'missing_FIPS':[],'duplicated_FIPS':[],'geographic_display_crs':'EPSG:5070','boundary_vintage':2020,'state_counts':state_counts.to_dict(),'validation_cells_per_method':2128,'validation_groups_per_method':298,'paired_key_identity':True,'validation_metric_max_absolute_reaggregation_discrepancy':maxdiff,'no_eligible_validation_counties':int((vc==0).sum()),'observation_years':[2009,2020],'new_model_fits':0,'new_allocations':0,'new_bootstraps':0,'new_p_values':0,'new_confidence_intervals':0,'annual_exposure_conversion_repeated':False},ROOT/'audit/data_integrity.json')
print('Build and numerical audits complete; visual/collision review still required.',flush=True)
