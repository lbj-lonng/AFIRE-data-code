from shared_style import *
def build():
    fig=plt.figure(figsize=(183/25.4,165/25.4));a=axes(fig,[13,99,67,56],'a');b=axes(fig,[109,99,68,56],'b');c=axes(fig,[20,23,64,51],'c');d=axes(fig,[113,23,64,51],'d')
    cm=plt.get_cmap('BrBG_r');norm=TwoSlopeNorm(vcenter=0,vmin=-3.5,vmax=3.5);data=county_map(a,'ses',cm,norm);title(a,'a','Baseline disadvantage');cbar(fig,cm,norm,[24,90,44,2.5],'Disadvantage (SD)',[-3,0,3]);panel_data(4,'a',data[['county_fips','state_abbr','ses']])
    ref=read('primary').set_index('outcome_id').loc[IDS[:5]].reset_index();panel_data(4,'b',ref);ys=np.arange(5)
    lo,hi=error_points(b,ref,ys,BLUE,'o');forest_axis(b,LABELS[:5],(min(-.12,lo-.1),hi+.15),'Interaction: RRR change (%)');title(b,'b','Socioeconomic modification')
    marg=read('conditional');marg=marg[marg.outcome_id.isin(IDS[:5]) & marg.ses_sd.isin([0,1,2])];panel_data(4,'c',marg)
    lows=[];his=[]
    for sd,dy,color,m in [(0,-.23,BLUE,'o'),(1,0,GREEN,'s'),(2,.23,ORANGE,'D')]:
        sub=marg[marg.ses_sd.eq(sd)].set_index('outcome_id').loc[IDS[:5]];l,h=error_points(c,sub,ys+dy,color,m,label=f'{sd:+d} SD' if sd else '0 SD');lows.append(l);his.append(h)
    forest_axis(c,LABELS[:5],(min(lows)-.2,max(his)+.2),'Conditional smoke association (%)');title(c,'c','Associations at fixed disadvantage');c.legend(loc='lower left',bbox_to_anchor=(-.04,-.47),ncol=3,handlelength=.8,columnspacing=.7)
    common=read('common_sample');pair=common[common.outcome_id.isin(IDS[:5]) & common.model_id.isin(['M2','M3PL_joint'])].copy();assert len(pair)==10 and set(pair.n_county_years)=={3062}
    assert len(set(pair.sample_hash))==1 and set(pair.n_imputations)=={30};panel_data(4,'d',pair);lows=[];his=[]
    for model,dy,color,m,label in [('M2',-.13,GREY,'o','Common-sample M2'),('M3PL_joint',.13,ORANGE,'D','Joint environment')]:
        sub=pair[pair.model_id.eq(model)].set_index('outcome_id').loc[IDS[:5]];l,h=error_points(d,sub,ys+dy,color,m,label);lows.append(l);his.append(h)
    forest_axis(d,LABELS[:5],(min(-.12,min(lows)-.1),max(his)+.15),'Interaction: RRR change (%)');title(d,'d','Same-sample environment adjustment');d.legend(loc='lower left',bbox_to_anchor=(-.04,-.48),ncol=1,handlelength=.8,labelspacing=.5)
    finish(fig,'Figure_4',[a,b,c,d],rows=[['a','b'],['c','d']])
if __name__=='__main__':build()
