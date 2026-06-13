SPDX-License-Identifier: Apache-2.0
Copyright 2026 ZeroNode

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

See the License for the specific language governing permissions and
limitations under the License.

devnet_plot_logic.md

This document records DevNet plot-generation logic and visualization design notes.

------------------------------------------------------------------------------

# Table of Contents
- [Table of Contents](#table-of-contents)
- [Devnet Plot generation logic](#devnet-plot-generation-logic)
  - [Generation Marginal Cost Correlation: LMP Spread, MAX PU, Near\_bind \& Top Stress lines](#generation-marginal-cost-correlation-lmp-spread-max-pu-near_bind--top-stress-lines)
  - [Generation Marginal Cost Correlation: Overlay composition](#generation-marginal-cost-correlation-overlay-composition)
    - [Generation Marginal Cost Correlation: Overlay composition alternatives](#generation-marginal-cost-correlation-overlay-composition-alternatives)
    - [Generation Marginal Cost Correlation: Overlay top stressed lines](#generation-marginal-cost-correlation-overlay-top-stressed-lines)
- [Reference](#reference)

---

# Devnet Plot generation logic
Devnet plot generation & visualization logic to correlate stress parameter on DC OPF solved network.

## Generation Marginal Cost Correlation: LMP Spread, MAX PU, Near_bind & Top Stress lines
Best visualizations (minimal, effective)
Heatmap (recommended)
Rows: commits / test cases
Columns: bus marginal costs (WECC_NW … ERCOT)
Color: LMP spread
→ Instantly shows which bus cost perturbations drive spread.

Scatter (2–3 plots)
x: Δmc at one bus (50→70)
y: LMP spread
Color/marker: max_loading_pu
→ Clean cause–effect for each bus.

Bar + annotation
Bars: LMP spread per commit
Annotations: top_lines (most stressed)
→ Ties prices to congestion locations.

That’s enough—don’t over-plot.

> Q: Great!, worked. 
>   The heat ap of LMP we are gnerating is pretty good. We are missing the correlation between mc >    on each bus the following: 
Max loading PU, near_bind_ct and top lines. 
>   For the next plot, can we have the [Max loading PU, near_bind_ct and top lines] plotted to the right of LMP Spread legend of the heatmap plot we just generated. 

> So as a composite we have:  
>   - mc table to the far left  
>   - heatmap in the center  
>   - LMP Spread legend to its right and 
>   - The far right after the LMP Spread legend a color coded table of:   
>       - PU, near_bind and top lines (similar to the color coded mc table)?  
> What are your thoughts other visually compelling options...  
> Please be very tight...  

## Generation Marginal Cost Correlation: Overlay composition

**Best “tight + compelling” layout:**
* **Left:** MC table (you already have)
* **Center:** Heatmap (color = LMP spread)
* **Right (next to heatmap):** discrete **LMP spread legend** (keep)
* **Far right:** a **metrics panel** with 3 stacked mini-blocks:

  * **Max_loading_pu** (single numeric cell per case; color by thresholds)
  * **near_bind_ct** (integer; color by bins)
  * **top_lines** (3-line text per case; optionally color the *line name* if it matches the max-loading line)

This is more readable than trying to cram those metrics into one table.

---

### Generation Marginal Cost Correlation: Overlay composition alternatives

**Option A (my preference):**
Replace the far-right “table” with **3 tiny aligned heatbars** (same row order):

* bar 1: max_loading_pu (continuous color)
* bar 2: near_bind_ct (discrete color)
* bar 3: top1/top2/top3 as text only

**Option B (most publication-style):**

Keep everything as-is, but add:
* **one small “stress fingerprint” strip** per case (3 colored squares = top_lines loadings)

If you say **“Proceed with Layout A”**, I’ll give you the exact drop-in code block for `devnet_plot.py` (minimal edits).


### Generation Marginal Cost Correlation: Overlay top stressed lines

> Q: Great!, that was clean. Now let us do the top line [most stressed lines].  
>   My thought is, let us create a concise table on the farthest right after the near_bind bar showing:  
>   Only the lines where the PDF is >= 0.95.
>   So on the top aligned with the heatmaps on the left we will have: 
>   L_WECC_SW_SPP_MISO
>   Below this: 
>   L_WECC_SW_SPP_MISO, L_SPP_MISO_PJM_NE
>   and so on. 
>   Did you get the idea? 


> Q: Fantastic!!!.. the plot is really really impressive.  
>   Now let us get to plotting the objective function (system operating cost) against the LMP_Spread..  
>   See the devnet_plots.xlsx. It is clear that objective function is lower for higher LMP Spread 20, 10 etc..  
>   I have accordingly sorted the xlsx rows by LMP_Spread with the higher LMP Spread at the top row.  
>   
>   Is there a way we can overlay an objective function trend line on the current plot png?   
>   Simple and elegant without any visual clutter.   
>   I have some thoughts, let me see what you come up with.   
> Please keep the disucssion tight  

> A: Yes — clean way: add a thin objective “sparkline” column (shares the same Y rows)  
> 
>   This avoids cluttering the heatmap itself and still reads as an overlay/trend on the same figure.  


---

# Reference
- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev3](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15/c/6972f266-e858-832e-b4d8-ec7ed137bbfc)  

---

*Prepared collaboratively with ChatGPT-5, January 2026*  




