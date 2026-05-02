================================================================================
ASR-DASH::COMMIT::c3::baseline
----------------------------------------
args: scenario=baseline  mc_mode=set  line=-  k_load={"WECC_NW": 1.4, "WECC_SW": 1.4, "SPP_MISO": 1.4, "PJM_NE": 1.4, "SERC_SE": 1.4, "ERCOT": 1.4}  k_line={}  mc_bus={}  dc_site=N
objective        : 2.100e+06
lmp_spread       : 0.000   max_lmp: 50.000 @ WECC_NW
max_loading_pu   : 0.500 @ L_PJM_NE_SERC_SE
near_bind_ct(>=.95): 0
top_lines        : L_PJM_NE_SERC_SE:0.50 | L_SERC_SE_ERCOT:0.50 | L_WECC_SW_SPP_MISO:0.40
================================================================================
