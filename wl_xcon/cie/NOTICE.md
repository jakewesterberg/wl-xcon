# The CIE's data in this folder

The CSV and JSON files here, but for `stockman_sharpe_2deg.csv` (below), are the International
Commission on Illumination's (CIE) data sets and their metadata, **unmodified**, as downloaded from files.cie.co.at on 2026-10-10. They are
licensed under the Creative Commons Attribution-ShareAlike 4.0 International license (CC BY-SA
4.0, https://creativecommons.org/licenses/by-sa/4.0/), as each metadata file's `rightsList`
states, **not** under this repository's Apache-2.0 license. The CIE offers them as-is, without
warranties (the license's Section 5). The data set pages carry the notice "Copyright © 2026 CIE".

- `CIE_lms_cf_10deg.csv` (metadata `CIE_lms_cf_10deg.csv_metadata_v2.json`): CIE 2006, CIE 2006
  LMS cone fundamentals for 10° field size in terms of energy, International Commission on
  Illumination (CIE), Vienna, AT, DOI: 10.25039/CIE.DS.nxsqeri8
  (https://doi.org/10.25039/CIE.DS.nxsqeri8). From CIE 170-1:2006, Table 6.2. sha256
  bd64f1f688a4b319c6d3fa6b31770a32eaaaaea0eed532befd0424f96304db18.
- `CIE_cfb_stv_10deg.csv` (metadata `CIE_cfb_stv_10deg.csv_metadata.json`): CIE 2015, CIE
  cone-fundamental-based spectral tristimulus values for 10°field size, International Commission
  on Illumination (CIE), Vienna, AT, DOI: 10.25039/CIE.DS.dm6qiig7
  (https://doi.org/10.25039/CIE.DS.dm6qiig7). From CIE 170-2:2015, Table 10.8. sha256
  9019a35f8f51215e245f818e87d4251147d1925a8fbe9a49944fe7f011f16e38.

The citations are the CIE's own ("How to cite this data set"). `wl_xcon/cones.py` reads them,
refuses either if its checksum is not the CIE's, and interpolates between their values in memory
only; nothing derived from them is written. Why they are here: ADR-0012.

## `stockman_sharpe_2deg.csv`: not the CIE's

The Stockman-Sharpe 2° cone fundamentals, exported on 2026-11-07 from colour-science 0.4.7
(`DATA_CMFS_LMS["Stockman & Sharpe 2 Degree Cone Fundamentals"]` in
`colour/colorimetry/datasets/cmfs.py`), each number's text as colour writes it, one row per
nanometre from 390 to 830: `nm,l,m,s`. colour cites the data to CVRL: Stockman, A., & Sharpe,
L. T. (2000). Cone Fundamentals, http://www.cvrl.org/cones.htm. sha256
81ae6f81ce67e6b291638738cb404c3d79a0092c89a62329e45e99329ce8c228. **Its own licence is
UNVERIFIED** (CVRL states none; ADR-0012, amended 2026-11-07). colour-science distributes it
under this licence:

> Copyright 2013 Colour Developers
>
> Redistribution and use in source and binary forms, with or without modification, are permitted
> provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of
>    conditions and the following disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of
>    conditions and the following disclaimer in the documentation and/or other materials provided
>    with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its contributors may be used to
>    endorse or promote products derived from this software without specific prior written
>    permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS” AND ANY EXPRESS OR
> IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
> FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
> CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
> DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
> DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
> WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY
> WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE

`wl_xcon/cones.py` reads it for macaque luminance alone and refuses it if its checksum is not the
export's.
