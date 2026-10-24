# 必需数据放置位置

请从已经完成数据下载和整合的 v6.3 项目复制以下两个文件到本目录：

1. `county_year_disease_panel_v6_3.csv`
2. `imputed_deaths_eb_history_v5.npz`

最终路径必须为：

```text
Afire_project_v7_final_experiments_linux/
└── data_processed/
    ├── county_year_disease_panel_v6_3.csv
    └── imputed_deaths_eb_history_v5.npz
```

这两个文件已经包含最终实验需要的健康结局、多重插补、野火 PM2.5、SES、Census、NOAA、CDC-Air 和 PLACES 协变量。运行最终实验不需要再次复制原始下载文件。
