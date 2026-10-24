"""Redraw the complete in-scope supplementary evidence from stored values."""
from shared_style import *

def save(fig,n,data,axs=None,rows=None,cols=None):
    name=f'Supplementary_Figure_S{n}';out=SUB/'figures/supplementary'
    fig.canvas.draw()
    if axs:require_matplotlib_panel_alignment(fig,axes=axs,row_groups=rows,column_groups=cols,json_out=QA/(name+'.alignment.json'),tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True)
    for ext in ['pdf','svg']:fig.savefig(out/(name+'.'+ext))
    fig.savefig(out/(name+'.png'),dpi=600)
    fig.savefig(QA/(name+'.final_size.png'),dpi=180)
    data.to_csv(SD/'full_results'/(name+'_data.csv'),index=False)
    for tool,args in [('audit_pdf_text.py',['--min-pt','5','--json']),('audit_figure_collisions.py',['--json-out',str(QA/(name+'.collision.json'))])]:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/qa_helpers'/tool),str(out/(name+'.pdf')),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)})
        (QA/'pdf_text_audit'/(name+'.'+tool+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8');print(name,tool,r.returncode,flush=True)
    plt.close(fig)

def forest(n,source):
    data=read(source);lo=data.percent_CI_lower.min();hi=data.percent_CI_upper.max();pad=(hi-lo)*.10
    fig=plt.figure(figsize=(183/25.4,225/25.4));allaxs=[]
    for j,oid in enumerate(IDS):
        row=j//2;col=j%2
        ax=axes(fig,[31+92*col,164-70*row,53,45],chr(97+j));allaxs.append(ax)
        d=data[data.outcome_id.eq(oid)].copy()
        if n==1:d=d.sort_values('ses_sd');labs=[f'{s:+g} SD' if s else '0 SD' for s in d.ses_sd]
        else:
            labs=d.model_id.tolist()
            short={'reference':'Full','full':'Full','drop2020':'No 2020','dropCA':'No CA','dropCA_and2020':'No CA / 2020','dropCA2020':'No CA in 2020','dropCA2020_only':'No CA in 2020','dropCA2020only':'No CA in 2020'}
            labs=[short.get(s,s).replace('_relaxed_',' r ').replace('_strict_',' s ').replace('noLST','−L').replace('withLST','+L') for s in labs]
        error_points(ax,d,np.arange(len(d)),BLUE,'o');forest_axis(ax,labs,(lo-pad,hi+pad),'Conditional association (%)' if n==1 else 'Interaction: RRR change (%)');title(ax,chr(97+j),LABELS[j])
    note='Ordinary 95% confidence intervals\nSame saved estimates and scales\n30 existing imputations per fit\n2009–2020 study window'
    if n==4:note+='\nr / s: relaxed / strict QA\n−L / +L: without / with LST'
    fig.text(123/183,30/225,note,fontsize=7.5,linespacing=1.8)
    save(fig,n,data,allaxs,rows=[['a','b'],['c','d']],cols=[['a','c','e'],['b','d']])

def run():
    for n,source in [(1,'conditional'),(2,'common_sample'),(3,'targeted_omissions'),(4,'LST_pairs')]:forest(n,source)
    d=read('nested_outcome_check');labs=[s.replace(' subset ',' > ') for s in d.relation];ys=np.arange(len(d))
    fig=plt.figure(figsize=(183/25.4,90/25.4));a=axes(fig,[34,21,53,52],'a');b=axes(fig,[125,21,51,52],'b')
    a.barh(ys,d.draw_violations,color=BLUE,height=.5);a.set(yticks=ys,yticklabels=labs,ylim=(2.6,-.6),xlabel='Draw-level violations',xlim=(0,11000));a.tick_params(axis='y',length=0);title(a,'a','92,160 comparisons per relation')
    for y,v in zip(ys,d.draw_violations):a.text(v+100,y,f'{v:,}',va='center',fontsize=7)
    b.barh(ys-.17,d.any_draw_violations,color=BLUE,height=.3,label='Any draw');b.barh(ys+.17,d.mean_count_violations,color=ORANGE,height=.3,label='Mean count');b.set(yticks=ys,yticklabels=labs,ylim=(2.6,-.6),xlabel='County–years',xlim=(0,950));b.tick_params(axis='y',length=0);title(b,'b','3,072 county–years per relation');b.legend(loc='lower left',bbox_to_anchor=(-.03,-.33),ncol=2,fontsize=7,handlelength=1.2,columnspacing=.8)
    save(fig,5,d,[a,b],rows=[['a','b']])
    d=read('county_aggregated_state_year');value='population_weighted_smoke';assert value in d
    fig=plt.figure(figsize=(183/25.4,85/25.4));ax=axes(fig,[17,24,137,47],'a')
    mat=d.pivot(index='state_abbr',columns='year',values=value).loc[SIX];im=ax.imshow(mat,aspect='auto',cmap='YlOrBr',vmin=0,vmax=np.ceil(mat.to_numpy().max()))
    ax.set(yticks=range(6),yticklabels=SIX,xticks=range(12),xticklabels=range(2009,2021),xlabel='Year');ax.tick_params(axis='x',rotation=45);title(ax,'a','Annual county-population-weighted state smoke')
    cb=fig.colorbar(im,cax=axes(fig,[161,24,3,47],'colourbar'));cb.set_label('Smoke PM2.5 (μg/m³)');cb.solids.set_rasterized(False)
    save(fig,6,d)
    d=read('county_map_values').sort_values('county_fips');vs=[d.loc[d.state_abbr.eq(s),'smoke_mean'].to_numpy() for s in SIX]
    fig=plt.figure(figsize=(183/25.4,105/25.4));ax=axes(fig,[20,24,154,68],'a')
    bp=ax.boxplot(vs,showfliers=False,widths=.5,patch_artist=True,medianprops={'color':BLACK},boxprops={'facecolor':'#F0F4F6'})
    for j,v in enumerate(vs,1):ax.scatter(j+.2*np.sin(np.arange(len(v))*2.3999632297),v,s=9,color=BLUE,alpha=.7,zorder=3);ax.scatter([j],[v.mean()],s=26,color=ORANGE,marker='D',zorder=5)
    ax.set(xticks=range(1,7),xticklabels=[f'{s}\nn={len(v)}' for s,v in zip(SIX,vs)],ylabel='County mean smoke, 2009–2020 (μg/m³)',ylim=(0,2.8));title(ax,'a','Within-state county exposure distributions')
    ax.legend(handles=[Line2D([],[],marker='D',color=ORANGE,ls='none',label='Mean'),Line2D([],[],color=BLACK,label='Median')],loc='upper right',ncol=2)
    save(fig,7,d[['county_fips','state_abbr','smoke_mean']])
if __name__=='__main__':run()
