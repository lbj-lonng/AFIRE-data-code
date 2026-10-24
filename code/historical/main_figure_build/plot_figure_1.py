from shared_style import *
import shapefile
def build():
    fig=plt.figure(figsize=(183/25.4,184/25.4));a=axes(fig,[8,123,78,51],'a');b=axes(fig,[113,123,64,51],'b');c=axes(fig,[20,20,64,62],'c');d=axes(fig,[119,20,58,62],'d')
    st=read('state_map').set_index('state_abbr');r=shapefile.Reader(str(next((GEO/'raw/state').glob('*.shp'))));fields=[x[0] for x in r.fields[1:]];states={}
    for sr in r.iterShapeRecords():
        p=dict(zip(fields,sr.record));ab=p['STUSPS']
        if ab in st.index:states[ab]=(p,shape(sr.shape.__geo_interface__))
    assert len(states)==51 and st.smoke_mean.notna().sum()==49
    cm=plt.get_cmap('YlGnBu');norm=Normalize(0,1.2);bounds=[];audit=[]
    for ab,(p,g) in states.items():
        assert p['STATEFP']==st.loc[ab,'state_fips'];epsg=3338 if ab=='AK' else 26904 if ab=='HI' else 5070
        h=transform(Transformer.from_crs(4269,epsg,always_xy=True).transform,g)
        audit.append({'state_abbr':ab,'state_fips':p['STATEFP'],'geometry_valid':h.is_valid,'exposure_present':np.isfinite(st.loc[ab,'smoke_mean']),'projection':epsg})
        if ab in ['AK','HI']:continue
        bounds.append(h.bounds);v=st.loc[ab,'smoke_mean'];assert norm.vmin<=v<=norm.vmax
        fill(a,h,cm(norm(v)),'white',.3,gid='state:'+ab)
        if ab in SIX:fill(a,h,'none',BLACK,.8,3)
    bb=np.array(bounds);a.set(xlim=(bb[:,0].min()-50000,bb[:,2].max()+50000),ylim=(bb[:,1].min()-50000,bb[:,3].max()+50000));a.set_aspect('equal',adjustable='datalim');a.axis('off');title(a,'a','State smoke, 2009–2020')
    for ab,rect,epsg in [('AK',[10,107,18,11],3338),('HI',[36,107,17,11],26904),('DC',[69,107,9,11],5070)]:
        ia=axes(fig,rect,ab+'_inset');h=transform(Transformer.from_crs(4269,epsg,always_xy=True).transform,states[ab][1]);miss=ab in ['AK','HI'];fill(ia,h,'#E1E4E6' if miss else cm(norm(st.loc[ab,'smoke_mean'])),'#7B858C',.35)
        x0,y0,x1,y1=h.bounds;pad=max(x1-x0,y1-y0)*.05;ia.set(xlim=(x0-pad,x1+pad),ylim=(y0-pad,y1+pad));ia.set_aspect('equal');ia.axis('off');ia.text(.5,-.12,ab,transform=ia.transAxes,ha='center',va='top',fontsize=7)
    fig.text(113/183,107/184,'AK / HI: no exposure values\nInsets use independent scales',fontsize=7,linespacing=1.5)
    cbar(fig,cm,norm,[8,100,78,2.5],'Mean smoke PM2.5 (μg/m³)',[0,.4,.8,1.2]);panel_data(1,'a',st.reset_index())
    pd.DataFrame(audit).to_csv(QA/'state_geographic_match.csv',index=False)
    ann=read('state_annual');panel_data(1,'b',ann);b.fill_between(ann.year,ann.state_p10,ann.state_p90,color=PALE,lw=0,label='State P10–P90');b.plot(ann.year,ann.state_median,color=GREY,ls='--',label='State median');b.plot(ann.year,ann.state_mean,color=BLUE,marker='o',ms=2.8,label='Equal-state mean');b.set(xlim=(2008.5,2020.5),ylim=(0,2.05),ylabel='Annual smoke PM2.5 (μg/m³)',xticks=[2009,2012,2016,2020],yticks=[0,.5,1,1.5,2]);title(b,'b','49-unit annual distribution');b.legend(loc='upper left',handlelength=1.4,labelspacing=.45)
    econ=read('state_baseline_poverty');assert len(econ)==49;panel_data(1,'c',econ)
    # All states have equal point area; the six existing study states are marked,
    # not selected by economic direction. No fit, correlation or significance test.
    six=econ.state_abbr.isin(SIX);c.scatter(econ.loc[~six,'poverty_percent'],econ.loc[~six,'smoke_mean'],s=20,color=GREY,alpha=.75,edgecolors='white',linewidths=.4);c.scatter(econ.loc[six,'poverty_percent'],econ.loc[six,'smoke_mean'],s=20,color=ORANGE,edgecolors=BLACK,linewidths=.4,zorder=4)
    for _,row in econ[six].iterrows():
        leader={'arrowstyle':'-','color':GREY,'lw':.5,'shrinkA':2,'shrinkB':4} if row.state_abbr=='CO' else None
        c.annotate(row.state_abbr,(row.poverty_percent,row.smoke_mean),xytext={'CA':(5,5),'CO':(4,-20),'OR':(5,-7),'WA':(5,3),'AZ':(5,-3),'ID':(-12,7)}[row.state_abbr],textcoords='offset points',fontsize=7,color=BLACK,arrowprops=leader)
    c.set(xlabel='Baseline poverty proxy (%)\nCounty-population weighted',ylabel='Mean smoke, 2009–2020 (μg/m³)',xlim=(econ.poverty_percent.min()-1.2,econ.poverty_percent.max()+1.2),ylim=(0,1.25));title(c,'c','State economy and exposure')
    counts=read('fire_state_counts').sort_values(['catalogue_record_assignments','state_abbr'],ascending=[False,True]);assert counts.catalogue_record_assignments.sum()==89;panel_data(1,'d',counts)
    ys=np.arange(len(counts));d.barh(ys,counts.catalogue_record_assignments,color=[ORANGE if s in SIX else GREY for s in counts.state_abbr],height=.65);d.set(yticks=ys,yticklabels=counts.state_abbr,ylim=(len(counts)-.35,-.65),xlim=(0,counts.catalogue_record_assignments.max()+3),xlabel='State–catalogue record assignments');d.tick_params(axis='y',length=0);title(d,'d','Archived fires, 2009–2020')
    for y,v in zip(ys,counts.catalogue_record_assignments):d.text(v+.4,y,str(v),va='center',fontsize=7)
    fig.text(119/183,6/184,'81 records; 89 state assignments',fontsize=7)
    finish(fig,'Figure_1',[a,b,c,d],rows=[['a','b'],['c','d']])
if __name__=='__main__':build()
