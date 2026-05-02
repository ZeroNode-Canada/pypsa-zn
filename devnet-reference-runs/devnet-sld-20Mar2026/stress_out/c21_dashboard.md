================================================================================
ASR-DASH::COMMIT::c21::baseline
----------------------------------------
args: scenario=baseline  mc_mode=set  line=-  k_load={"PJM_NE": 2.0}  k_line={}  mc_bus={"WECC_NW": 50.0, "WECC_SW": 50.0, "SPP_MISO": 50.0, "PJM_NE": 60.0, "SERC_SE": 50.0, "ERCOT": 70.0}  dc_site=N
objective        : 1.790e+06
lmp_spread       : 10.000   max_lmp: 60.000 @ SPP_MISO
max_loading_pu   : 1.000 @ L_WECC_SW_SPP_MISO
near_bind_ct(>=.95): 1
top_lines        : L_WECC_SW_SPP_MISO:1.00 | L_SPP_MISO_PJM_NE:0.85 | L_SPP_MISO_ERCOT:0.75
================================================================================
