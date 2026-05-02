================================================================================
ASR-DASH::COMMIT::c2::baseline
----------------------------------------
args: scenario=baseline  mc_mode=set  line=-  k_load={"WECC_NW": 1.2, "WECC_SW": 1.2, "SPP_MISO": 1.2, "PJM_NE": 1.2, "SERC_SE": 1.2, "ERCOT": 1.2}  k_line={}  mc_bus={}  dc_site=N
objective        : 1.800e+06
lmp_spread       : 0.000   max_lmp: 50.000 @ WECC_NW
max_loading_pu   : 0.800 @ L_WECC_SW_SPP_MISO
near_bind_ct(>=.95): 0
top_lines        : L_WECC_SW_SPP_MISO:0.80 | L_PJM_NE_SERC_SE:0.80 | L_SPP_MISO_ERCOT:0.80
================================================================================
