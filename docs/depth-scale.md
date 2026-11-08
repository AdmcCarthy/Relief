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

- Colour only. Fracture zones and abyssal hills are a few hundred metres on a 2.5 to 5 km grid; shading would show them far
  better, but the house style has no illumination. If an exception is wanted for ocean basins, the renderer already has
  soft shading and a sea-floor shade strength.
- The Atlantic and world use ETOPO 2022 (1.85 km source). GEBCO 2026 (450 m) is the upgrade for finer lineations; it is a
  4 to 7 GB download.
- Two ramps mean the same depth has a different colour in a shelf map and an ocean map (200 m is the same pale tone in
  both; 1,000 m is not). Every map carries its own depth key.
