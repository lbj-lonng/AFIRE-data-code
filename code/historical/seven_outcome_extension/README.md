# AFIRE 七结局统一扩展

总结果：AFIRE_7outcome_all_results.csv；Excel：AFIRE_7outcome_results.xlsx。中文结果见RESULTS_SUMMARY_CN.md，核查见AUDIT_REPORT.md。配置和协议先冻结，全部结果局限本目录；空白字段为不适用或不可计算，不等于0。

复现：在项目根目录用 experiment_longrun_20260906/.venv/bin/python 本目录/run_extension.py models 断点续跑；随后同环境执行deliver.py，系统python执行export_xlsx.py。不要再次运行audit以覆盖冻结配置。所有模型30份，不允许部分合并。最终核查执行final_check.py。

figures内有可编辑SVG/PDF和PNG，图注及source_data配套。sample_keys有每任务样本及排除键，per_imputation保存逐份估计和协方差，checkpoints/logs保存指纹及任务状态。所有结局顺序固定。A七参考交互为唯一主要Holm家族，B–E均为解释性或敏感性分析。
