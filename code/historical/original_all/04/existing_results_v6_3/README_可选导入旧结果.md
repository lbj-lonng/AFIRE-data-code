# 可选：导入已经完成的 v6.3 正式结果

为了避免重复运行已经成功的 v6.3 模型，可以执行：

```bash
bash import_existing_v6_3_results.sh /你的/v6.3项目绝对路径
```

脚本会复制：

- `tables/pooled_available_models_v6_3.csv`
- `tables/model_run_status_v6_3.csv`
- `tables/model_failures_v6_3.csv`
- `tables/per_imputation_available_models_v6_3.csv.gz`（存在时）

新补充实验不依赖这些文件；不导入也可以运行 `run_everything_from_scratch_linux.sh` 完整重跑。
