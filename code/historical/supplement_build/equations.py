"""Display equations describing the frozen implementation; no estimation code."""
EQUATIONS = {
1: [r'A_{ct}=\frac{1}{365.25}\sum_{d\in t}A_{ctd},\qquad S_{ct}=A_{ct}/IQR_A',
    r'\bar A_{Rt}^{pop}=\frac{\sum_{c\in R}N_{ct}A_{ct}}{\sum_{c\in R}N_{ct}}'],
2: [r'G_t=\frac{\sum_{i=1}^{K}\sum_{j=1}^{K}|A_{it}-A_{jt}|}{2K^2\bar A_t},\qquad\bar A_t=K^{-1}\sum_{i=1}^{K}A_{it}'],
3: [r'R_g=T_g-\sum_{i\in O_g}Y_i^{obs},\qquad h_g=|H_g|,\qquad h_g\le R_g\le 9h_g',
    r'Y_{ig}^{(m)}=Y_{ig}^{obs}\ (i\in O_g),\qquad 1\le Z_{ig}^{(m)}\le9,\qquad\sum_{i\in H_g}Z_{ig}^{(m)}=R_g'],
4: [r'\tilde r_{ca}=\frac{D_{ca}^{hist}+E_{0,sa}r_{sa}^{hist}}{P_{ca}^{hist}+E_{0,sa}},\qquad\lambda_{cat}=N_{ct}\tilde r_{ca}',
    r'E_{0,sa}=3\,\mathrm{median}_{c\in s,\ t\in H}(N_{ct})'],
5: [r'p(\mathbf z_g\mid R_g,\boldsymbol\lambda_g)\propto\prod_{i\in H_g}\frac{\lambda_i^{z_i}}{z_i!}\,\mathbf1\{\mathbf z_g\in\{1,\ldots,9\}^{h_g},\ \sum_i z_i=R_g\}'],
6: [r'w_j(k)=\lambda_j^k/k!,\qquad F(j,r)=\sum_{k=1}^{9}w_j(k)F(j+1,r-k)',
    r'F(h+1,0)=1,\qquad p(Z_j=k\mid r)=\frac{w_j(k)F(j+1,r-k)}{\sum_{u=1}^{9}w_j(u)F(j+1,r-u)}'],
7: [r'Y_{ct}^{(m)}\sim\mathrm{NB}(\mu_{ct}^{(m)},\alpha),\qquad\mathrm{Var}(Y_{ct}^{(m)})=\mu_{ct}^{(m)}+\alpha(\mu_{ct}^{(m)})^2',
    r'\log\mu_{ct}^{(m)}=\log N_{ct}+\eta_c+\tau_t+\beta_S S_{ct}+\beta_{SD}S_{ct}D_c+\boldsymbol\gamma^\top\mathbf X_{ct}'],
8: [r'\widehat\alpha=\mathrm{clip}_{[0.001,2]}\left[\frac{\sum_{ct}\{(\bar Y_{ct}-\widehat\mu_{ct})^2-\bar Y_{ct}\}}{\max(\sum_{ct}\widehat\mu_{ct}^{2},10^{-12})}\right]'],
9: [r'c_{cluster}=\frac{G}{G-1}\frac{n-1}{n-K}'],
10: [r'\bar Q=M^{-1}\sum_{m=1}^{M}Q_m,\quad\bar U=M^{-1}\sum_{m=1}^{M}U_m,\quad B=\frac{\sum_{m=1}^{M}(Q_m-\bar Q)^2}{M-1}',
     r'T=\bar U+(1+M^{-1})B,\quad r=(1+M^{-1})B/\bar U,\quad M=30',
     r'\nu=(M-1)(1+r^{-1})^2,\qquad CI_Q=\bar Q\pm t_{\nu,0.975}\sqrt{T}'],
11: [r'FMI=\frac{r+2/(\nu+3)}{r+1},\qquad MCSE(\bar Q)=\sqrt{B/M}'],
12: [r'Q_m(s)=\beta_{S,m}+s\beta_{SD,m}',
     r'U_m(s)=\mathrm{Var}(\beta_{S,m})+s^2\mathrm{Var}(\beta_{SD,m})+2s\mathrm{Cov}(\beta_{S,m},\beta_{SD,m})']
}
