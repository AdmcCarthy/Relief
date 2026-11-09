# Sea-floor colour scales

Review of the bathymetric colour scale, 2026-11-08. The house style fixes the sea as a **linear gradient** (no steps, no
contours, no illumination); this note is about the gradient's depth range and lightness steps.

## The problem

The Detuned sea ramp ran from pale to deep indigo over **0 to 1,300 m**, which is right for shelf and coast maps (the North
Sea, the Barents Sea) where all the structure is shallow. At basin and global scale it fails:

- **76 % of the world's ocean floor is deeper than 1,300 m**, so it was painted one colour (measured on the 5 km world grid:
  0 to 1,000 m is 23 % of the ocean, 1,000 to 3,000 m 11 %, 3,000 to 6,000 m 64 %).
- That deep part is where sea-floor spreading shows: ridge crests at about 2,500 to 3,000 m, flanks deepening to 4,000 to
  5,000 m with age, fracture zones as offsets across the ridge, abyssal plains at 4,500 to 6,000 m and trenches beyond.
- The shelf ramp had used up almost all of its lightness by 500 m (OKLab L 0.95 to 0.52), leaving nothing for the deep.

## The fix: two ramps, one family

| | shelf | ocean |
|---|---|---|
| Depth range | 0 to 1,300 m | 0 to 7,000 m (darkest beyond) |
| Used by | North Sea, Barents Sea, NE Europe, Vestland | Norwegian Sea, Atlantic, world |
| Hue | blue to indigo | the same family (OKLCH hue 215 to 275) |
| Lightness (light theme) | 0.95 to 0.27 over 1,300 m | 0.955 to 0.23 over 7,000 m |

The ocean ramp is a sequential ramp (one hue family, light to dark with depth). It is designed in OKLCH by
`scripts/depth_ramp.py`, which prints the hex stops for `preview/palette.js` and checks them; `tests/test_depth_ramp.py`
keeps the two in step. Stops (depth, light, dark theme):

```
 depth m   light     dark
       0   #e2f4f9   #71b7c8
     200   #bfe2ed   #56a5bd
   1,000   #83bddc   #2c83aa
   2,000   #5c9acd   #1d679c
   3,000   #4579ba   #154b8a
   4,000   #355a9f   #113375
   5,000   #2a3e80   #101e5c
   6,000   #1e2763   #0a0b42
   7,000   #131546   #040027
```

## How it was judged

By lightness and perceptual step, not by eye (the dataviz method for sequential ramps: lightness must be monotonic, and the
step between depths must stay visible). Step = OKLab delta E x 100 between a depth and 500 m deeper (about 2 is just visible):

| Depth step | shelf ramp | ocean ramp |
|---|---|---|
| 0 to 500 m | 44.0 | 11.5 |
| 500 to 1,000 m | 11.2 | 7.9 |
| 1,000 to 1,500 m | 11.3 | 5.4 |
| 1,500 m and deeper | **0.0** | **3.7 to 5.5** (to 6,500 m), even |

- Lightness falls at every stop in both themes; hues stay between blue and indigo.
- Minimum 500 m step across 1,000 to 6,000 m: 3.7 (light) and 3.3 (dark); the largest step is under twice the smallest (5.5 and
  4.2), so no depth range is favoured.
- A ridge crest (2,600 m) against the plain beside it (4,600 m): delta E 18.8 (light) and 15.2 (dark) on the ocean ramp, 0 on the
  shelf ramp.
- A 300 m feature (a fracture-zone offset) is only 2.7 (light) and 2.1 (dark): at the edge of visibility, and more so in the
  dark theme. Ridges, flanks and plains read clearly; fine lineations need shading or a finer grid (below).

## Where it shows

The world and the new **Atlantic** region (Lambert azimuthal, centred on 25 W) now show the Mid-Atlantic Ridge as a pale
S-shaped band with its flanks, offsets across it near the equator, the Indian Ocean ridges, the East Pacific Rise and the
western Pacific trenches (checked in screenshots of both themes). The Norwegian Sea basin, which was a flat navy, shows the Vøring margin and the Lofoten and
Norway basins.

## Limits

- Colour alone leaves fracture zones and abyssal hills at the edge of visibility at the full-basin view (see Shading, below).
- **GEBCO 2026 for the Atlantic** (15 arc-second, about 463 m, averaged to 2 km; replaces ETOPO 2022 at 2.5 km): measured on
  four 1,800 km patches of deep sea floor (2,000 to 6,500 m), small-scale relief (std of height minus a 20 km blur) rose only
  3 to 6 % (for example 244 to 250 m at the Romanche fracture zone, 210 to 222 m on the southern ridge), and side by side the two
  look alike. ETOPO 2022 already carries much of the same deep-ocean data; GEBCO's extra resolution shows where ships have
  surveyed (margins, ridge axes, seamounts). The colour scale, not the grid, is what made the ridge, the Romanche trough and the
  abyssal-hill lineations visible. Zoomed in (the zoom page), both resolve fracture zones and ridge-parallel hills.
- Two ramps mean the same depth has a different colour in a shelf map and an ocean map (200 m is the same pale tone in
  both; 1,000 m is not). Every map carries its own depth key.

## Shading for ocean basins (an exception to the house style)

The house style has no illumination. For the three ocean-scale regions only (Norwegian Sea, Atlantic, world) the sea floor gets
the renderer's soft multi-directional shading; land stays unshaded and shelf regions are unchanged. It can be switched off on the
zoom page (the "Shading" button) or with `?shade=off`.

- **Why:** colour alone puts a 300 m fracture-zone offset at delta E 2 to 3; shading turns the same offset into a lit and a
  shaded edge, which reads at a glance, and makes ridge-parallel abyssal hills visible as texture.
- **Strength:** vertical exaggeration has to grow with the metres each screen pixel covers, or the relief goes flat when zoomed
  out: `exag = clamp(m per pixel / 1500, 4, 40)`, about 14 for the Atlantic fitted to a screen; sea-floor shade 0.8, land 0.
  Tried at 6, 14 and 30 on the Atlantic: 6 barely changes the colour map, 30 darkens coasts and islands and muddies the depth
  colours, 14 shows ridge texture and fracture zones without hiding the depth key. `?exag=N&k=K` overrides it for experiments.
- **Cost:** shading modulates the colours, so the depth key is read less exactly in shaded maps; the colour bar is unchanged.

