# The CIE's data in this folder

The CSV and JSON files here are the International Commission on Illumination's (CIE) data sets
and their metadata, **unmodified**, as downloaded from files.cie.co.at on 2026-10-10. They are
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
