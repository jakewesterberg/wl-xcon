# SpikeGLX real-time access: facts and consequences

**As of 2026-08-30.** Sources: billkarsh.github.io/SpikeGLX (docs, release notes, help
pages), the SDK repos (read directly), and the cited preprint.

## SDK facts (verified)

- Official remote API over TCP/IP with SDKs in **C++, C, C#, and Python**
  ([SpikeGLX-CPP-SDK](https://github.com/billkarsh/SpikeGLX-CPP-SDK), Python package
  `sglx_pkg` via ctypes; [MATLAB SDK](https://github.com/billkarsh/SpikeGLX-MATLAB-SDK)).
  **Linux clients supported** (added 2024-06). SpikeGLX itself remains Windows-only.
  Repos actively maintained (SDK commit 2026-07-21; app commit 2026-08-28).
- Key calls: `sglx_fetchLatest` (most recent samples, no index bookkeeping),
  `sglx_fetch` (from sample index), `sglx_mapSample` (cross-stream time mapping),
  channel-subset and integer downsample arguments on both fetches.
- **Server-side filtered AP stream** (`js = -2`, since release 20240129): SpikeGLX
  maintains a bandpassed, globally demuxed-CAR stream; set band edges on the IM tab.
  The CAR + filter cost is paid inside SpikeGLX's C++, not in our client. This is the
  intended MUA feed.
- **Latency** (vendor): "Fetch data with low latency (<4 ms on same computer)"
  [@karsh2026spikeglx]; the SDK's shipped closed-loop test histogram (NP 2.0, C++ client,
  same-machine loopback) concentrates at ~1.5-2.5 ms with a tail to ~4 ms
  [@karsh2026spikeglxcppsdk].
- **OP-GLX** (preprint, doi 10.64898/2026.03.04.709636 [@slack2026opglx]; the 10.1101 form
  does not resolve, 2026-10-08) gives a minimum of ~6.5 ms end to end, which it attributes to
  the SpikeGLX API's round trip, citing the SpikeGLX MATLAB SDK, not to a measurement of its
  own (Discussion); that SDK's README shows only the C++ histogram near 2 ms
  [@karsh2026spikeglxcppsdk], so the 6.5 ms's origin is untraced and it is not quoted as
  measured. ~~Treat this as the realistic bound for non-C++ clients.~~ *(Corrected 2026-10-08:
  this called OP-GLX an "Independent measurement", a MATLAB client on simulated recordings
  with a minimum ~6.5 ms end-to-end round trip, and linked the 10.1101 form.)*
- **"Low latency" mode** (IM Setup tab): reduces closed-loop latency by >1 ms but
  "drives the CPU 50%+ harder and reduces the maximum number of probes you can safely
  run concurrently." Real trade-off on multi-probe rigs — budget CPU accordingly.
- Caveats stated in the docs: lowest latency is same-machine loopback (127.0.0.1);
  WSL2 does not get the loopback path; C++ clients are fastest (Python adds
  conversion/copies); connection handles time out after 10 s idle and reconnects can
  take tens of ms (keep the loop hot); multithreaded clients need one handle per
  thread.

## OneBox / PXIe hardware facts (verified)

- OneBox: 2 headstage ports, up to 12 analog inputs, up to 12 analog outputs; DAC
  settable during a run via SDK (`sglx_obx_AO_set`); **WavePlayer** on DAC-0 can be
  armed via SDK and **hardware-triggered by a TTL on AI-1** (no software in the
  trigger path). Use it for stimulus/feedback waveforms; our controller supplies only
  the trigger edge.
- **No onboard neural threshold-to-TTL exists anywhere** in OneBox or the PXIe
  basestations. Every neural-contingent decision transits host software.
- Corollary: never route the stim trigger back out through the SpikeGLX API
  (`sglx_ni_DO_set` / `sglx_obx_AO_set` are API round trips). The task/neural plane
  asserts TTLs from its own DAQ or microcontroller.

## Consequences for our architecture

1. The fetch client (`neurofeatd`) lives **on the acquisition PC, in C++, over
   loopback** — the only configuration the vendor numbers actually describe — and
   publishes compact MUA feature vectors (tens of floats) over the network. Python
   stays on the far side of the wire.
2. Expected neural-event-to-TTL budget on this path: ~3-6 ms (estimate; to be
   measured per validation protocol V4 before any scientific claim).
3. **Fallback with a published number**: Open Ephys [@siegle2017open] (Neuropix-PXI supports
   NHP probe variants, Windows) + Falcon Output plugin -> Linux consumer: median 9.2 ms,
   SD 1.3 ms, maximum 13 ms round trip for one Neuropixels probe, as the Falcon Output page
   reads on 2026-10-08 [@openephys2026falcon]; the "9.241 ms ... 384 channels" read on
   2026-08-30 is no longer there; TTL verified by loopback into the PXIe
   ([plugin docs](https://open-ephys.github.io/gui-docs/User-Manual/Plugins/Falcon-Output.html)).
   *(Corrected 2026-10-08.)* Falcon itself is from Kloosterman's group (NERF, Leuven)
   [@ciliberti2017falcon] — a local collaboration
   to pursue regardless.
4. Every loop event (feature publication, decision, TTL) is mirrored into the
   SpikeGLX-recorded digital streams so true closed-loop latency is measured from
   recorded data, not asserted.
