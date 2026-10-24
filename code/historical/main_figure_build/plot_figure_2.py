from shared_style import *
def build():
    fig=plt.figure(figsize=(183/25.4,168/25.4));a=axes(fig,[13,99,67,56],'a');b=axes(fig,[113,99,64,56],'b');c=axes(fig,[20,20,64,52],'c');d=axes(fig,[113,20,64,52],'d')
    cm=plt.get_cmap('YlOrBr');norm=Normalize(0,2.6);counties=county_map(a,'smoke_mean',cm,norm);title(a,'a','County smoke, 2009–2020');cbar(fig,cm,norm,[22,90,48,2.5],'Mean smoke PM2.5 (μg/m³)',[0,1,2,2.6]);panel_data(2,'a',counties)
    ann=read('annual');panel_data(2,'b',ann);panel_data(2,'c',ann[['year','n_counties','unweighted_county_gini']])
    b.fill_between(ann.year,ann.county_p10,ann.county_p90,color=PALE,lw=0,label='County P10–P90');b.plot(ann.year,ann.county_median,color=GREY,ls='--',label='County median');b.plot(ann.year,ann.population_weighted_smoke,color=BLUE,marker='o',ms=2.8,label='Population-weighted mean')
    b.set(xlim=(2008.5,2020.5),ylim=(0,7),ylabel='Annual smoke PM2.5 (μg/m³)',xticks=[2009,2012,2016,2020],yticks=[0,2,4,6]);title(b,'b','Six-state annual exposure');b.legend(loc='upper left',handlelength=1.4,labelspacing=.45)
    c.plot(ann.year,ann.unweighted_county_gini,color=BLUE,marker='o',ms=3);c.set(xlim=(2008.5,2020.5),ylim=(.25,.65),ylabel='Equal-county Gini',xlabel='Year',xticks=[2009,2012,2016,2020],yticks=[.3,.4,.5,.6]);title(c,'c','County exposure inequality')
    counties=counties.sort_values('county_fips');vals=[counties[counties.quintile.eq(i)].smoke_mean.to_numpy() for i in range(1,6)];assert list(map(len,vals))==[52,51,51,51,51]
    bp=d.boxplot(vals,widths=.52,patch_artist=True,showfliers=False,medianprops={'color':BLACK,'linewidth':1},boxprops={'linewidth':.8},whiskerprops={'linewidth':.8},capprops={'linewidth':.8})
    for box in bp['boxes']:box.set_facecolor('#F0F4F6')
    for i,v in enumerate(vals,1):
        d.scatter(i+.20*np.sin(np.arange(len(v))*2.399963229728653),v,s=7,color=BLUE,alpha=.6,linewidths=0,zorder=3);d.scatter([i],[v.mean()],s=24,marker='D',color=ORANGE,edgecolors='white',linewidths=.5,zorder=5)
    d.set(xlim=(.5,5.5),ylim=(0,2.8),ylabel='County mean smoke (μg/m³)',xlabel='Disadvantage quintile (low to high)',xticks=range(1,6),xticklabels=['1\nn=52','2\nn=51','3\nn=51','4\nn=51','5\nn=51'],yticks=[0,1,2]);title(d,'d','Exposure by disadvantage')
    d.legend(handles=[Line2D([],[],marker='D',color=ORANGE,ls='none',ms=4,label='Mean'),Line2D([],[],color=BLACK,label='Median')],loc='upper right',ncol=2,handlelength=.8,columnspacing=.6);panel_data(2,'d',counties[['county_fips','state_abbr','ses','quintile','smoke_mean']])
    finish(fig,'Figure_2',[a,b,c,d],rows=[['a','b'],['c','d']],cols=[['b','d']])
if __name__=='__main__':build()
