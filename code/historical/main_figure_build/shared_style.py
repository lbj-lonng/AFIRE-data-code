"""Four-panel figures from frozen estimates. No fitting or new inference."""
from environment import ROOT,SUB,SD,AUD
import os,json,sys,subprocess
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from matplotlib.colors import Normalize,TwoSlopeNorm
from matplotlib.lines import Line2D
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer
from audit_panel_alignment import require_matplotlib_panel_alignment
GEO=SD/'geography'; QA=AUD
BLUE='#226A8F';ORANGE='#BB652F';GREY='#78838B';BLACK='#242A2E';PALE='#DFE7EA';GREEN='#3E807A'
from scope import IDS,LABELS,SIX
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],'font.size':7.5,'axes.labelsize':7.5,'axes.titlesize':8,'xtick.labelsize':7,'ytick.labelsize':7.5,'legend.fontsize':7,'axes.linewidth':.8,'lines.linewidth':1.1,'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,'savefig.facecolor':'white'})
def read(n):return pd.read_csv(SD/'full_results'/(n+'.csv'),dtype={'county_fips':str,'state_fips':str},float_precision='round_trip')
def panel_data(fig,panel,data):
    d=SD/f'Figure_{fig}';d.mkdir(exist_ok=True);data.to_csv(d/f'panel_{panel}.csv',index=False)
def axes(fig,rect,gid):
    w,h=fig.get_size_inches()*25.4;ax=fig.add_axes([rect[0]/w,rect[1]/h,rect[2]/w,rect[3]/h]);ax.set_gid(gid);return ax
def title(ax,letter,label):
    ax.annotate(letter,(0,1),xycoords='axes fraction',xytext=(-11,7),textcoords='offset points',va='bottom',fontweight='bold',fontsize=8)
    ax.annotate(label,(0,1),xycoords='axes fraction',xytext=(0,7),textcoords='offset points',va='bottom',fontsize=8)
def poly_path(g):
    verts=[];codes=[]
    for ring in [g.exterior,*g.interiors]:
        pts=np.asarray(ring.coords);verts.extend(pts);codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(pts)-2)+[MPath.CLOSEPOLY])
    return MPath(np.array(verts),codes)
def fill(ax,g,fc,ec='none',lw=.35,z=1,hatch=None,gid=None):
    for p in ([g] if g.geom_type=='Polygon' else g.geoms):
        patch=PathPatch(poly_path(p),facecolor=fc,edgecolor=ec,lw=lw,zorder=z,hatch=hatch);patch.set_gid(gid);ax.add_patch(patch)
def cbar(fig,cmap,norm,rect,label,ticks):
    ax=axes(fig,rect,'colourbar');cb=fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm,cmap=cmap),cax=ax,orientation='horizontal',ticks=ticks)
    cb.outline.set_visible(False);cb.solids.set_rasterized(False);cb.ax.tick_params(length=2,pad=1.5);cb.set_label(label,labelpad=2,fontsize=7)
    return ax
COUNTY=json.loads((GEO/'counties_256_epsg5070.geojson').read_text())['features']
CONTEXT=json.loads((GEO/'states_context_epsg5070.geojson').read_text())['features']
cfg=json.loads((GEO/'map_config.json').read_text());proj=Transformer.from_crs(4269,5070,always_xy=True)
def county_map(ax,field,cmap,norm):
    data=read('county_map_values').set_index('county_fips')
    assert len(data)==256 and not data.index.duplicated().any()
    matched=[]
    for f in CONTEXT:
        if f['properties']['role']=='outside study':fill(ax,shape(f['geometry']),'#ECEFF0','#D2D7D9')
    for f in COUNTY:
        key=f['properties']['county_fips'];matched.append(key);v=data.loc[key,field]
        assert np.isfinite(v) and norm.vmin<=v<=norm.vmax
        fill(ax,shape(f['geometry']),cmap(norm(v)),(1,1,1,.6),.25,gid='county:'+key)
    for f in CONTEXT:
        if f['properties']['role']=='study':fill(ax,shape(f['geometry']),'none','#56616A',.7,3)
    assert set(matched)==set(data.index)
    ax.set(xlim=cfg['extent'][:2],ylim=cfg['extent'][2:]);ax.set_aspect('equal',adjustable='datalim');ax.axis('off')
    for ab,lon,lat in [('WA',-120.6,50.1),('OR',-125.8,44.1),('CA',-122.7,35.4),('ID',-112.4,45.8),('CO',-100.5,39.2),('AZ',-112,30.3)]:
        ax.text(*proj.transform(lon,lat),ab,ha='center',va='center',fontsize=7,fontweight='bold')
    return data.reset_index()
def error_points(ax,df,ys,color,marker,label=None):
    x=df.percent_estimate.to_numpy();lo=df.percent_CI_lower.to_numpy();hi=df.percent_CI_upper.to_numpy()
    assert np.all(np.isfinite([x,lo,hi])) and np.all(lo<=x) and np.all(x<=hi)
    ec=ax.errorbar(x,ys,xerr=np.vstack([x-lo,hi-x]),fmt=marker,ms=4,color=color,elinewidth=1,capsize=2,label=label,zorder=3)
    # Verify actual rendered error-bar geometry, not only source numbers.
    segs=ec[2][0].get_segments()
    assert len(segs)==len(df)
    for seg,l,h in zip(segs,lo,hi):assert np.allclose(seg[:,0],[l,h],rtol=0,atol=1e-12)
    return min(lo),max(hi)
def forest_axis(ax,labels,xlim,xlabel):
    ax.axvline(0,color='#879299',ls='--',lw=.8,zorder=0)
    ax.set(yticks=range(len(labels)),yticklabels=labels,ylim=(len(labels)-.45,-.6),xlim=xlim,xlabel=xlabel)
    ax.tick_params(axis='y',length=0,pad=5);ax.spines['left'].set_visible(False)
def finish(fig,name,axs,rows=None,cols=None):
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,axes=axs,row_groups=rows,column_groups=cols,json_out=QA/(name+'.alignment.json'),overlay_svg=QA/(name+'.alignment.svg'),tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True)
    (QA/(name+'.axes.json')).write_text(json.dumps({'dimensions_mm':list(fig.get_size_inches()*25.4),'axes':[{'id':a.get_gid(),'bbox':list(a.get_position().bounds),'xlim':list(a.get_xlim()),'ylim':list(a.get_ylim())} for a in fig.axes]},indent=2))
    for ext in ['pdf','svg']:fig.savefig(SUB/'figures'/(name+'.'+ext))
    fig.savefig(SUB/'figures'/(name+'.png'),dpi=600)
    fig.savefig(SUB/'figures'/(name+'.tiff'),dpi=600,pil_kwargs={'compression':'tiff_lzw'})
    fig.savefig(QA/(name+'.final_size.png'),dpi=300)
    for tool,args in [('audit_pdf_text.py',['--min-pt','5','--json']),('audit_figure_collisions.py',['--json-out',str(QA/(name+'.collision.json'))])]:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/qa_helpers'/tool),str(SUB/'figures'/(name+'.pdf')),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)})
        (QA/'pdf_text_audit'/(name+'.'+tool+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8');print(name,tool,r.returncode,flush=True)
    plt.close(fig)
